# Backend 규칙

- PRD·`AGENTS.md` 범위 밖 API/의존성/모듈 추가 금지
- HTTP API, repository, KIS provider, stream orchestration 경계를 분리 유지
- 공개 API의 오류 형식·HTTP 상태 코드를 일관되게 유지
- Engine 내부에서 투자 판단·LLM 분석·뉴스 수집을 수행하지 않는다
- 외부 분석 payload는 opaque JSON으로 취급한다
