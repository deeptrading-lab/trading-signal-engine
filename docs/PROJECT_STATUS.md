# Trading Signal Engine — Project Status

Last updated: 2026-06-07

이 문서는 새 세션이 "지금까지 무엇이 구현됐고, 오늘 무엇을 하면 되는가"를 빠르게 판단하기 위한 상태판이다. 세션 시작의 세부 맥락은 `docs/SESSION_NOTES.md` 최신 항목과 `docs/HANDOFF.md` 최근 항목을 함께 확인한다.

## Product Direction

- **신규 우선 방향**은 국내 대형주 뉴스 수집·요약·점수화 엔진이다.
- 기준 PRD는 `docs/prd/kr-stock-news-signal-mvp.md`다.
- 초기 watchlist는 삼성전자(`005930.KS`), SK하이닉스(`000660.KS`), 현대차(`005380.KS`)다.
- 국내 주식 가격 provider는 프론트엔드에 구현되어 있으므로 이 엔진에서는 구현하지 않는다.
- 이 엔진은 당분간 매수/매도 신호, 추천 가격대, 추천 수량을 생성하지 않는다.
- 뉴스는 이미 주가에 선반영될 수 있으므로 투자 판단의 보조 feature로만 사용한다.
- 기존 Bitcoin allocation engine은 구현 자산으로 남아 있지만 신규 방향에서는 superseded 상태다.
- Dev Manager/dev-relay 봇 자산은 별도 레포 `HY0118/dev-manager-bot`로 분리되었고, 이 저장소의 본업은 Trading Signal Engine이다.

## Implemented

- **Korean stock news MVP skeleton**
  - `ai.kr_stock_signal` 패키지 추가.
  - 삼성전자(`005930.KS`), SK하이닉스(`000660.KS`), 현대차(`005380.KS`) watchlist.
  - SQLite repository schema: `watchlist_symbols`, `news_items`, `daily_news_scores`.
  - 뉴스 item validation, daily score aggregation, 최근 10일 뉴스 feature 집계.
  - OpenAI Responses API web search provider 경계 추가. 실제 실행은 `OPENAI_API_KEY` 필요.
  - sample provider 기반 CLI smoke path.
  - CLI: `python -m ai.kr_stock_signal.cli 삼성전자 --provider sample`.
  - SQLite/Supabase repository 선택: `KR_STOCK_DB_BACKEND`.
  - Supabase Postgres migration과 backend-only RLS 기본 정책.
  - Korean news HTTP API: refresh, daily, feature.

- **Bitcoin analysis engine**
  - `ai.bitcoin_signal.engine.analyze_bitcoin` 진입점.
  - BTC alias만 허용: `BTC`, `BTC-USD`, `BITCOIN`, `비트코인`, `비트`.
  - 액션 enum, 확신도, 점수, allocation condition, risk-off condition, sizing, 근거/리스크, data quality를 반환한다.
  - 신규 국내 주식 방향과는 별개로 기존 기능 유지 상태다.

- **Existing interfaces**
  - Bitcoin CLI: `python -m ai.bitcoin_signal.cli BTC`, `--offline`.
  - Bitcoin HTTP server: `python -m ai.bitcoin_signal.server`.
  - Bitcoin HTTP API: `GET /health`, `GET /api/bitcoin/brief`, `POST /api/bitcoin/brief`.
  - Korean news CLI: `make kr-news`, `make kr-news-sample`.

- **Coordinator basics**
  - Slack coordinator daemon exists under `ai/coordinator`.
  - Supports `.env` autoload, Slack Socket Mode config validation, allowed-user filtering, bot self-message guard, DM-only handling, subtype guard, `ping`, `status`, fallback, compliance safe-send.

## Current Commands

```bash
PYTHON=.venv/bin/python make kr-news-sample SYMBOL=삼성전자
PYTHON=.venv/bin/python make kr-news SYMBOL=삼성전자
PYTHON=.venv/bin/python make kr-news-server
PYTHON=.venv/bin/python make test-kr-stock-signal
make signal-offline SYMBOL=BTC
make signal SYMBOL=BTC
make bitcoin-server
make test-bitcoin-signal
make test
```

## Known Gaps

- 실제 OpenAI 삼성전자 뉴스 ingestion smoke는 완료했다.
- Supabase migration 적용과 sample ingestion/API smoke가 완료됐다.
- 운영용 backend secret을 로컬/배포 환경에 안전하게 설정하고 채팅에 노출된 검증용 secret을 회전해야 한다.
- scheduler entrypoint가 아직 없다.
- 프론트엔드는 엔진 API 경유로 확정됐으며 실제 frontend 연동 smoke가 남았다.
- 비용 한도 enforcement와 ingestion run log가 아직 없다.
- retention cleanup job이 아직 없다.
- Codex CLI adapter는 가능성 검토만 되었고 구현하지 않는다. MVP 기본 경로는 Python scheduler + OpenAI API 직접 호출이다.

## Today / Next TODO

1. **Supabase 운영 secret 정리**
   - migration, sample upsert, daily/feature API smoke는 완료됐다.
   - 채팅에 노출된 기존 secret을 Supabase Dashboard에서 rotate한다.
   - 새 `SUPABASE_SECRET_KEY`는 `.env.local` 또는 배포 secret manager에만 설정한다.

2. **scheduler 구현**
   - 08:30/12:30/16:10 `Asia/Seoul` 기준.
   - Supabase 사용 시 중복 실행에도 같은 결과가 되도록 upsert/실행 lock 정책을 둔다.

3. **비용/실행 로그**
   - `ingestion_runs` 테이블 추가 검토.
   - 모델, token usage, estimated cost, status, error message 저장.

4. **프론트엔드 연동**
   - 가격 데이터는 프론트엔드가 제공한다.
   - 이 엔진은 symbol/date/lookback 기준 뉴스 점수와 요약만 반환한다.
   - frontend는 Supabase 직접 접근 없이 이 엔진의 HTTP API만 호출한다.

5. **문서/README 최종 정리**
   - Bitcoin-only 문구는 기존 구현 설명으로 남기되 신규 방향과 혼동되지 않게 한다.

## Supabase Setup Needed From User

Codex가 연결 작업을 시작할 때 필요한 정보:

1. 기존 Supabase 프로젝트를 쓸지, 새 Free 프로젝트를 만들지 결정.
2. 기존 프로젝트라면 project name 또는 project ref만 전달. 비밀키는 채팅에 붙이지 않는다.
3. 새 프로젝트라면 Supabase Dashboard에서 organization과 region을 선택해 프로젝트 생성.
4. 앱 실행용 값은 로컬 `.env.local`에 직접 설정:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY` 또는 legacy service-role key
5. frontend 조회 방식은 `frontend → 이 엔진 HTTP API → Supabase`로 확정.

Supabase MCP가 현재 Codex 세션에 연결되어 있으면 migration과 schema 확인은 MCP로 수행한다.
Supabase MCP/CLI 로그인 없이 Dashboard SQL Editor와 backend REST secret으로 연결 검증을 완료했다.

## Answering "What Should I Do Today?"

사용자가 "오늘 뭐하지?", "다음에 뭐하지?", "현재 상태 알려줘", "TODO 정리해줘", "next action"처럼 물으면:

1. 이 파일의 `Today / Next TODO`를 먼저 기준으로 답한다.
2. 그 다음 `docs/SESSION_NOTES.md` 최신 1~2개 항목에서 사용자 합의나 보류 결정을 반영한다.
3. 마지막으로 `docs/HANDOFF.md` 최근 5개 항목에서 PR 단위 후속을 보강한다.
4. dev-relay 후속이 보이더라도, 이 저장소에서는 Trading Signal Engine 본업 TODO를 우선한다. dev-relay 작업은 별도 레포로 안내한다.
