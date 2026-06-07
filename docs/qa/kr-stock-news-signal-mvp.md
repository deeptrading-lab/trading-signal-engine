# QA: kr-stock-news-signal-mvp

- **slug**: `kr-stock-news-signal-mvp`
- **QA 일자**: 2026-06-07
- **대상 PRD**: `docs/prd/kr-stock-news-signal-mvp.md`
- **대상 구현**: `ai/kr_stock_signal/*`, `ai/tests/test_kr_stock_signal.py`
- **판정**: PASS

---

## 1. 자동화 테스트 결과

실행 명령:

```bash
.venv/bin/python -m pytest ai/tests/test_kr_stock_signal.py -v
.venv/bin/python -m pytest ai/tests/ -v
git diff --check
```

결과:

- `ai/tests/test_kr_stock_signal.py`: 10 passed
- 전체 `ai/tests/`: 195 passed
- `git diff --check`: pass
- OpenAI real smoke: 삼성전자(`005930.KS`) 뉴스 1건 수집/요약/점수화/SQLite 저장 성공
- Supabase real smoke: watchlist seed, sample 2회 idempotent upsert, daily/feature API 조회 성공

---

## 2. PRD AC 매핑

| PRD 수용 기준 | 검증 항목 | 결과 |
|---|---|---|
| watchlist 외 종목 요청은 거절 | `test_watchlist_accepts_initial_three_symbols_and_rejects_others` | PASS |
| 삼성전자/SK하이닉스/현대차 watchlist | `WATCHLIST` set 검증 | PASS |
| SQLite schema에 뉴스 전용 테이블 생성 | `test_repository_initializes_schema_seeds_watchlist_and_upserts` | PASS |
| schema에 `price_bars`, `signal_reports` 없음 | sqlite master table 검증 | PASS |
| 뉴스 item과 daily score 저장 | `test_news_ingestion_service_persists_items_and_daily_score` | PASS |
| 뉴스 원문 body 미저장 | schema에 body column 없음, metadata/summary/score만 저장 | PASS |
| 중복 URL/hash/title/summary idempotency | `news_item_id` 안정성 + ingestion dedupe + `upsert_news_items` 반복 호출 | PASS |
| schema validation 실패 시 반영 차단 | `validate_news_item` invalid score/summary reject | PASS |
| 최근 10일 뉴스 점수는 저장 feature만 사용 | `test_news_feature_uses_recent_10_scores_without_raw_reanalysis` | PASS |
| 최소 local test는 API key 없이 가능 | fake/sample provider 기반 테스트 | PASS |
| OpenAI payload mapping은 schema validation 가능 | `test_openai_news_payload_mapping_is_schema_validated_by_news_layer` | PASS |
| OpenAI real provider로 삼성전자 뉴스 수집 가능 | 수동 smoke, `/private/tmp/kr_stock_news_openai_test_final.db` | PASS |
| Supabase stable id/upsert 요청 | `test_supabase_repository_uses_backend_secret_and_postgrest_upsert` | PASS |
| publishable key로 backend write 차단 | `test_supabase_repository_maps_daily_scores_and_rejects_publishable_key` | PASS |
| 신규 secret/legacy service-role 헤더 호환 | Supabase 공식 API key 규칙 + repository 단위 테스트 | PASS |
| refresh → daily → feature 엔진 API | `test_kr_stock_news_http_api_refresh_daily_and_feature` | PASS |
| 실제 Supabase sample 2회 upsert | `2026-06-07` row 1건 유지 | PASS |
| 실제 엔진 API → Supabase 조회 | health/daily/feature 수동 smoke | PASS |

---

## 3. 에지 케이스

- **뉴스 API key 없음**: `OpenAINewsProvider`는 `OPENAI_API_KEY is not configured`로 실패한다. sample provider 테스트는 API key 없이 가능해야 한다.
- **DB 중복 저장**: `daily_news_scores`, `news_items` 모두 primary key/upsert 경로를 둔다.
- **DB 동시 writer**: Supabase 경로는 stable primary key와 PostgREST upsert를 사용한다.
- **뉴스 schema 불량**: score 범위, risk tag, summary 길이 validation으로 차단한다.
- **watchlist 외 종목**: ValueError로 명확히 거절한다.
- **OpenAI 응답 비JSON**: provider가 `NewsProviderError`로 실패해야 하며, 실패 run log 테이블은 후속 구현 대상이다.
- **OpenAI 검색 품질**: 실제 smoke 중 유사 요약 반복과 허용 목록 밖 risk tag가 관찰됐다. ingestion title/summary dedupe와 provider risk tag allowlist 필터를 추가해 DB 저장 경계를 보강했다. source 신뢰도/ranking은 후속 개선 필요.

---

## 4. 남은 수동 확인 / 사용자 필요 작업

아직 필요한 사용자 작업:

1. 실제 반복 실행을 원하면 `OPENAI_API_KEY`를 `.env.local` 또는 OS secret에 설정.
2. OpenAI 일일 비용 한도 기본값 `$0.50` 유지 여부 확인.
3. 채팅에 노출된 Supabase secret을 rotate하고 새 secret을 `.env.local`에 직접 설정.
4. publishable key는 엔진 backend write에 사용하지 않는다.
5. 채팅에 노출된 OpenAI API key는 운영용으로 계속 쓰기보다 새 key로 rotate하는 것을 권장.

후속 구현 후보:

- scheduler entrypoint.
- ingestion run log와 비용 한도 enforcement.
- retention cleanup job.
