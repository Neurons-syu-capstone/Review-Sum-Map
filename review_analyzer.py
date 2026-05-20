"""
review_analyzer.py
==================
Amazon 리뷰 데이터를 분석하여 상품별 이슈 키워드와 요약을 생성하는 모듈입니다.

주요 처리 흐름:
    [1] 데이터 정제 → [2] 영어 필터링 → [3] 중복 제거 → [4] 상품별 그룹화
    → [5] Low-rating 기반 우선순위 선정 → [6] 리뷰 분류
    → [7] Sentence-BERT 임베딩 → [8] Aspect 기반 대표 리뷰 추출
    → [9] Qwen2.5-7B-Instruct (4bit) → [10] 키워드/요약 생성 → [11] JSON 저장

사용 방법:
    python review_analyzer.py --input data/shoes_reviews.json --output data/results.json --top 100

팀 통합 방법:
    from review_analyzer import ReviewAnalyzer
    analyzer = ReviewAnalyzer()
    results = analyzer.run(reviews_raw)
"""

import json
import re
import math
import logging
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional

import torch
from tqdm import tqdm
from sentence_transformers import SentenceTransformer, util

# =============================================================================
# 로깅 설정
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# ★ 설정 변경 가이드 ★
#
# [모델 변경]
#   - LLM 모델: LLM_MODEL_NAME 값을 수정 (Hugging Face 모델 ID)
#     예) "unsloth/Llama-3.1-8B-Instruct-bnb-4bit"
#   - 임베딩 모델: SBERT_MODEL_NAME 값을 수정
#     예) "all-mpnet-base-v2", "paraphrase-multilingual-MiniLM-L12-v2"
#
# [데이터셋 변경]
#   - 입력 파일: --input 인자로 전달하거나 FILE_PATH 기본값을 수정
#   - JSON 필드명이 다를 경우: preprocess_reviews() 함수 내 r.get("필드명") 부분 수정
#
# [분석 Aspect 변경]
#   - 신발 외 다른 카테고리로 변경 시: ASPECTS, ASPECT_QUERIES 등 딕셔너리 수정
#
# [추출 개수 변경]
#   - MIN_REVIEWS: 분석에 필요한 최소 대표 리뷰 수 (기본 5)
#   - TOP_N: Aspect당 최대 대표 리뷰 수 (동적 계산의 상한, 기본 12)
# =============================================================================

# --- 모델 설정 ---
LLM_MODEL_NAME = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"   # LLM 모델
SBERT_MODEL_NAME = "all-MiniLM-L6-v2"                      # 임베딩 모델

# --- 추출 개수 설정 ---
MIN_REVIEWS = 5   # 분석에 필요한 최소 대표 리뷰 수
TOP_N = 12        # Aspect당 최대 대표 리뷰 추출 수 (동적 샘플링의 상한)

# --- Aspect 정의 ---
ASPECTS = {
    "comfort":    "착용감",
    "size":       "사이즈",
    "durability": "내구성",
    "design":     "디자인",
    "price":      "가격",
}

ASPECT_DEFINITION = {
    "comfort": "pain, discomfort, blisters, cushioning, arch support, heel/toe pain while wearing shoes",
    "size": "shoe sizing, width, toe box, heel slip, tight/loose fit, runs small or large",
    "durability": "material failure, sole separation, stitching, glue, strap, tearing, peeling, breaking, wearing out quickly",
    "design": "visual style, color, appearance, bulky shape, looks different from photos",
    "price": "price, value for money, overpriced, cheap materials, not worth buying",
}

# 이슈 리뷰 검색용 쿼리 (부정적 측면)
ASPECT_QUERIES = {
    "comfort":    "painful walking blisters hurts feet uncomfortable cushioning arch support heel pain foot fatigue sore feet rubbing",
    "size":       "runs small runs large too narrow too wide tight toe box loose heel poor fit sizing issue",
    "durability": "sole separated outsole detached glue failure ripped stitching tearing material broken strap peeling falling apart worn out quickly",
    "design":     "ugly color looks different from pictures poor visual design unattractive bulky appearance wrong color",
    "price":      "overpriced poor value expensive for quality cheap materials waste of money not worth the price",
}

# 강점 리뷰 검색용 쿼리 (긍정적 측면)
ASPECT_QUERIES_POS = {
    "comfort":    "comfortable all day soft cushioning excellent arch support no foot pain comfortable hiking",
    "size":       "true to size perfect fit roomy toe box wide fit secure heel fit",
    "durability": "long lasting sole durable construction strong stitching high quality materials outsole holds up well",
    "design":     "stylish design modern appearance attractive color fashionable looks premium",
    "price":      "worth the money excellent value affordable quality great budget option good value for price",
}

# Aspect별 필터 키워드 (해당 키워드가 없는 리뷰는 제외)
ASPECT_FILTER_KEYWORDS = {
    "comfort":    ["uncomfortable", "comfort", "blister", "pain", "painful", "hurt", "hurts", "cushion", "arch", "heel pain", "sore", "rub", "rubbing"],
    "size":       ["size", "sizing", "fit", "small", "large", "narrow", "wide", "tight", "loose", "toe box", "runs small", "runs large"],
    "durability": ["sole", "detached", "separated", "glue", "ripped", "tear", "torn", "broken", "peeling", "fall apart", "fell apart", "worn out", "wear out", "fraying", "stitching", "strap"],
    "design":     ["ugly", "color", "colour", "appearance", "design", "style", "picture", "pictures", "photo", "photos", "bulky", "looked different", "looks different"],
    "price":      ["price", "value", "worth", "overpriced", "expensive", "cheap", "money", "waste", "not worth"],
}

# Aspect별 제외 키워드 (다른 Aspect의 핵심어가 섞인 리뷰 걸러내기)
ASPECT_EXCLUDE_KEYWORDS = {
    "comfort":    ["sole separated", "glue failure", "ripped stitching", "outsole detached", "not worth the money"],
    "size":       ["glue failure", "sole detached", "ripped stitching", "not worth the money"],
    "durability": ["arch support", "true to size", "too narrow", "too wide"],
    "design":     ["blister", "heel pain", "toe box", "sole separated", "arch support"],
    "price":      ["blister", "foot pain", "sole detached", "toe box"],
}

# 부정적 키워드 (3점 리뷰를 이슈로 분류할 때 사용)
NEG_KEYWORDS = [
    "small", "large", "narrow", "tight", "loose", "broke", "fell", "apart",
    "uncomfortable", "hurt", "pain", "blister", "cheap", "terrible", "awful",
    "disappointed", "waste", "return", "refund", "wrong", "fake", "poor"
]

# LLM 키워드 결과에서 걸러낼 너무 일반적인 단어들
GENERIC_KEYWORDS = {
    "shoe", "shoes", "product", "quality", "bad", "good", "comfortable", "uncomfortable",
    "pair", "amazon", "item", "wear", "wearing", "bought", "purchase"
}


# =============================================================================
# ReviewAnalyzer 클래스
# =============================================================================

class ReviewAnalyzer:
    """
    Amazon 리뷰 분석 파이프라인 클래스.

    대시보드 등 외부 코드에서 통합할 때는 이 클래스를 import하여 사용합니다:

        from review_analyzer import ReviewAnalyzer
        analyzer = ReviewAnalyzer()
        results = analyzer.run(reviews_raw, top_n_products=100)
    """

    def __init__(self):
        # 모델은 처음 run() 호출 시 로드됩니다 (지연 로딩)
        self.sbert: Optional[SentenceTransformer] = None
        self.llm_model = None
        self.llm_tokenizer = None

    # =========================================================================
    # [1] ~ [3] 데이터 정제, 영어 필터링, 중복 제거
    # =========================================================================

    def preprocess_reviews(self, reviews_raw: list) -> list:
        """
        원본 리뷰 리스트를 정제합니다.
        - HTML 태그 제거
        - 영어 리뷰만 남기기 (ASCII 비율 80% 이상)
        - 중복 텍스트 제거

        """
        logger.info("데이터 정제 시작...")

        def _clean_text(text: str) -> str:
            if not text or not isinstance(text, str):
                return ""
            text = re.sub(r'<[^>]+>', ' ', text)   # HTML 태그 제거
            text = re.sub(r'\s+', ' ', text)         # 연속 공백 정리
            return text.strip()

        def _is_english(text: str) -> bool:
            if not text:
                return False
            sample = text[:1000]
            return sum(1 for c in sample if ord(c) < 128) / max(len(sample), 1) > 0.8

        cleaned, seen = [], set()
        for r in reviews_raw:
            text = _clean_text(r.get("text", "") or "")
            if not text or not _is_english(text) or text in seen:
                continue
            seen.add(text)
            cleaned.append({
                "parent_asin":       r.get("parent_asin", ""),
                "asin":              r.get("asin", ""),
                "product_title":     r.get("product_title", ""),
                "brand":             r.get("brand", ""),
                "rating":            float(r.get("rating", 0) or 0),
                "text":              text,
                "year":              r.get("year", ""),
                "title":             _clean_text(r.get("title", "")),
                "helpful_vote":      int(r.get("helpful_vote") or 0),
                "verified_purchase": bool(r.get("verified_purchase", False)),
            })

        logger.info(f"정제 완료: {len(reviews_raw):,}건 → {len(cleaned):,}건")
        return cleaned

    # =========================================================================
    # [4] 상품별 그룹화
    # =========================================================================

    def group_by_product(self, cleaned: list) -> dict:
        """정제된 리뷰를 parent_asin 기준으로 그룹화합니다."""
        product_reviews = defaultdict(list)
        for r in cleaned:
            if r["parent_asin"]:
                product_reviews[r["parent_asin"]].append(r)
        logger.info(f"상품 수: {len(product_reviews):,}개")
        return dict(product_reviews)

    # =========================================================================
    # [5] Low-rating 기반 상품 우선순위 선정
    # =========================================================================

    def sort_by_issue_count(self, product_reviews: dict) -> list:
        """
        낮은 평점(1~2점) 리뷰가 많은 순으로 상품을 정렬합니다.
        반환: [(asin, reviews), ...] 형태의 정렬된 리스트
        """
        return sorted(
            product_reviews.items(),
            key=lambda x: sum(1 for r in x[1] if r["rating"] <= 2),
            reverse=True,
        )

    # =========================================================================
    # [6] 리뷰 분류 (이슈 vs 강점)
    # =========================================================================

    def classify_reviews(self, reviews: list) -> tuple:
        """
        리뷰를 이슈 리뷰와 강점 리뷰로 분류합니다.
        - 이슈 리뷰: 1~2점 + 3점 중 부정 키워드 포함
        - 강점 리뷰: 4~5점
        반환: (issue_reviews, strength_reviews)
        """
        low  = [r for r in reviews if r["rating"] <= 2]
        high = [r for r in reviews if r["rating"] >= 4]
        mid  = [r for r in reviews if r["rating"] == 3
                and any(kw in r["text"].lower() for kw in NEG_KEYWORDS)]
        return low + mid, high

    # =========================================================================
    # [7] Sentence-BERT 임베딩 (지연 로딩)
    # =========================================================================

    def _load_sbert(self):
        """Sentence-BERT 모델을 처음 필요할 때 로드합니다."""
        if self.sbert is None:
            logger.info(f"Sentence-BERT 로딩 중: {SBERT_MODEL_NAME}")
            self.sbert = SentenceTransformer(SBERT_MODEL_NAME)

    def encode_reviews(self, reviews: list) -> torch.Tensor:
        """리뷰 텍스트를 Sentence-BERT로 임베딩합니다."""
        self._load_sbert()
        texts = [r["text"][:300] for r in reviews]
        if not texts:
            return torch.zeros(0)
        return self.sbert.encode(
            texts, batch_size=32, show_progress_bar=False, convert_to_tensor=True
        )

    # =========================================================================
    # [8] Aspect 기반 대표 리뷰 추출
    # =========================================================================

    def _keyword_hits(self, text: str, keywords: list) -> tuple:
        text_lower = text.lower()
        hits = [kw for kw in keywords if kw in text_lower]
        return len(hits), hits

    def _priority_score(self, review: dict, semantic_score: float, hit_count: int) -> float:
        """
        대표 리뷰 우선순위 점수 계산.
        - 시맨틱 유사도(62%), 키워드 적중(20%), 낮은 평점(13%), 도움됨 투표(5%) + 구매 확인 보너스
        """
        rating   = float(review.get("rating", 0) or 0)
        severity = max(0, 5 - rating) / 4
        helpful  = min(math.log1p(int(review.get("helpful_vote") or 0)) / 6, 1)
        verified = 0.08 if review.get("verified_purchase") else 0
        return (0.62 * float(semantic_score)
                + 0.20 * min(hit_count / 3, 1)
                + 0.13 * severity
                + 0.05 * helpful
                + verified)

    def get_top_reviews(
        self,
        query: str,
        embeddings: torch.Tensor,
        reviews: list,
        top_n: int = TOP_N,
        asp: Optional[str] = None,
    ) -> list:
        """
        쿼리와 시맨틱 유사도가 높고 키워드가 일치하는 대표 리뷰를 추출합니다.
        """
        if len(reviews) == 0 or embeddings.shape[0] == 0:
            return []

        self._load_sbert()
        query_emb = self.sbert.encode(query, convert_to_tensor=True)
        scores    = util.cos_sim(query_emb, embeddings)[0]
        top_idx   = scores.argsort(descending=True)

        filter_kws  = ASPECT_FILTER_KEYWORDS.get(asp, [])
        exclude_kws = ASPECT_EXCLUDE_KEYWORDS.get(asp, [])
        candidates, used_texts = [], set()

        for idx in top_idx:
            idx        = int(idx)
            review     = reviews[idx]
            text       = review["text"]
            text_lower = text.lower()

            # 너무 짧은 리뷰 제외
            if len(text_lower.split()) < 8:
                continue
            # 다른 Aspect 키워드가 섞인 리뷰 제외
            if any(bad_kw in text_lower for bad_kw in exclude_kws):
                continue
            # 해당 Aspect 키워드가 없는 리뷰 제외
            hit_count, hits = self._keyword_hits(text_lower, filter_kws)
            if filter_kws and hit_count == 0:
                continue
            # 중복 제거 (앞 160자로 비교)
            dedup_key = re.sub(r"[^a-z0-9 ]+", "", text_lower)[:160]
            if dedup_key in used_texts:
                continue
            used_texts.add(dedup_key)

            enriched = dict(review)
            enriched["aspect_hits"]     = hits
            enriched["semantic_score"]  = round(float(scores[idx]), 4)
            enriched["priority_score"]  = round(
                self._priority_score(review, scores[idx], hit_count), 4
            )
            candidates.append(enriched)

            if len(candidates) >= top_n * 4:
                break

        candidates.sort(key=lambda r: r["priority_score"], reverse=True)
        return candidates[:top_n]

    # =========================================================================
    # [9] ~ [10] LLM 분석 (Qwen2.5-7B-Instruct 4bit)
    # =========================================================================

    def _load_llm(self):
        """LLM을 처음 필요할 때 로드합니다."""
        if self.llm_model is None:
            logger.info(f"LLM 로딩 중: {LLM_MODEL_NAME}")
            # ★ unsloth를 사용하지 않을 경우 아래 import와 로딩 방식을 변경하세요 ★
            # 예) transformers의 AutoModelForCausalLM으로 변경 가능:
            #   from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            #   quantization_config = BitsAndBytesConfig(load_in_4bit=True)
            #   self.llm_model = AutoModelForCausalLM.from_pretrained(
            #       LLM_MODEL_NAME, quantization_config=quantization_config, device_map="auto"
            #   )
            #   self.llm_tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
            from unsloth import FastLanguageModel
            self.llm_model, self.llm_tokenizer = FastLanguageModel.from_pretrained(
                model_name=LLM_MODEL_NAME,
                max_seq_length=2048,
                dtype=None,        # None이면 자동 감지 (bf16 권장)
                load_in_4bit=True, # VRAM 절약을 위한 4bit 양자화
            )
            FastLanguageModel.for_inference(self.llm_model)
            logger.info("LLM 로딩 완료!")

    def _generate(self, prompt: str, max_tokens: int = 260) -> str:
        """LLM에 프롬프트를 입력하고 텍스트를 생성합니다."""
        self._load_llm()
        messages = [{"role": "user", "content": prompt}]
        text = self.llm_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.llm_tokenizer([text], return_tensors="pt").to(self.llm_model.device)
        with torch.no_grad():
            outputs = self.llm_model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0.0,      # Greedy decoding (재현 가능한 결과)
                do_sample=False,
                pad_token_id=self.llm_tokenizer.eos_token_id,
            )
        return self.llm_tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True,
        ).strip()

    def _parse_json_response(self, text: str) -> dict:
        """LLM 응답에서 JSON 부분을 파싱합니다."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    def _fallback_keywords(self, reviews: list, aspect: str) -> list:
        """LLM 응답 파싱 실패 시 빈도 기반 키워드를 반환합니다."""
        counts = Counter()
        include = ASPECT_FILTER_KEYWORDS.get(aspect, [])
        for r in reviews:
            text = r["text"].lower()
            for kw in include:
                if kw in text and kw not in GENERIC_KEYWORDS:
                    counts[kw] += 1
            for phrase in re.findall(
                r"\b(?:too|very|really|extremely)\s+[a-z]{3,15}\b"
                r"|\b[a-z]{3,15}\s+(?:broke|broken|hurt|hurts|peeling|tight|loose|narrow|wide)\b",
                text,
            ):
                if phrase not in GENERIC_KEYWORDS:
                    counts[phrase] += 1
        return [kw for kw, _ in counts.most_common(6)]

    def analyze_with_llm(
        self, reviews: list, aspect: str, sentiment: str
    ) -> tuple:
        """
        LLM으로 Aspect의 키워드, 요약, 긴급 이슈를 생성합니다.

        Args:
            reviews:   대표 리뷰 리스트
            aspect:    분석할 Aspect 키 (예: "comfort")
            sentiment: "positive" 또는 "negative"

        Returns:
            (keywords: list, summary_ko: str, urgent_issue_ko: str)
        """
        if not reviews:
            return [], "", ""

        is_positive = (sentiment == "positive")
        task_label  = "strengths" if is_positive else "issues/problems"
        schema_key  = "strength_keywords" if is_positive else "issue_keywords"

        sample = "\n".join([
            f"- rating={r.get('rating')}, helpful={r.get('helpful_vote', 0)}, "
            f"matched={r.get('aspect_hits', [])}: {r['text'][:320]}"
            for r in reviews
        ])

        # 프롬프트 구성
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
  "summary_ko": "Korean 1-2 sentence summary for the seller",
  "urgent_issue_ko": "Korean phrase naming the most urgent concrete issue; for positive sentiment, write the strongest selling point"
}}

Strict rules:
- Use only evidence explicitly present in the reviews above.
- Keywords must be 3-6 concrete English phrases, preferably 2-4 words each.
- Avoid generic words: shoe, shoes, product, quality, bad, good, comfortable, uncomfortable.
- Do not mix in other aspects. Stay inside {aspect}: {ASPECT_DEFINITION[aspect]}.
- summary_ko must explain the repeated pattern and buyer impact, not just translate keywords.
- No markdown, no commentary, JSON only."""

        raw    = self._generate(prompt, max_tokens=260)
        parsed = self._parse_json_response(raw)

        keywords = parsed.get(schema_key, [])
        keywords = [str(k).strip() for k in keywords if str(k).strip()] if isinstance(keywords, list) else []
        if not keywords:
            keywords = self._fallback_keywords(reviews, aspect)

        summary = str(parsed.get("summary_ko", "")).strip()
        urgent  = str(parsed.get("urgent_issue_ko", "")).strip()

        if not summary:
            summary = f"{ASPECTS[aspect]} 측면의 키워드 {', '.join(keywords[:3])} 등을 바탕으로 요약을 생성했습니다."
        if not urgent:
            urgent = keywords[0] if keywords else "주요 이슈 확인 불가"

        return keywords[:6], summary, urgent

    # =========================================================================
    # 단일 상품 분석
    # =========================================================================

    def analyze_product(self, asin: str, reviews: list) -> dict:
        """
        단일 상품에 대해 전체 파이프라인(분류~LLM 분석)을 실행합니다.

        Args:
            asin:    상품의 parent_asin
            reviews: 해당 상품의 정제된 리뷰 리스트

        Returns:
            분석 결과 딕셔너리
        """
        issue_reviews, strength_reviews = self.classify_reviews(reviews)

        # 이슈 리뷰 수에 따라 Aspect당 추출 개수를 동적으로 결정
        # (최소 5개, 최대 20개, 이슈 리뷰의 10% 기준)
        dynamic_top_n = max(5, min(20, len(issue_reviews) // 10))

        # Sentence-BERT 임베딩
        issue_embs    = self.encode_reviews(issue_reviews)
        strength_embs = self.encode_reviews(strength_reviews)

        # Aspect별 대표 리뷰 추출
        representative = {}
        for asp in ASPECTS:
            issue_reps    = self.get_top_reviews(ASPECT_QUERIES[asp],     issue_embs,    issue_reviews,    top_n=dynamic_top_n, asp=asp)
            strength_reps = self.get_top_reviews(ASPECT_QUERIES_POS[asp], strength_embs, strength_reviews, top_n=dynamic_top_n, asp=asp)
            representative[asp] = {
                "issue_reviews":    issue_reps,
                "strength_reviews": strength_reps,
                "skip": len(issue_reps) < MIN_REVIEWS and len(strength_reps) < MIN_REVIEWS,
            }

        # LLM 분석
        results_data            = {}
        used_issue_keywords     = set()
        used_strength_keywords  = set()

        for asp in ASPECTS:
            if representative[asp]["skip"]:
                results_data[asp] = {
                    "issue_keywords":    [],
                    "strength_keywords": [],
                    "issue_summary":     "Not enough reviews to analyze",
                    "strength_summary":  "Not enough reviews to analyze",
                    "urgent_issue":      "Not enough reviews to analyze",
                    "issue_review_meta":    [],
                    "strength_review_meta": [],
                    "skipped": True,
                }
                continue

            issue_reps    = representative[asp]["issue_reviews"]
            strength_reps = representative[asp]["strength_reviews"]

            issue_kw, issue_summary, urgent_issue = self.analyze_with_llm(issue_reps,    asp, "negative")
            strength_kw, strength_summary, _      = self.analyze_with_llm(strength_reps, asp, "positive")

            # 이미 다른 Aspect에서 쓴 키워드는 제거 (중복 방지)
            issue_kw    = [k for k in issue_kw    if k.lower() not in used_issue_keywords]
            strength_kw = [k for k in strength_kw if k.lower() not in used_strength_keywords]
            used_issue_keywords.update(k.lower() for k in issue_kw)
            used_strength_keywords.update(k.lower() for k in strength_kw)

            # 긴급도 점수: 낮은 평점 + helpful_vote + priority_score 합산
            urgency_score = round(
                sum(
                    6 - float(r.get("rating", 0) or 0)
                    + math.log1p(int(r.get("helpful_vote") or 0))
                    + r.get("priority_score", 0)
                    for r in issue_reps
                ),
                2,
            )

            def _meta(r):
                return {
                    "title":          r.get("title", ""),
                    "rating":         r.get("rating", 0),
                    "year":           r.get("year", ""),
                    "helpful_vote":   r.get("helpful_vote", 0),
                    "aspect_hits":    r.get("aspect_hits", []),
                    "semantic_score": r.get("semantic_score", 0),
                    "priority_score": r.get("priority_score", 0),
                    "text":           r.get("text", ""),
                }

            results_data[asp] = {
                "issue_count":        len(issue_reps),
                "strength_count":     len(strength_reps),
                "issue_keywords":     issue_kw,
                "strength_keywords":  strength_kw,
                "issue_summary":      issue_summary,
                "strength_summary":   strength_summary,
                "urgent_issue":       urgent_issue,
                "urgency_score":      urgency_score,
                "issue_review_meta":    [_meta(r) for r in issue_reps],
                "strength_review_meta": [_meta(r) for r in strength_reps],
                "skipped": False,
            }

        # 가장 긴급한 Aspect 선정
        valid = {a: d for a, d in results_data.items() if not d.get("skipped") and d.get("issue_count", 0) > 0}
        most_urgent = max(valid, key=lambda a: valid[a]["urgency_score"]) if valid else None

        return {
            "product_title":     reviews[0].get("product_title", ""),
            "brand":             reviews[0].get("brand", ""),
            "review_count":      len(reviews),
            "low_review_count":  len(issue_reviews),
            "high_review_count": len(strength_reviews),
            "most_urgent_aspect": most_urgent,
            "aspects":           results_data,
        }

    # =========================================================================
    # 전체 파이프라인 실행
    # =========================================================================

    def run(
        self,
        reviews_raw: list,
        top_n_products: int = 100,
        save_path: Optional[str] = None,
        save_every: int = 10,
    ) -> dict:
        """
        전체 분석 파이프라인을 실행합니다.

        Args:
            reviews_raw:     원본 리뷰 JSON 리스트
            top_n_products:  분석할 상품 수 (낮은 평점 많은 순 상위 N개)
            save_path:       중간 저장 파일 경로 (None이면 저장 안 함)
            save_every:      몇 개 상품마다 중간 저장할지 (기본 10)

        Returns:
            {asin: 분석결과} 형태의 딕셔너리
        """
        # 데이터 전처리
        cleaned         = self.preprocess_reviews(reviews_raw)
        product_reviews = self.group_by_product(cleaned)
        sorted_products = self.sort_by_issue_count(product_reviews)

        # 분석 대상 상품 선택
        targets = sorted_products[:top_n_products]
        logger.info(f"분석 대상: {len(targets)}개 상품 (전체 {len(sorted_products)}개 중)")

        all_results = {}

        for i, (asin, reviews) in enumerate(tqdm(targets, desc="상품 분석 중"), start=1):
            title = reviews[0].get("product_title", asin)
            logger.info(f"[{i}/{len(targets)}] {asin} | {title[:50]}")

            try:
                result = self.analyze_product(asin, reviews)
                all_results[asin] = result

                # 가장 긴급한 이슈 로그 출력
                most_urgent = result.get("most_urgent_aspect")
                if most_urgent:
                    asp_data = result["aspects"][most_urgent]
                    logger.info(
                        f"  → 주요 이슈: [{ASPECTS[most_urgent]}] "
                        f"{asp_data.get('urgent_issue', '')} "
                        f"(score={asp_data.get('urgency_score', 0)})"
                    )

            except Exception as e:
                logger.error(f"  ✗ 오류 발생 ({asin}): {e}", exc_info=True)
                all_results[asin] = {"error": str(e)}

            # 중간 저장 (save_every 개마다)
            if save_path and i % save_every == 0:
                self._save(all_results, save_path)
                logger.info(f"  [중간 저장] {i}개 완료 → {save_path}")

        # 최종 저장
        if save_path:
            self._save(all_results, save_path)
            logger.info(f"최종 저장 완료: {save_path}")

        return all_results

    def _save(self, results: dict, path: str):
        """결과를 JSON 파일로 저장합니다."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


# =============================================================================
# CLI 진입점
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Amazon 리뷰 분석 파이프라인")
    parser.add_argument(
        "--input", "-i",
        default="data/shoes_sample.json",  # ← 기본 입력 파일 경로
        help="입력 JSON 파일 경로",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/results.json",                # ← 기본 출력 파일 경로
        help="결과 저장 JSON 파일 경로",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=100,                                # ← 기본 분석 상품 수
        help="분석할 상품 수 (낮은 평점 많은 순 상위 N개)",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=10,
        help="몇 개 상품마다 중간 저장할지 (기본: 10)",
    )
    args = parser.parse_args()

    # 입력 파일 로드
    logger.info(f"입력 파일 로드: {args.input}")
    with open(args.input, encoding="utf-8") as f:
        reviews_raw = json.load(f)
    logger.info(f"원본 리뷰 수: {len(reviews_raw):,}건")

    # 분석 실행
    analyzer = ReviewAnalyzer()
    analyzer.run(
        reviews_raw=reviews_raw,
        top_n_products=args.top,
        save_path=args.output,
        save_every=args.save_every,
    )


if __name__ == "__main__":
    main()
