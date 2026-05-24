# =============================================================================
# embedder.py
# 레이어 [9][10][11]
# SBERT 임베딩 생성 → Aspect 할당 → 대표 리뷰 추출
# =============================================================================

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config import (
    ASPECTS, ASPECT_QUERIES, ASPECT_QUERIES_POS,
    ASPECT_FILTER_KEYWORDS, ASPECT_EXCLUDE_KEYWORDS,
    NEG_KEYWORDS,
    COSINE_THRESHOLD,
    REPR_WEIGHT_COSINE, REPR_WEIGHT_HELPFUL,
    REPR_WEIGHT_VERIFIED, REPR_WEIGHT_INTENSITY,
    MAX_ISSUE_REVIEWS, MAX_STRENGTH_REVIEWS,
    RECENCY_DAYS,
)

logger = logging.getLogger(__name__)

SBERT_MODEL_NAME = "all-MiniLM-L6-v2"


# =============================================================================
# [9] SBERT 모델 로딩 및 임베딩 생성
# =============================================================================

def load_model() -> SentenceTransformer:
    """all-MiniLM-L6-v2 모델 로딩."""
    logger.info(f"SBERT 모델 로딩: {SBERT_MODEL_NAME}")
    return SentenceTransformer(SBERT_MODEL_NAME)


def embed_texts(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    """텍스트 리스트를 SBERT 임베딩으로 변환."""
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def embed_aspect_queries(model: SentenceTransformer) -> tuple[dict, dict]:
    """
    aspect별 issue / strength 쿼리 임베딩 생성.
    반환: (issue_query_embeddings, strength_query_embeddings)
    """
    issue_embeddings = {}
    strength_embeddings = {}

    for aspect in ASPECTS:
        issue_embeddings[aspect] = model.encode(
            [ASPECT_QUERIES[aspect]], convert_to_numpy=True
        )
        strength_embeddings[aspect] = model.encode(
            [ASPECT_QUERIES_POS[aspect]], convert_to_numpy=True
        )

    logger.info("Aspect 쿼리 임베딩 완료")
    return issue_embeddings, strength_embeddings


# =============================================================================
# [10] Aspect 기반 리뷰 클러스터링 (할당)
# =============================================================================

def assign_aspects(
    reviews: list[dict],
    review_embeddings: np.ndarray,
    query_embeddings: dict,
    sentiment: str,
    product_scores: dict = {},
) -> dict[str, list[dict]]:
    assigned: dict[str, list[dict]] = {asp: [] for asp in ASPECTS}

    for idx, review in enumerate(reviews):
        review_emb = review_embeddings[idx:idx+1]
        text_lower = review["_text"].lower()

        for aspect, query_emb in query_embeddings.items():
            # Step 1. 코사인 유사도
            sim = float(cosine_similarity(review_emb, query_emb)[0][0])
            threshold = COSINE_THRESHOLD[aspect] if isinstance(COSINE_THRESHOLD, dict) else COSINE_THRESHOLD
            if sim < threshold:
                continue

            # Step 2. FILTER_KEYWORDS
            # neg_count >= 10이면 완화 (스코어보드 근거)
            filter_kws = ASPECT_FILTER_KEYWORDS.get(aspect, [])
            neg_count = product_scores.get(aspect, {}).get("neg_count", 0)
            if filter_kws and neg_count < 10:
                if not any(kw in text_lower for kw in filter_kws):
                    continue

            # Step 3. EXCLUDE_KEYWORDS
            exclude_kws = ASPECT_EXCLUDE_KEYWORDS.get(aspect, [])
            if any(kw in text_lower for kw in exclude_kws):
                continue

            review["_cosine_sim"] = review.get("_cosine_sim", {})
            review["_cosine_sim"][aspect] = round(sim, 4)
            assigned[aspect].append(review)

    for asp in ASPECTS:
        logger.debug(f"  {asp}: {len(assigned[asp])}개 리뷰 할당 ({sentiment})")

    return assigned


# =============================================================================
# [11] Aspect별 대표 리뷰 추출
# =============================================================================

def extract_representative_reviews(
    assigned_issues: dict[str, list[dict]],
    assigned_strengths: dict[str, list[dict]],
) -> dict[str, dict]:
    """
    aspect별 issue / strength 대표 리뷰 추출.

    representative_score =
        cosine_similarity * 0.4
        + helpful_vote_norm * 0.3
        + verified_purchase * 0.2
        + complaint_intensity * 0.1  (issue만 해당)
    """
    repr_reviews: dict[str, dict] = {}

    for aspect in ASPECTS:
        issue_reviews = assigned_issues.get(aspect, [])
        strength_reviews = assigned_strengths.get(aspect, [])

        top_issues = _score_and_select(
            issue_reviews, aspect, sentiment="issue", max_count=MAX_ISSUE_REVIEWS
        )
        top_strengths = _score_and_select(
            strength_reviews, aspect, sentiment="strength", max_count=MAX_STRENGTH_REVIEWS
        )

        repr_reviews[aspect] = {
            "issue": top_issues,
            "strength": top_strengths,
        }

        logger.debug(f"  {aspect}: issue {len(top_issues)}개, "
                     f"strength {len(top_strengths)}개 대표 리뷰 선정")

    return repr_reviews


def _score_and_select(
    reviews: list[dict],
    aspect: str,
    sentiment: str,
    max_count: int,
) -> list[dict]:
    if not reviews:
        return []

    # representative_score 계산 + aspect_hits 저장
    for r in reviews:
        cosine_sim = r.get("_cosine_sim", {}).get(aspect, 0.0)
        helpful_norm = r.get("_helpful_vote_norm", 0.0)
        verified = 1.0 if r.get("_verified") else 0.0
        intensity = _complaint_intensity(r["_text"]) if sentiment == "issue" else 0.0
        r["_repr_score"] = (
            cosine_sim * REPR_WEIGHT_COSINE
            + helpful_norm * REPR_WEIGHT_HELPFUL
            + verified * REPR_WEIGHT_VERIFIED
            + intensity * REPR_WEIGHT_INTENSITY
        )
        text_lower = r["_text"].lower()
        filter_kws = ASPECT_FILTER_KEYWORDS.get(aspect, [])
        r["_aspect_hits"] = [kw for kw in filter_kws if kw in text_lower]

    if len(reviews) <= max_count:
        reviews.sort(key=lambda r: r["_repr_score"], reverse=True)
        return reviews

    # 임베딩 벡터 추출
    embeddings = np.array([
        r.get("_embedding", [0.0] * 384) for r in reviews
    ])

    # 임베딩이 없거나 모두 0이면 점수 기반 폴백
    if embeddings.max() == 0:
        reviews.sort(key=lambda r: r["_repr_score"], reverse=True)
        return reviews[:max_count]

    # MMR 선택
    lambda_val = 0.7
    scores = np.array([r["_repr_score"] for r in reviews])
    selected_indices = []
    candidate_indices = list(range(len(reviews)))

    for _ in range(max_count):
        if not candidate_indices:
            break

        if not selected_indices:
            best = max(candidate_indices, key=lambda i: scores[i])
        else:
            selected_embs = embeddings[selected_indices]
            best_score = -float('inf')
            best = None

            for i in candidate_indices:
                relevance = scores[i]
                sim_to_selected = cosine_similarity(
                    embeddings[i:i+1], selected_embs
                ).max()
                mmr_score = lambda_val * relevance - (1 - lambda_val) * sim_to_selected
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = i

        selected_indices.append(best)
        candidate_indices.remove(best)

    return [reviews[i] for i in selected_indices]


def _complaint_intensity(text: str) -> float:
    """
    NEG_KEYWORDS 밀도 기반 complaint intensity 계산 (0~1).
    단어 수 대비 부정 키워드 비율.
    """
    words = text.lower().split()
    if not words:
        return 0.0
    count = sum(1 for w in words if w in NEG_KEYWORDS)
    return min(count / len(words) * 10, 1.0)


# =============================================================================
# 전체 상품 임베딩 파이프라인 실행
# =============================================================================

def run_embedding_pipeline(
    model: SentenceTransformer,
    issue_reviews: list[dict],
    strength_reviews: list[dict],
    product_scores: dict = {},
) -> dict[str, dict]:
    """
    단일 상품에 대해 임베딩 → aspect 할당 → 대표 리뷰 추출 전체 실행.

    반환: repr_reviews (aspect별 대표 issue/strength 리뷰)
    """
    # 쿼리 임베딩
    issue_query_embs, strength_query_embs = embed_aspect_queries(model)

    # 리뷰 임베딩
    repr_reviews: dict[str, dict] = {asp: {"issue": [], "strength": []} for asp in ASPECTS}

    if issue_reviews:
        issue_texts = [r["_text"] for r in issue_reviews]
        issue_embs = embed_texts(model, issue_texts)
        for i, r in enumerate(issue_reviews):
            r["_embedding"] = issue_embs[i].tolist()
        assigned_issues = assign_aspects(
            issue_reviews, issue_embs, issue_query_embs,
            sentiment="issue", product_scores=product_scores
        )
    else:
        assigned_issues = {asp: [] for asp in ASPECTS}

    if strength_reviews:
        strength_texts = [r["_text"] for r in strength_reviews]
        strength_embs = embed_texts(model, strength_texts)
        for i, r in enumerate(strength_reviews):
            r["_embedding"] = strength_embs[i].tolist()
        assigned_strengths = assign_aspects(
            strength_reviews, strength_embs, strength_query_embs,
            sentiment="strength", product_scores=product_scores
        )
    else:
        assigned_strengths = {asp: [] for asp in ASPECTS}

    repr_reviews = extract_representative_reviews(assigned_issues, assigned_strengths)
    return repr_reviews


# =============================================================================
# invalid aspect 재분류 (validator에서 호출)
# =============================================================================

def remap_invalid_aspect(
    model: SentenceTransformer,
    invalid_aspect_name: str,
    remap_threshold: float = 0.40,
) -> str | None:
    """
    LLM이 반환한 invalid aspect 이름을 SBERT로 임베딩하여
    5개 고정 aspect 중 가장 유사한 것에 매핑.
    유사도 remap_threshold 미만이면 None 반환.
    """
    valid_aspect_names = list(ASPECTS.keys())
    invalid_emb = model.encode([invalid_aspect_name], convert_to_numpy=True)
    valid_embs = model.encode(valid_aspect_names, convert_to_numpy=True)

    sims = cosine_similarity(invalid_emb, valid_embs)[0]
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])

    if best_sim >= remap_threshold:
        logger.info(f"invalid aspect '{invalid_aspect_name}' → '{valid_aspect_names[best_idx]}' "
                    f"(유사도: {best_sim:.3f})")
        return valid_aspect_names[best_idx]

    logger.info(f"invalid aspect '{invalid_aspect_name}' 재분류 실패 "
                f"(최고 유사도: {best_sim:.3f} < {remap_threshold})")
    return None
