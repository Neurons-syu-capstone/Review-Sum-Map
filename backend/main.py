# =============================================================================
# main.py
# 전체 파이프라인 실행 진입점
# =============================================================================
from dotenv import load_dotenv
load_dotenv()

import json
import logging
import sys
from pathlib import Path

from pipeline import preprocess, prioritize, classify, validate, save_results
from embedder import load_model, run_embedding_pipeline
from llm_analyzer import analyze_product

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run(input_path: str, output_path: str = "data/results.json", limit: int = None) -> None:
    # -------------------------------------------------------------------------
    # 데이터 로딩
    # -------------------------------------------------------------------------
    logger.info(f"데이터 로딩: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    logger.info(f"원본 리뷰 수: {len(raw_data)}")

    # 스코어보드 로딩
    score_data = {}
    score_path = Path("data/llm_scores_by_product.json")
    if score_path.exists():
        with open(score_path, encoding="utf-8") as f:
            score_data = json.load(f)
        logger.info(f"스코어보드 로딩 완료: {len(score_data)}개 상품")
    else:
        logger.warning("llm_scores_by_product.json 없음. 스코어보드 없이 진행")

    # -------------------------------------------------------------------------
    # [1~6] 전처리
    # -------------------------------------------------------------------------
    logger.info("=" * 50)
    logger.info("[1~6] 전처리 시작")
    grouped = preprocess(raw_data)

    # -------------------------------------------------------------------------
    # [7] 상품 우선순위 선정
    # -------------------------------------------------------------------------
    logger.info("[7] 상품 우선순위 선정")
    prioritized = prioritize(grouped)
    logger.info(f"분석 대상: {len(prioritized)}개 상품")

    # -------------------------------------------------------------------------
    # [9] SBERT 모델 로딩
    # -------------------------------------------------------------------------
    logger.info("[9] SBERT 모델 로딩")
    model = load_model()

    # -------------------------------------------------------------------------
    # 상품별 파이프라인 실행
    # -------------------------------------------------------------------------
    results = []

    if limit:
        prioritized = prioritized[:limit]

    for rank, (product_id, priority_score) in enumerate(prioritized, 1):
        reviews = grouped[product_id]
        product_name = _get_product_name(reviews)
        product_scores = score_data.get(product_id, {}).get("scores", {})

        logger.info("=" * 50)
        logger.info(f"[{rank}/{len(prioritized)}] 상품 분석: {product_name} "
                    f"(priority: {priority_score:.3f})")

        try:
            # [8] 긍정/부정 분류
            logger.info("  [8] 긍정/부정 분류")
            issue_reviews, strength_reviews = classify(reviews)
            logger.info(f"  issue: {len(issue_reviews)}개, "
                        f"strength: {len(strength_reviews)}개")

            # [9~11] 임베딩 + aspect 할당 + 대표 리뷰 추출
            logger.info("  [9~11] 임베딩 + aspect 할당 + 대표 리뷰 추출")
            repr_reviews = run_embedding_pipeline(
                model, issue_reviews, strength_reviews, product_scores
            )

            # [12] GPT-4o-mini 분석
            logger.info("  [12] GPT-4o-mini 분석")
            llm_result = analyze_product(
                product_id=product_id,
                product_name=product_name,
                repr_reviews=repr_reviews,
                all_reviews=reviews,
                product_scores=product_scores,
            )

            # [13~17] 검증
            logger.info("  [13~17] 검증")
            validated = validate(llm_result, repr_reviews)
            flags = validated.get("_flags", [])
            if flags:
                logger.warning(f"  검증 플래그: {flags}")

            results.append(validated)
            save_results(results, output_path)
            logger.info(f"  완료 (validation_status: "
                        f"{validated.get('validation_status', 'unknown')})")

        except Exception as e:
            logger.error(f"  상품 분석 실패 ({product_id}): {e}", exc_info=True)
            results.append({
                "product_id": product_id,
                "product_name": product_name,
                "validation_status": "failed",
                "error": str(e),
            })

    # -------------------------------------------------------------------------
    # [18] 결과 저장
    # -------------------------------------------------------------------------
    logger.info("=" * 50)
    logger.info("[18] 결과 저장")
    save_results(results, output_path)

    # 요약 출력
    ok = sum(1 for r in results if r.get("validation_status") == "ok")
    partial = sum(1 for r in results if r.get("validation_status") == "partial")
    warned = sum(1 for r in results if r.get("validation_status") == "warned")
    failed = sum(1 for r in results if r.get("validation_status") == "failed")

    logger.info(f"완료: ok={ok}, warned={warned}, partial={partial}, failed={failed}")
    logger.info(f"결과 저장 위치: {output_path}")


def _get_product_name(reviews: list[dict]) -> str:
    """리뷰 목록에서 상품명 추출."""
    for r in reviews:
        name = r.get("product_title") or r.get("title") or r.get("name")
        if name:
            return name.strip()
    return reviews[0].get("_product_id", "Unknown Product") if reviews else "Unknown"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python main.py <input_json_path> [output_json_path] [limit]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "data/results.json"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    run(input_path, output_path, limit)
