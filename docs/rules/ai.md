# Python Engine 규칙

- Engine은 CRUD와 market data stream만 담당한다.
- LLM SDK, prompt, 신호 산출, 뉴스 수집 코드를 추가하지 않는다.
- provider frame을 공통 tick/candle schema로 정규화한 뒤 저장한다.
- secret이나 원본 인증 응답을 로그에 남기지 않는다.
- 장시간 stream은 bounded reconnect backoff와 health 상태를 제공한다.
