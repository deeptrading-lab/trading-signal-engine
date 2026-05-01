# Backend 규칙 (도메인 코어)

> 외부 노출 텍스트의 도메인 키워드 평문 금지. 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조.

- PRD·`AGENTS.md` 범위 밖 API/의존성/모듈 추가 금지
- 도메인 로직과 브로커·외부 연동 어댑터 분리 유지
- 공개 API의 오류 형식·HTTP 상태 코드를 일관되게 유지

