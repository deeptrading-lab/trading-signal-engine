# Data/News Handoff: kr-stock-news-signal-mvp

- **slug**: `kr-stock-news-signal-mvp`
- **작성일**: 2026-06-06
- **담당 역할**: Data/News Analyst
- **입력 PRD**: `docs/prd/kr-stock-news-signal-mvp.md`

---

## 1. Source Policy

### Watchlist

MVP는 아래 3개 종목만 처리한다.

| symbol | name_ko | market | enabled |
|---|---|---|---|
| `005930.KS` | 삼성전자 | KOSPI | true |
| `000660.KS` | SK하이닉스 | KOSPI | true |
| `005380.KS` | 현대차 | KOSPI | true |

watchlist 외 symbol은 분석하지 않고 "watchlist 등록 필요"로 거절한다.

### News Provider

기본 경로는 OpenAI Responses API `web_search` + JSON output이다.

필요한 사용자 준비:

- `OPENAI_API_KEY`를 local shell 또는 `.env.local`에 설정
- 비용 한도 합의: 기본 일 $0.50 이하 권장

대체/후속 후보:

- Naver Search API: 별도 client id/secret 필요
- OpenDART API: OpenDART API key 필요
- 거래소/IR RSS: source별 adapter 필요

MVP에서는 OpenAI 외 API key 가입을 요구하지 않는다.

### Explicitly Not This Engine

- 국내 주식 가격 provider
- 가격/거래량 저장
- 기술 지표
- 매수/매도 action
- 추천 수량/금액

위 기능은 프론트엔드 또는 후속 별도 엔진에서 담당한다.

---

## 2. Query Template

종목별 검색 query:

```text
{name_ko} {symbol} 오늘 뉴스 주가 실적 수급 증권 리포트
```

산업 키워드:

- 삼성전자/SK하이닉스: `반도체`, `메모리`, `HBM`, `AI`, `파운드리`, `환율`, `수출`
- 현대차: `자동차`, `전기차`, `환율`, `미국`, `관세`, `노조`, `판매량`

검색 결과는 당일 뉴스 우선이며, 오래된 배경 기사는 `relevance_score <= 1`로 낮춘다.

---

## 3. Structured Output Schema

뉴스 수집 LLM 출력은 아래 JSON만 허용한다.

```json
{
  "symbol": "005930.KS",
  "as_of": "2026-06-06T08:30:00+09:00",
  "items": [
    {
      "title": "string",
      "source": "string",
      "url": "string",
      "published_at": "string|null",
      "summary_ko": "string",
      "sentiment_score": 0,
      "impact_score": 0,
      "relevance_score": 0,
      "novelty": "NEW|REPEAT|UNKNOWN",
      "risk_tags": ["earnings"],
      "confidence": "LOW|MEDIUM|HIGH"
    }
  ]
}
```

Validation rules:

- `sentiment_score`: integer, `-3..3`
- `impact_score`: integer, `0..3`
- `relevance_score`: integer, `0..3`
- `novelty`: one of `NEW`, `REPEAT`, `UNKNOWN`
- `confidence`: one of `LOW`, `MEDIUM`, `HIGH`
- `risk_tags`: allowed set only
- `summary_ko`: 20~300 chars
- `url`: empty string allowed only when source has no URL; id generation then falls back to title hash

Allowed risk tags:

```text
earnings, guidance, macro, fx, supply_chain, regulation, labor,
geopolitics, product, customer, sector, valuation, liquidity
```

---

## 4. Score Aggregation

Item weighted score:

```text
item_score = sentiment_score * impact_score * relevance_score
```

Daily fields:

- `weighted_score`: sum of item_score
- `positive_count`: item_score > 0
- `negative_count`: item_score < 0
- `high_impact_count`: impact_score >= 3 and relevance_score >= 2
- `negative_shock_count`: sentiment_score <= -2 and impact_score >= 2 and relevance_score >= 2
- `top_summaries`: max 3 items sorted by `abs(item_score)` desc
- `risk_tags`: de-duplicated tags from included items

10 day feature:

```text
D0-D2 weight = 1.0
D3-D5 weight = 0.7
D6-D9 weight = 0.4
news_score_10d = sum(daily.weighted_score * decay_weight)
```

This feature is advisory only. It should not directly trigger a buy/sell action.

---

## 5. DB Storage

SQLite remains the local/offline test storage. Recommended local path:

```text
data/kr_stock_news.db
```

Do not commit the DB file. Commit only schema/repository code.

The next shared/remote storage target is Supabase Postgres Free tier.

- Keep the existing SQLite repository for tests and offline smoke runs.
- Add a Supabase repository behind the same repository contract.
- Use Postgres-native `jsonb`, `timestamptz`, `date`, and boolean types instead of SQLite JSON/text encodings.
- Apply schema changes as versioned migrations.
- Backend ingestion credentials must never be exposed to the frontend.
- Prefer frontend access through this engine's HTTP API. Direct frontend reads require read-only RLS policies.

Tables:

- `watchlist_symbols`
- `news_items`
- `daily_news_scores`

Idempotency:

- `news_items.id = sha256(symbol | normalized_url_or_title | published_at_or_date)`
- `daily_news_scores` primary key: `(symbol, date)`

Retention:

- `news_items`: 90 days
- `daily_news_scores`: 1 year

Supabase migration checklist:

1. Create `watchlist_symbols`, `news_items`, and `daily_news_scores`.
2. Preserve the existing primary keys and idempotent upsert behavior.
3. Add indexes for `news_items(symbol, published_at desc)` and
   `daily_news_scores(symbol, date desc)`.
4. Enable RLS before allowing frontend credentials.
5. Deny public writes; ingestion writes are backend-only.
6. Add a read policy only for the tables/columns the frontend actually needs.
7. Run sample ingestion twice and verify row counts do not increase from duplicates.

---

## 6. User-Provided Setup Needed

Required now:

- None for sample/local tests. SQLite is local and uses no signup.

Required before real news ingestion:

- OpenAI API key with Responses API access.
- Put it in `.env.local` or the shell environment as:

```bash
OPENAI_API_KEY=...
OPENAI_NEWS_MODEL=gpt-4.1-mini
OPENAI_DAILY_COST_LIMIT_USD=0.50
```

Optional later:

- Naver Search API client id/secret if OpenAI web search is too expensive or noisy.
- OpenDART API key if 공시 데이터를 official source로 붙일 때.
- Supabase Free project for shared persistence and frontend/backend integration.

Required for the Supabase step:

- Existing/new project decision.
- Existing project name or project ref. Do not paste database passwords or secret keys into chat.
- Put runtime secrets in `.env.local`:

```bash
KR_STOCK_DB_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<local-only-secret>
```

- Frontend reads through the engine HTTP API. It does not receive the backend
  Supabase secret or access Supabase tables directly.

---

## 7. Backend Handoff

Implemented first:

1. `ai/kr_stock_signal/models.py`
2. `ai/kr_stock_signal/repository.py`
3. `ai/kr_stock_signal/news.py`
4. `ai/kr_stock_signal/ingestion.py`
5. `ai/kr_stock_signal/openai_news.py`
6. `ai/kr_stock_signal/cli.py`
7. `ai/tests/test_kr_stock_signal.py`

Acceptance focus:

- watchlist seed
- SQLite schema creation without price/signal tables
- news item upsert idempotency
- daily news score aggregation
- 10-day feature aggregation without LLM
- watchlist reject
- sample provider test without API key
- real OpenAI provider smoke test when API key is available
