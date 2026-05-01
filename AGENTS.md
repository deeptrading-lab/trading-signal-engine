# AGENTS — 작업 방식 (Trading Signal Engine)

이 문서는 **사람과 AI 에이전트**가 이 저장소에서 일할 때 공통으로 따르는 **역할·순서·산출물**을 정의합니다.  
제품·아키텍처 개요는 [README.md](./README.md)를 참고하세요.

> ⚡ **모든 작업 시작 전 [docs/HANDOFF.md](./docs/HANDOFF.md)의 최근 5개 항목을 먼저 읽는다.** 직전에 무엇이 머지되었고 어떤 후속 작업이 남아 있는지 확인하기 위함이다. 사람이든 AI 에이전트든 이 단계를 건너뛰지 않는다.

---

## 구조: 문서와 Cursor 자산

| 위치 | 역할 |
|------|------|
| **이 파일 (`AGENTS.md`)** | 프로세스·PRD·커밋·배포 기준의 **단일 본문**. GitHub·리뷰·온보딩에서 먼저 읽습니다. |
| **`docs/HANDOFF.md`** | 작업 인수인계 로그. 작업 시작 전 최근 항목을 읽고, PR이 머지되면 GitHub Actions가 자동 append합니다. |
| **`docs/agents/*.md`** | 다른 IDE/CLI에서도 활용 가능한 **역할별 공용 문서(원본)**. |
| **`docs/rules/*.md`** | 다른 IDE/CLI에서도 활용 가능한 **규칙 공용 문서(원본)**. |
| **`skills/**/SKILL.md`** | 다른 IDE/CLI에서도 활용 가능한 **스택별 공용 스킬(원본)**. |
| **`.cursor/rules/*.mdc`** | Cursor 적용용(경로·주제별). 공용 문서(`docs/rules`)를 참조하는 얇은 규칙. |
| **`.cursor/skills/**/SKILL.md`** | Cursor 스킬 로딩용. 공용 스킬(`skills/`)과 내용 동기화. |

**원칙:** 절차·역할 정의를 바꿀 때는 **먼저 `AGENTS.md`를 수정**한다.  
공용 원본(`docs/`, `skills/`)을 먼저 고치고, `.cursor/`는 본문과 모순되지 않게 맞추며 중복은 최소화한다.

---

## 멀티 에이전트 역할 (7인 체제 + Manager)

한 대화 안에서도 역할을 명시해 전환합니다. 예: `역할: PM으로 PRD만 작성해줘`.

각 에이전트는 **서로를 견제하고 보완**하는 구조입니다. 7개 역할은 항상 열려 있으며, PRD에서 요구하는 범위에 따라 필요한 역할이 합류합니다. (예: UI가 필요한 PRD라면 UX/UI·Frontend Dev도 MVP 단계에서 바로 합류합니다.)

| # | 역할 | 하는 일 | 하지 않는 일(원칙) |
|---|------|-----------|---------------------|
| 1 | **PM (기획)** | 비즈니스 가치·비용 판단, 사용자 요구를 **PRD**로 정리해 개발에 넘김 | 구현·커밋·push |
| 2 | **UX/UI 디자이너** | 유저 시나리오 설계, **디자인 시스템 가이드**(shadcn/ui 등) 제공 | 코드 구현·머지 승인 |
| 3 | **Frontend Dev** | 디자이너 가이드에 맞춰 **UI 컴포넌트 구현**, 디자인 시스템 준수 | 디자인 의사결정 임의 변경 |
| 4 | **Backend Dev** | `ai/`(Python) 분석·파이프라인, `backend/`(Kotlin) 주문·리스크 구현. **한글 요약** 커밋 | PRD 없이 범위 임의 확장 |
| 5 | **QA (검증)** | PRD의 **수용 기준(AC)** → 테스트 항목·체크리스트 → 실행. 에지 케이스(예: 거래소 서버 다운) 포함 | PRD와 무관한 임의 테스트만으로 통과 판정 |
| 6 | **Code Reviewer** | PR의 **코드 퀄리티·아키텍처·클린 코드** 감시, 머지 승인 게이트 | PRD 수용 테스트 실행(= QA 영역) |
| 7 | **DevOps (배포)** | **유효한 커밋**일 때만 `git push`, CI/CD·운영 모니터링, **Slack 알림/인프라 비용** 관리 | 실패한 테스트·깨진 빌드 상태에서 push |
| + | **Manager (관찰·보고)** | 전체 slug 현황·블록·우선순위를 **read-only**로 조회해 리포트. `/status` 커맨드 진입점. | 라벨 변경·머지·파일 쓰기·다른 에이전트 실행 트리거 |

### 권장 흐름

```text
요구 → PM(PRD)
        ↓
   UX/UI(시나리오·디자인)   ← UI 작업이 PRD에 포함될 때
        ↓
   Frontend Dev / Backend Dev (구현 + 한글 요약 commit)
        ↓
   QA (항목 정리 + 실행)
        ↓
   Code Reviewer (PR 리뷰·머지 승인)
        ↓
   DevOps (push · 배포 · 모니터링)
```

---

## PRD (PM 산출물)

Backend/Frontend Dev·QA·Code Reviewer가 동일한 기준을 쓰도록 PRD는 아래를 **채워서** 작성합니다.

1. **배경 / 문제** — 왜 하는가  
2. **목표** — 무엇이 달라지면 성공인가  
3. **범위(In scope)** — 이번에 반드시 포함  
4. **비범위(Out of scope)** — 이번에 하지 않음  
5. **수용 기준(Acceptance criteria)** — 검증 가능한 문장 (예: “~할 때 ~한 결과”)  
6. **가정·제약** — 기술·일정·비용 등  
7. **참고** — 링크, 이슈 번호, 관련 파일 경로  

PM은 PRD만 전달하고, 개발자(Frontend/Backend)는 **PRD에 없는 기능을 임의로 넣지 않습니다.** 모호하면 PM에게 되물은 뒤 PRD를 갱신합니다.

---

## UX/UI 디자이너 산출물

UI·유저 인터랙션이 PRD에 포함될 때 합류합니다.

- **유저 시나리오**: 주요 태스크 플로우(예: 신호 확인 → 승인 → 주문 실행)
- **디자인 시스템 가이드 (DESIGN.md 포맷 필수)**:
  - 단일 진실 소스: 모든 `docs/design/<slug>.md`는 [Google Labs **DESIGN.md**](https://github.com/google-labs-code/design.md) 포맷을 따릅니다. 포맷 상세는 [`docs/rules/design-md.md`](docs/rules/design-md.md) 참조.
  - YAML front matter에 토큰(`colors`, `typography`, `rounded`, `spacing`, `components`)을 정의하고, 본문은 표준 섹션 순서(Overview → Colors → Typography → Layout → Elevation & Depth → Shapes → Components → Do's and Don'ts)로 작성합니다.
  - 색·간격은 토큰 참조(`{colors.primary}`)로만 연결합니다. 코드·컴포넌트에 hex/px를 직접 박지 않습니다.
- **검증**: 산출 직전 `npx @google/design.md lint docs/design/<slug>.md`를 실행하고 **error 0건**을 확인합니다. lint 요약을 PR/응답에 첨부합니다.
- **핸드오프 산출물**: Frontend Dev가 바로 구현할 수 있는 수준의 명세(스펙·상태·에러 케이스 포함). Frontend는 front matter의 토큰을 그대로 사용합니다.

디자이너는 코드 커밋·머지 승인을 하지 않습니다. Frontend Dev가 가이드를 따르지 않는다고 판단되면(예: 토큰 미사용, 임의 hex) Code Reviewer와 함께 변경을 요청합니다.

---

## 개발자 (Backend / Frontend): 커밋 메시지 (한글·요점만)

- **언어**: 한글  
- **길이**: 제목 한 줄 위주; 필요 시 본문은 불릿 2~5줄 이내  
- **내용**: “무엇을·왜”만 (구현 디테일 나열 지양)

예시:

- `README에 Slack MVP 및 에이전트 역할 반영`  
- `AI 서비스에 종목 분석 엔드포인트 추가`  
- `Slack 웹훅 전송 실패 시 재시도 로직 추가`  

---

## QA: PRD → 테스트 항목

1. PRD의 **수용 기준**마다 최소 1개 이상의 검증 항목을 만든다.  
2. 각 항목은 **재현 절차**와 **기대 결과**를 적는다.  
3. 자동화 테스트가 있으면 실행하고, 없으면 수동 체크리스트로라도 남긴다.  
4. **에지 케이스**(거래소 서버 다운·네트워크 지연·API 레이트리밋·뉴스 피드 장애 등)를 별도 섹션으로 정리한다.
5. 실패 시 **재현 조건·로그·스크린샷(필요 시)**를 남기고 개발자에게 되돌린다.  
6. 검증이 끝나면 결과를 **한 덩어리의 산출물**(통과/실패 목록, 실패 항목의 재현 절차·기대 대비 실제)로 정리해 **개발자에게 전달**한다. 수정이 필요하면 PRD 범위 안에서 무엇을 고쳐야 하는지 명시한다.

---

## Code Reviewer: 리뷰 게이트

- **범위**: 코드 퀄리티·아키텍처 일관성·클린 코드·보안·가독성. **PRD 수용 테스트 실행은 QA 영역**이므로 중복하지 않는다.
- **체크**: 불필요한 복잡도·중복·부적절한 책임 분리·네이밍·예외 처리 경로. `docs/rules/review.md` 준수.
- **HANDOFF 항목 점검**: `qa-passed` 라벨이 붙은 시점에 자동 commit된 `docs/HANDOFF.md` 항목이 PR diff에 포함된다. Reviewer는 (a) 사실관계, (b) "다음 작업 후보" 가 적절한지를 함께 검토한다. 부적절하면 직접 수정 후 머지.
- **결과**: 승인 / 변경 요청 / 보류 중 하나. 머지 승인은 Code Reviewer가 게이트한다.

---

## DevOps: `git push` · 배포 조건

다음을 만족할 때만 원격에 push 한다.

- 커밋이 **의도한 작업 단위**로 정리되어 있다 (WIP 대량 혼재 지양).  
- **QA 필수 검증**을 통과했거나, PRD상 “이번엔 스킵”이 명시되어 있다.  
- **Code Reviewer 승인**을 받은 상태다.
- 빌드/린트 등 저장소에 정의된 **필수 체크**가 있다면 통과했다.

불확실하면 push 하지 않고 확인을 요청한다.

추가로 DevOps는 다음을 책임진다.

- **CI/CD 파이프라인** 정의·유지, 배포 산출물 버전 관리
- **Slack 알림** 자동화(MVP 단계 핵심 채널), 장애·실패 알림 경로 확보
- **인프라 비용 모니터링** (`README.md`의 Cost Strategy 범위 내 유지)
- 운영 환경 헬스체크·로그 수집·경보 구성
- **머지 후 브랜치 정리**: 로컬·원격 feature 브랜치, QA/Reviewer가 만든 `pr-<N>` 체크아웃 ref를 정리한다. 헬퍼는 `scripts/cleanup-merged-branches.sh`. GitHub UI로 직접 머지한 경우에도 이 정리는 수동으로 수행해야 한다(상세는 `.claude/agents/devops.md` §"머지 후 정리")

---

## Cursor 사용 시 팁

- 큰 작업은 `PM → (UX/UI →) Frontend/Backend Dev → QA → Code Reviewer → DevOps` 순으로 **한 번에 한 역할**을 요청하면 산출물이 섞이지 않는다.  
- “PRD 초안만”, “이 PRD로 구현만”, “PRD 기준 테스트 계획만”, “PR 리뷰만”처럼 **출력물을 한 가지로 제한**한다.
- 역할·스택 힌트: `docs/agents/`의 해당 파일을 열어 두거나, 메시지에 `역할: QA`처럼 명시한다.

---

## 에이전트 간 핸드오프 규약

각 역할은 **정해진 파일 경로**에 산출물을 남기고, 다음 역할은 그 파일을 읽어 작업한다. 에이전트는 메모리가 아니라 **파일/PR/라벨**로 소통한다.

| 역할 | 입력 | 출력 | 트리거 (라벨/상태) | 다음 |
|------|------|------|--------------------|------|
| PM | 사용자 아이디어, GitHub Issue | `docs/prd/<slug>.md` + Issue 업데이트 | 라벨 `prd-requested` | `prd-ready` |
| UX/UI | `docs/prd/<slug>.md` (UI 포함 시) | `docs/design/<slug>.md` | 라벨 `prd-ready` + PRD에 UI 범위 | `design-ready` |
| Backend Dev | `docs/prd/<slug>.md` | 브랜치 `feature/<slug>` + PR | 라벨 `prd-ready` / `design-ready` | PR + `impl-ready` |
| Frontend Dev | `docs/prd/<slug>.md` + `docs/design/<slug>.md` | 브랜치 `feature/<slug>` + PR | 라벨 `design-ready` | PR + `impl-ready` |
| QA | PRD + PR diff | `docs/qa/<slug>.md` | 라벨 `impl-ready` | `qa-passed` / `qa-failed` |
| Code Reviewer | PR diff + `docs/qa/<slug>.md` | PR 리뷰 코멘트 | 라벨 `qa-passed` | `review-approved` / `review-changes-requested` |
| DevOps | 승인된 PR | 머지 + push + Slack 알림 | 라벨 `review-approved` | `devops-ready` |

### slug 규칙
- kebab-case, 기능 단위: `slack-signal-approval`, `kis-rate-limit-retry`
- PRD 파일명·브랜치·Issue 제목에 동일 slug 사용 → 검색·자동화 용이

### 파일 레이아웃
```
docs/
├── prd/<slug>.md         # PM 산출물
├── design/<slug>.md      # UX/UI 산출물 (UI 있을 때만)
└── qa/<slug>.md          # QA 리포트
```

---

## GitHub 라벨 플로우

두 사람이 동시에 일할 때 **어느 단계인지**를 Issue/PR 라벨로 표시한다. 에이전트는 `gh` CLI로 라벨을 읽고 쓴다.

```
prd-requested → prd-ready → design-ready → impl-wip → impl-ready
              → qa-pending → qa-passed     (실패 시 qa-failed → impl-wip 로 회귀)
              → review-pending → review-approved (또는 review-changes-requested → impl-wip)
              → devops-ready (DevOps가 머지·push 후 제거)
```

필수 라벨(`gh label create`로 1회 생성):

```bash
gh label create prd-requested prd-ready design-ready impl-wip impl-ready \
  qa-pending qa-passed qa-failed \
  review-pending review-approved review-changes-requested devops-ready
```

---

## 이슈 우선순위 (P0 / P1 / P2)

모든 GitHub Issue는 정확히 **하나의 priority 라벨**을 갖는다. 생성 시점에 영향(impact) × 노력(effort)을 평가해 부여한다.

| 라벨 | 정의 | 예시 |
|---|---|---|
| `priority:P0` | 긴급 — 실제 버그 / 사용자 경험 직접 영향 / 보안 / 데이터 정합성 | 메시지 편집·삭제 시 봇이 오답 발사, 토큰 평문 누출, 인증 우회 |
| `priority:P1` | 중요 — ROI 좋은 개선 / 다른 작업의 prerequisite / 자주 쓰는 UX 개선 | dotenv 자동 로딩, 다음 PRD가 의존하는 모듈화 |
| `priority:P2` | 여유 — 코드 품질 / 기술 부채 / chore / 회귀 방지용 테스트 보강 | 미사용 import 정리, dispatcher 단위 테스트, 마이너 가드 보강 |

### 신규 이슈 생성 절차 (PM / DevOps / Reviewer 공통)

1. **기존 open 이슈 스캐닝**: `gh issue list --state open --limit 100` 또는 `gh search issues` 로 동일·유사 이슈 중복을 확인. 중복이면 새로 만들지 말고 기존 이슈에 코멘트로 컨텍스트 추가.
2. **priority 평가**: 위 표 기준으로 P0/P1/P2 결정. 애매하면 더 높은 쪽으로 (P1 vs P2 → P1).
3. **라벨 부여**: 이슈 본문 작성 시 `--label priority:P0` (또는 P1/P2) + 도메인 라벨(`enhancement`/`tech-debt`/`chore`/`bug` 등) 동시 부여.
4. **출처 명시**: 본문에 "출처: PR #N 리뷰 / QA §x.x / 가이드 §y" 형태로 기록 — 스캐닝 시 컨텍스트 회복이 빠르다.

### 우선순위 변경
- 평가 후 잘못 매겼다고 판단되면 PR 코멘트나 이슈 코멘트로 근거를 남기고 라벨 교체. 침묵 변경 금지.

---

## 두 사람 작업 규칙 (락·동시성)

- **작업 선점 = Issue assignee 설정**. 같은 slug를 두 명이 동시에 잡지 않는다.
- **PR assignee = 작업 의뢰자**. PR 생성 시 `gh pr create --assignee @me` 로 현재 `gh` 인증 사용자를 자동 지정한다. 두 명이 같은 저장소에서 일할 때 누가 책임지는 PR인지 한눈에 보이도록 한다.
- **브랜치는 슬러그 하나당 하나**: `feature/<slug>`. 두 역할(예: FE + BE)이 같은 slug면 같은 브랜치에서 작업하거나 `feature/<slug>-fe`, `feature/<slug>-be`로 분리.
- **PRD 수정은 PM만**. 구현 중 모호함이 나오면 QA/개발자는 PR·Issue 코멘트로 질문 → PM이 PRD를 갱신 → 라벨 되돌림.
- **리뷰어 독립성**: PR 작성자와 다른 사람(또는 별도 cmux 패널/워크트리의 Reviewer 에이전트)이 리뷰. 본인 PR 자가-승인 금지.
- **slug 산출물은 feature 브랜치에**: `docs/prd/<slug>.md`, `docs/qa/<slug>.md`, `docs/design/<slug>.md` 등 특정 slug에 귀속되는 산출물은 그 slug의 `feature/<slug>` 브랜치에 commit한다. main에 직접 commit·push 금지. 메인 Claude가 sub-agent 산출물(QA 리포트 등)을 push할 때는 `git branch --show-current` 로 현재 브랜치를 먼저 확인하고, 잘못 main에 들어간 commit이 있으면 즉시 cherry-pick → reset 으로 정정한다.

---

## 작업 인수인계 (HANDOFF)

두 사람이 비동기로 작업하기 때문에 **누가 직전에 무엇을 머지했고 무엇이 남았는지**를 빠르게 따라잡는 장치가 필요하다. [docs/HANDOFF.md](./docs/HANDOFF.md) 가 그 역할을 한다.

- **시작 전**: 사람이든 AI 에이전트든 새 작업을 잡기 전 `docs/HANDOFF.md` 의 **최근 5개 항목**을 먼저 읽는다. 본인이 다시 돌아왔을 때도 동일하게 확인.
- **자동 append (QA 통과 시점)**: PR에 `qa-passed` 라벨이 붙으면 [.github/workflows/handoff-append.yml](./.github/workflows/handoff-append.yml) 가 **해당 PR의 feature 브랜치 자체에** HANDOFF 항목을 commit한다. 별도의 chore PR을 만들지 않으므로 PR이 한 개로 유지되고, Reviewer가 머지 직전 HANDOFF 항목까지 한 번에 최종 점검한다.
- **다음 작업 후보 자동 추출**: PR 본문에 `## 다음 작업` (또는 `## Next steps`, `## Follow-up`, `## 후속`) 섹션을 넣으면 그 내용이 HANDOFF에 자동 채워진다. **후보일 뿐 절대적 지시가 아니다.** 다음 작업자(사람·AI 모두)는 참고만 하고 우선순위·문맥에 따라 자유롭게 결정한다.
- **머지 전 최종 점검**: Reviewer는 PR diff에서 HANDOFF 항목을 함께 검토한다. 사실관계·다음 작업 후보가 부적절하면 PR에서 직접 수정 후 머지한다.
- **수동 append (선택)**: PR로 묶이지 않는 메모(WIP 중단, 디버깅 발견, 후속 TODO)는 세션 끝에 직접 추가해도 된다. `### YYYY-MM-DD — [WIP] 제목` 형태로 적는다.
- **순서**: 위가 오래된 항목, 아래가 최신. 최근 항목은 파일 하단에서 읽는다.

---

## 자동 파이프라인 (`/pipeline`)

[.claude/commands/pipeline.md](.claude/commands/pipeline.md) 슬래시 커맨드가 오케스트레이터 역할을 한다. 메인 Claude가 현재 라벨/파일 상태를 읽고, 다음 단계 서브에이전트([.claude/agents/](.claude/agents/))를 Agent 툴로 호출한다.

사용 예:

```
/pipeline slack-signal-approval              # 현재 상태에서 다음 단계부터 이어서 실행
/pipeline slack-signal-approval from=qa      # 특정 역할부터 재개
/pipeline slack-signal-approval idea="..."   # 신규: PM부터 전체 파이프라인 실행
```

오케스트레이터는 다음을 지킨다.

- 각 단계 산출물(파일 경로 또는 PR 번호)을 **명시적으로 다음 에이전트 프롬프트에 전달**한다.
- 단계 실패·변경 요청 시 **멈추고 사용자에게 보고**한다.
- **DevOps의 push·머지 단계는 사용자 확인 없이 자동 실행하지 않는다.**
- 각 단계 완료 시 GitHub 라벨을 자동 업데이트한다.

---

## 현황 조회 (`/status`)

실행은 `/pipeline`이 담당하고, **보고는 `/status`** 가 담당한다. 역할이 겹치지 않도록 `/status`가 호출하는 `manager` 서브에이전트는 **read-only**다.

사용 예:

```
/status                              # 모든 slug 현황(표 + 블록 경고 + 추천 액션)
/status slack-signal-approval        # 특정 slug 상세
/status --write                      # 리포트를 docs/STATUS.md 에 저장
/status --for @friend                # 특정 사용자 기준 우선순위 추천
```

매니저는 다음을 지킨다.

- **read-only**: 라벨·PR·파일 변경 금지. `gh ... list`·`git log`·파일 읽기만 허용.
- 실행 제안은 항상 **`/pipeline` 호출 안내**로 마무리한다 (자동 실행 금지).
- 기본 출력은 콘솔. `--write` 옵션일 때만 `docs/STATUS.md` 갱신.
