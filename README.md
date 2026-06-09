# Trading Signal Engine

AWS에서 실행되는 **CRUD + market data stream backend**입니다.

이 Engine은 투자 판단을 하지 않습니다. 다른 서비스가 만든 뉴스·분석 결과를
Supabase에 저장·조회하고, 한국투자증권(KIS) REST/WebSocket API에서 국내주식
시세를 받아 tick과 candle로 정규화합니다.

## Responsibilities

- 종목 CRUD
- 외부 분석 결과 opaque JSON CRUD
- KIS 일봉·주봉·월봉·당일 분봉 동기화
- KIS 실시간 체결가(`H0STCNT0`) 구독
- tick 저장과 1분봉 집계
- Engine WebSocket을 통한 실시간 이벤트 중계
- Supabase RLS 기반 backend-only 저장

OpenAI/Anthropic 호출, 뉴스 수집·분석, 매수·매도 신호, Bitcoin 분석, Slack bot,
주문·계좌 기능은 포함하지 않습니다.

기준 문서:

- [재구축 PRD](./docs/prd/market-data-engine-rebuild.md)
- [데이터 계약](./docs/data/market-data-engine-rebuild.md)
- [프로젝트 상태](./docs/PROJECT_STATUS.md)

## Setup

Python 3.12를 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
make install-dev
cp .env.example .env.local
```

Supabase에서 다음 migration을 실행합니다.

```text
supabase/migrations/202606090001_market_data_engine.sql
```

주의: 이 migration은 이전 뉴스 엔진 테이블을 제거합니다.

서버 실행:

```bash
PYTHON=.venv/bin/python make server
```

테스트:

```bash
PYTHON=.venv/bin/python make test
```

## Environment

필수:

```bash
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
ENGINE_WRITE_TOKEN=<long-random-secret>
```

KIS 실시간 수집을 사용할 때:

```bash
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ENVIRONMENT=prod
KIS_STREAM_ENABLED=true
KIS_SYMBOLS=005930,000660,005380
```

`KIS_ENVIRONMENT`는 `prod` 또는 `vps`입니다. API endpoint override가 필요한 경우
`KIS_REST_URL`, `KIS_WS_URL`을 설정할 수 있습니다. `KIS_SYMBOLS`를 비우면
Supabase `instruments.enabled=true` 종목을 시작 시 구독합니다.

## API

변경 API는 다음 header가 필요합니다.

```http
Authorization: Bearer <ENGINE_WRITE_TOKEN>
```

### Health

```http
GET /health
```

DB backend, stream 활성 여부, 연결 상태, 마지막 이벤트와 오류를 반환합니다.

### Instruments

```http
GET    /api/v1/instruments
POST   /api/v1/instruments
PATCH  /api/v1/instruments/{symbol}
DELETE /api/v1/instruments/{symbol}
```

### External analyses

```http
GET    /api/v1/analyses
GET    /api/v1/analyses/{id}
POST   /api/v1/analyses
PATCH  /api/v1/analyses/{id}
DELETE /api/v1/analyses/{id}
```

`payload`는 Engine이 해석하지 않는 JSON 객체입니다.

### Market data

```http
GET  /api/v1/ticks?symbol=005930
GET  /api/v1/candles?symbol=005930&interval=1w
POST /api/v1/candles/sync
```

캔들 sync 예:

```json
{
  "symbol": "005930",
  "interval": "1w",
  "start": "20260101",
  "end": "20260609"
}
```

지원 interval은 `1m`, `1d`, `1w`, `1mo`입니다. `1m`은 KIS 정책상 당일 분봉만
동기화합니다.

### WebSocket

```text
ws://<engine-host>/ws/market?token=<ENGINE_WRITE_TOKEN>
```

수신 이벤트:

```json
{
  "type": "market.tick",
  "tick": {},
  "candle": {}
}
```

## Deployment

`Dockerfile`과 `apprunner.yaml`은 `ai.market_data_engine.server`를 실행합니다.
Supabase/KIS credential과 write token은 AWS secret 환경변수로 주입합니다.

KIS 시세의 화면 표출 또는 제3자 제공 전에는 KIS와 거래소의 이용 조건을 별도로
확인해야 합니다.
