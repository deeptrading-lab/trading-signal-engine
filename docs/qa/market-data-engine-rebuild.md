# QA: Market Data Engine Rebuild

검증일: 2026-06-09

## 결과

자동화 범위 PASS. 실제 Supabase migration과 KIS 실전/모의 연결은 credential이
필요해 미실행했다.

## 수용 기준 매핑

| AC | 검증 | 결과 |
|---|---|---|
| 1 | LLM/Slack dependency 없이 앱 생성 및 `/health` smoke | PASS |
| 2 | instrument/analysis CRUD route와 write auth | PASS |
| 3 | nested external analysis payload 원형 비교 | PASS |
| 4 | `1m`, `1d`, `1w`, `1mo` model 및 candle sync 저장 | PASS |
| 5 | `H0STCNT0` frame parse와 stream orchestration | PASS (unit) |
| 6 | 같은 분 tick의 OHLCV aggregation | PASS |
| 7 | `/ws/market` broadcast 수신 | PASS |
| 8 | 최대 30초 reconnect backoff 코드 경로 | PASS (review) |
| 9 | stream 상태 포함 `/health` 응답 | PASS |
| 10 | 변경 요청의 잘못된 token `401` | PASS |
| 11 | migration의 RLS/public policy 부재 | PASS (review) |
| 12 | 이전 runtime code/dependency 검색 | PASS |

## 실행 기록

```text
.venv/bin/python -m pytest ai/tests/ -q
6 passed, 1 warning in 0.37s

.venv/bin/python -m compileall -q ai
pass

git diff --check
pass
```

로컬 서버 smoke:

```json
{
  "ok": true,
  "service": "market-data-engine",
  "database": "supabase",
  "stream": {
    "enabled": false,
    "connected": false,
    "symbols": []
  }
}
```

## 미실행 외부 검증

1. Supabase에 `202606090001_market_data_engine.sql` 적용
2. Supabase CRUD real smoke
3. KIS access token/approval key 발급
4. KIS 주봉·당일 분봉 real response mapping
5. 장중 `H0STCNT0` 수신, 저장, 재연결

## 관찰

- FastAPI TestClient에서 Starlette의 `httpx` deprecation warning 1건이 발생한다.
  테스트 실패나 런타임 오류는 아니다.
- 운영 requirements와 test requirements를 분리했으며 Docker에는 FastAPI, httpx,
  pydantic, dotenv, uvicorn, websockets만 설치한다.
- migration은 이전 뉴스 테이블을 삭제하므로 적용 전 필요한 데이터 export 여부를
  확인해야 한다.
