# 코디네이터 문서 잔존 노출 정정

- Issue: [#17](https://github.com/deeptrading-lab/trading-signal-engine/issues/17)
- 라벨: `chore`, `priority:P2`, `documentation`
- 출처: PR #14 QA §3.3 / PR #16 Reviewer 등록
- UI 포함 여부: **No** (문서 정정 전용)

## 1. 배경 / 문제

PR #16에서 `handlers.py` docstring 및 가이드 §1.1의 잔존 도메인 키워드 평문은 정정됐으나, 그 이전에 작성된 PRD 4건 (`slack-coordinator-inbound`, `slack-message-subtype-guard`, `coordinator-compliance-module`, `coordinator-dotenv-autoload`) 본문에 평문 인용이 잔존한다. SSoT(`ai/coordinator/_compliance.FORBIDDEN_KEYWORDS`)와 문서 표현이 어긋나 정책 일관성이 깨진다.

## 2. 목표

`docs/prd/`·`docs/qa/`의 잔존 평문 키워드 인용을 `_compliance.FORBIDDEN_KEYWORDS` SSoT 참조 표현으로 일괄 정정해 단일 정의 지점 일관성을 회복한다.

## 3. 범위 (In scope)

1. `docs/prd/` 4개 문서(위 4건)의 평문 키워드 인용을 SSoT 참조 메타 표현으로 대체.
2. `docs/qa/` 디렉토리도 단어 경계 grep 후 동일 패턴 발견 시 같은 PR에 포함.
3. 정정 패턴은 PR #16과 동일 — 평문 나열 대신 "정확한 정책 목록은 `ai/coordinator/_compliance.py`의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조"로 통일.

## 4. 비범위 (Out of scope)

- 코드 변경 (SSoT 모듈 자체는 손대지 않음).
- 신규 문서 작성 또는 PRD 외 영역(`README`, `references/` 등) 정정 — 잔존 발견 시 후속 이슈로 분리.
- 라벨 플로우·테스트 인프라 변경.

## 5. 수용 기준 (Acceptance criteria)

- **AC-1**: 정정 후 `docs/prd/`·`docs/qa/` 전체에 단어 경계(`\b`) grep을 돌렸을 때 평문 매치 0건이다(검사 정규식 메타·GitHub URL 저장소명 운영 예외 제외).
- **AC-2**: 정정 문서 내 SSoT 참조가 정확한 경로(`ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`)로 표기돼 있다.
- **AC-3**: 코드 변경이 없으므로 기존 단위 테스트 sanity check 모두 통과한다.
- **AC-4**: PR 본문·커밋 메시지·본 PRD 본문에 평문 키워드 0건이다(예외 동일).
- **AC-5**: PR 본문에 `Closes #17`이 포함돼 자동 종료된다.

## 6. 가정·제약

- 검색 기준은 단어 경계(`\b`) grep이며, 검사 정규식 메타와 GitHub URL의 `trading-signal-engine` 저장소명은 PR #14 선례에 따라 운영 해석상 예외다.
- Dev가 `docs/qa/` grep에서 추가 매치를 발견하면 동일 PR 범위에 포함하되, `references/` 등 다른 위치 잔존은 후속 이슈로 분리한다.

## 7. 참고

- Issue: https://github.com/deeptrading-lab/trading-signal-engine/issues/17
- 선행 PR: #14 (QA §3.3 노출 지적), #16 (Reviewer 등록 + handlers/guide 1차 정정)
- SSoT: `ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`
- 대상 문서: `docs/prd/slack-coordinator-inbound.md`, `docs/prd/slack-message-subtype-guard.md`, `docs/prd/coordinator-compliance-module.md`, `docs/prd/coordinator-dotenv-autoload.md` (+ `docs/qa/` grep 결과 추가분)
