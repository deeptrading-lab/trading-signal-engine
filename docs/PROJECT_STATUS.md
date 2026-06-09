# Trading Signal Engine - Project Status

Last updated: 2026-06-09

## Product Direction

Engine은 AWS에서 실행되는 CRUD 및 market data stream backend다.

- 외부 서비스가 만든 분석 결과를 Supabase에 CRUD한다.
- KIS REST API에서 분봉·일봉·주봉·월봉을 동기화한다.
- KIS WebSocket에서 실시간 체결과 거래량을 수신한다.
- tick을 저장하고 1분봉으로 집계하며 Engine WebSocket으로 중계한다.
- Engine은 뉴스 수집, LLM 분석, 투자 신호, 주문을 수행하지 않는다.

기준 PRD는 `docs/prd/market-data-engine-rebuild.md`다.

## Implemented

- FastAPI HTTP/WebSocket server
- Supabase REST repository
- instrument CRUD
- opaque external analysis CRUD
- tick/candle query API
- KIS OAuth/approval key client
- KIS `1m`, `1d`, `1w`, `1mo` candle normalization
- KIS `H0STCNT0` frame parsing
- tick persistence, minute candle aggregation, client broadcast
- reconnect backoff and stream health
- Supabase migration, RLS, Docker/App Runner entrypoint

## Removed

- OpenAI/Anthropic and LLM cost pipeline
- Korean stock news collection/scoring
- Bitcoin allocation engine
- Slack coordinator
- SQLite news repository
- old analysis/signal APIs and tests

## Today / Next TODO

### Today

1. **Supabase migration 안전 적용 및 CRUD smoke**
   - 기존 `news_items`, `daily_news_scores`, `watchlist_symbols` 데이터의 export 필요
     여부를 먼저 결정한다.
   - 보존이 필요하면 export 후 `202606090001_market_data_engine.sql`을 적용한다.
   - instrument와 external analysis create/read/update/delete를 실제 Supabase에서
     검증한다.

### Next

2. AWS secret에 Supabase/KIS/write token 설정
3. KIS 모의 또는 실전 key로 `1m`, `1d`, `1w`, `1mo` candle sync smoke
4. 장중 `H0STCNT0` stream, batch persistence, 재연결 smoke
5. tick retention/partition 정책 결정
6. App Runner 장기 WebSocket 적합성 확인 후 필요하면 ECS/Fargate로 배포 대상 변경

## Next Action Definition

다음 작업 slug는 `market-data-supabase-migration-smoke`로 정한다.

완료 조건:

1. 기존 뉴스 테이블 보존 또는 폐기 결정이 기록되어 있다.
2. 새 migration이 Supabase에 적용되어 4개 신규 테이블과 RLS가 확인된다.
3. 실제 Engine API를 통해 instrument와 external analysis CRUD가 통과한다.
4. 사용한 secret 값은 문서·로그·Git에 남지 않는다.
