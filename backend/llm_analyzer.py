# =============================================================================
# llm_analyzer.py
# 레이어 [12]
# GPT-4o-mini API 호출 + aspect별 개별 호출 구조
# 상품당 최대 10회 병렬 호출 (5 aspects × 2 sentiments)
# =============================================================================

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import (
    OPENAI_API_KEY, LLM_MODEL, LLM_TEMPERATURE,
    ASPECTS, ASPECT_DEFINITION,
)

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# =============================================================================
# [12] GPT-4o-mini 분석 메인
# =============================================================================

def analyze_product(
    product_id: str,
    product_name: str,
    repr_reviews: dict[str, dict],
    all_reviews: list[dict],
    product_scores: dict = {},
) -> dict:
    """
    단일 상품에 대해 aspect별 × sentiment 병렬 GPT 호출.
    상품당 최대 10회 동시 호출.
    """
    # urgency 계산 (스코어보드 기반)
    urgency_scores = _compute_urgency_scores(product_scores, repr_reviews)

    logger.info(f"GPT-4o-mini 병렬 호출 시작: {product_name} ({product_id})")

    # 호출 태스크 목록 구성
    tasks = []
    for aspect in ASPECTS:
        issue_reviews = repr_reviews.get(aspect, {}).get("issue", [])
        strength_reviews = repr_reviews.get(aspect, {}).get("strength", [])
        if issue_reviews:
            tasks.append((aspect, issue_reviews, "issue"))
        if strength_reviews:
            tasks.append((aspect, strength_reviews, "strength"))

    # 병렬 호출
    call_results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_call_aspect, asp, revs, sent): (asp, sent)
            for asp, revs, sent in tasks
        }
        for future in as_completed(futures):
            asp, sent = futures[future]
            try:
                call_results[(asp, sent)] = future.result()
            except Exception as e:
                logger.warning(f"호출 실패 ({asp}/{sent}): {e}")
                call_results[(asp, sent)] = {}

    # 결과 조립
    aspect_analysis = {}
    for aspect in ASPECTS:
        issue_result = call_results.get((aspect, "issue"), {})
        strength_result = call_results.get((aspect, "strength"), {})
        issue_reviews = repr_reviews.get(aspect, {}).get("issue", [])
        strength_reviews = repr_reviews.get(aspect, {}).get("strength", [])

        aspect_analysis[aspect] = {
            "issue_keywords": _parse_keywords(issue_result.get("issue_keywords", [])),
            "issue_summary": issue_result.get("summary_ko", ""),
            "strength_keywords": _parse_keywords(strength_result.get("strength_keywords", [])),
            "strength_summary": strength_result.get("summary_ko", ""),
            "urgency_score": urgency_scores.get(aspect, 0.0),
            "representative_reviews": [
                _format_review(r, "issue") for r in issue_reviews
            ] + [
                _format_review(r, "strength") for r in strength_reviews
            ],
        }

    result = _build_result(
        product_id, product_name, all_reviews,
        aspect_analysis, urgency_scores
    )

    logger.info(f"완료: {product_name} ({len(tasks)}회 호출)")
    return result


# =============================================================================
# aspect별 개별 GPT 호출
# =============================================================================

def _call_aspect(aspect: str, reviews: list[dict], sentiment: str) -> dict:
    """
    단일 aspect × sentiment 분석 호출.
    sentiment: "issue" or "strength"
    """
    task_label = "negative issues" if sentiment == "issue" else "positive strengths"
    schema_key = "issue_keywords" if sentiment == "issue" else "strength_keywords"

    sample = "\n".join(
        f"[{i+1}] (rating:{r['_rating']:.0f}, helpful:{r['_helpful_vote']:.0f}, "
        f"matched={r.get('_aspect_hits', [])}) "
        f"{r['_text'][:300]}"
        for i, r in enumerate(reviews)
    )

    prompt = f"""You are a senior product-quality analyst for shoe reviews.
Analyze ONLY the {task_label} for this aspect.

Aspect key: {aspect}
Aspect Korean label: {ASPECTS[aspect]}
Aspect definition: {ASPECT_DEFINITION[aspect]}

Representative reviews:
{sample}

Return JSON only with this exact schema:
{{
  "{schema_key}": ["keyword phrase 1", "keyword phrase 2", "keyword phrase 3"],
  "summary_ko": "Korean 1-2 sentence summary for the seller"
}}

Strict rules:
- Before extracting keywords, silently discard any review that does not directly discuss {aspect}: {ASPECT_DEFINITION[aspect]}. Only use remaining reviews.
- Keywords must be English phrases copied verbatim or closely paraphrased from the reviews.
- Keywords must directly relate to {aspect}: {ASPECT_DEFINITION[aspect]}.
- Keywords must NOT contain numbers, dates, or measurements.
- Keywords must NOT be generic: shoe, shoes, product, quality, bad, good, comfortable, uncomfortable, pair, bought.
- Keywords must be 1-3 words maximum. Never extract full sentences.
- Extract 3 to 6 keywords maximum. If fewer than 3 relevant keywords exist, return only what exists.
- Do not mix in other aspects. Stay strictly inside {aspect}.
- summary_ko must explain the repeated pattern and buyer impact in Korean.
- No markdown, no commentary, JSON only."""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=500,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"aspect 호출 실패 ({aspect}/{sentiment}): {e}")
        return {}


# =============================================================================
# 키워드 파싱
# =============================================================================

def _parse_keywords(raw: list) -> list[str]:
    result = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict) and item.get("keyword"):
            result.append(item["keyword"].strip())
    return result


# =============================================================================
# urgency score 계산 (스코어보드 기반)
# =============================================================================

def _compute_urgency_scores(
    product_scores: dict,
    repr_reviews: dict[str, dict],
) -> dict[str, float]:
    """
    urgency_score 산출 (0~10 스케일).
    스코어보드 score가 낮을수록 urgency 높음.
    스코어보드 없으면 complaint_ratio 기반 단순 계산.
    """
    scores = {}

    for aspect in ASPECTS:
        sb = product_scores.get(aspect, {})
        sb_score = sb.get("score", None)

        if sb_score is not None:
            scores[aspect] = round((1 - sb_score / 10) * 10, 2)
        else:
            # 스코어보드 없으면 complaint_ratio 기반 단순 계산
            issue = repr_reviews.get(aspect, {}).get("issue", [])
            strength = repr_reviews.get(aspect, {}).get("strength", [])
            total = len(issue) + len(strength)
            complaint_ratio = len(issue) / total if total > 0 else 0.0
            scores[aspect] = round(complaint_ratio * 10, 2)

    return scores


# =============================================================================
# 최종 결과 조립
# =============================================================================

def _build_result(
    product_id: str,
    product_name: str,
    all_reviews: list[dict],
    aspect_analysis: dict,
    urgency_scores: dict,
) -> dict:
    total = len(all_reviews)
    negative = len([r for r in all_reviews if r["_rating"] <= 2])
    positive = len([r for r in all_reviews if r["_rating"] >= 4])
    avg_rating = sum(r["_rating"] for r in all_reviews) / total if total else 0

    # urgent_issues: urgency_score 최고 aspect 1개
    best_aspect = max(urgency_scores, key=urgency_scores.get)
    urgent_issues = [{
        "aspect": best_aspect,
        "urgency_score": urgency_scores[best_aspect],
        "summary": aspect_analysis.get(best_aspect, {}).get("issue_summary", ""),
    }]

    return {
        "product_id": product_id,
        "product_name": product_name,
        "average_rating": round(avg_rating, 2),
        "review_count": {
            "total": total,
            "positive": positive,
            "negative": negative,
        },
        "urgent_issues": urgent_issues,
        "aspect_analysis": aspect_analysis,
    }


def _format_review(r: dict, sentiment: str) -> dict:
    return {
        "text": r["_text"],
        "date": r.get("_date", ""),
        "rating": r.get("_rating", 0),
        "helpful_vote": int(r.get("_helpful_vote", 0)),
        "verified_purchase": r.get("_verified", False),
        "sentiment": sentiment,
    }