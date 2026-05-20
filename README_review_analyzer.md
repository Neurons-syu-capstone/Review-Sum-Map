# review_analyzer.py — 사용 가이드

Amazon 리뷰 데이터를 받아 **상품별 Aspect 키워드와 요약**을 생성하는 파이프라인입니다.

---

## 파이프라인 흐름

```
Amazon Reviews JSON
      ↓
[1]  데이터 정제 (HTML 제거, 공백 정리)
[2]  영어 리뷰 필터링
[3]  중복 제거
[4]  상품별 그룹화 (parent_asin 기준)
[5]  Low-rating 기반 우선순위 선정
[6]  리뷰 분류 → issue_reviews / strength_reviews
[7]  Sentence-BERT 임베딩 (all-MiniLM-L6-v2)
[8]  Aspect 기반 대표 리뷰 추출
[9]  Qwen2.5-7B-Instruct (4bit)
[10] Aspect별 키워드/요약 생성
[11] JSON 저장 (results.json)
```

---

## 설치

```bash
# 기본 패키지
pip install transformers torch accelerate sentencepiece sentence-transformers tqdm

# unsloth (Vast.ai CUDA 12.x + Ampere GPU 기준)
pip install "unsloth[cu124-ampere-torch24] @ git+https://github.com/unslothai/unsloth.git"
pip install bitsandbytes unsloth_zoo
```

---

## 실행 방법

### 방법 1 — CLI (터미널에서 직접 실행)

```bash
python review_analyzer.py \
  --input  data/shoes_reviews_cleaned.json \
  --output data/results.json \
  --top    100 \
  --save-every 10
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--input`  | 입력 JSON 파일 경로 | `data/shoes_reviews_cleaned.json` |
| `--output` | 결과 저장 경로 | `data/results.json` |
| `--top`    | 분석할 상품 수 | `100` |
| `--save-every` | 몇 개마다 중간 저장 | `10` |

### 방법 2 — 코드에서 import (팀 대시보드 통합용)

```python
from review_analyzer import ReviewAnalyzer
import json

# 원본 리뷰 로드
with open("data/shoes_reviews_cleaned.json") as f:
    reviews_raw = json.load(f)

# 분석기 생성 및 실행
analyzer = ReviewAnalyzer()
results = analyzer.run(
    reviews_raw=reviews_raw,
    top_n_products=100,
    save_path="data/results.json",
    save_every=10,
)

# results = { "ASIN_1": {...}, "ASIN_2": {...}, ... }
```

---

## 결과 JSON 구조

```json
{
  "B0XXXXXXXX": {
    "product_title": "상품명",
    "brand": "브랜드",
    "review_count": 500,
    "low_review_count": 80,
    "high_review_count": 320,
    "most_urgent_aspect": "durability",
    "aspects": {
      "comfort": {
        "issue_keywords": ["heel pain", "no arch support"],
        "strength_keywords": ["cushioned insole", "all-day comfort"],
        "issue_summary": "착용 시 뒤꿈치 통증과 아치 지지 부족 호소가 반복됩니다.",
        "strength_summary": "쿠션감이 좋고 하루 종일 착용해도 편안하다는 평가가 많습니다.",
        "urgent_issue": "뒤꿈치 통증",
        "urgency_score": 42.3,
        "issue_review_meta": [ ... ],
        "strength_review_meta": [ ... ],
        "skipped": false
      },
      ...
    }
  }
}
```

---

## 수정 포인트 정리

### 1. LLM 모델 변경
```python
# review_analyzer.py 상단
LLM_MODEL_NAME = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
# 예시 변경:
# LLM_MODEL_NAME = "unsloth/Llama-3.1-8B-Instruct-bnb-4bit"
```

unsloth 대신 일반 transformers를 쓰려면 `_load_llm()` 함수 내 주석 처리된 코드 블록을 활성화하세요.

### 2. 임베딩 모델 변경
```python
SBERT_MODEL_NAME = "all-MiniLM-L6-v2"
# 예시 변경 (다국어):
# SBERT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
```

### 3. 데이터셋 JSON 필드명 변경
`preprocess_reviews()` 함수 안에서 `r.get("필드명")` 부분을 실제 필드명으로 수정합니다.

```python
# 예: "reviewText" → "text" 로 매핑되어 있는 경우
text = _clean_text(r.get("reviewText", "") or "")
```

### 4. 분석 카테고리(Aspect) 변경
신발 외 다른 카테고리를 분석하려면 파일 상단의 딕셔너리 5개를 수정합니다:
`ASPECTS`, `ASPECT_DEFINITION`, `ASPECT_QUERIES`, `ASPECT_QUERIES_POS`, `ASPECT_FILTER_KEYWORDS`

### 5. 중간 저장 빈도 조정
```bash
# 5개마다 저장하고 싶을 때
python review_analyzer.py --save-every 5
```
또는 코드에서: `analyzer.run(..., save_every=5)`
