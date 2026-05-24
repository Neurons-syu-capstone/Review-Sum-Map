# Review Intelligence Dashboard

**AI 기반 상품 리뷰 분석 및 이슈 탐지 모듈**

리뷰 기반 상품 분석 인사이트 대시보드의 4개 핵심 기능 중 하나

---

## 한 줄 요약

Amazon 신발 리뷰 데이터를 전처리·임베딩·GPT 분석 파이프라인으로 처리해, 상품별 aspect(착용감·사이즈·내구성·디자인·가격) 단위 이슈 키워드·요약·긴급도를 자동 추출하고 대시보드로 시각화한다.

---

## 왜 이 구조인가

리뷰 데이터는 2018~2023 정적 데이터지만, 구조는 실제 서비스와 동일하게 설계했다.

| 실제 서비스 | 이 프로젝트 |
|---|---|
| 새 리뷰가 실시간으로 들어옴 | 전체 리뷰를 한 번에 처리 |
| 파이프라인이 자동 실행 | CLI로 파이프라인 실행 |
| 경보 즉시 알림 | results.json으로 결과 저장 → 대시보드 표시 |

즉, 알고리즘 자체는 동일하고 데이터 입력 방식만 다르다.

---

## 데이터 플로우

```
[Amazon Reviews JSON]
        │
        ▼
  preprocessor       ← null 제거, 영어 필터링, 중복 제거, 정규화
        │
        ▼
  prioritizer        ← 평점·complaint ratio·리뷰 수 기반 상품 우선순위 선정
        │
        ▼
  classifier         ← 1~2점 issue / 4~5점 strength / 3점 키워드 판단
        │
        ▼
  embedder           ← SBERT(all-MiniLM-L6-v2) 임베딩 + 3중 필터 aspect 할당
        │             (코사인 유사도 + FILTER_KEYWORDS + EXCLUDE_KEYWORDS)
        │             MMR 기반 다양성 보장 대표 리뷰 추출
        ▼
  llm_analyzer       ← GPT-4o-mini aspect별 병렬 호출 (상품당 최대 10회)
        │             issue/strength 키워드 추출 + 한국어 요약 생성
        ▼
  validator          ← JSON schema 검증, urgency score 이상값 처리
        │
        ▼
  results.json       ← 상품별 분석 결과 저장
        │
        ▼
  React Dashboard    ← 긴급 이슈 / aspect 분석 / 키워드 / 대표 리뷰 시각화
```

---

## 디렉토리 구조

```
sample_review/
│
├── backend/
│   ├── main.py              # 전체 파이프라인 실행 진입점
│   ├── config.py            # 전 레이어 공통 상수 (aspect 정의, 가중치, 임계값)
│   ├── pipeline.py          # 전처리 + 우선순위 + 분류 + 검증 + 저장
│   ├── embedder.py          # SBERT 임베딩 + aspect 할당 + 대표 리뷰 추출
│   ├── llm_analyzer.py      # GPT-4o-mini API 호출 + 프롬프트
│   ├── api_server.py        # FastAPI 키워드 검색 서버
│   ├── requirements.txt
│   ├── .env
│   └── data/
│       ├── shoes_sample.json           # 원본 리뷰 데이터 (git 제외)
│       ├── llm_scores_by_product.json  # 스코어보드 데이터 (팀원 제공)
│       └── results.json                # 파이프라인 출력물
│
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx
        ├── index.css
        ├── main.jsx
        ├── api/
        │   └── resultsApi.js          # results.json 로딩 함수
        ├── components/
        │   ├── AspectPanel.jsx        # aspect별 분석 카드
        │   ├── DonutChart.jsx         # 긍정/부정 원 그래프
        │   ├── KeywordPanel.jsx       # 키워드 버튼
        │   ├── ReviewDrawer.jsx       # 키워드 클릭 시 리뷰 슬라이드 패널
        │   └── UrgentIssuePanel.jsx   # 긴급 이슈 카드
        └── pages/
            └── DashboardPage.jsx      # 메인 페이지
```

---

## 각 파일 역할

### `config.py`
파이프라인 전체에서 공유하는 상수를 정의한다.

| 항목 | 설명 |
|---|---|
| `ASPECTS` | 5개 고정 aspect (comfort·size·durability·design·price) |
| `ASPECT_DEFINITION` | 각 aspect의 분석 범위 정의 (GPT 프롬프트에 전달) |
| `ASPECT_QUERIES` / `ASPECT_QUERIES_POS` | SBERT 검색용 issue/strength 쿼리 |
| `ASPECT_FILTER_KEYWORDS` | aspect 할당 필수 키워드 (precision 보완) |
| `ASPECT_EXCLUDE_KEYWORDS` | 다른 aspect 오염 방지 키워드 |
| 가중치 상수 | 우선순위·대표 리뷰·urgency 계산 가중치 |

### `pipeline.py`
전처리부터 검증·저장까지 데이터 변환 로직을 담당한다.

| 함수 | 역할 |
|---|---|
| `preprocess()` | null 제거, 영어 필터링, 중복 제거, helpful vote 정규화 |
| `prioritize()` | 평점·complaint ratio·리뷰 수 기반 priority score 계산 |
| `classify()` | 평점 기반 issue/strength 분류 (3점은 NEG_KEYWORDS 판단) |
| `validate()` | JSON schema 검증, urgency score clipping |
| `save_results()` | results.json 저장 |

### `embedder.py`
SBERT 임베딩 기반 aspect 할당과 대표 리뷰 추출을 담당한다.

**3중 필터 구조:**
1. 코사인 유사도 ≥ 0.35 (의미적 관련성)
2. FILTER_KEYWORDS 포함 (도메인 특화 precision 보완)
3. EXCLUDE_KEYWORDS 미포함 (aspect 간 오염 방지)

**MMR(Maximal Marginal Relevance) 기반 대표 리뷰 추출:**
관련성은 높으면서 서로 다양한 리뷰를 선택해 GPT에 다양한 패턴을 전달한다.

### `llm_analyzer.py`
GPT-4o-mini를 호출해 키워드와 요약을 생성한다.

- **상품당 최대 10회 병렬 호출** (5 aspects × issue/strength 각각)
- issue 리뷰가 없는 aspect는 호출 스킵
- urgency score는 팀원 스코어보드(`llm_scores_by_product.json`) 기반 계산
- temperature 0.2로 hallucination 최소화

### `api_server.py`
키워드 클릭 시 전체 리뷰에서 해당 키워드를 검색해 반환하는 FastAPI 서버.

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/search` | 키워드 + product_id로 전체 리뷰 검색. 최근순 반환 |
| `GET` | `/health` | 서버 상태 및 로딩된 리뷰 수 확인 |

---

## urgency score 계산

스코어보드(`llm_scores_by_product.json`) 기반으로 계산한다.

```
urgency_score = (1 - scoreboard_score / 10) * 10
```

스코어보드가 없는 경우 대표 리뷰의 complaint ratio 기반으로 단순 계산한다.

---

## 실행 방법

### 파이프라인 실행

```bash
cd backend

# 패키지 설치
pip install -r requirements.txt

# 전체 실행
python main.py data/shoes_sample.json data/results.json

# 테스트 (3개 상품만)
python main.py data/shoes_sample.json data/results.json 3
```

### 키워드 검색 API 서버

```bash
cd backend
uvicorn api_server:app --port 8000 --reload
```

### 프론트엔드

```bash
# results.json 복사
cp backend/data/results.json frontend/public/results.json

cd frontend
npm install
npm run dev
→ http://localhost:3000
```

백엔드 API 서버를 먼저 실행해야 키워드 클릭 시 전체 리뷰 검색이 동작한다.

---

## 데이터 연동 방법

데이터 파일은 용량 문제로 git에 포함되지 않는다. 팀 공유 채널을 통해 전달받은 후 `backend/data/`에 위치시킨다.

```
backend/data/shoes_sample.json           ← 원본 리뷰 데이터
backend/data/llm_scores_by_product.json  ← 팀원 스코어보드 데이터
```

**필수 컬럼:**

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `parent_asin` | str | 상품 ID |
| `text` | str | 리뷰 본문 |
| `rating` | float | 별점 (1.0 ~ 5.0) |
| `review_date` | str | 리뷰 날짜 |

**선택 컬럼:**

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `product_title` | str | 상품명 (없으면 parent_asin 표시) |
| `helpful_vote` | int | helpful vote 수 |
| `verified_purchase` | bool | 실구매 여부 |

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| 백엔드 | Python 3.12, FastAPI, sentence-transformers, OpenAI API |
| 임베딩 | all-MiniLM-L6-v2 (SBERT) |
| LLM | GPT-4o-mini |
| 프론트엔드 | React 18, Vite |
| 데이터 | Amazon Reviews (Shoes, 2018~2023), 약 28,000건 |

---

## 비용

GPT-4o-mini 기준 100개 상품 분석 시 약 **$0.40 (약 550원)** 수준.

---

## 개발 현황

### ✅ 완료

- 전처리 파이프라인 (null 제거, 영어 필터링, 중복 제거, 정규화)
- SBERT 기반 3중 필터 aspect 할당
- MMR 기반 다양성 보장 대표 리뷰 추출
- GPT-4o-mini aspect별 병렬 호출 (상품당 최대 10회)
- 스코어보드 연동 urgency score 계산
- JSON schema 검증 및 폴백 처리
- FastAPI 키워드 검색 서버
- React 대시보드 (긴급 이슈·aspect 분석·키워드·대표 리뷰)
- 실데이터 100개 상품 분석 완료

### 🔲 남은 작업

| 항목 | 설명 | 우선순위 |
|---|---|---|
| 키워드 클릭 리뷰 검색 | api_server.py 연동 완료 후 프론트 연결 | 높음 |
| 전체 대시보드 통합 | 스코어보드·리스크레이더 등 다른 기능과 탭으로 묶기 | 팀 협의 |
| 키워드 튜닝 | 실데이터 기반 ASPECT_FILTER_KEYWORDS 보완 | 중간 |