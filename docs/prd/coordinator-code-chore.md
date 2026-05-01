# PRD — Coordinator Code Chore (#6 + #10 + #7 묶음)

> 본 PRD 본문에서 도메인 키워드 평문 노출은 회피하며, 정의 SSoT는 `ai/coordinator/_compliance.FORBIDDEN_KEYWORDS`다.

- **Issues**: [#6](https://github.com/deeptrading-lab/trading-signal-engine/issues/6), [#10](https://github.com/deeptrading-lab/trading-signal-engine/issues/10), [#7](https://github.com/deeptrading-lab/trading-signal-engine/issues/7)
- **Labels**: `tech-debt`, `chore`, `priority:P2`
- **출처**: PR #3 리뷰 발견 2·3 + 재리뷰 권고 1·2
- **UI 포함 여부**: no

---

## 1. 배경 / 문제

코디네이터 영역에 P2 코드 정리 3건이 누적되어 있다. (a) `handle_message_im` 클로저가 통합 테스트 불가 구조, (b) `.env.example` placeholder가 prefix 검사를 통과해 fail-fast가 무력화, (c) 미사용 import가 잔존. 단건 PR로 쪼개기엔 변경량이 작아 한 PR로 묶어 처리한다.

## 2. 목표

세 P2 코드 정리를 한 PR로 묶어 코디네이터 코드 영역 기술부채를 정리하고, dispatcher 통합 테스트 및 placeholder 가드 회귀 테스트로 같은 종류의 잔존 위험을 차단한다.

## 3. 범위 (In scope)

1. **dispatcher 추출 (#6)** — `ai/coordinator/main.py`의 `handle_message_im` 클로저 로직을 `_dispatch_message(event, *, say, logger, config, self_user_id)` 모듈 함수로 추출하고, `handle_message_im`은 얇은 wrapper로 유지. 신규 통합 테스트 파일 `ai/tests/test_coordinator_dispatch.py`에 mock `say` 기반 시나리오 5개 이상(정상/자기 메시지/비-IM/비처리 subtype/비허용 발신자) 추가.
2. **placeholder 가드 (#10)** — `ai/coordinator/config.py`에 명시적 placeholder 토큰 가드(방식 B) 추가: `_PLACEHOLDER_TOKENS = frozenset({"xoxb-여기에붙여넣기", "xapp-여기에붙여넣기"})` 매칭 시 `ConfigError`. `.env.example:18` 코멘트는 작업 노트 표현을 가이드 참조(`docs/references/slack-coordinator-bot-setup.md` §3-2) 형태로 정리.
3. **미사용 import 정리 (#7)** — `ai/coordinator/handlers.py:13`의 `import sys` 제거, `ai/tests/test_coordinator_handlers.py:6`의 `timedelta`만 제거(나머지 datetime 임포트 유지).

## 4. 비범위 (Out of scope)

- 새 응답 명령·기능 추가.
- 가이드 문서 본문 갱신(별도 정리 PR-2에서).
- placeholder 가드 방식 A(.env.example 형식만 변경) — B로 결정.

## 5. 수용 기준 (Acceptance criteria)

- **AC-1**: `_dispatch_message` 모듈 함수가 존재하고 `handle_message_im`이 이를 호출한다.
- **AC-2**: `ai/tests/test_coordinator_dispatch.py`에 통합 테스트 5개 이상이 추가되어 모두 통과한다(정상/자기/비-IM/비처리 subtype/비허용).
- **AC-3**: placeholder(`xoxb-여기에붙여넣기` 또는 `xapp-여기에붙여넣기`)로 데몬을 시작하면 `ConfigError`가 발생하고 프로세스가 non-zero exit 한다.
- **AC-4**: placeholder 가드 단위 테스트가 추가되어 통과한다(config 단계, 두 토큰 모두 커버).
- **AC-5**: `.env.example:18` 코멘트가 작업 노트 표현 없이 가이드 §3-2 참조 형태로 정리되어 있다.
- **AC-6**: `ai/coordinator/handlers.py`에 `import sys`가 없고, `ai/tests/test_coordinator_handlers.py`에 사용되지 않는 `timedelta`가 없다.
- **AC-7**: 기존 `ai/tests/` 단위 테스트와 신규 추가 테스트가 모두 통과한다.
- **AC-8**: PRD/PR/커밋 본문 어디에도 도메인 키워드 평문 노출이 없다(`_compliance.FORBIDDEN_KEYWORDS` 기준).
- **AC-9**: PR 본문에 `Closes #6` `Closes #10` `Closes #7`이 모두 포함되어 머지 시 세 이슈가 자동 종료된다.

## 6. 가정 / 제약

- Python 3.11+, 의존성 추가 없음.
- 기존 컴플라이언스 모듈(`ai/coordinator/_compliance.py`)·dotenv 자동 로딩 동작을 변경하지 않는다.
- placeholder SSoT는 `ai/coordinator/config.py::_PLACEHOLDER_TOKENS`로 두며, `.env.example`의 placeholder 표현이 바뀌더라도 코드 가드가 우선한다.

## 7. 참고

- Issues: #6, #10, #7
- 출처 PR: #3 (리뷰 발견 2·3, 재리뷰 권고 1·2)
- 관련 파일:
  - `ai/coordinator/main.py` (`handle_message_im` 클로저)
  - `ai/coordinator/config.py` (placeholder 가드 추가 지점)
  - `ai/coordinator/handlers.py:13` (`import sys` 제거)
  - `ai/tests/test_coordinator_handlers.py:6` (`timedelta` 제거)
  - `ai/tests/test_coordinator_dispatch.py` (신규)
  - `.env.example:18` (코멘트 정리)
  - `docs/references/slack-coordinator-bot-setup.md` §3-2 (참조 대상)
- 사용자 메모리: `project_slack_bot_naming.md` (봇 표시명 도메인 노출 금지)

---

## 보고 — 핵심 결정 사항

- **placeholder 가드 방식**: **B(코드 가드)** 채택. 이유는 (1) `.env.example` 표현이 어떻게 바뀌든 코드 단계에서 명시 차단이 가능하고, (2) 사용자 안내 문구(`.env.example` 코멘트)는 친절함을 유지할 수 있으며, (3) SSoT가 코드 한 곳(`config.py::_PLACEHOLDER_TOKENS`)으로 모인다. A는 미채택.
- **테스트 파일 분리**: 신규 `ai/tests/test_coordinator_dispatch.py`로 분리 — 기존 `test_coordinator_main_dotenv.py`는 dotenv 로딩 책임에 집중되어 있어 dispatcher 시나리오 5건 추가 시 파일 책임이 흐려진다.
- **import 정리 범위**: `handlers.py` `sys`와 테스트 `timedelta`만 핀포인트 제거. 광범위 lint 스윕은 본 PR 범위 밖.
