# PRD: stock-signal-mvp

- **slug**: `stock-signal-mvp`
- **작성일**: 2026-05-08
- **제품 방향**: 종목 매수/매도 의사결정 브리핑
- **대상 디렉터리**: `ai/` Python, Slack command routing
- **UI 포함 여부**: No. MVP는 Slack DM 텍스트/Block Kit 응답만 사용한다.
- **LLM 범위**: LLM은 해석과 요약만 담당한다. 가격/지표 계산, 가드, 점수 산출은 코드가 담당한다.
- **배포 목표**: 작은 팀이 월 $20~$80 수준으로 운영 가능한 로컬 또는 AWS Lightsail/EC2 데몬.

---

## 1. 배경 / 문제

사용자는 특정 종목에 대해 "지금 사야 하는지, 팔아야 하는지, 기다려야 하는지"를 빠르게 판단하고 싶다. 기존 PRD는 `BUY / SELL / HOLD` 신호를 중심으로 설계되어 있었지만, 실제 매매 의사결정에서는 단일 라벨만으로는 부족하다.

실제 판단에 필요한 질문은 다음에 가깝다.

- 현재 가격에서 신규 진입해도 되는가?
- 이미 보유 중이면 계속 보유할 근거가 있는가?
- 어떤 가격 또는 조건에서 판단이 무효화되는가?
- 기대수익 대비 감수해야 하는 손실은 합리적인가?
- 지금 신호를 믿으면 안 되는 데이터 결측 또는 이벤트 리스크가 있는가?

따라서 MVP는 단순한 `BUY / SELL / HOLD` 예측기가 아니라, 사용자가 직접 최종 결정을 내릴 수 있도록 돕는 **종목 의사결정 브리핑 카드**를 제공해야 한다.

중요 원칙:

- 시스템은 투자 조언을 확정적으로 제공하지 않는다.
- LLM은 수치 계산을 하지 않는다. 계산은 Python 코드에서 수행한다.
- LLM은 정규화된 데이터와 코드 산출 점수를 해석하고 설명한다.
- 데이터 품질이 낮거나 이벤트 리스크가 크면 신호 강도를 자동으로 낮춘다.
- 자동 주문은 MVP 범위가 아니다.

---

## 2. 목표

### 2.1 제품 목표

사용자가 Slack DM에서 다음과 같이 입력하면:

```text
analyze AAPL
```

5분 이내에 다음 정보를 포함한 종목 브리핑을 받는다.

- 최종 행동 제안: `ACTIONABLE_LONG`, `CONDITIONAL_LONG`, `HOLD_MONITOR`, `REDUCE_RISK`, `AVOID`
- 확신도: `LOW`, `MEDIUM`, `HIGH`
- 종합 점수: 0~100
- 시간축: `SHORT_TERM`, `SWING`, `POSITION`
- 핵심 근거 3~5개
- 주요 리스크 2~4개
- 진입 조건 또는 관망 조건
- 무효 조건, 즉 이 조건이 깨지면 판단을 폐기해야 하는 기준
- 리스크/보상 요약
- 데이터 품질과 기준 시각
- "자동 주문 아님" 고지

### 2.2 역제안: BUY/SELL/HOLD 대신 Decision Brief

기존의 `BUY / SELL / HOLD`는 지나치게 단순하다. 특히 개인 또는 작은 팀 운영 환경에서는 신호 적중률을 과장하기 쉽고, 손실 관리 기준이 빠지기 쉽다.

MVP의 기본 출력은 다음 구조로 바꾼다.

```text
Decision Brief
- Action: 조건부 진입
- Conviction: MEDIUM
- Score: 67/100
- Timeframe: SWING
- Entry condition: 20일선 위에서 거래량 동반 돌파 시
- Invalidation: 종가 기준 50일선 이탈
- Risk/Reward: 대략 1 : 2.1
- Why now: ...
- What can go wrong: ...
```

이 방식은 사용자가 "사라"라는 결론만 받는 것이 아니라, **언제 들어가고, 언제 틀렸다고 인정하며, 어떤 리스크를 감수하는지**를 함께 보게 한다.

### 2.3 성공 기준

- 사용자가 `analyze <ticker>`를 입력하면 종목 브리핑을 받는다.
- 결과는 단순 신호가 아니라 진입/관망/축소 판단에 필요한 근거를 포함한다.
- 데이터 일부가 실패해도 결과는 안전하게 degrade 된다.
- 데이터 품질이 낮으면 `LOW` 확신도 또는 `HOLD_MONITOR`/`AVOID`로 제한된다.
- 코드 기반 지표와 LLM 설명이 분리되어 재현 가능하다.

---

## 3. 핵심 사용자

### 3.1 1차 사용자

- 소규모 투자팀 또는 1~3인 운영팀
- 관심 종목을 직접 입력해 빠르게 판단하고 싶은 사용자
- 자동매매보다 의사결정 보조 리포트를 먼저 원하는 사용자

### 3.2 사용자 상황

- 장중 또는 장 마감 후 특정 종목을 검토한다.
- 매수 후보를 찾기보다, 이미 관심 있는 종목의 현재 상태를 확인한다.
- 긴 리서치 리포트보다 1분 안에 읽을 수 있는 판단 요약을 원한다.

---

## 4. 범위

### 4.1 Slack 명령

필수 명령:

```text
analyze <ticker>
```

허용 alias:

```text
signal <ticker>
brief <ticker>
분석 <ticker>
시그널 <ticker>
```

입력 규칙:

- 명령어는 대소문자 무시.
- ticker는 대문자로 정규화.
- 기본 ticker 패턴은 `^[A-Z][A-Z0-9.\-]{0,9}$`.
- MVP는 미국 상장 주식과 ETF를 우선 지원한다.
- ticker 외 추가 문장은 MVP에서 무시하지 않고 validation error로 처리한다.

### 4.2 분석 대상

MVP 필수:

- 미국 상장 보통주
- 미국 상장 ETF

MVP 제외:

- 한국 주식
- 암호화폐
- 선물/옵션
- 외환
- 레버리지/인버스 ETF
- 개별 옵션 전략

후속 확장을 위해 내부 모델에는 `asset_type`, `exchange`, `currency` 필드를 둔다.

### 4.3 데이터 소스

작은 팀 운영 기준에서는 데이터 소스를 과하게 늘리지 않는다.

MVP 권장:

- 가격/거래량: `yfinance` 또는 저비용 market data provider
- 뉴스: RSS 또는 저비용 news provider
- 실적/공시: provider에서 가능한 범위, 없으면 명확한 결측 표시
- 기준 금리/시장 지수: `SPY`, `QQQ`, `VIX` 대체 지표를 우선 사용

운영 권장:

- 가격 데이터 SLA가 필요해지면 Finnhub, Polygon, Alpha Vantage 중 하나로 교체 가능하게 provider interface를 둔다.
- provider 장애 시 stale data 또는 unavailable 상태를 명시한다.

### 4.4 분석 시간축

MVP는 사용자가 시간축을 지정하지 않으면 `SWING`으로 분석한다.

시간축 정의:

- `SHORT_TERM`: 1~5거래일
- `SWING`: 2~8주
- `POSITION`: 3~12개월

MVP 명령은 ticker만 받되, 내부 모델은 시간축 확장을 지원한다.

---

## 5. 의사결정 모델

### 5.1 최종 Action

`BUY / SELL / HOLD` 대신 다음 action을 사용한다.

| Action | 의미 | 사용 조건 |
|---|---|---|
| `ACTIONABLE_LONG` | 현재 조건에서 매수 검토 가능 | 추세, 모멘텀, 데이터 품질, 리스크/보상이 모두 양호 |
| `CONDITIONAL_LONG` | 조건 충족 시 진입 검토 | 가격 돌파, 되돌림, 거래량 확인 등 추가 조건 필요 |
| `HOLD_MONITOR` | 관망 또는 보유 유지 | 방향성은 있으나 진입 매력 부족 또는 확인 필요 |
| `REDUCE_RISK` | 보유 비중 축소 검토 | 추세 훼손, 변동성 확대, 이벤트 리스크 증가 |
| `AVOID` | 신규 진입 회피 | 데이터 불량, 하락 추세, 리스크/보상 불리 |

### 5.2 점수 구조

종합 점수는 0~100으로 산출한다.

권장 가중치:

- Trend: 25점
- Momentum: 20점
- Volume/Participation: 15점
- Volatility/Risk: 15점
- News/Event: 15점
- Market Regime: 10점

점수는 LLM이 만들지 않는다. Python 코드가 산출하고, LLM은 점수의 의미를 설명한다.

### 5.3 Confidence

확신도는 점수만으로 결정하지 않는다. 데이터 품질과 이벤트 리스크를 함께 반영한다.

- `HIGH`: 데이터 신선도 양호, 주요 소스 정상, 점수와 근거 일관
- `MEDIUM`: 일부 결측 또는 혼재 신호 존재
- `LOW`: 데이터 결측, 이벤트 임박, 변동성 과다, 뉴스 불확실성 존재

가드 규칙:

- 가격 데이터가 stale이면 `HIGH` 금지.
- 뉴스 또는 이벤트 데이터가 unavailable이면 `HIGH` 금지.
- 실적 발표 3거래일 이내면 `ACTIONABLE_LONG` 금지, 기본은 `CONDITIONAL_LONG` 이하.
- 20일 변동성이 임계값을 넘으면 확신도 한 단계 하향.

### 5.4 리스크/보상

MVP는 정밀한 목표가 예측보다 실용적인 기준을 쓴다.

필수 출력:

- reference price
- suggested entry zone 또는 조건
- invalidation level
- upside reference
- downside reference
- approximate risk/reward

계산 원칙:

- 지지/저항은 최근 swing high/low, 이동평균, 52주 위치를 조합한다.
- 목표가는 보수적 reference로 표시하고 확정 수익률처럼 표현하지 않는다.
- 손절/무효 조건은 숫자 또는 조건으로 명확히 둔다.

---

## 6. 지표 요구사항

### 6.1 가격/기술 지표

필수:

- last price
- previous close
- open, high, low
- volume
- average volume
- 20/50/200일 이동평균
- 20/60일 수익률
- 14일 RSI
- 20일 realized volatility
- volume ratio
- 52주 고점/저점 대비 위치

선택:

- MACD
- Bollinger Band position
- ATR
- relative strength vs SPY/QQQ

### 6.2 이벤트/뉴스 지표

필수:

- 최근 7일 뉴스 최대 10개
- 중복 제목/URL 제거
- source, published_at, title, url
- earnings date 또는 unavailable 상태
- 최근 실적/가이던스 이벤트 요약, 가능할 때

뉴스 해석:

- LLM은 뉴스 제목과 요약을 감성/이벤트 관점으로 분류한다.
- 뉴스가 없으면 "뉴스 없음"과 "수집 실패"를 구분한다.

### 6.3 시장 환경

MVP에서는 복잡한 regime model을 만들지 않는다.

필수 reference:

- SPY 20/60일 수익률
- QQQ 20/60일 수익률
- VIX 또는 대체 변동성 지표, 가능할 때

시장 환경이 불리하면 개별 종목 점수의 action을 한 단계 보수적으로 조정한다.

---

## 7. 출력 포맷

### 7.1 Slack 응답 예시

```text
AAPL Decision Brief

Action: CONDITIONAL_LONG
Conviction: MEDIUM
Score: 67/100
Timeframe: SWING
Data time: 2026-05-08 09:30 ET

Entry condition
- 20일선 위에서 거래량이 평균 대비 1.3배 이상 동반될 때 진입 검토

Invalidation
- 종가 기준 50일선 이탈 시 이 시나리오 폐기

Risk / Reward
- Downside reference: -4.8%
- Upside reference: +10.1%
- Approx R/R: 1 : 2.1

Why
- 20/50/200일선 배열이 우상향
- RSI는 과열 직전이나 아직 극단값은 아님
- 최근 뉴스는 제품 수요와 마진 개선 쪽으로 중립~긍정

Risks
- 실적 발표가 6거래일 뒤 예정되어 변동성 확대 가능
- QQQ가 20일선 아래로 밀리면 개별 종목 신호도 약화

This is not an automated order.
```

### 7.2 금지 표현

아래 표현은 사용하지 않는다.

- "무조건 매수"
- "확실한 수익"
- "손실 가능성 없음"
- "지금 사야 한다"
- "자동으로 주문한다"

---

## 8. 데이터 모델

### 8.1 StockDecisionBrief

```python
class StockDecisionBrief:
    ticker: str
    asset_type: str
    action: str
    confidence: str
    score: int
    timeframe: str
    reference_price: float | None
    entry_condition: str
    invalidation: str
    upside_reference_pct: float | None
    downside_reference_pct: float | None
    risk_reward: float | None
    reasons: list[str]
    risks: list[str]
    data_quality: DataQuality
    generated_at: str
    disclaimer: str
```

### 8.2 ComponentScores

```python
class ComponentScores:
    trend: int
    momentum: int
    volume: int
    volatility_risk: int
    news_event: int
    market_regime: int
```

### 8.3 DataQuality

```python
class DataQuality:
    price: str        # fresh | stale | unavailable
    technicals: str   # complete | partial | unavailable
    news: str         # complete | partial | none | unavailable
    events: str       # complete | partial | unavailable
    generated_at: str
```

---

## 9. LLM 사용 원칙

### 9.1 LLM이 할 일

- 정규화된 데이터와 점수를 읽고 자연어로 해석한다.
- 상충되는 근거를 설명한다.
- 사용자가 이해하기 쉬운 브리핑으로 압축한다.
- 뉴스와 이벤트의 의미를 요약한다.

### 9.2 LLM이 하지 않을 일

- 이동평균, RSI, 변동성, 점수를 직접 계산하지 않는다.
- 가격 목표를 임의로 창작하지 않는다.
- 데이터가 없는데 있는 것처럼 표현하지 않는다.
- 주문 실행 또는 포지션 사이징을 지시하지 않는다.

### 9.3 Prompt 요구사항

System prompt는 다음 원칙을 포함해야 한다.

- You are an investment decision-support analyst, not an order execution agent.
- Use only provided data.
- Do not invent missing data.
- Explain uncertainty explicitly.
- If data quality is weak, reduce conviction.
- Never imply guaranteed return.

Claude 응답은 구조화된 JSON으로 받고, 렌더링은 코드가 담당한다.

---

## 10. 규칙 기반 가드

필수 가드:

- 가격 데이터 unavailable이면 분석 실패 응답.
- 가격 데이터 stale이면 `HIGH` 금지.
- 뉴스 unavailable이면 `HIGH` 금지.
- 실적 발표 3거래일 이내면 `ACTIONABLE_LONG` 금지.
- 변동성 임계값 초과 시 confidence 한 단계 하향.
- 종합 점수 40 미만이면 `ACTIONABLE_LONG`/`CONDITIONAL_LONG` 금지.
- 종합 점수 70 미만이면 `HIGH` 금지.
- 리스크/보상 1.5 미만이면 `ACTIONABLE_LONG` 금지.

가드는 LLM 응답 이후에도 재검증한다.

---

## 11. 작은 팀 운영 가이드

### 11.1 운영 방식

MVP는 수동 요청 기반으로 시작한다.

- 사용자가 필요할 때 Slack DM으로 요청한다.
- 서버는 24시간 구동하되, 예약 분석은 후속으로 둔다.
- 1회 분석은 최대 5분 이내 완료한다.
- 동일 ticker 반복 요청은 10분 캐시한다.

### 11.2 비용 제한

초기 비용 상한:

- Infra: 월 $10~$30
- LLM/API: 월 $20~$80
- 1일 분석 횟수 제한: 기본 50회
- ticker별 캐시 TTL: 10분

비용 초과 시:

- 신규 분석은 제한한다.
- 캐시된 최신 분석을 반환한다.
- Slack 응답에 "cached result"를 표시한다.

### 11.3 관측성

필수 로그:

- command_received
- data_fetch_started / data_fetch_done / data_fetch_failed
- score_calculated
- llm_invoked
- guard_applied
- response_sent

필수 메트릭:

- 분석 성공률
- provider 실패율
- 평균 분석 시간
- LLM 호출 비용
- 캐시 hit rate
- action 분포

### 11.4 운영 리스크

- 데이터 지연으로 잘못된 결론을 낼 수 있다.
- 뉴스 감성 해석은 과적합될 수 있다.
- 장중 급변 시 Slack 리포트가 빠르게 stale해질 수 있다.
- 작은 팀은 실시간 자동매매보다 의사결정 보조에 집중해야 한다.

---

## 12. 수용 기준

### AC-1. Slack 명령 파싱

- `analyze AAPL`, `signal aapl`, `분석 AAPL`이 정상 파싱된다.
- ticker는 `AAPL`로 정규화된다.
- ticker가 없으면 사용법을 반환한다.

### AC-2. 가격 데이터 수집

- 지원 ticker에 대해 가격, 거래량, 기준 시각을 수집한다.
- 실패 시 명확한 오류와 함께 분석을 중단한다.

### AC-3. 기술 지표 계산

- Python 코드가 20/50/200일 이동평균, RSI, 수익률, 변동성, 거래량 비율을 계산한다.
- LLM prompt에는 계산 결과만 전달된다.

### AC-4. 뉴스/이벤트 수집

- 최근 7일 뉴스 최대 10개를 수집한다.
- 뉴스 없음과 수집 실패를 구분한다.
- 실적 이벤트가 없거나 수집 실패하면 data_quality에 표시한다.

### AC-5. 점수 산출

- component score와 total score가 코드에서 계산된다.
- total score는 0~100 범위를 벗어나지 않는다.

### AC-6. Action 결정

- action은 점수와 가드 결과를 조합해 결정된다.
- 가드가 action을 낮춘 경우 응답에 그 사유가 포함된다.

### AC-7. LLM 응답

- LLM은 제공된 데이터만 사용한다.
- 결측 데이터는 명시한다.
- 응답은 JSON schema로 파싱 가능해야 한다.

### AC-8. Slack 렌더링

- 응답은 1분 안에 읽을 수 있는 브리핑 형태다.
- action, confidence, score, entry condition, invalidation, risks가 포함된다.

### AC-9. 데이터 품질 가드

- stale/unavailable 데이터가 있으면 confidence가 제한된다.
- 제한 사유가 응답에 표시된다.

### AC-10. 테스트

- ticker parser 단위 테스트
- technical indicator 계산 테스트
- scoring 테스트
- guardrail 테스트
- Slack renderer 테스트
- provider 실패 fallback 테스트

---

## 13. 단계별 구현 계획

### Phase 1. PRD 확정

- 본 PRD를 기획 기준으로 확정한다.
- 기존 `BUY/SELL/HOLD` 중심 표현을 `Decision Brief` 중심으로 교체한다.

### Phase 2. 도메인 모델

- `StockDecisionBrief`
- `ComponentScores`
- `DataQuality`
- `MarketSnapshot`
- `TechnicalSnapshot`
- `NewsSnapshot`

### Phase 3. 데이터 provider

- 가격 provider interface
- 뉴스 provider interface
- 이벤트 provider interface
- mock provider와 실제 provider 분리

### Phase 4. 지표 계산

- 이동평균
- RSI
- 수익률
- 변동성
- 거래량 비율
- 52주 위치

### Phase 5. 점수 및 가드

- component score 계산
- total score 계산
- action mapping
- guardrail 재검증

### Phase 6. LLM 요약

- prompt builder
- JSON schema parser
- LLM 실패 fallback

### Phase 7. Slack 연결

- `analyze <ticker>` 명령 연결
- Slack renderer
- 캐시 표시

### Phase 8. 운영 검증

- 로컬 E2E
- provider 실패 테스트
- 비용 제한 테스트
- 로그 확인

---

## 14. 비범위

- 자동 주문
- 브로커 API 연동
- 포트폴리오 최적화
- 실시간 tick streaming
- 초단타 신호
- 한국 주식 지원
- options strategy
- 사용자별 세금/계좌 상황 반영
- VaR 기반 기관급 리스크 엔진
- 웹 대시보드

---

## 15. 다음 작업 후보

1. 본 PRD 기준으로 `ai/stock_signal/` 패키지 구조 설계
2. mock data 기반 `StockDecisionBrief` 생성 테스트 작성
3. `analyze <ticker>` Slack command parser 구현
4. `yfinance` provider proof-of-concept 작성
5. scoring/guardrail을 LLM 없이 먼저 완성
