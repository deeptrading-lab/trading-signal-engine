# PRD: kr-stock-news-signal-mvp

- **slug**: `kr-stock-news-signal-mvp`
- **작성일**: 2026-06-06
- **제품 방향**: 국내 대형주 뉴스 수집·요약·점수화 엔진
- **초기 대상 종목**: 삼성전자, SK하이닉스, 현대차
- **대상 디렉터리**: `ai/` Python, scheduler, SQLite DB, local HTTP API
- **UI 포함 여부**: No. 이 저장소는 백엔드 엔진만 담당한다.
- **가격 데이터 범위**: No. 국내 주식 가격 provider는 프론트엔드에서 담당한다.
- **LLM 범위**: 당일 뉴스 검색, 한국어 요약, 점수화, source metadata 저장.

---

## 1. 배경 / 문제

사용자는 삼성전자, SK하이닉스, 현대차처럼 관심 종목을 정해 두고 매수/매도 판단에 참고할 뉴스 흐름을 보고 싶어 한다. 다만 뉴스는 이미 주가에 일부 선반영되는 경우가 많으므로, 이 엔진은 가격 판단을 대체하지 않고 **보조 정보**만 만든다.

국내 주식 가격 provider는 프론트엔드에 이미 구현되어 있다. 따라서 이 백엔드 엔진은 가격 저장, 기술 지표, 매수/매도 신호, 수량 계산을 하지 않는다. MVP의 책임은 종목별 당일 뉴스를 검색하고, 요약하고, `sentiment/impact/relevance` 점수를 매긴 뒤 DB에 저장하는 것이다.

핵심 비용 전략은 뉴스 원문 전체를 반복적으로 LLM에 넣지 않는 것이다. 당일 수집 시점에 한 번만 요약·점수화하고, 이후에는 저장된 daily score와 최근 요약을 조회해 프론트엔드나 후속 엔진이 보조 feature로 사용한다.

---

## 2. 목표

사용자가 다음처럼 요청하거나 scheduler가 실행되면:

```text
삼성전자 뉴스 분석해줘
오늘 삼성전자 관련 뉴스 점수 갱신해줘
최근 10일 삼성전자 뉴스 흐름 알려줘
```

엔진은 다음을 제공한다.

- 종목별 당일 뉴스 item 목록: title, source, URL, published_at, summary_ko
- 기사별 점수: `sentiment_score -3..3`, `impact_score 0..3`, `relevance_score 0..3`
- 기사별 메타: novelty, risk_tags, confidence, prompt_version, model, token usage
- 일별 집계: weighted_score, positive/negative count, high impact count, negative shock count, top summaries
- 최근 10일 feature: decay를 적용한 `news_score_10d`, risk tags, 최근 핵심 요약
- 저장 우선 동작: 이미 DB에 저장된 요약/점수는 원문 재분석 없이 재사용한다.

---

## 3. 범위

### In Scope

- 초기 watchlist는 3종목으로 제한한다.
  - 삼성전자: `005930.KS`
  - SK하이닉스: `000660.KS`
  - 현대차: `005380.KS`
- watchlist 외 종목은 "watchlist 등록 필요"로 거절한다.
- OpenAI Responses API web search를 기본 뉴스 검색/요약/점수화 경로로 사용한다.
- 뉴스 원문 body는 저장하지 않고 source metadata, 짧은 한국어 요약, 점수만 저장한다.
- SQLite DB를 MVP 기본 저장소로 사용한다.
- 같은 뉴스는 stable id로 upsert해 중복 저장을 막는다.
- 저장된 `daily_news_scores`만 사용해 최근 10일 뉴스 feature를 계산한다.
- 로컬 컴퓨터가 켜져 있는 동안 scheduler가 정해진 주기로 뉴스 수집을 실행할 수 있게 설계한다.
- CLI와 local HTTP API는 뉴스 refresh/query만 담당한다.

### Out Of Scope

- 국내 주식 가격 provider 구현.
- 일봉/분봉 가격 저장.
- 기술 지표 계산.
- 매수/매도 신호 생성.
- "얼마에 몇 주 사/팔지" 수량 계산.
- 자동 주문, 브로커/증권사 API 연동.
- 전 종목 자동 스캔.
- 뉴스만으로 매수/매도 결론을 내리는 기능.
- Codex CLI가 DB에 직접 쓰거나 로컬 서버를 우회하는 흐름.

---

## 4. 핵심 제품 판단

뉴스는 보조지표다. 좋은 뉴스가 많아도 매수를 강제하지 않고, 나쁜 뉴스가 있어도 즉시 매도를 강제하지 않는다. 이 엔진의 출력은 프론트엔드 가격 provider나 후속 신호 엔진이 참고할 수 있는 정규화된 뉴스 feature다.

권장 사용 방식:

- 가격 화면 옆에 "오늘 뉴스 점수"와 핵심 요약을 보조 표시한다.
- 최근 10일 score가 큰 음수이거나 negative shock이 반복되면 리스크 경고를 띄운다.
- 긍정 뉴스가 많더라도 가격이 과열인지 여부는 프론트엔드/후속 엔진이 별도로 판단한다.

---

## 5. 데이터 모델

SQLite MVP schema:

```text
watchlist_symbols
- symbol text primary key
- name_ko text not null
- market text not null
- enabled integer not null
- created_at text not null

news_items
- id text primary key
- symbol text not null
- published_at text
- source text
- title text not null
- url text
- summary_ko text not null
- sentiment_score integer not null
- impact_score integer not null
- relevance_score integer not null
- novelty text not null
- risk_tags_json text not null
- confidence text not null
- collected_at text not null
- prompt_version text not null
- model text
- input_tokens integer
- output_tokens integer
- estimated_cost_usd real

daily_news_scores
- symbol text not null
- date text not null
- item_count integer not null
- weighted_score real not null
- positive_count integer not null
- negative_count integer not null
- high_impact_count integer not null
- negative_shock_count integer not null
- top_summaries_json text not null
- risk_tags_json text not null
- primary key(symbol, date)
```

보존 정책:

- `news_items`: 기본 90일 보존. 원문 body는 저장하지 않는다.
- `daily_news_scores`: 1년 보존.
- DB 파일은 커밋하지 않는다.

---

## 6. 뉴스 수집·요약·점수화

### 실행 주기

로컬 컴퓨터가 켜져 있는 동안 다음 주기로 실행한다.

- 장전: `08:30 Asia/Seoul`
- 장중 보조: `12:30 Asia/Seoul`
- 장마감 후: `16:10 Asia/Seoul`
- 수동 refresh: 사용자가 CLI/API로 요청할 때

### Query Template

```text
{company_name_ko} {symbol} 오늘 뉴스 주가 실적 수급 증권 리포트
```

산업 키워드:

- 삼성전자/SK하이닉스: `반도체`, `메모리`, `HBM`, `AI`, `파운드리`, `환율`, `수출`
- 현대차: `자동차`, `전기차`, `환율`, `미국`, `관세`, `노조`, `판매량`

### Structured Output

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
      "summary_ko": "20-300자 한국어 요약",
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

Validation:

- `sentiment_score`: integer, `-3..3`
- `impact_score`: integer, `0..3`
- `relevance_score`: integer, `0..3`
- `novelty`: `NEW|REPEAT|UNKNOWN`
- `confidence`: `LOW|MEDIUM|HIGH`
- `summary_ko`: 20~300 chars
- `risk_tags`: `earnings`, `guidance`, `macro`, `fx`, `supply_chain`, `regulation`, `labor`, `geopolitics`, `product`, `customer`, `sector`, `valuation`, `liquidity`

---

## 7. 점수 집계

Item weighted score:

```text
item_score = sentiment_score * impact_score * relevance_score
```

Daily fields:

- `weighted_score`: item_score 합계
- `positive_count`: item_score > 0
- `negative_count`: item_score < 0
- `high_impact_count`: impact_score >= 3 and relevance_score >= 2
- `negative_shock_count`: sentiment_score <= -2 and impact_score >= 2 and relevance_score >= 2
- `top_summaries`: abs(item_score) 기준 상위 3개 요약
- `risk_tags`: 포함 기사 risk tag dedupe

최근 10일 feature:

```text
D0-D2 weight = 1.0
D3-D5 weight = 0.7
D6-D9 weight = 0.4
news_score_10d = sum(daily.weighted_score * decay_weight)
```

---

## 8. Codex CLI 연동 가능성

Codex CLI에 주기적으로 "뉴스 검색, 요약, 점수화"를 요청하고 로컬 서버가 결과를 받아 DB에 저장하는 구조는 실험적으로 가능하다. 하지만 MVP 기본 경로로는 권장하지 않는다.

판단:

- 가능성: 높음. Codex CLI가 정해진 템플릿으로 JSON을 출력하고 local HTTP endpoint에 POST하는 adapter를 만들 수 있다.
- 리스크: CLI 세션 상태, 출력 형식 흔들림, 비용/권한 통제, 로컬 서버 인증, 실패 재시도가 복잡해진다.
- 권장: MVP는 Python scheduler가 OpenAI Responses API를 직접 호출한다. Codex CLI adapter는 `experimental`로 격리하고 DB에는 직접 쓰지 않게 한다.

---

## 9. API / CLI

MVP CLI:

```bash
PYTHON=.venv/bin/python make kr-news SYMBOL=삼성전자
PYTHON=.venv/bin/python make kr-news-sample SYMBOL=삼성전자
PYTHON=.venv/bin/python make test-kr-stock-signal
```

후속 local HTTP API:

```text
POST /api/kr-stocks/news/refresh
GET  /api/kr-stocks/news/daily?symbol=005930.KS&date=YYYY-MM-DD
GET  /api/kr-stocks/news/feature?symbol=005930.KS&lookback_days=10
```

---

## 10. 수용 기준

- `docs/prd/kr-stock-news-signal-mvp.md`가 뉴스 전용 엔진 기준 PRD로 존재한다.
- 삼성전자/SK하이닉스/현대차 watchlist가 seed 된다.
- watchlist 외 종목은 거절된다.
- SQLite schema에는 `watchlist_symbols`, `news_items`, `daily_news_scores`가 생성된다.
- schema에는 `price_bars`, `signal_reports`가 없다.
- 뉴스 item은 source metadata, 요약, 점수만 저장하고 원문 body를 저장하지 않는다.
- 같은 뉴스 item은 stable id로 upsert되어 중복 저장되지 않는다.
- invalid score, invalid risk tag, 너무 짧은 summary는 저장 전 reject된다.
- 최근 10일 feature는 저장된 daily score만 사용하고 원문을 LLM에 다시 보내지 않는다.
- OpenAI API key가 없으면 real provider는 명확히 실패하고 sample provider 테스트는 통과한다.
- `make test-kr-stock-signal`이 신규 core tests를 실행한다.

---

## 11. 가정·제약

- 실제 뉴스 ingestion에는 `OPENAI_API_KEY`가 필요하다.
- 로컬 MVP DB는 SQLite로 충분하다. 원격 DB 가입은 아직 필요 없다.
- 뉴스 검색 품질과 비용이 맞지 않으면 Naver Search API 또는 OpenDART API를 후속 adapter로 검토한다.
- 이 엔진의 점수는 투자 조언이나 자동 주문이 아니다.
