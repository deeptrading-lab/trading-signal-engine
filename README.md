# Trading Signal Engine

국내 대형주 뉴스를 수집하고 한국어로 요약·점수화한 뒤 SQLite 또는
Supabase에 저장하는 백엔드 엔진입니다.

현재 watchlist는 다음 3개 종목입니다.

| 종목 | Symbol | 시장 |
|---|---|---|
| 삼성전자 | `005930.KS` | KOSPI |
| SK하이닉스 | `000660.KS` | KOSPI |
| 현대차 | `005380.KS` | KOSPI |

이 엔진은 가격 데이터, 기술 지표, 매수·매도 신호, 추천 가격이나 수량을
만들지 않습니다. 국내 주식 가격은 별도 프론트엔드에서 처리하며, 이 저장소는
뉴스를 투자 판단의 보조 feature로 정규화하는 역할에 집중합니다.

기준 문서:

- [프로젝트 상태](./docs/PROJECT_STATUS.md)
- [국내 주식 뉴스 MVP PRD](./docs/prd/kr-stock-news-signal-mvp.md)
- [Data/News 설계](./docs/data/kr-stock-news-signal-mvp.md)
- [QA 결과](./docs/qa/kr-stock-news-signal-mvp.md)

## 주요 기능

- OpenAI Responses API의 web search를 이용한 종목별 뉴스 수집
- 기사별 한국어 요약과 점수 산출
  - `sentiment_score`: `-3..3`
  - `impact_score`: `0..3`
  - `relevance_score`: `0..3`
- novelty, confidence, risk tag 검증
- URL·제목·날짜 기반 중복 제거와 idempotent upsert
- 일별 뉴스 점수와 최근 10일 decay feature 집계
- SQLite 로컬 저장과 Supabase 공유 저장 지원
- refresh, daily score, feature 조회 HTTP API
- refresh API Bearer 인증과 OpenAI 비용 한도 가드

뉴스 점수는 매수·매도 결론이 아니라 가격 화면이나 후속 분석 엔진이 참고하는
보조 정보입니다.

## 처리 흐름

```text
OpenAI web search
        ↓
뉴스 metadata + 한국어 요약 + structured score
        ↓
schema validation / dedupe / stable ID
        ↓
SQLite 또는 Supabase
        ↓
daily score / recent 10-day feature
        ↓
HTTP API
        ↓
trading-signal-frontend
```

저장하는 데이터:

- 기사 title, source, URL, published time
- 짧은 한국어 요약
- sentiment, impact, relevance 점수
- novelty, confidence, risk tags
- model, token usage, estimated cost metadata
- 종목별 일별 집계와 최근 핵심 요약

뉴스 원문 body는 저장하지 않습니다.

## 빠른 시작

Python 3.11 이상을 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env.local
```

API key 없이 sample 데이터로 실행:

```bash
PYTHON=.venv/bin/python make kr-news-sample SYMBOL=삼성전자
```

국내 주식 뉴스 테스트:

```bash
PYTHON=.venv/bin/python make test-kr-stock-signal
```

전체 테스트:

```bash
PYTHON=.venv/bin/python make test
```

## OpenAI 설정

실제 뉴스 수집에는 `.env.local`에 `OPENAI_API_KEY`가 필요합니다.

```bash
OPENAI_API_KEY=sk-proj-...
OPENAI_NEWS_MODEL=gpt-5.4-nano
OPENAI_DAILY_COST_LIMIT_USD=0.50
OPENAI_NEWS_MAX_REQUEST_COST_USD=0.10
```

실행:

```bash
PYTHON=.venv/bin/python make kr-news SYMBOL=삼성전자
```

비용 가드는 OpenAI 호출 전에 요청별 최대 예상 비용을 일일 한도에서
예약합니다. 프로세스 재시작을 넘어서는 비용·실행 이력 저장은 후속 작업입니다.

## 저장소 설정

### SQLite

기본값이며 가입이나 외부 서비스가 필요 없습니다.

```bash
KR_STOCK_DB_BACKEND=sqlite
KR_STOCK_SQLITE_PATH=data/kr_stock_news.db
```

SQLite 파일은 로컬 테스트와 오프라인 실행에 사용하며 Git에 커밋하지 않습니다.

### Supabase

공유 데이터와 프론트엔드 연동을 위한 운영 저장소입니다.

먼저 아래 migration을 Supabase에 적용합니다.

```text
supabase/migrations/202606070001_kr_stock_news.sql
```

이후 `.env.local`에 backend 전용 값을 설정합니다.

```bash
KR_STOCK_DB_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
```

보안 원칙:

- `SUPABASE_SECRET_KEY`는 프론트엔드에 전달하지 않습니다.
- publishable key는 backend 쓰기 인증으로 사용하지 않습니다.
- Supabase 테이블은 RLS가 활성화되어 있으며 public policy를 만들지 않습니다.
- 프론트엔드는 Supabase를 직접 읽지 않고 이 엔진의 HTTP API를 호출합니다.
- secret은 `.env.local` 또는 배포 secret manager에만 저장합니다.

## HTTP API

서버 실행:

```bash
PYTHON=.venv/bin/python make kr-news-server
```

기본 주소는 `http://127.0.0.1:8766`입니다.

### Health

```http
GET /health
```

### 뉴스 수집

```http
POST /api/kr-stocks/news/refresh
Authorization: Bearer <KR_STOCK_REFRESH_TOKEN>
Content-Type: application/json

{
  "symbol": "삼성전자",
  "provider": "openai",
  "score_date": "2026-06-08"
}
```

`.env.local` 설정:

```bash
KR_STOCK_REFRESH_TOKEN=<충분히 긴 임의 문자열>
```

인증이 없거나 token이 다르면 `401`을 반환합니다. 로컬 sample 확인에는
`provider`를 `sample`로 지정할 수 있습니다.

### 일별 점수 조회

```http
GET /api/kr-stocks/news/daily?symbol=005930.KS&date=2026-06-08
```

응답에는 item count, weighted score, positive/negative count, high impact count,
negative shock count, 핵심 요약과 risk tag가 포함됩니다.

### 최근 뉴스 feature 조회

```http
GET /api/kr-stocks/news/feature?symbol=005930.KS&lookback_days=10
```

저장된 일별 점수에 decay를 적용한 `news_score_10d`, 충격 뉴스 수, 고영향 뉴스 수,
최근 핵심 요약과 risk tag를 반환합니다. 원문을 LLM에 다시 보내지 않습니다.

## 환경변수

| 변수 | 기본값 | 용도 |
|---|---|---|
| `OPENAI_API_KEY` | 없음 | 실제 뉴스 수집 |
| `OPENAI_NEWS_MODEL` | provider 기본값 | 뉴스 검색·요약 모델 |
| `OPENAI_DAILY_COST_LIMIT_USD` | `0.50` | 프로세스 일일 비용 한도 |
| `OPENAI_NEWS_MAX_REQUEST_COST_USD` | `0.10` | 요청별 비용 예약값 |
| `KR_STOCK_DB_BACKEND` | `sqlite` | `sqlite` 또는 `supabase` |
| `KR_STOCK_SQLITE_PATH` | `data/kr_stock_news.db` | SQLite 파일 경로 |
| `SUPABASE_URL` | 없음 | Supabase project URL |
| `SUPABASE_SECRET_KEY` | 없음 | backend 전용 Supabase key |
| `KR_STOCK_REFRESH_TOKEN` | 없음 | refresh API Bearer token |
| `KR_STOCK_PORT` | `8766` | HTTP API port |
| `HOST` | `127.0.0.1` | HTTP bind host |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | 허용 CORS origin |

전체 템플릿은 [.env.example](./.env.example)을 참고하세요.

## 프로젝트 구조

```text
ai/kr_stock_signal/
├── cli.py             # 뉴스 수집 CLI와 sample provider
├── ingestion.py       # validation, dedupe, 저장 orchestration
├── models.py          # NewsItem, DailyNewsScore, NewsFeature
├── news.py            # 점수 validation과 집계
├── openai_news.py     # OpenAI web search provider와 비용 가드
├── repository.py      # SQLite/Supabase repository
├── server.py          # refresh/daily/feature HTTP API
└── watchlist.py       # 삼성전자, SK하이닉스, 현대차

supabase/migrations/
└── 202606070001_kr_stock_news.sql
```

## 현재 상태

완료:

- 국내 대형주 3종 watchlist
- OpenAI 뉴스 수집·요약·점수화
- 저장 전 schema validation과 중복 제거
- SQLite와 Supabase 저장
- Supabase migration, RLS, idempotent upsert
- daily score와 최근 10일 feature
- refresh/daily/feature HTTP API
- refresh 인증과 OpenAI 비용 사전 가드
- 실제 OpenAI 및 Supabase smoke test

다음 작업:

1. `08:30`, `12:30`, `16:10` `Asia/Seoul` scheduler
2. `ingestion_runs`와 token/cost/error 실행 로그
3. frontend API 연동 smoke
4. retention cleanup과 source 신뢰도 개선
5. 원격 배포 구성

최신 우선순위는 [docs/PROJECT_STATUS.md](./docs/PROJECT_STATUS.md)를 기준으로 합니다.

## 기존 호환 기능

기존 Bitcoin allocation engine은 `ai/bitcoin_signal`에 유지되어 있습니다. 현재 제품
우선순위에서는 superseded 상태이며 신규 국내 주식 뉴스 엔진과 별도 경로입니다.

```bash
make signal-offline SYMBOL=BTC
make signal SYMBOL=BTC
make bitcoin-server
make test-bitcoin-signal
```

기존 Bitcoin 설계는
[docs/prd/bitcoin-allocation-mvp.md](./docs/prd/bitcoin-allocation-mvp.md)를 참고하세요.

## 개발 절차

요구사항, PRD, Data/News 설계, 구현, QA, 리뷰, 배포 절차는
[AGENTS.md](./AGENTS.md)를 따릅니다.
