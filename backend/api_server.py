# =============================================================================
# api_server.py
# 키워드 검색 API 서버
# 실행: uvicorn api_server:app --port 8000 --reload
# =============================================================================

import json
import logging
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS 설정 (React 개발 서버 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_PATH    = "data/shoes_sample.json"
RESULTS_PATH = "data/results.json"
_reviews: list[dict] = []
_results: list[dict] = []

@app.on_event("startup")
def load_data():
    global _reviews, _results

    path = Path(DATA_PATH)
    if not path.exists():
        logger.warning(f"{DATA_PATH} 파일 없음")
    else:
        with open(path, encoding="utf-8") as f:
            _reviews = json.load(f)
        logger.info(f"리뷰 데이터 로딩 완료: {len(_reviews):,}건")

    rpath = Path(RESULTS_PATH)
    if not rpath.exists():
        logger.warning(f"{RESULTS_PATH} 파일 없음")
    else:
        with open(rpath, encoding="utf-8") as f:
            _results = json.load(f)
        logger.info(f"results.json 로딩 완료: {len(_results):,}개 상품")


def _matches_keyword(text: str, keyword: str) -> bool:
    """
    키워드를 단어별로 쪼개서 AND 검색.
    불용어 제외하고 의미있는 단어만 검색.
    """
    STOPWORDS = {"is","the","a","an","in","of","for","to","and","or","on","at","my","me"}
    text_lower = text.lower()
    words = [w for w in keyword.lower().split() if w not in STOPWORDS]
    if not words:
        return keyword.lower() in text_lower
    return all(w in text_lower for w in words)


def _get_aspect_review_ids(product_id: str, aspect: str) -> set[str]:
    """
    results.json에서 해당 상품+aspect의 대표 리뷰 텍스트 앞 60자를 키로 반환.
    """
    for p in _results:
        if p.get("product_id") == product_id:
            data = p.get("aspect_analysis", {}).get(aspect, {})
            return {
                r["text"][:60]
                for r in (data.get("representative_reviews") or [])
                if r.get("text")
            }
    return set()


@app.get("/keyword-counts")
def keyword_counts(
    product_id: str = Query(..., description="상품 parent_asin"),
):
    """
    해당 상품의 전체 리뷰에서 results.json의 각 키워드가
    실제로 몇 번 등장하는지 세서 반환.
    """
    # 해당 상품의 results.json 데이터 찾기
    product_result = None
    for p in _results:
        if p.get("product_id") == product_id:
            product_result = p
            break

    if not product_result:
        return {"product_id": product_id, "counts": {}}

    # 해당 상품의 전체 리뷰
    product_reviews = [
        r for r in _reviews
        if (r.get("parent_asin") or r.get("asin")) == product_id
    ]

    if not product_reviews:
        return {"product_id": product_id, "counts": {}}

    # 모든 aspect의 키워드 수집
    all_keywords = set()
    for aspect_data in product_result.get("aspect_analysis", {}).values():
        if not aspect_data:
            continue
        for kw in (aspect_data.get("issue_keywords") or []):
            if kw:
                all_keywords.add(kw)
        for kw in (aspect_data.get("strength_keywords") or []):
            if kw:
                all_keywords.add(kw)

    # 키워드별 실제 등장 횟수 계산
    counts = {}
    for kw in all_keywords:
        counts[kw] = sum(
            1 for r in product_reviews
            if _matches_keyword(r.get("text") or "", kw)
        )

    return {"product_id": product_id, "counts": counts}


@app.get("/search")
def search_reviews(
    keyword: str = Query(..., description="검색할 키워드"),
    product_id: str = Query(..., description="상품 parent_asin"),
    limit: int = Query(30, description="최대 반환 수"),
    aspect: str = Query(None, description="aspect 필터 (없으면 전체)"),
):
    """
    특정 상품의 전체 리뷰에서 키워드가 포함된 리뷰를 검색.
    키워드는 단어별 AND 검색 (불용어 제외).
    최근순 정렬, 최대 limit개 반환.
    """
    product_reviews = [
        r for r in _reviews
        if (r.get("parent_asin") or r.get("asin")) == product_id
        and _matches_keyword(r.get("text") or "", keyword)
    ]

    if aspect:
        aspect_keys = _get_aspect_review_ids(product_id, aspect)
        if aspect_keys:
            product_reviews = [
                r for r in product_reviews
                if (r.get("text") or "")[:60] in aspect_keys
            ]

    def _parse_date(r):
        return r.get("review_date") or r.get("reviewTime") or ""

    product_reviews.sort(key=_parse_date, reverse=True)
    product_reviews = product_reviews[:limit]

    results = []
    for r in product_reviews:
        text   = r.get("text") or ""
        rating = float(r.get("rating") or r.get("overall") or 0)
        sentiment = "issue" if rating <= 2 else "strength"

        results.append({
            "text": text,
            "date": (r.get("review_date") or r.get("reviewTime") or "")[:10],
            "rating": rating,
            "helpful_vote": int(r.get("helpful_vote") or 0),
            "verified_purchase": bool(r.get("verified_purchase", False)),
            "sentiment": sentiment,
        })

    return {
        "keyword": keyword,
        "product_id": product_id,
        "aspect": aspect,
        "total": len(results),
        "reviews": results,
    }


@app.get("/health")
def health():
    return {"status": "ok", "review_count": len(_reviews)}