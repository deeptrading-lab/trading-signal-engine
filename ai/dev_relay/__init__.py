"""
로컬 개발 협업 릴레이 데몬 패키지.

PRD: docs/prd/slack-dev-relay.md

Slack Socket Mode 기반 로컬 데몬:
- `config`: 환경변수 로딩·검증 (fail-fast)
- `auth`: 발신자 화이트리스트 판정
- `queue`: SQLite 작업 큐 (멱등성·동시 1건·재시작 복구)
- `dispatcher`: 명령 파싱·라우팅 (`status` / `review pr <N>` / `merge pr <N>`)
- `agent_runner`: Claude Agent SDK 호출 래퍼 (sync + worker thread)
- `slack_renderer`: Block Kit 메시지 빌드 + 발사 직전 컴플라이언스 가드
- `main`: 엔트리포인트 (`python -m ai.dev_relay.main`)

외부 노출 텍스트(사용자 응답·Block Kit 라벨·로그)는 도메인 키워드를 노출하지 않는다.
정책 단일 정의 지점은 `ai.coordinator._compliance.FORBIDDEN_KEYWORDS`.
"""
