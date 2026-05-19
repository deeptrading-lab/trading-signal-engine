# PRD: bitcoin-allocation-mvp

- **slug**: `bitcoin-allocation-mvp`
- **작성일**: 2026-05-18
- **제품 방향**: 비트코인 전용 자산 배분 의사결정 브리핑
- **대상 디렉터리**: `ai/` Python, Slack command routing, frontend dashboard
- **UI 포함 여부**: Yes. Slack/CLI 텍스트와 로컬 웹 대시보드 모두 같은 분석 결과를 표시한다.
- **LLM 범위**: LLM은 해석과 요약만 담당한다. 가격/지표 계산, 가드, 점수 산출, 배분 액션은 코드가 담당한다.

---

## 1. 배경 / 문제

초기 방향은 여러 자산군의 매수/매도 시그널이었지만, 현재 MVP는 비트코인 하나에 집중한다. 사용자는 장기/중기/단기 차트, 뉴스, 매매 동향을 조합해 지금 보유 자산에서 비트코인 비중을 늘릴지, 유지할지, 줄일지 판단하고 싶다.

MVP는 여러 자산을 고르는 추천기가 아니라 **Bitcoin Allocation Brief**를 제공한다. 자동 주문은 하지 않으며, 사용자가 최종 결정을 내릴 수 있도록 배분 액션, 근거, 리스크오프 조건, 데이터 품질을 함께 제시한다.

---

## 2. 목표

사용자가 다음처럼 요청하면:

```text
analyze BTC
signal bitcoin
분석 BTC
```

5분 이내에 다음 정보를 포함한 비트코인 배분 브리핑을 받는다.

- 최종 배분 액션: `INCREASE_ALLOCATION`, `CONDITIONAL_INCREASE`, `MAINTAIN_ALLOCATION`, `REDUCE_ALLOCATION`, `RISK_OFF`
- 확신도: `LOW`, `MEDIUM`, `HIGH`
- 종합 점수: 0~100
- 시간축: `SHORT_TERM`, `SWING`, `POSITION`
- BTC 기준 가격
- 구체적 매수/매도 크기: 예) `사용 가능 시드의 5% 매수`, `보유 BTC의 10% 매도`
- 비중 확대/유지/축소 조건
- 리스크오프 조건
- 상방/하방 참고 범위
- 핵심 근거 3~5개
- 주요 리스크 2~4개
- 데이터 소스와 신선도
- 투자 조언/자동 주문 아님 고지

---

## 3. 범위

### In Scope

- 분석 대상은 Bitcoin spot 하나로 고정한다.
- 허용 심볼은 `BTC`, `BTC-USD`, `bitcoin`, `비트코인`, `비트`다.
- 가격/거래량은 무료 BTC-USD 일봉 소스를 우선 사용한다.
- 오프라인 검증을 위해 synthetic Bitcoin 가격 provider를 유지한다.
- 장기/중기/단기 판단은 20/50/200일 이동평균, 20/60일 수익률, RSI, 실현 변동성, 최근 고점 대비 낙폭, 거래 참여 proxy를 조합한다.
- 뉴스는 OpenAI web search로, 거래소 매매 동향은 Binance 공개 API로 연결한다.
- 온체인 데이터는 아직 unavailable로 명시하고, 확신도 상한을 적용한다.
- 프론트엔드는 같은 브리핑 구조를 로컬에서 확인 가능한 대시보드로 제공한다.

### Out Of Scope

- 비트코인 외 자산 분석
- 임의 심볼을 분석 대상 또는 필수 시장 지표로 사용하는 흐름
- 기업 실적, 공시, 섹터/기업 이벤트 분석
- 자동 주문, 브로커/증권사 주문 연동
- 자동 주문 수량 산출. 단, 사용자가 입력한 시드/보유량 기준의 퍼센트 추천은 포함한다.

---

## 4. 의사결정 모델

점수는 0~100으로 코드에서 산출한다.

- Trend: 25점
- Momentum: 20점
- Participation: 15점
- Volatility/Drawdown Risk: 15점
- News Flow: 15점
- Macro/Market Regime: 10점

가드 규칙:

- 비트코인이 아닌 심볼은 명확히 거부한다.
- 가격 데이터가 stale 또는 unavailable이면 `HIGH` 확신도 금지, 심각하면 `RISK_OFF`.
- 실현 변동성이 높으면 공격적 비중 확대를 금지한다.
- 뉴스/수급 데이터가 unavailable이면 점수는 중립으로 두되 확신도는 보수적으로 제한한다.
- LLM은 제공된 수치와 코드 산출 액션을 요약할 뿐, 가격 목표나 배분 퍼센트를 발명하지 않는다.

---

## 5. 구체적 액션 산출

엔진은 액션 enum 외에 사용자가 바로 실행 여부를 판단할 수 있는 `sizing`을 반드시 반환한다. 배분 크기 계산은 코드가 담당하고, LLM은 이를 바꾸지 못한다.

필드:

- `sizing_basis`: `AVAILABLE_SEED`, `BTC_HOLDINGS`, `PORTFOLIO_TARGET`, `NO_SIZE`
- `available_seed_pct`: 사용 가능 현금/시드 중 매수 검토 비율
- `btc_holdings_sell_pct`: 현재 보유 BTC 중 매도 검토 비율
- `target_btc_allocation_pct`: 사용자가 전체 포트폴리오 정보를 제공할 때만 목표 BTC 비중
- `cash_amount`: 요청 시 사용자가 입력한 현재 사용 가능 현금. 저장 기본값은 `null`
- `cash_currency`: `KRW` 또는 `USD`
- `btc_holding_amount`: 요청 시 사용자가 입력한 현재 BTC 보유량. 저장 기본값은 `null`
- `estimated_order_cash_amount`: 퍼센트 추천을 현금 금액으로 환산한 값. 입력이 있을 때만 표시
- `estimated_order_btc_amount`: 퍼센트 추천을 BTC 수량으로 환산한 값. 입력이 있을 때만 표시
- `sizing_label_ko`: 초보자가 바로 이해하는 문장

예시:

```text
Action: CONDITIONAL_INCREASE
Sizing: 사용 가능 시드의 5%만 조건부 매수
User input: 현금 1,000,000 KRW, BTC 0.02개 보유
Display: 조건이 맞으면 약 50,000원만 매수 검토
Condition: BTC가 20일 평균 가격 위를 유지하고 변동성이 줄어들 때
```

```text
Action: REDUCE_ALLOCATION
Sizing: 보유 BTC의 10% 매도 검토
User input: 현금 300,000 KRW, BTC 0.02개 보유
Display: 보유 BTC 중 약 0.002 BTC 매도 검토
Reason: 50일 평균 가격 이탈, 뉴스 흐름 악화, 낙폭 확대
```

가드:

- 사용자는 요청할 때마다 현금과 BTC 보유량을 입력할 수 있다. 기본 정책은 raw portfolio 입력값을 장기 저장하지 않고, 해당 요청의 환산 결과와 엔진 의견만 저장한다.
- 사용자 시드/보유량 입력이 없으면 퍼센트 밴드만 제시한다.
- `KRW` 입력을 실제 BTC 수량으로 환산하려면 BTC/KRW 가격 provider 또는 USD/KRW 환율 provider가 필요하다. provider가 없으면 금액 기준 추천만 표시하고 BTC 수량 환산은 숨긴다.
- 단일 매수 추천은 기본적으로 사용 가능 시드의 0%, 5%, 10% 중 하나다.
- `HIGH` 확신도와 낮은 변동성이 동시에 확인되지 않으면 단일 매수 추천은 10%를 넘지 않는다.
- 일반 축소 추천은 보유 BTC의 5~25% 범위로 제한한다.
- `RISK_OFF`에서는 보유 BTC의 25~50% 축소를 허용하되, 재진입 조건을 반드시 표시한다.
- 가격 데이터가 stale이면 `NO_SIZE`로 반환하고 구체적 매수/매도 비율을 내지 않는다.

---

## 6. 오전 브리핑과 뉴스 업데이트

사용자는 다음날 오전에 확인하는 흐름을 기본 사용 시나리오로 본다. 기준 시간대는 `Asia/Tokyo`다.

### 6.1 오전 브리핑

오전 브리핑은 다음 데이터를 합쳐 1개의 의견을 만든다.

1. 최신 BTC 가격/기술 지표
2. 전일 동향 요약
3. 당일 09:00 뉴스 스냅샷
4. 최근 30일 의견 이력
5. 직전 오전 의견 대비 변화

출력:

- 오늘의 종합 의견
- 구체적 액션: `사용 가능 시드의 5% 매수`, `보유 BTC의 10% 매도`, `오늘은 매수 없음`
- 어제 대비 변화: 상향/유지/하향
- 핵심 변화 1~3개
- 리스크오프 조건
- 초보자용 한 줄 설명

### 6.2 예약 뉴스 업데이트

뉴스 업데이트는 하루 3회 실행한다.

- `09:00 Asia/Tokyo`
- `12:00 Asia/Tokyo`
- `15:00 Asia/Tokyo`

각 실행은 BTC 관련 시장, 규제, 기관 수급, 거시경제, 거래소/보안 이슈를 검색하고 compact summary로 저장한다. 뉴스 업데이트 자체는 새 매수/매도 의견을 만들지 않는다. 의견 생성은 오전 브리핑 또는 사용자의 명시적 요청에서만 수행한다.

뉴스 스냅샷 모델:

```json
{
  "as_of": "2026-05-18T09:00:00+09:00",
  "window": "since_previous_refresh",
  "sentiment": "positive|neutral|negative|mixed",
  "impact": "low|medium|high",
  "items": [
    {
      "title": "...",
      "source": "...",
      "url": "...",
      "published_at": "...",
      "btc_relevance": "low|medium|high",
      "summary": "..."
    }
  ]
}
```

---

## 7. 의견 저장과 30일 이력

최근 30일의 엔진 의견을 저장하고, 오늘 의견 생성 시 비교 맥락으로 사용한다. 토큰 절감을 위해 원문 전체를 매번 LLM에 넣지 않고 7일/30일 요약 digest를 만들어 사용한다.

저장 모델:

```text
bitcoin_allocation_opinions
- id
- created_at
- run_type: MORNING | MANUAL | BACKTEST | SCHEDULED_NEWS_CONTEXT
- action
- confidence
- score
- sizing_basis
- available_seed_pct
- btc_holdings_sell_pct
- target_btc_allocation_pct
- btc_reference_price
- timeframe
- reasons_json
- risks_json
- data_freshness_json
- news_snapshot_id nullable
- prompt_version
- engine_version
- token_usage_json nullable
- pinned boolean
```

보존 정책:

- 기본 30일 보존
- `pinned=true`는 자동 삭제하지 않음
- 오전 브리핑은 직전 `MORNING` 의견과 7일 추세를 비교한다.

---

## 8. OpenAI/GPT 뉴스 연동

새 연동은 OpenAI Responses API를 기준으로 한다. OpenAI 공식 문서에 따르면 Responses API는 web search, file search, function calling 같은 도구를 사용할 수 있고, web search는 최신 인터넷 정보를 검색해 citation/source 기반 답변을 만들 수 있다.

사용자가 로컬 환경에서 GPT 분석을 사용하려면 본인의 OpenAI API key를 로컬 환경변수로 입력한다. API key는 저장소에 커밋하지 않는다. 대화나 로그에 노출된 key는 폐기하고 새 key로 교체한다.

현재 구현은 `data_provider=openai` 일 때 OpenAI web search 뉴스와 Binance 공개 API 매매 동향을 함께 읽는다. `data_provider=claude` 는 UI 토글만 있고 백엔드 구현은 아직 없다.

필요 정보:

- `OPENAI_API_KEY`
- `OPENAI_NEWS_MODEL`: `gpt-5.4-nano`
- `OPENAI_BRIEF_MODEL`: `gpt-5.4-mini`
- `OPENAI_MONTHLY_BILLING_LIMIT_USD`: `20`
- `OPENAI_DAILY_COST_LIMIT_USD`: `0.50`
- `NEWS_REFRESH_MAX_ARTICLES`: 기본 8개
- `NEWS_REFRESH_MAX_INPUT_TOKENS`: 기본 6000
- `MORNING_BRIEF_MAX_OUTPUT_TOKENS`: 기본 900
- `MANUAL_BRIEF_MAX_OUTPUT_TOKENS`: 기본 1200
- `ANTHROPIC_API_KEY`: 추후 Claude provider 구현 시 사용
- 우선/차단 뉴스 도메인 목록
- 운영 시간대: 기본 `Asia/Tokyo`

연동 원칙:

- GPT는 뉴스 검색, 뉴스 요약, 사용자 친화적 설명만 담당한다.
- 기술 지표, 점수, 액션, sizing은 Python 엔진이 계산한다.
- OpenAI web search 실패 시 기술 지표만으로 브리핑하고 데이터 품질 경고를 표시한다.
- cached news가 3시간 이내면 수동 요청에서 재검색하지 않고 저장된 뉴스 스냅샷을 재사용한다.
- 모든 LLM 호출은 model, prompt_version, token_usage, source URLs를 저장한다.

모델/비용 결정:

- 뉴스 검색/압축은 `gpt-5.4-nano`를 기본값으로 한다. 요약·분류 작업에 충분히 저렴하고 빠른 모델을 우선 사용한다.
- 최종 사용자 브리핑은 `gpt-5.4-mini`를 기본값으로 한다. 초보자용 설명, 리스크 해석, 액션 문구 품질이 중요하므로 nano보다 한 단계 높은 모델을 사용한다.
- 월 billing limit이 $20이므로 앱 내부 일일 소프트 한도는 $0.50으로 둔다. 단순 월평균($20 / 31일 ≈ $0.64)보다 낮게 잡아 web search tool call과 재시도 비용 버퍼를 남긴다.
- OpenAI Costs API 또는 대시보드는 실제 사용 비용 확인용이며, 앱은 자체 `OPENAI_DAILY_COST_LIMIT_USD`로 선제 차단한다.
- web search는 tool call 비용과 검색 컨텍스트 토큰 비용이 추가될 수 있으므로, 09/12/15시 예약 검색 결과를 캐시하고 수동 요청은 캐시 우선으로 처리한다.

---

## 9. 수용 기준

- `analyze BTC`, `analyze bitcoin`, `signal BTC`, `분석 BTC`가 단일 Bitcoin 분석 경로로 연결된다.
- 비트코인이 아닌 심볼은 “Bitcoin only” 메시지로 거부된다.
- 도메인 모델은 `asset_type="BITCOIN_SPOT"`을 반환한다.
- 렌더링 제목은 `Bitcoin Allocation Brief`다.
- 출력에는 Action, Confidence, Score, Timeframe, BTC reference price, Allocation condition, Risk-off condition, Risk range, Why, Risks, Data source, Disclaimer가 포함된다.
- 점수는 항상 0~100 범위다.
- 비트코인 외 자산 예시가 Bitcoin 출력에 나타나지 않는다.
- `make signal-offline SYMBOL=BTC`로 네트워크 없이 로컬 확인이 가능하다.
- `make test-bitcoin-signal`이 통과한다.
- 오전 브리핑은 `사용 가능 시드의 5% 매수`, `보유 BTC의 10% 매도`, `오늘은 매수 없음`처럼 구체적 액션을 포함한다.
- 뉴스 스냅샷은 09:00, 12:00, 15:00 `Asia/Tokyo` 기준으로 저장된다.
- 최근 30일 의견을 조회하고 오늘 의견과 비교할 수 있다.
- LLM 출력은 엔진의 action/sizing을 덮어쓸 수 없다.
- web search 실패 시 graceful degrade하고 확신도를 보수적으로 제한한다.
- LLM 호출별 모델명, 토큰 사용량, source URL이 저장된다.

---

## 10. 개발자 핸드오프

- 기존 다중 자산 분석 패키지는 `bitcoin_signal`로 대체한다.
- 분석 진입점은 `analyze_bitcoin`을 사용한다.
- renderer 문구는 Decision/Entry/Invalidation보다 Allocation/Risk-off/Risk range를 사용한다.
- Makefile과 테스트 타깃에서 비트코인 외 자산 명칭과 기본값을 제거한다.
- README와 프론트엔드 문서도 Bitcoin-only 방향을 기준으로 갱신한다.
- 엔진 출력에 sizing 필드를 추가한다.
- 의견 저장 repository와 뉴스 스냅샷 repository를 추가한다.
- 09:00/12:00/15:00 JST 뉴스 업데이트 entrypoint를 추가한다.
- 오전 브리핑 service는 엔진 결과, 최신 뉴스 스냅샷, 최근 30일 의견 digest를 결합한다.
- OpenAI Responses API client wrapper를 추가하고 web search 결과 source를 저장한다.
- sizing guard, stale data, 30일 retention, cached news reuse, LLM override 방지 테스트를 추가한다.
