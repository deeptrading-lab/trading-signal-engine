# Trading Signal Engine

> **Current planning direction (2026-06-07)**: 신규 우선 PRD는 [docs/prd/kr-stock-news-signal-mvp.md](./docs/prd/kr-stock-news-signal-mvp.md)입니다. 삼성전자·SK하이닉스·현대차 뉴스 수집·요약·점수화 결과를 로컬 SQLite 또는 Supabase에 저장하고 엔진 HTTP API로 조회합니다. 국내 주식 가격 provider와 매수/매도 수량 계산은 이 엔진 범위가 아니며, 아래 Bitcoin-only 설명은 현재 구현된 기존 엔진 맥락으로 남겨 둡니다.

비트코인 전용 자산 배분 의사결정 엔진입니다.

MVP는 BTC 일봉 가격, 장기/중기/단기 기술 지표, 변동성, 거래 참여 proxy, 최신 뉴스, Binance 거래소 매매 동향을 조합해 `Bitcoin Allocation Brief`를 생성합니다. 자동 주문은 하지 않으며, 사용자가 현재 보유 현금과 BTC 보유량에 맞춰 비중 확대/유지/축소 여부를 판단하도록 돕는 분석 레이어입니다.

## Goals

- Bitcoin-only 분석 경로 제공
- `INCREASE_ALLOCATION`, `CONDITIONAL_INCREASE`, `MAINTAIN_ALLOCATION`, `REDUCE_ALLOCATION`, `RISK_OFF` 액션 산출
- 20/50/200일 이동평균, 20/60일 수익률, RSI, 실현 변동성, 최근 고점 대비 낙폭 기반 점수화
- OpenAI web search 뉴스 요약과 Binance 공개 API 매매 동향을 결합
- 뉴스/수급 데이터가 없을 때도 명확한 data quality와 보수적 confidence 적용
- Slack/CLI/외부 소비자가 같은 분석 결과를 조회하도록 백엔드 API 유지

## Quick Start

```bash
make signal-offline SYMBOL=BTC
make test-bitcoin-signal
```

네트워크가 가능하면 무료 BTC-USD chart provider를 사용한다.

```bash
make signal SYMBOL=BTC
```

로컬 웹 대시보드는 이 저장소 범위가 아니며, 별도 `trading-signal-frontend` 저장소에서 실행한다.

```bash
cd ../trading-signal-frontend
npm run dev
```

엔진은 기본적으로 `http://127.0.0.1:8765/api/bitcoin/brief` 를 사용한다.

## Architecture

```text
User request / Slack / CLI / external client
↓
AI Analysis Service (Python)
- Bitcoin price provider
- Technical indicator engine
- Risk and allocation scoring
- OpenAI web search news snapshot
- Binance public market-flow snapshot
↓
Bitcoin Allocation Brief
- Action
- Confidence
- Score
- Allocation condition
- Risk-off condition
- Reasons / Risks
```

## Core Philosophy

- LLM은 계산하지 않는다. 계산과 가드는 Python 코드가 담당한다.
- 브리핑은 투자 조언이나 자동 주문이 아니라 의사결정 보조 산출물이다.
- 데이터가 부족하면 결과를 과감하게 보수화한다.
- 비트코인 외 자산 분석은 MVP 범위가 아니다.

## API Usage

### Korean Stock News

```bash
PYTHON=.venv/bin/python make kr-news-server
```

기본 주소는 `http://127.0.0.1:8766`이다.

```text
POST /api/kr-stocks/news/refresh
GET  /api/kr-stocks/news/daily?symbol=005930.KS&date=YYYY-MM-DD
GET  /api/kr-stocks/news/feature?symbol=005930.KS&lookback_days=10
```

공유 저장소는 `KR_STOCK_DB_BACKEND=supabase`로 선택하며 `SUPABASE_URL`과
backend 전용 `SUPABASE_SECRET_KEY`를 `.env.local` 또는 배포 secret manager에
설정한다. 프론트엔드는 Supabase에 직접 접근하지 않고 이 API를 호출한다.
refresh 요청은 `KR_STOCK_REFRESH_TOKEN`을 Bearer token으로 전달해야 하며,
`OPENAI_DAILY_COST_LIMIT_USD`와 `OPENAI_NEWS_MAX_REQUEST_COST_USD`로 비용을 제한한다.

### OpenAI

OpenAI는 현재 활성화된 데이터 수집 경로다. 다음 조건이 필요하다.

- `OPENAI_API_KEY` 를 `trading-signal-engine/.env.local` 에 설정
- `data_provider=openai` 로 요청
- OpenAI Responses API의 web search tool이 최신 BTC 뉴스 검색에 사용됨
- Binance 공개 API가 매매 동향 계산에 사용됨

API 요청에서 `data_provider=openai`를 선택하면 이 경로를 사용한다. 키가 없으면 뉴스 수집은 비활성화된다.

### Claude

Claude는 최종 요약 helper만 일부 준비되어 있고, 백엔드 데이터 수집 provider는 아직 미구현이다.

- `ANTHROPIC_API_KEY` 는 아직 분석 경로에 연결되지 않았다.
- `Claude` 토글은 준비 상태 표시만 한다.
- Claude 경로를 실제로 쓰려면 별도 provider 구현이 필요하다.

## Agent Workflow

요구사항부터 구현, QA, 리뷰, 운영까지의 절차는 [AGENTS.md](./AGENTS.md)를 따른다. 신규 우선 제품 PRD는 [docs/prd/kr-stock-news-signal-mvp.md](./docs/prd/kr-stock-news-signal-mvp.md)이며, 기존 Bitcoin-only 구현 맥락은 [docs/prd/bitcoin-allocation-mvp.md](./docs/prd/bitcoin-allocation-mvp.md)를 참고한다.

## Current Status

- [x] 비트코인 전용 분석 경로
- [x] 기술 지표 기반 배분 액션
- [x] OpenAI web search 뉴스 수집
- [x] Binance 공개 API 매매 동향 수집
- [x] 모바일 웹 대시보드
- [x] 로컬 실행 및 검증
- [ ] 원격 배포
- [x] Supabase DB 연동
- [ ] 하루 1회 배치 저장
- [ ] 전일 뉴스 + 전일 매매 동향 기반 저장 결과 조회
- [ ] Claude 데이터 수집 경로 구현

## Next Phase

다음 단계는 분석을 매 요청마다 다시 계산하는 대신, 하루 한 번 전일 뉴스와 매매 동향을 저장하고 이를 조회하는 구조로 옮기는 것이다.

목표:

- 원격 배포 환경에서 스케줄러가 하루 1회 실행
- 전일 뉴스 스냅샷, 전일 Binance 매매 동향, 엔진 의견을 DB에 저장
- 사용자가 API/CLI로 요청하면 최신 저장 결과를 조회
- 필요할 때만 재계산하고, 기본 경로는 저장된 결과 재사용

체크리스트:

- [ ] DB 스키마 설계
- [ ] 뉴스 스냅샷 저장 테이블
- [ ] 일별 의견 저장 테이블
- [ ] 1일 1회 배치 잡
- [ ] 조회 API를 저장 결과 우선으로 변경
- [ ] 원격 배포 구성
- [ ] Claude provider 구현 여부 재검토
