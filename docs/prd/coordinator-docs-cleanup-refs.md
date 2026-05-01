# 코디네이터 문서 잔존 노출 정정 (references/rules)

- Issue: [#21](https://github.com/deeptrading-lab/trading-signal-engine/issues/21)
- 라벨: `chore`, `priority:P2`, `documentation`
- 출처: PR #19 Reviewer 후속 권고
- UI 포함 여부: **No** (문서 정정 전용)

## 1. 배경 / 문제

PR #19에서 `docs/prd/`·`docs/qa/` 평문 키워드는 정정됐으나, `docs/references/`·`docs/rules/` 디렉토리에 동일 패턴의 잔존 인용이 4곳 남아 있어 SSoT(`ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`)와 문서 표현이 다시 어긋난다.

## 2. 목표

`docs/references/`·`docs/rules/`의 잔존 평문 키워드 인용을 SSoT 참조 메타 표현으로 정정해 단일 정의 지점 일관성을 회복한다.

## 3. 범위 (In scope)

1. 확인된 4개 위치(`docs/references/slack-mcp-setup.md:168`, `docs/references/everything-claude-code.md:275`, `docs/references/everything-claude-code.md:417`, `docs/rules/backend.md:1`)를 PR #16·#19와 동일 패턴(SSoT 참조 메타 표현)으로 정정.
2. Dev가 `docs/references/`·`docs/rules/` 단어 경계 grep으로 추가 매치 발견 시 같은 PR에 포함.

## 4. 비범위 (Out of scope)

- 코드 변경 (SSoT 모듈 무변경).
- `docs/agents/` 등 다른 디렉토리 잔존은 별도 후속 이슈로 분리.

## 5. 수용 기준 (Acceptance criteria)

- **AC-1**: 정정 후 `docs/references/`·`docs/rules/` 전체에 단어 경계(`\b`) grep 시 평문 매치 0건(검사 정규식 메타·GitHub URL 저장소명 운영 예외 제외).
- **AC-2**: 정정 문서 내 SSoT 참조가 정확한 경로(`ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`)로 표기.
- **AC-3**: 코드 변경 없음 — 기존 pytest sanity check 통과.
- **AC-4**: PR 본문·커밋 메시지·본 PRD 본문에 평문 키워드 0건(예외 동일).
- **AC-5**: PR 본문에 `Closes #21` 포함.

## 6. 가정·제약

- 검색 기준은 단어 경계(`\b`) grep이며, 검사 정규식 메타·GitHub URL `trading-signal-engine` 저장소명은 PR #14·#19 선례에 따라 운영 예외.
- Dev가 grep으로 추가 매치 발견 시 동일 PR 범위에 포함하되, `docs/agents/` 등 본 범위 외 디렉토리 잔존은 후속 이슈로 분리.

## 7. 참고

- Issue: https://github.com/deeptrading-lab/trading-signal-engine/issues/21
- 선행 PR: #14 (1차 노출 지적), #16 (handlers/guide 정정), #19 (`docs/prd`·`docs/qa` 정정)
- SSoT: `ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`
- 대상 문서: `docs/references/slack-mcp-setup.md`, `docs/references/everything-claude-code.md`, `docs/rules/backend.md` (+ grep 결과 추가분)
