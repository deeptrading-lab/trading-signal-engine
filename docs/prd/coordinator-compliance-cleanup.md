# PRD — Coordinator Compliance Cleanup (docs-only 잔존 노출 정정)

> 본 PRD는 문서·docstring 잔존 노출 정정을 위한 경량 PRD다.
> PRD 본문 자체에서도 도메인 키워드 평문 노출을 피하고, 정의 위치는 `ai/coordinator/_compliance.py`의 `FORBIDDEN_KEYWORDS` 단일 출처(SSoT)를 메타 표현으로만 참조한다.

- **Issue**: [#15](https://github.com/deeptrading-lab/trading-signal-engine/issues/15)
- **Labels**: `enhancement`, `priority:P1`
- **출처**: PR #14 reviewer 발견 항목 2·3
- **UI 포함 여부**: no

---

## 1. 배경 / 문제

PR #3 시점에 도입된 두 위치(`ai/coordinator/handlers.py:5-6` 모듈 docstring, `docs/references/slack-coordinator-bot-setup.md:24` 가이드 §1.1)에 트레이딩 도메인 키워드가 평문으로 나열되어 있다. PR #14에서 컴플라이언스 모듈을 도입하며 다른 영역의 잔존 노출은 정리되었으나, 이 두 군데가 정정에서 누락되어 동료 가시성 있는 회사 Slack 정책 기준에서 외부 노출 위험이 남는다.

## 2. 목표

두 위치의 평문 키워드 나열을 (a) `ai/coordinator/_compliance.FORBIDDEN_KEYWORDS` 정의 참조 또는 (b) "도메인 키워드" / "정책 목록" 같은 메타 표현으로 우회하여, 사용자 노출 영역에서 키워드 평문 등장이 정의 1곳 + 테스트 fixture 외 0건이 되도록 한다.

## 3. 범위 (In scope)

1. `ai/coordinator/handlers.py` 모듈 docstring에서 키워드 나열을 제거하고 `_compliance.py` 정책 참조 또는 메타 표현으로 대체.
2. `docs/references/slack-coordinator-bot-setup.md` §1.1 "금지 키워드" 인용 부분을 `_compliance.py` 참조 또는 메타 표현으로 대체.

## 4. 비범위 (Out of scope)

- 다른 docs/코드 파일의 잔존 노출(있다면 별도 이슈로 분리).
- `_compliance.py` 정책 자체(목록·로직)의 변경.
- 테스트 fixture의 키워드 평문(정책 검증 목적이므로 허용).

## 5. 수용 기준 (Acceptance criteria)

- **AC-1**: `ai/coordinator/handlers.py` 모듈 docstring에 트레이딩 도메인 키워드 평문이 단어 경계 기반 grep에서 0건이다.
- **AC-2**: `docs/references/slack-coordinator-bot-setup.md` §1.1 본문에 트레이딩 도메인 키워드 평문이 0건이다.
- **AC-3**: 두 위치 모두 메타 표현 또는 `ai/coordinator/_compliance.py` 참조를 통해 의미가 동일하게 전달되어, 독자가 어디서 정책을 확인해야 하는지 판단할 수 있다.
- **AC-4**: 회귀 — 기존 단위 테스트(166개)가 모두 통과한다(`pytest ai/tests/`).
- **AC-5**: 본 정정은 다른 chore PR과 묶이지 않고 컴플라이언스 모듈이 머지된 main에서 분기한 단독 PR로 제출 가능하다.
- **AC-6**: PRD 본문·커밋 메시지·PR 본문 어디에도 트레이딩 도메인 키워드 평문 노출이 없다.

## 6. 가정 / 제약

- 정책 정의 단일 진실 공급원(SSoT)은 `ai/coordinator/_compliance.FORBIDDEN_KEYWORDS`이며, 본 정정은 이를 변경하지 않는다.
- 변경 후 사용자 노출 영역(코드 docstring + 가이드 본문)에서 키워드 평문 등장은 정의 1곳 + 테스트 fixture 외 0건이어야 한다.
- 회사 Slack은 동료 가시성이 있어 코드 docstring(IDE 호버·GitHub 미리보기)·가이드 본문도 외부 노출 영역으로 간주한다.

## 7. 참고

- Issue: https://github.com/deeptrading-lab/trading-signal-engine/issues/15
- 출처 PR: #14 (review-approved) — `feature/coordinator-compliance-module`
- QA 리포트: `docs/qa/coordinator-compliance-module.md` §5
- 관련 파일:
  - `ai/coordinator/handlers.py` (모듈 docstring 5-6행)
  - `docs/references/slack-coordinator-bot-setup.md` (§1.1, 24행 부근)
  - `ai/coordinator/_compliance.py` (SSoT)
- 사용자 메모리: `project_slack_bot_naming.md` (봇 표시명 도메인 노출 금지)

---

## 보고 — 핵심 결정 사항

- **메타 표현 방식 권장 우선순위**: (1) `ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS` 참조 링크가 우선. 코드와 가이드 어느 쪽이든 SSoT를 직접 가리키면 추후 정책 추가/삭제 시 자동으로 일관성 유지된다.
- **차선**: 참조가 어색한 산문 컨텍스트에서는 "도메인 키워드" / "트레이딩 도메인 용어 일반" / "정책 목록" 같은 우회 표현 사용. 단, 이 경우에도 "상세는 `ai/coordinator/_compliance.py` 참조" 한 줄을 함께 둬서 독자가 정의 지점에 도달 가능하도록 한다.
- **금지**: 키워드 일부만 남기거나 다른 단어로 부분 치환하는 방식(잔존 노출 위험 + SSoT 분산).
