# PRD: ai-signal-workbench

- **slug**: `ai-signal-workbench`
- **작성일**: 2026-05-10
- **작성 역할**: PM / AI Product Planner
- **기획 모델 기준**: `gpt-5.5`
- **제품 방향**: 화이트리스트 기반 종목 검색, 목표 자본/수익률/기간 기반 AI 매수·매도 의사결정 워크벤치
- **대상 디렉터리**: `ai/`, 신규 `backend/`, 신규 `frontend/`, `infrastructure/`, `docs/design/`
- **UI 포함 여부**: Yes
- **전제**: 기존 `stock-signal-mvp`의 Decision Brief, 기술 지표, 점수/가드 철학을 확장한다.
- **초기 화이트리스트**: Apple(`AAPL`), Bitcoin(`BTC-USD`, alias `BTC`)

---

## 1. 배경 / 문제

현재 시스템은 Slack 중심으로 `analyze <ticker>` 요청에 대해 기술적 지표 기반 Decision Brief를 만드는 MVP에 가깝다. 사용자가 원하는 다음 단계는 단순 종목 브리핑이 아니라, 실제 의사결정 흐름 전체를 지원하는 웹 기반 분석 워크벤치다.

사용자는 다음 질문에 답을 원한다.

- 내가 입력한 종목이 분석 가능한 승인 종목인가?
- 지금 조회 시점 기준으로 매수, 매도, 관망 중 무엇이 합리적인가?
- 당일, 1주, 1달, 3달, 6달, 1년 기준으로 추세와 리스크가 어떻게 다른가?
- 내 투입 자본금, 목표 수익률, 달성 기간이 현실적인가?
- 실제 매수/매도한 뒤 현재 상태를 반영하면 다음 분석은 어떻게 바뀌는가?
- 당일 매도 시 익절/손절 기준과 포지션 규모는 어떻게 잡아야 하는가?

중요 원칙:

- 시스템은 투자 조언을 확정적으로 제공하지 않는다. 출력은 의사결정 보조다.
- LLM은 데이터 해석과 설명을 담당하고, 가격/지표/리스크 계산은 코드가 담당한다.
- 화이트리스트에 없는 종목은 분석하지 않는다.
- 사용자의 실제 매매 입력은 주문 실행이 아니라 포지션 상태 업데이트로만 처리한다.
- 터무니없는 목표 수익률/기간은 "현실성 낮음"으로 분류하고 대체 시나리오를 제안한다.

---

## 2. 목표

### 2.1 제품 목표

웹 화면에서 사용자가 종목, 투입 자본금, 목표 수익률, 목표 기간을 입력하면 최초 입력일을 기준으로 분석 메타데이터가 생성된다. 시스템은 가격, 거래량, 뉴스, 기업 정보, 재무제표, 수급/거래 현황, 시장 환경을 결합해 다음을 제공한다.

- 종목 검색 및 화이트리스트 검증
- 다중 기간 분석: 기준일, 1주, 1달, 3달, 6달, 1년
- 액션: `ACTIONABLE_BUY`, `CONDITIONAL_BUY`, `HOLD`, `PARTIAL_SELL`, `SELL`, `AVOID`
- 확신도: `LOW`, `MEDIUM`, `HIGH`
- 목표 현실성: `REALISTIC`, `STRETCHED`, `UNREALISTIC`
- 권장 매수 금액 또는 비중
- 당일 익절가, 손절가, 무효 조건
- 실제 매수/매도 입력 후 포지션 상태 업데이트
- 다음날 또는 수동 분석 버튼을 통한 재분석
- 데이터 품질, 결측, stale 여부 표시

### 2.2 성공 기준

- 화이트리스트 종목 검색 시 10초 이내에 분석 화면이 열린다.
- 최초 분석은 60초 이내 완료된다. 외부 데이터 지연 시 부분 결과와 재시도 상태를 표시한다.
- 사용자가 실제 거래를 입력하면 평균단가, 보유수량, 실현/미실현 손익, 남은 자본이 갱신된다.
- 재분석은 기존 분석 메타데이터와 포지션 이력을 참조해 전일 대비 변화와 다음 액션을 제안한다.
- LLM 응답은 JSON schema로 검증 가능하며, 코드 가드가 최종 액션을 재검증한다.

---

## 3. 핵심 사용자

- 개인 투자자 또는 소규모 투자팀
- 관심 종목 리스트를 제한적으로 관리하고 싶은 사용자
- 자동매매보다 "AI 분석 + 사람이 최종 결정" 흐름을 원하는 사용자
- 매매 일지를 남기고 다음날 판단을 이어가고 싶은 사용자

---

## 4. 범위

### 4.1 In Scope

- 화이트리스트 종목 관리
- 종목 검색 화면
- 투자 입력 폼: 종목, 투입 자본금, 목표 수익률, 목표 기간
- 최초 분석 메타데이터 생성
- 다중 기간 기술/가격 분석
- 뉴스, 이벤트, 기업 상세, 재무제표, 수급/거래 현황 수집 인터페이스
- AI 기반 종합 해석
- 현실성 평가
- 매수/매도/관망 시그널
- 권장 포지션 사이징
- 당일 익절/손절 기준
- 실제 매수/매도 입력
- 포지션 상태 업데이트
- 수동 재분석 버튼
- 캐싱, 비용 추적, 토큰 최적화
- API key 설정 가이드

### 4.2 Out Of Scope

- 증권사 API를 통한 실제 주문 실행
- 완전 자동매매
- 옵션/선물/마진/레버리지 전략
- 초단타 체결 알고리즘
- 법적 투자 자문 문구
- 화이트리스트 자동 확장
- 사용자의 브로커 계좌 직접 연동

---

## 5. 사용자 플로우

### 5.1 최초 분석

1. 사용자가 검색창에 ticker 또는 종목명을 입력한다.
2. 시스템이 화이트리스트를 조회한다.
3. 화이트리스트에 없으면 "지원하지 않는 종목"을 표시하고 분석하지 않는다.
4. 화이트리스트에 있으면 투자 입력 폼을 표시한다.
5. 사용자가 투입 자본금, 목표 수익률, 목표 기간을 입력한다.
6. 시스템이 `analysis_case`를 생성하고 기준일을 저장한다.
7. 가격/뉴스/기업/재무/수급/시장 데이터를 수집한다.
8. 코드가 지표, 점수, 리스크, 현실성, 포지션 사이징을 계산한다.
9. LLM이 정규화된 데이터만 읽고 해석 리포트를 생성한다.
10. 화면에 종합 결과와 기간별 분석을 표시한다.

### 5.2 실제 거래 입력

1. 사용자가 "매수 기록" 또는 "매도 기록"을 선택한다.
2. 거래일, 수량, 단가, 수수료, 메모를 입력한다.
3. 시스템이 포지션 상태를 갱신한다.
4. 기존 분석과 실제 실행 결과가 연결된다.
5. 다음 재분석에서 보유 상태 기준의 액션을 산출한다.

### 5.3 재분석

1. 사용자가 분석 버튼을 누르거나 예약 작업이 실행된다.
2. 시스템은 이전 분석, 포지션, 시장 변화, 최신 뉴스/재무/가격을 비교한다.
3. 전일 대비 변경점, 액션 변경 사유, 유지/축소/추가매수 조건을 표시한다.

---

## 6. 기능 요구사항

### 6.1 화이트리스트

필드:

- `ticker`
- `name`
- `asset_type`: `US_EQUITY`, `US_ETF`, `CRYPTO`, future 확장
- `exchange`
- `currency`
- `sector`
- `enabled`
- `risk_tier`: `LOW`, `MEDIUM`, `HIGH`, `SPECULATIVE`
- `notes`
- `created_at`, `updated_at`

규칙:

- `enabled=false` 종목은 검색 결과에는 표시할 수 있으나 분석 버튼은 비활성화한다.
- ticker alias를 지원한다. 예: `BRK.B`, `BRK-B` 정규화.
- 초기 버전은 관리자 seed 파일 또는 DB migration으로 관리한다.
- 최초 구현은 Apple(`AAPL`)과 Bitcoin(`BTC-USD`)만 seed로 둔다.

### 6.2 분석 입력

필수 입력:

- ticker
- capital_amount
- target_return_pct
- target_period_days

선택 입력:

- risk_preference: `CONSERVATIVE`, `BALANCED`, `AGGRESSIVE`
- max_loss_pct
- notes

검증:

- 자본금은 0보다 커야 한다.
- 목표 수익률은 음수 불가.
- 기간은 1일 이상이어야 한다.
- 연환산 목표 수익률이 비정상적으로 높으면 `UNREALISTIC`으로 분류한다.

현실성 판단 기본값:

- 연환산 목표 수익률 25% 이하: `REALISTIC`
- 25% 초과 80% 이하: `STRETCHED`
- 80% 초과: `UNREALISTIC`
- 단, 종목 변동성, ATR, 최근 추세, 이벤트 리스크에 따라 한 단계 상향/하향 가능하다.

### 6.3 기준일 규칙

- 정규장 중 또는 장 마감 후 최신 거래일 데이터가 있으면 당일을 기준으로 한다.
- 개장 전이고 당일 OHLCV가 없으면 직전 거래일을 기준으로 한다.
- 기준 시각, 데이터 시각, 장 상태를 모두 저장한다.
- stale 데이터이면 `HIGH` 확신도와 공격적 매수 제안을 금지한다.

### 6.4 기간별 분석

필수 기간:

- 기준일 또는 직전 거래일
- 1주
- 1달
- 3달
- 6달
- 1년

각 기간 산출:

- 시작가/종가/고가/저가
- 수익률
- 변동성
- 최대 낙폭
- 거래량 변화
- SPY/QQQ 대비 상대강도
- 주요 뉴스/이벤트 수
- 기간별 방향성: `BULLISH`, `NEUTRAL`, `BEARISH`

### 6.5 가격/기술 지표

필수:

- last price, previous close, open/high/low
- volume, average volume, volume ratio
- 20/50/200일 이동평균
- RSI 14
- ATR 14
- 20일 realized volatility
- 52주 고점/저점
- MACD
- Bollinger Band position
- relative strength vs SPY/QQQ

### 6.6 뉴스/이벤트/기업 데이터

필수:

- 최근 7일 뉴스 최대 20개
- 최근 30일 주요 뉴스 요약
- 중복 제목/URL 제거
- source, published_at, title, url, summary
- 실적 발표일, 최근 실적 결과, 가이던스
- 기업 개요, 산업, 시가총액, 주요 재무 지표

재무 지표:

- 매출 성장률
- 영업이익률
- 순이익률
- EPS 성장
- 부채비율
- ROE 또는 ROIC
- FCF 가능 시
- valuation: PER/PBR/PSR/EV/EBITDA 가능 시

수급/거래 현황:

- 기관/내부자/공매도 데이터는 provider 가용성에 따라 optional로 시작한다.
- 데이터가 없으면 결측으로 표시하고 LLM이 추정하지 못하게 한다.

### 6.7 AI 종합 판단

LLM 입력은 정규화된 JSON만 사용한다.

LLM이 할 일:

- 기간별 신호를 종합한다.
- 뉴스/이벤트/재무 맥락을 설명한다.
- 목표 수익률/기간의 현실성을 설명한다.
- 매수/매도/관망 시나리오를 자연어로 정리한다.
- 상충 신호를 명시한다.

LLM이 하지 않을 일:

- 없는 데이터를 만들어내지 않는다.
- 코드 계산값을 임의 수정하지 않는다.
- 확정 수익을 약속하지 않는다.
- 주문 실행을 지시하지 않는다.

### 6.8 최종 액션

액션 enum:

- `ACTIONABLE_BUY`: 현재 조건에서 분할 매수 검토 가능
- `CONDITIONAL_BUY`: 조건 충족 시 매수 검토
- `HOLD`: 관망 또는 보유 유지
- `PARTIAL_SELL`: 일부 익절/리스크 축소 검토
- `SELL`: 보유 중이면 매도 검토
- `AVOID`: 신규 진입 회피

포지션이 없을 때:

- `ACTIONABLE_BUY`, `CONDITIONAL_BUY`, `HOLD`, `AVOID` 중심

포지션이 있을 때:

- `HOLD`, `PARTIAL_SELL`, `SELL`, `CONDITIONAL_BUY` 중심

### 6.9 권장 매수 금액과 리스크 관리

포지션 사이징은 코드가 계산한다.

입력:

- 사용자 자본금
- 최대 허용 손실률
- ATR
- 손절 기준
- 종목 risk tier
- 목표 기간

출력:

- suggested_buy_amount
- suggested_share_qty
- entry_zone
- take_profit_price_for_day
- stop_loss_price_for_day
- invalidation_condition
- expected_loss_if_stopped
- expected_gain_if_take_profit
- risk_reward_ratio

기본 가드:

- 1회 거래의 예상 손실은 총 자본의 1~2%를 기본 상한으로 한다.
- `SPECULATIVE` 종목은 권장 금액을 자동 축소한다.
- `UNREALISTIC` 목표면 공격적 매수 액션 금지.
- 실적 발표 3거래일 이내면 `ACTIONABLE_BUY` 금지.

---

## 7. UX/UI 요구사항

### 7.1 페이지

- `/signals`: 검색 및 최근 분석 리스트
- `/signals/new`: 신규 분석 입력
- `/signals/{case_id}`: 분석 상세
- `/positions/{position_id}`: 포지션 상세 및 거래 입력
- `/admin/whitelist`: 화이트리스트 관리

### 7.2 분석 상세 화면

상단:

- ticker, 종목명, 현재가, 기준일, 장 상태
- 최종 액션, 확신도, 종합 점수
- 데이터 품질 배지

핵심 카드:

- 투자 목표 현실성
- 권장 매수 금액/비중
- 당일 익절가/손절가
- 무효 조건
- 주요 근거 3~5개
- 주요 리스크 3~5개

탭:

- Overview
- Time Horizons
- News & Events
- Fundamentals
- Position
- Audit

주의:

- 분석 기능 설명을 화면에 장황하게 노출하지 않는다.
- 사용자가 바로 판단할 수 있도록 밀도 있는 대시보드 형태로 만든다.
- 법적 고지는 하단 또는 결과 영역에 짧게 표시한다.

---

## 8. 백엔드/API 요구사항

### 8.1 엔드포인트

- `GET /api/whitelist/search?q=`
- `GET /api/whitelist/{ticker}`
- `POST /api/analysis-cases`
- `GET /api/analysis-cases/{case_id}`
- `POST /api/analysis-cases/{case_id}/run`
- `GET /api/analysis-cases/{case_id}/runs`
- `POST /api/positions/{case_id}/trades`
- `GET /api/positions/{position_id}`
- `GET /api/provider-health`

### 8.2 주요 테이블

- `stock_whitelist`
- `analysis_cases`
- `analysis_runs`
- `analysis_inputs`
- `market_snapshots`
- `news_snapshots`
- `fundamental_snapshots`
- `llm_reports`
- `positions`
- `trades`
- `provider_cache`
- `cost_events`

### 8.3 분석 실행 상태

- `PENDING`
- `FETCHING_DATA`
- `SCORING`
- `LLM_ANALYZING`
- `GUARD_APPLYING`
- `COMPLETED`
- `PARTIAL`
- `FAILED`

---

## 9. AI/API 설계

### 9.1 OpenAI 사용

OpenAI는 Responses API를 기본으로 검토한다. 공식 문서 기준으로 Responses API는 텍스트/이미지 입력, 텍스트/JSON 출력, 도구 호출, 상태 기반 상호작용을 지원한다.

모델:

- 기획/고난도 종합 판단: `gpt-5.5`
- 운영 비용 최적화 후보: `gpt-5.4-mini` 또는 더 작은 모델을 뉴스 분류/요약에 분리 적용
- 사용자가 지정한 기획 모델은 `gpt-5.5`로 고정하되, 프로덕션은 비용 상한 때문에 라우팅을 둔다.

Structured Outputs:

- LLM 응답은 JSON Schema 기반 structured output으로 받는다.
- Python에서는 Pydantic 모델과 schema를 단일 소스로 둔다.
- schema validation 실패 시 재시도 1회, 실패하면 LLM 해석 없이 코드 산출 브리핑만 표시한다.

API key 전달 방식:

- key 값을 채팅에 직접 붙여넣지 않는다.
- 로컬에서는 `.env.local`에 `OPENAI_API_KEY=...`로 저장한다.
- 서버/배포 환경에서는 Secret Manager 또는 CI/CD secret으로 주입한다.
- `.env.example`에는 placeholder만 추가한다.
- OpenAI SDK는 일반적으로 `OPENAI_API_KEY` 환경변수를 자동으로 읽는 방식으로 구성한다.

### 9.2 Prompt 구조

System prompt:

- 역할: 투자 의사결정 보조 애널리스트
- 제공된 데이터만 사용
- 결측 데이터 추정 금지
- 확실한 수익 표현 금지
- 목표 수익률/기간의 현실성 평가
- 액션이 코드 가드와 충돌하면 코드 가드를 우선

User payload:

- analysis_case
- whitelist metadata
- price/technical snapshots
- horizon summaries
- news/event summaries
- fundamentals
- position state
- risk calculations
- guard results

Output schema:

- executive_summary
- action_interpretation
- target_feasibility_reasoning
- buy_plan
- sell_plan
- hold_plan
- risks
- missing_data_warnings
- next_review_triggers

---

## 10. 캐싱 및 토큰 최적화

### 10.1 데이터 캐시

권장 TTL:

- whitelist: 24시간
- ticker profile/fundamentals: 24시간
- financial statements: 24시간~7일
- daily OHLCV: 장중 1~5분, 장마감 후 24시간
- news search: 30~60분
- news article summary: URL hash 기준 7일
- market regime: 5~15분
- completed analysis run: 동일 입력/동일 데이터 hash 기준 10분

### 10.2 LLM 토큰 절감

- 원문 뉴스 전체를 매번 넣지 않고 사전 요약본만 넣는다.
- 오래된 재무제표는 hash 기반으로 snapshot id만 재사용하고, 변경 시에만 다시 넣는다.
- 기간별 가격 데이터는 원시 캔들 전체가 아니라 계산된 feature만 전달한다.
- system prompt는 버전 관리하고 가능한 캐시 가능한 블록으로 유지한다.
- 뉴스 분류, 재무 요약, 최종 판단을 분리해 저비용 모델과 고성능 모델을 라우팅한다.
- 동일 case 재분석 시 이전 분석 전체가 아니라 delta만 전달한다.
- `cost_events`에 input/output token, cached token, provider, model, case_id를 기록한다.

### 10.3 캐시 무효화

- 새로운 거래 입력 발생 시 position 관련 분석 캐시는 무효화한다.
- 화이트리스트 risk tier 변경 시 해당 ticker 분석 캐시는 무효화한다.
- provider 데이터가 stale에서 fresh로 바뀌면 재분석 가능 상태로 표시한다.
- 실적 발표일 당일과 다음 거래일은 뉴스/이벤트 캐시 TTL을 짧게 둔다.

---

## 11. 인프라/운영

초기 권장:

- Frontend: `trading-signal-frontend` 저장소의 Next.js 앱
- Backend API: FastAPI 기반 bypass API
- DB: PostgreSQL
- Cache/Queue: Redis
- Worker: Python background worker 또는 Celery/RQ
- Deployment: Docker Compose on EC2/Lightsail
- Observability: structured logs + Prometheus/Grafana 후속

비용 관리:

- 일 분석 횟수 상한
- 사용자별 rate limit
- 종목별 캐시 TTL
- LLM 월 예산 상한
- provider별 장애율 모니터링

장애 대응:

- 가격 데이터 실패: 분석 실패 또는 stale 명시
- 뉴스 실패: 기술/재무 중심 PARTIAL 분석
- LLM 실패: 코드 산출 brief만 반환
- DB 실패: 신규 분석 생성 중단
- Redis 실패: 캐시 없이 제한 운영

---

## 12. 수용 기준

### AC-1. 화이트리스트 검색

- 화이트리스트에 있는 ticker는 검색 결과에 표시된다.
- 화이트리스트에 없는 ticker는 분석 생성이 차단된다.
- 비활성 ticker는 분석 버튼이 비활성화된다.

### AC-2. 최초 분석 생성

- 사용자가 ticker, 자본금, 목표 수익률, 목표 기간을 입력하면 `analysis_case`가 생성된다.
- 최초 입력일과 기준 거래일이 저장된다.
- 개장 전 데이터가 없으면 직전 거래일 기준으로 분석한다.

### AC-3. 기간별 분석

- 기준일, 1주, 1달, 3달, 6달, 1년 horizon summary가 생성된다.
- 각 horizon은 수익률, 변동성, 최대 낙폭, 상대강도를 포함한다.

### AC-4. 목표 현실성 평가

- 터무니없는 목표 수익률/기간 조합은 `UNREALISTIC`으로 표시된다.
- `UNREALISTIC`이면 공격적 매수 액션이 금지된다.
- UI는 대체 목표 기간 또는 목표 수익률을 제안한다.

### AC-5. AI 분석

- LLM은 structured output schema를 만족해야 한다.
- 결측 데이터는 missing_data_warnings에 포함된다.
- LLM이 코드 계산값과 다른 가격/수량을 만들면 응답은 폐기된다.

### AC-6. 매수/매도 기록

- 사용자는 실제 매수/매도 내역을 입력할 수 있다.
- 포지션 평균단가, 수량, 실현/미실현 손익이 갱신된다.
- 다음 분석은 포지션 상태를 반영한다.

### AC-7. 재분석

- 사용자가 분석 버튼을 누르면 새로운 `analysis_run`이 생성된다.
- 이전 run 대비 액션 변경 사유가 표시된다.
- 최신 데이터 실패 시 PARTIAL 또는 FAILED 상태가 명확히 표시된다.

### AC-8. 리스크 관리

- 권장 매수 금액은 최대 손실 상한과 손절 기준을 기반으로 계산된다.
- 익절가, 손절가, 무효 조건이 모두 표시된다.
- 데이터 stale이면 `HIGH` confidence가 금지된다.

### AC-9. 비용/캐시

- 동일 ticker/동일 입력/동일 데이터 hash 분석은 10분 내 캐시를 사용할 수 있다.
- LLM 호출 비용은 case_id 단위로 기록된다.
- 월 예산 초과 시 신규 LLM 분석 대신 코드 산출 brief 또는 캐시 결과를 반환한다.

### AC-10. 보안

- API key는 저장소에 커밋되지 않는다.
- `.env.local` 또는 secret manager에서만 읽는다.
- 사용자 입력은 서버에서 재검증한다.

---

## 13. QA 체크리스트

- 화이트리스트 정규화 테스트
- 비지원 종목 차단 테스트
- 개장 전 기준일 fallback 테스트
- 목표 현실성 평가 테스트
- 기간별 feature 계산 테스트
- 포지션 평균단가/손익 계산 테스트
- LLM schema validation 실패 fallback 테스트
- provider timeout 테스트
- 캐시 hit/miss 테스트
- 비용 상한 초과 테스트
- stale 데이터 confidence 제한 테스트
- 실적 발표 임박 action downgrade 테스트

---

## 14. 보안/컴플라이언스

- 결과 화면에 "투자 판단 보조이며 자동 주문/투자 자문이 아님"을 표시한다.
- 확정 수익, 무조건 매수, 손실 없음 표현을 금지한다.
- provider license와 데이터 재배포 조건을 확인한다.
- API key는 `.env.local`, secret manager, CI secret 이외 경로로 저장하지 않는다.
- 분석 결과와 거래 기록은 사용자 식별 정보와 분리 가능한 구조로 설계한다.

---

## 15. 개발 단계 제안

### Phase 1. 웹 기반 분석 케이스

- whitelist DB
- search page
- analysis case create
- 기존 기술 지표 엔진 확장
- horizon summary
- 결과 상세 화면 skeleton

### Phase 2. 포지션/거래 기록

- trades/positions model
- 매수/매도 입력 UI
- 평균단가/손익 계산
- 포지션 기반 재분석

### Phase 3. 뉴스/재무/AI

- provider interface
- 뉴스/재무 snapshot
- OpenAI Responses API adapter
- structured output validation
- token/cost tracking

### Phase 4. 운영 안정화

- Redis cache
- background worker
- provider health
- budget guard
- scheduled daily reanalysis

---

## 16. 현재 프로젝트 적용성 분석

### 16.1 바로 적용 가능한 영역

현재 저장소에는 `ai/stock_signal` 패키지와 `ai/llm` 공통 유틸이 이미 존재한다. 따라서 개발자는 처음부터 전체 웹/백엔드/인프라를 만들기보다, 기존 분석 엔진을 확장해 "API가 반환할 수 있는 분석 결과 모델"을 먼저 안정화해야 한다.

즉시 재사용:

- `ai/stock_signal/models.py`: `Action`, `Confidence`, `Timeframe`, `StockDecisionBrief`, `ComponentScores`, `DataQuality`
- `ai/stock_signal/engine.py`: 가격 데이터 기반 score, action, confidence, risk/reward 산출
- `ai/stock_signal/indicators.py`: 이동평균, RSI, 변동성, ATR 등 기술 지표 계산
- `ai/stock_signal/providers.py`: Yahoo chart provider, synthetic fallback
- `ai/llm/cost_tracker.py`: LLM 비용 추적 개념
- `ai/llm/cache.py`: system prompt 캐싱 헬퍼 개념

바로 반영할 개발 범위:

- whitelist 모델과 ticker 정규화 함수
- horizon summary 계산
- target feasibility 계산
- position/trade 계산
- OpenAI Responses API adapter
- structured output schema
- LLM 실패 시 코드 산출 brief fallback

### 16.2 지금 프로젝트에 맞춰 축소해야 할 영역

초기 구현에서 PostgreSQL, Redis, Next.js, 배포 인프라를 동시에 도입하면 범위가 커진다. 현재 저장소는 Python 분석 엔진 중심이므로 첫 개발 PR은 DB/웹 전체가 아니라 "분석 도메인 모델 + API-ready service"를 목표로 한다.

초기 축소안:

- whitelist는 DB 대신 YAML/JSON seed 파일 또는 Python 상수로 시작
- position/trade는 영속 DB 대신 dataclass/service 테스트부터 시작
- news/fundamentals provider는 interface와 mock/stub 우선
- Redis cache는 후속으로 두고, 우선 in-memory TTL 또는 deterministic cache key만 정의
- frontend는 Phase 1 분석 API가 안정화된 뒤 별도 PRD/design 산출물로 구현

### 16.3 이미 완료된 환경 반영

- `.env.local`에 `OPENAI_API_KEY`가 설정되어 있다.
- OpenAI Python SDK는 `openai>=2.36.0`으로 업데이트되어 `OpenAI().responses` 사용이 가능하다.
- `gpt-5.5` Responses API 최소 호출은 성공했다.
- 개발자는 `.env.local` 값을 커밋하지 말고, `.env.example`에는 placeholder만 추가해야 한다.

### 16.4 적용 우선순위

1. `ai/stock_signal` 도메인 확장
2. OpenAI adapter와 structured output validation
3. 분석 service orchestration
4. whitelist와 analysis input validation
5. position/trade state 계산
6. API endpoint 또는 CLI smoke path
7. frontend/dashboard
8. Redis/PostgreSQL/worker 인프라

---

## 17. 개발자 핸드오프

### 17.0 PM 검토 결과

사용자 확인용 MVP는 프론트엔드를 별도 저장소 `trading-signal-frontend`로 분리한다. 엔진 저장소는 FastAPI 기반 bypass API만 제공하고, 화면은 Next.js가 담당한다.

스펙 변경:

- Backend: `python -m ai.stock_signal.server`로 FastAPI 실행
- Frontend: `trading-signal-frontend` Next.js App Router
- API는 독립 비즈니스 로직을 갖지 않고 `analyze_workbench()`를 그대로 호출한다.
- 브라우저는 FastAPI를 직접 호출하지 않고 Next.js route handler를 호출한다.
- 지원 검색 대상은 Apple(`AAPL`)과 Bitcoin(`BTC`, `BTC-USD`)만 유지한다.
- DB/Redis/worker는 후속 PR로 미룬다.

### 17.1 첫 번째 개발 PR 범위

첫 PR은 `ai-signal-workbench-domain`으로 분리한다. UI와 DB는 제외하고, 기존 `ai/stock_signal`을 확장해 웹/API가 호출할 수 있는 분석 도메인 서비스를 만든다.

권장 변경 파일:

- `ai/stock_signal/models.py`
- `ai/stock_signal/engine.py`
- `ai/stock_signal/indicators.py`
- `ai/stock_signal/providers.py`
- 신규 `ai/stock_signal/whitelist.py`
- 신규 `ai/stock_signal/horizons.py`
- 신규 `ai/stock_signal/positions.py`
- 신규 `ai/stock_signal/feasibility.py`
- 신규 `ai/stock_signal/openai_adapter.py`
- 신규 테스트 `ai/tests/test_stock_signal_workbench.py`

### 17.2 구현 상세

개발자는 다음 순서로 구현한다.

1. `WhitelistEntry`, `AnalysisInput`, `AnalysisCase`, `AnalysisRun`, `HorizonSummary`, `PositionState`, `Trade`, `RiskPlan` dataclass를 추가한다.
2. whitelist lookup은 seed 기반으로 만들고, 비지원 ticker는 분석 전에 차단한다.
3. `build_horizon_summaries(bars)`에서 기준일, 1주, 1달, 3달, 6달, 1년 요약을 산출한다.
4. `evaluate_target_feasibility(input, technicals, whitelist_entry)`에서 `REALISTIC`, `STRETCHED`, `UNREALISTIC`을 산출한다.
5. `calculate_position_state(trades)`로 평균단가, 보유수량, 실현/미실현 손익을 계산한다.
6. `build_risk_plan(input, technicals, feasibility, risk_tier)`에서 권장 매수 금액, 수량, 익절가, 손절가, risk/reward를 산출한다.
7. OpenAI adapter는 `OPENAI_API_KEY` 환경변수를 사용하고, structured output schema validation 실패 시 코드 산출 결과만 반환한다.
8. LLM은 코드가 계산한 가격, 수량, 손절/익절 값을 변경할 수 없다.

### 17.3 첫 PR 수용 기준

- 화이트리스트에 없는 ticker 분석 요청은 명확한 validation error를 낸다.
- 화이트리스트 ticker는 기존 가격 provider로 분석 가능하다.
- horizon summary 6개가 생성된다.
- 비현실적 목표는 `UNREALISTIC`으로 분류된다.
- risk plan은 권장 매수 금액, 수량, 익절가, 손절가를 포함한다.
- trade list를 입력하면 position state가 계산된다.
- OpenAI 호출 실패 또는 quota 오류가 발생해도 코드 산출 brief는 반환된다.
- 신규 로직은 단위 테스트로 검증된다.

### 17.4 후속 PR 분리

- `ai-signal-workbench-api`: FastAPI endpoint와 request/response schema
- `ai-signal-workbench-ui`: `/signals` 화면과 분석 상세 대시보드
- `ai-signal-workbench-persistence`: PostgreSQL schema와 migration
- `ai-signal-workbench-cache`: Redis cache, provider cache, cost_events
- `ai-signal-workbench-news-fundamentals`: 뉴스/재무 provider 실제 연동

### 17.5 현재 구현된 호출 경로

현재 브랜치에서는 Apple과 Bitcoin에 대해 CLI 호출이 가능하다.

```bash
python -m ai.stock_signal.cli workbench AAPL --capital 10000 --target-return 8 --target-days 90
python -m ai.stock_signal.cli workbench BTC --capital 5000 --target-return 15 --target-days 180
```

네트워크 없이 deterministic 확인이 필요하면 `--offline`을 붙인다.

```bash
python -m ai.stock_signal.cli workbench AAPL --capital 10000 --target-return 8 --target-days 90 --offline
python -m ai.stock_signal.cli workbench BTC --capital 5000 --target-return 15 --target-days 180 --offline
```

### 17.6 현재 구현된 API/프론트 호출 경로

FastAPI 서버 실행:

```bash
make signal-workbench
```

또는:

```bash
python -m ai.stock_signal.server
```

프론트엔드 저장소:

```text
../trading-signal-frontend
```

화이트리스트 검색 API:

```bash
curl "http://127.0.0.1:8000/api/whitelist/search?q=AAPL"
curl "http://127.0.0.1:8000/api/whitelist/search?q=BTC"
```

분석 API:

```bash
curl -X POST "http://127.0.0.1:8000/api/workbench/analyze" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","capital_amount":10000,"target_return_pct":8,"target_period_days":90}'
```

현재 FastAPI는 별도 판단 로직 없이 `ai.stock_signal.workbench.analyze_workbench()`를 호출하는 bypass layer다.

---

## 18. 공식 문서 참고

- OpenAI Models: https://developers.openai.com/api/docs/models
- GPT-5.5 model: https://developers.openai.com/api/docs/models/gpt-5.5
- Responses API: https://platform.openai.com/docs/api-reference/responses
- OpenAI Quickstart / `OPENAI_API_KEY`: https://platform.openai.com/docs/quickstart
- Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs

---

## 19. 1차 검토 결과와 개선점

1. **투자 목표 현실성 평가가 단순 수익률 기준만으로는 약함**
   - 보완: 연환산 수익률뿐 아니라 종목 변동성, ATR, 이벤트 리스크, risk tier로 현실성 등급을 조정하도록 추가했다.

2. **AI가 가격/수량을 임의 생성할 위험**
   - 보완: 포지션 사이징, 익절/손절, risk/reward는 코드 계산값만 사용하고 LLM 산출값이 충돌하면 폐기하도록 명시했다.

3. **재분석이 기존 분석과 독립 실행되면 맥락이 끊김**
   - 보완: `analysis_case`와 `analysis_run`을 분리하고, 포지션/거래 이력과 이전 run 대비 delta를 재분석 입력에 포함하도록 했다.

---

## 20. 2차 검토 결과와 개선점

1. **데이터 provider 실패 시 사용자 경험이 불명확**
   - 보완: 가격/뉴스/LLM/DB/Redis 장애별 degrade 정책과 `PARTIAL`, `FAILED` 상태를 추가했다.

2. **토큰 비용 최적화가 추상적**
   - 보완: 뉴스 URL hash 요약 캐시, fundamentals snapshot 재사용, delta-only 재분석, model routing, `cost_events` 기록을 구체화했다.

3. **UI가 단순 리포트 페이지로 흐를 위험**
   - 보완: 분석 상세 화면을 행동 중심 대시보드로 정의하고, Overview/Time Horizons/News/Fundamentals/Position/Audit 탭 구조를 추가했다.

---

## 21. 3차 적용성 검토 결과와 개선점

1. **초기 PR 범위가 웹/DB/AI/인프라를 모두 포함해 과대해질 위험**
   - 보완: 첫 개발 PR을 `ai-signal-workbench-domain`으로 축소하고, UI/DB/Redis/provider 실연동을 후속 PR로 분리했다.

2. **기존 `ai/stock_signal` 자산을 재사용하지 못하고 새 시스템을 만들 위험**
   - 보완: 재사용 가능한 파일과 확장 대상 파일을 명시하고, 기존 Decision Brief/지표/가드 구조를 확장하도록 했다.

3. **OpenAI 연결 준비 상태가 개발자에게 불명확**
   - 보완: `.env.local`, `openai>=2.36.0`, `OpenAI().responses`, `gpt-5.5` smoke call 성공 상태를 반영했다.

---

## 22. 미결 결정

- 초기 데이터 provider 선택: 무료/저비용 조합으로 시작할지, Polygon/Finnhub/Alpha Vantage 같은 유료 provider를 바로 쓸지 결정 필요.
- Backend를 FastAPI 단독으로 갈지, 향후 Kotlin Trading Core와 분리할지 결정 필요.
- 지원 시장: 초기에는 Apple과 Bitcoin만 허용한다. 이후 미국 주식/ETF 확장과 crypto 확장은 별도 provider 품질을 보고 결정한다.
- 실사용 전 법적 고지 문구는 별도 검토가 필요하다.
