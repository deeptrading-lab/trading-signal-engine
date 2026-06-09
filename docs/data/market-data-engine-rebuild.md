# Data Contract: Market Data Engine

## Provider

### KIS REST

| 데이터 | API | 제한/정책 |
|---|---|---|
| 일·주·월봉 | `inquire-daily-itemchartprice` | 호출당 최대 100건 |
| 당일 분봉 | `inquire-time-itemchartprice` | 호출당 최대 30건, 전일 분봉 미제공 |
| OAuth | `/oauth2/tokenP` | 토큰을 만료 전까지 메모리 재사용 |

### KIS WebSocket

- approval key: `/oauth2/Approval`
- 실시간 체결 TR: `H0STCNT0`
- 기본적으로 Supabase의 enabled instrument마다 종목코드로 구독
- `KIS_SYMBOLS`가 있으면 배포 환경의 명시적 subscription allowlist로 우선 사용
- 연결 종료 시 1초부터 최대 30초까지 backoff
- ping frame은 provider 형식을 유지해 응답
- 체결 수신과 Supabase 쓰기를 분리하고 최대 200개 또는 0.2초 단위로 batch 저장

## Supabase Tables

### `instruments`

- `symbol`: KIS 6자리 종목코드
- `name`, `market`, `enabled`
- stream subscription의 단일 기준

### `external_analyses`

- `id`, `symbol`, `analysis_type`, `source`
- `payload jsonb`: 외부 서비스가 만든 결과 원형
- `observed_at`, `created_at`, `updated_at`

### `market_ticks`

- 체결 시각, 가격, 체결량, 누적 거래량
- provider 원문 중 운영 디버깅에 필요한 필드를 `raw jsonb`로 보존

### `market_candles`

- `(symbol, interval, opened_at)` unique
- `1m`, `1d`, `1w`, `1mo`
- OHLCV와 source

## Failure Policy

- Supabase 오류: API는 `502`, stream 저장 오류는 health의 `last_error`에 기록
- KIS 인증 오류: 자격증명을 로그에 남기지 않고 재연결
- malformed WebSocket frame: 해당 frame만 폐기
- DB 저장이 실패해도 client broadcast는 계속하며 오류 상태를 health에 노출
- 중복 candle은 unique key upsert
