---
description: PM → UX/UI → Dev → QA → Reviewer → DevOps 자동 체이닝. 파일·GitHub 라벨 상태로 현재 단계 판별 후 다음 서브에이전트 호출.
argument-hint: <slug> [from=<role>] [idea="..."]
---

사용자가 `/pipeline $ARGUMENTS` 를 호출했다. 아래 플레이북을 따라 **순차적으로** 서브에이전트를 Agent 툴로 호출하라.

## 0. 인자 파싱
- 첫 번째 토큰: **slug** (kebab-case). 없으면 사용자에게 되묻고 중단.
- `from=<role>`: 지정된 역할부터 시작 (`pm|ux-designer|backend-dev|frontend-dev|qa|reviewer|devops`).
- `idea="..."`: PM 단계에 넘길 아이디어 원문. `from=pm`일 때만 의미 있음.

## 1. 현재 단계 판별
다음을 순서대로 확인한다(존재하는 가장 진행된 단계의 **다음**부터 시작).

| 조건 | 다음 단계 |
|------|-----------|
| `docs/prd/<slug>.md` 없음 | `pm` |
| PRD에 UI 포함 **and** `docs/design/<slug>.md` 없음 | `ux-designer` |
| `gh pr list --search "feature/<slug>"` 비어 있음 | `backend-dev` (+ UI 있으면 `frontend-dev` 병렬) |
| 해당 PR에 `impl-ready` 라벨 있음 | `qa` |
| PR에 `qa-passed` 라벨 있음 | `reviewer` |
| PR에 `review-approved` 라벨 있음 | `devops` (사용자 확인 필수) |

`from=<role>` 이 주어지면 위 판별을 건너뛰고 해당 역할부터 시작한다.

## 2. 각 단계 실행 규칙

단계 하나씩 Agent 툴 호출 → 결과 확인 → 라벨 갱신 → 다음 단계. **절대 여러 단계를 한 번에 묶지 않는다** (산출물 섞임 방지).

### 프롬프트 공통 양식
```
slug: <slug>
입력: <직전 단계 산출물 경로/PR 번호>
목표: <그 역할의 본연 산출물>
완료 조건: 최종 응답 마지막 줄에 산출물 경로/PR·라벨을 한 줄로 명시.
```

### 단계별 세부

- **pm**: `Agent(subagent_type="pm", prompt="slug=<slug>, 아이디어=<idea>, 출력=docs/prd/<slug>.md")`. 완료 후 PRD 읽고 `UI 포함 여부` 확인.
- **ux-designer**: PRD에 UI 있을 때만. `Agent(subagent_type="ux-designer", prompt="PRD=docs/prd/<slug>.md, 출력=docs/design/<slug>.md")`.
- **backend-dev / frontend-dev**: PRD·디자인 문서 경로 전달. UI·백엔드가 모두 필요하면 **한 메시지에 두 Agent 호출을 병렬**로. PR URL·번호 회수.
- **qa**: `Agent(subagent_type="qa", prompt="PRD=docs/prd/<slug>.md, PR=#<N>, 출력=docs/qa/<slug>.md")`. 판정이 `qa-failed`면 개발자에게 돌리고 **루프 중단 + 사용자 보고**.
- **reviewer**: `Agent(subagent_type="reviewer", prompt="PR=#<N>, QA=docs/qa/<slug>.md")`. `changes-requested`면 루프 중단 + 사용자 보고.
- **devops**: 실행 **전 사용자에게 명시적 승인**을 받는다("PR #N을 머지·push 해도 될까요?"). 승인 후에만 `Agent(subagent_type="devops", prompt="PR=#<N>")`.

## 3. 라벨 갱신
각 단계 완료 시 `gh issue edit`/`gh pr edit --add-label <L> --remove-label <prev>` 로 상태 이동.
라벨 생성이 안 되어 있으면 첫 실행 시 [AGENTS.md](/AGENTS.md)의 `gh label create` 명령을 제안.

## 4. 중단 조건
다음 중 하나면 **즉시 멈추고 사용자에게 보고**한다:
- 서브에이전트가 오류 반환
- `qa-failed` 또는 `review-changes-requested`
- DevOps 단계 진입 (사용자 승인 필요)
- slug 충돌 (동일 slug의 다른 사람 Issue assignee 존재)

## 5. 최종 보고
각 단계 완료마다 한 줄 진행 상황을 사용자에게 보여주고, 전체 파이프라인 종료 시 산출물·PR 링크를 요약한다.