# =============================================================================
# pipeline.py
# 전처리 → 우선순위 선정 → 긍정/부정 분류 → 검증 → 저장
# =============================================================================

import json
import math
import re
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from langdetect import detect, LangDetectException

from config import (
    MIN_REVIEW_WORDS,
    PRIORITY_WEIGHT_RATING, PRIORITY_WEIGHT_COMPLAINT,
    PRIORITY_WEIGHT_COUNT, PRIORITY_WEIGHT_HELPFUL,
    NEG_KEYWORDS,ASPECTS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1~6 전처리
# =============================================================================

def preprocess(raw_data: list[dict]) -> dict[str, list[dict]]:
    """
    원본 리뷰 JSON 리스트를 받아 정제 후 product_id 기준으로 그룹화 반환.

    수행 작업:
        [1] null / 빈값 제거
        [2] 영어 리뷰 필터링 (langdetect)
        [3] 중복 리뷰 제거 (텍스트 exact match)
        [4] 상품별 리뷰 그룹화
        [5] 15단어 미만 리뷰 제거
        [6] helpful_vote min-max 정규화 (상품별 독립 적용)
    """
    # [1] null / 필수 필드 누락 제거
    cleaned = []
    for r in raw_data:
        if not r:
            continue
        text = r.get("text") or r.get("reviewText") or ""
        product_id = r.get("parent_asin") or r.get("asin") or ""
        rating = r.get("rating") or r.get("overall")
        if not text.strip() or not product_id or rating is None:
            continue
        r["_text"] = text.strip()
        r["_product_id"] = product_id
        r["_rating"] = float(rating)
        r["_helpful_vote"] = _parse_helpful_vote(r)
        r["_verified"] = bool(r.get("verified_purchase", False))
        r["_date"] = r.get("review_date") or r.get("reviewTime") or ""
        cleaned.append(r)

    # [2] 영어 필터링
    english = []
    for r in cleaned:
        try:
            if detect(r["_text"]) == "en":
                english.append(r)
        except LangDetectException:
            pass

    # [3] 중복 제거 (상품 내 텍스트 exact match)
    seen: set[str] = set()
    deduped = []
    for r in english:
        key = f"{r['_product_id']}::{r['_text'].lower()}"
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # [4] 상품별 그룹화
    grouped: dict[str, list[dict]] = {}
    for r in deduped:
        pid = r["_product_id"]
        grouped.setdefault(pid, []).append(r)

    # [5] 15단어 미만 제거 + [6] helpful_vote 정규화 (상품별 독립)
    result: dict[str, list[dict]] = {}
    for pid, reviews in grouped.items():
        # [5]
        long_enough = [r for r in reviews if len(r["_text"].split()) >= MIN_REVIEW_WORDS]
        if not long_enough:
            continue
        # [6] 상품별 min-max 정규화
        votes = [r["_helpful_vote"] for r in long_enough]
        v_min, v_max = min(votes), max(votes)
        for r in long_enough:
            if v_max > v_min:
                r["_helpful_vote_norm"] = (r["_helpful_vote"] - v_min) / (v_max - v_min)
            else:
                r["_helpful_vote_norm"] = 0.0
        result[pid] = long_enough

    logger.info(f"전처리 완료: {len(result)}개 상품, "
                f"총 {sum(len(v) for v in result.values())}개 리뷰")
    return result


def _parse_helpful_vote(r: dict) -> float:
    """helpful vote 파싱. 여러 포맷 대응."""
    hv = r.get("helpful_vote") or r.get("helpful") or 0
    if isinstance(hv, list) and len(hv) >= 1:
        return float(hv[0])
    try:
        return float(hv)
    except (TypeError, ValueError):
        return 0.0


# =============================================================================
# 7 상품 우선순위 선정
# =============================================================================

def prioritize(grouped: dict[str, list[dict]]) -> list[tuple[str, float]]:
    """
    상품별 priority_score 계산 후 내림차순 정렬 반환.

    priority_score =
        (1 - avg_rating/5) * 0.4          # 낮은 평점일수록 높은 점수
        + complaint_ratio * 0.3            # 부정 리뷰 비율
        + log1p(count)/log1p(max) * 0.2   # 통계적 신뢰도 (log 스케일)
        + helpful_on_negative * 0.1        # 부정 리뷰의 helpful vote 집중도
    """
    scores: dict[str, float] = {}
    counts = [len(v) for v in grouped.values()]
    max_count = max(counts) if counts else 1

    for pid, reviews in grouped.items():
        ratings = [r["_rating"] for r in reviews]
        avg_rating = sum(ratings) / len(ratings)

        neg = [r for r in reviews if r["_rating"] <= 2]
        complaint_ratio = len(neg) / len(reviews)

        count_score = math.log1p(len(reviews)) / math.log1p(max_count)

        # 부정 리뷰의 helpful vote 집중도: 부정 리뷰 helpful_vote 평균 / 전체 평균
        all_helpful_avg = sum(r["_helpful_vote_norm"] for r in reviews) / len(reviews)
        neg_helpful_avg = (
            sum(r["_helpful_vote_norm"] for r in neg) / len(neg)
            if neg else 0.0
        )
        helpful_concentration = (
            neg_helpful_avg / all_helpful_avg
            if all_helpful_avg > 0 else 0.0
        )
        helpful_concentration = min(helpful_concentration, 1.0)

        score = (
            (1 - avg_rating / 5) * PRIORITY_WEIGHT_RATING
            + complaint_ratio * PRIORITY_WEIGHT_COMPLAINT
            + count_score * PRIORITY_WEIGHT_COUNT
            + helpful_concentration * PRIORITY_WEIGHT_HELPFUL
        )
        scores[pid] = score

    sorted_products = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    logger.info(f"우선순위 선정 완료: {len(sorted_products)}개 상품")
    return sorted_products


# =============================================================================
# 8 긍정/부정 분류
# =============================================================================

def classify(reviews: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    리뷰를 issue_reviews / strength_reviews 로 분류.

    기준:
        1~2점 → issue
        4~5점 → strength
        3점   → NEG_KEYWORDS 포함 여부로 판단
    """
    issue_reviews = []
    strength_reviews = []

    for r in reviews:
        rating = r["_rating"]
        if rating <= 2:
            issue_reviews.append(r)
        elif rating >= 4:
            strength_reviews.append(r)
        else:
            # 3점: 텍스트 기반 판단
            text_lower = r["_text"].lower()
            has_neg = any(kw in text_lower for kw in NEG_KEYWORDS)
            if has_neg:
                issue_reviews.append(r)
            else:
                strength_reviews.append(r)

    return issue_reviews, strength_reviews


# =============================================================================
# 13~17 검증
# =============================================================================

def validate(llm_result: dict, repr_reviews: dict) -> dict:
    validated = dict(llm_result)

    # schema 검증
    validated = _validate_schema(validated, repr_reviews)

    #  urgency score 이상값 처리
    validated = _validate_urgency(validated)

    return validated


def _validate_schema(result: dict, repr_reviews: dict) -> dict:
    """
    필수 필드 누락 시 폴백 복구. 완전 제거하지 않음.
    """
    required_top = ["product_id", "product_name", "average_rating",
                    "review_count", "urgent_issues", "aspect_analysis"]

    for field in required_top:
        if field not in result:
            result[field] = _get_fallback_value(field, result, repr_reviews)
            result.setdefault("_flags", []).append(f"schema_fallback:{field}")

    # aspect_analysis 내부 필드 검증
    for aspect in ASPECTS:
        aspect_data = result.get("aspect_analysis", {}).get(aspect, {})
        if not aspect_data:
            result.setdefault("aspect_analysis", {})[aspect] = _empty_aspect()
            result.setdefault("_flags", []).append(f"aspect_missing:{aspect}")
            continue

        for field in ["issue_summary", "strength_summary", "issue_keywords",
                      "strength_keywords", "representative_reviews"]:
            if field not in aspect_data or aspect_data[field] is None:
                aspect_data[field] = _fallback_aspect_field(
                    field, aspect, repr_reviews
                )
                result.setdefault("_flags", []).append(
                    f"aspect_field_fallback:{aspect}:{field}"
                )

    # validation_status 설정
    flags = result.get("_flags", [])
    if flags:
        result["validation_status"] = "partial" if len(flags) > 3 else "warned"
    else:
        result["validation_status"] = "ok"

    return result


def _validate_urgency(result: dict) -> dict:
    """
    urgency_score 이상값 clipping.
    범위 초과 → min-max clipping (0~10)
    NaN / null → complaint_ratio 기반 단순 재계산
    """
    urgent_issues = result.get("urgent_issues", [])
    for issue in urgent_issues:
        score = issue.get("urgency_score")
        try:
            score = float(score)
            if score < 0 or score > 10:
                issue["urgency_score"] = max(0.0, min(10.0, score))
                issue["urgency_flag"] = "clipped"
        except (TypeError, ValueError):
            # NaN / null → complaint_ratio 기반 재계산
            aspect = issue.get("aspect", "")
            aspect_data = result.get("aspect_analysis", {}).get(aspect, {})
            fallback_score = _recalculate_urgency(aspect_data, result)
            issue["urgency_score"] = fallback_score
            issue["urgency_flag"] = "urgency_recalculated"

    return result


# =============================================================================
# 18 결과 저장
# =============================================================================

def save_results(results: list[dict], output_path: str = "data/results.json") -> None:
    """
    검증 완료된 분석 결과를 results.json으로 저장.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"results.json 저장 완료: {output_path} ({len(results)}개 상품)")


# =============================================================================
# 내부 헬퍼 함수
# =============================================================================

def _get_fallback_value(field: str, result: dict, repr_reviews: dict) -> Any:
    defaults = {
        "product_id": "unknown",
        "product_name": "unknown",
        "average_rating": 0.0,
        "review_count": {"total": 0, "positive": 0, "negative": 0},
        "urgent_issues": [],
        "aspect_analysis": {asp: _empty_aspect() for asp in ASPECTS},
    }
    return defaults.get(field, "analysis_unavailable")


def _empty_aspect() -> dict:
    return {
        "issue_summary": "analysis_unavailable",
        "strength_summary": "analysis_unavailable",
        "issue_keywords": [],
        "strength_keywords": [],
        "representative_reviews": [],
    }


def _fallback_aspect_field(field: str, aspect: str, repr_reviews: dict) -> Any:
    issue_reviews = repr_reviews.get(aspect, {}).get("issue", [])
    if field in ["issue_summary", "strength_summary"]:
        if issue_reviews:
            return _get_first_sentences(issue_reviews[0]["_text"], n=2)
        return "analysis_unavailable"
    if field in ["issue_keywords", "strength_keywords"]:
        return []
    if field == "representative_reviews":
        return []
    return "analysis_unavailable"


def _get_first_sentences(text: str, n: int = 2) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sentences[:n])


def _recalculate_urgency(aspect_data: dict, result: dict) -> float:
    """complaint_ratio만으로 urgency_score 단순 재계산."""
    review_count = result.get("review_count", {})
    total = review_count.get("total", 1) or 1
    negative = review_count.get("negative", 0)
    complaint_ratio = negative / total
    return round(complaint_ratio * 10, 2)
