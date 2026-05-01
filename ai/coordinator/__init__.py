"""
코디네이터 인바운드 처리 모듈.

PRD: docs/prd/slack-coordinator-inbound.md

Slack Socket Mode 기반 로컬 데몬:
- `config`: 환경변수 로딩·검증 (fail-fast)
- `auth`: 발신자 화이트리스트 판정
- `handlers`: 명령(`ping`/`status`/fallback) 응답 텍스트 생성
- `main`: 엔트리포인트 (Socket Mode 앱 시작)

외부 노출 텍스트(사용자 응답·로그)는 트레이딩 도메인 키워드를 노출하지 않는다.
"""
