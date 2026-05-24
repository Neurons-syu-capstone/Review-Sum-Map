# =============================================================================
# config.py
# 전 레이어 공통 상수 정의
# =============================================================================

import os

# -----------------------------------------------------------------------------
# API 설정
# -----------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.2       # hallucination 억제를 위한 낮은 temperature
LLM_MAX_TOKENS = 2000

# -----------------------------------------------------------------------------
# 파이프라인 임계값
# -----------------------------------------------------------------------------
MIN_REVIEW_WORDS = 15               # 최소 리뷰 길이 (15단어 미만 제거)
COSINE_THRESHOLD = 0.30             # aspect 할당 코사인 유사도 하한
INVALID_ASPECT_REMAP_THRESHOLD = 0.40  # invalid aspect 재분류 임계값
MIN_KEYWORDS_PER_ASPECT = 3         # aspect당 최소 키워드 수
MAX_ISSUE_REVIEWS = 15               # aspect당 issue 대표 리뷰 최대 수
MAX_STRENGTH_REVIEWS = 15            # aspect당 strength 대표 리뷰 최대 수
RECENCY_DAYS = 90                   # urgency recency 기준 (일)

# -----------------------------------------------------------------------------
# 우선순위 점수 가중치
# priority_score = rating_w * (1 - avg_rating/5)
#                + complaint_w * complaint_ratio
#                + count_w * log1p(review_count)/log1p(max_count)
#                + helpful_w * helpful_vote_concentration
# -----------------------------------------------------------------------------
PRIORITY_WEIGHT_RATING = 0.4        # 가장 직접적인 품질 신호 (Mudambi & Schuff, 2010)
PRIORITY_WEIGHT_COMPLAINT = 0.3     # 구조적 결함 판단 신호 (Pang & Lee, 2008)
PRIORITY_WEIGHT_COUNT = 0.2         # 통계적 신뢰도 보정 (log 스케일)
PRIORITY_WEIGHT_HELPFUL = 0.1       # 보조 신호 (노출 기간 노이즈 존재)

# -----------------------------------------------------------------------------
# 대표 리뷰 점수 가중치
# representative_score = cosine_w * cosine_similarity
#                      + helpful_w * helpful_vote_norm
#                      + verified_w * verified_purchase
#                      + intensity_w * complaint_intensity (issue only)
# -----------------------------------------------------------------------------
REPR_WEIGHT_COSINE = 0.6            # aspect 관련성 (가장 중요)
REPR_WEIGHT_HELPFUL = 0.15           # 공감도 (Mudambi & Schuff, 2010)
REPR_WEIGHT_VERIFIED = 0.15          # 실구매 신뢰도
REPR_WEIGHT_INTENSITY = 0.1         # 부정 키워드 밀도 (issue만 해당)

# -----------------------------------------------------------------------------
# urgency score 가중치 (0~10 스케일)
# urgency = complaint_w * complaint_ratio
#         + helpful_w * helpful_vote_concentration
#         + keyword_w * keyword_freq_top3_avg_norm
#         + recency_w * recency_weight
# -----------------------------------------------------------------------------
URGENCY_WEIGHT_COMPLAINT = 0.35     # 구조적 결함의 직접 신호
URGENCY_WEIGHT_HELPFUL = 0.25       # 광범위한 공감 여부
URGENCY_WEIGHT_KEYWORD = 0.25       # 문제 재현 가능성
URGENCY_WEIGHT_RECENCY = 0.15       # 현재 진행형 이슈 보정

# -----------------------------------------------------------------------------
# Aspect 정의
# -----------------------------------------------------------------------------
ASPECTS = {
    "comfort":    "착용감",
    "size":       "사이즈",
    "durability": "내구성",
    "design":     "디자인",
    "price":      "가격",
}

ASPECT_DEFINITION = {
    "comfort":    "pain, discomfort, blisters, cushioning, arch support, heel/toe pain while wearing shoes",
    "size":       "shoe sizing, width, toe box, heel slip, tight/loose fit, runs small or large",
    "durability": "material failure, sole separation, stitching, glue, strap, tearing, peeling, breaking, wearing out quickly",
    "design":     "visual style, color, appearance, bulky shape, looks different from photos",
    "price":      "price, value for money, overpriced, cheap materials, not worth buying",
}

# -----------------------------------------------------------------------------
# Aspect 쿼리 (SBERT 임베딩 검색용)
# 부정/긍정 분리하여 issue_reviews / strength_reviews 각각에 적용
# -----------------------------------------------------------------------------
ASPECT_QUERIES = {
    "comfort":    "painful walking blisters hurts feet uncomfortable cushioning arch support heel pain foot fatigue sore feet rubbing",
    "size":       "runs small runs large too narrow too wide tight toe box loose heel poor fit sizing issue",
    "durability": "sole separated outsole detached glue failure ripped stitching tearing material broken strap peeling falling apart worn out quickly",
    "design":     "ugly color looks different from pictures poor visual design unattractive bulky appearance wrong color",
    "price":      "overpriced poor value expensive for quality cheap materials waste of money not worth the price",
}

ASPECT_QUERIES_POS = {
    "comfort":    "comfortable all day soft cushioning excellent arch support no foot pain comfortable hiking",
    "size":       "true to size perfect fit roomy toe box wide fit secure heel fit",
    "durability": "long lasting sole durable construction strong stitching high quality materials outsole holds up well",
    "design":     "stylish design modern appearance attractive color fashionable looks premium",
    "price":      "worth the money excellent value affordable quality great budget option good value for price",
}

# -----------------------------------------------------------------------------
# Aspect 필터 키워드
# 해당 키워드가 없는 리뷰는 해당 aspect에서 제외 (precision 보완)
# -----------------------------------------------------------------------------
ASPECT_FILTER_KEYWORDS = {
    "comfort":    ["uncomfortable", "comfort", "blister", "pain", "painful", "hurt", "hurts",
                   "cushion", "arch", "heel pain", "sore", "rub", "rubbing"],
    "size":       ["size", "sizing", "fit", "small", "large", "narrow", "wide", "tight",
                   "loose", "toe box", "runs small", "runs large"],
    "durability": ["sole", "detached", "separated", "glue", "ripped", "tear", "torn", "broken",
                   "peeling", "fall apart", "fell apart", "worn out", "wear out", "fraying",
                   "stitching", "strap"],
    "design": ["looks different", "looked different", "not what i expected",
           "different from photo", "different from picture", "different from image",
           "ugly", "bulky", "cheap looking", "cheap look", "poor design",
           "color is wrong", "wrong color", "color mismatch", "faded",
           "color looks", "not as pictured", "not as shown"],

    "price":  ["not worth", "waste of money", "overpriced", "too expensive",
           "for the price", "price is too", "poor value", "bad value",
           "not worth the price", "highway robbery", "rip off", "ripoff",
           "cheaply made", "cheap materials", "doesn't justify",
           "save your money", "spend your money"],
}

# -----------------------------------------------------------------------------
# Aspect 제외 키워드
# 다른 aspect의 핵심어가 섞인 리뷰를 걸러내기 위한 교차 오염 방지
# -----------------------------------------------------------------------------
ASPECT_EXCLUDE_KEYWORDS = {
    "comfort":    ["sole separated", "glue failure", "ripped stitching", "outsole detached",
                   "not worth the money"],
    "size":       ["glue failure", "sole detached", "ripped stitching", "not worth the money"],
    "durability": ["arch support", "true to size", "too narrow", "too wide"],
    "design":     ["blister", "heel pain", "toe box", "sole separated", "arch support"],
    "price":      ["blister", "foot pain", "sole detached", "toe box"],
}

# -----------------------------------------------------------------------------
# 3점 리뷰 부정 판단 키워드
# -----------------------------------------------------------------------------
NEG_KEYWORDS = [
    "small", "large", "narrow", "tight", "loose", "broke", "fell", "apart",
    "uncomfortable", "hurt", "pain", "blister", "cheap", "terrible", "awful",
    "disappointed", "waste", "return", "refund", "wrong", "fake", "poor"
]

