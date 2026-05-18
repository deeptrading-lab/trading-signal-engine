# PRD: Dev Manager — write 도구 통합 + reviewer SDK callable wire (Phase 2)

- **slug**: `dev-relay-write-tools`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-15
- **UI 포함 여부**: **No** (별도 웹/네이티브 UI 없음. 외부 노출은 Slack 메시지·Block Kit 버튼·confirm 다이얼로그만 — 상위 PRD `slack-dev-relay.md` 와 동일 정책)
- **상위 PRD**: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md) (MVP / 봇 네이밍·컴플라이언스 정책 단일 정의)
- **선행 PRD**: [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md) (F-3 = reviewer SDK callable wire 대상 정의)
- **인접 PRD**: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md), [`docs/prd/dev-relay-nl-serialize.md`](./dev-relay-nl-serialize.md)
- **선행 PR (이미 머지)**: #25 (MVP 데몬), #43 (reviewer/merger 통합 — `_build_reviewer` 가 `NotImplementedError` 로 남음), #48 (NL 분기 직렬화), #49/#50/#51 (PR #43·#48 reviewer 후속)
- **대상 코드**: `ai/dev_relay/main.py` `_build_reviewer` ([현 위치 ~1589 라인](../../ai/dev_relay/main.py)), 신규 write 도구 라우팅 (`dispatcher.py`, `tool_policy.py`, `slack_renderer.py`)

---

## 1. 배경 / 문제

### 1.1 현재 상태

상위 PRD `slack-dev-relay.md` 의 MVP 가치 정의는 "모바일로 데드타임 회수" 이다. PR #25 (데몬 골격) + PR #43 (reviewer/merger 통합) 으로 다음 한 사이클은 reproducible 한 상태다.

- 모바일 DM → `review pr <N>` → reviewer 결과 + Block Kit 버튼 → `[머지 검토]` → `[승인]` → 머지.

그러나 **두 개의 격차** 가 남아 있다.

#### 격차 A — write 도구 부재 (Phase 2 본체)

현 MVP 의 3개 명령은 모두 **read·머지** 액션이다. 코드 수정·커밋·push 같은 **write 액션** 은 사용자가 PC 앞으로 돌아가야 한다. 모바일에서 발견한 사소한 수정 (예: 오타·로그 메시지·문서 줄바꿈) 도 PC 도착까지 보류되며, 본래 PRD 가 회수하려던 데드타임이 다시 누적된다.

전형적 시나리오:

- 출퇴근 중 PR diff 를 보다 오타 1개 발견 → 메모해 두고 PC 앞에서 처리 → 잊거나 후순위로 밀림.
- 외근 중 reviewer 발견 사항을 받았는데 1줄 패치면 끝나는 케이스 → PC 도착 후 처리.
- 저녁 시간 봇 알림으로 사소한 fix 가 보였는데 PC 부팅 비용 > fix 비용.

#### 격차 B — reviewer SDK callable wire 미완 (PR #43 F-3 후속)

PR #43 에서 reviewer/merger 통합 골격은 머지됐으나 `_build_reviewer` (`ai/dev_relay/main.py:~1589`) 가 다음과 같이 NotImplementedError 를 raise 한다.

```python
def _reviewer(pr_number: int) -> ReviewResult:
    raise NotImplementedError(
        "reviewer SDK 호출 구현은 후속 단계에서 nl_sdk_runtime 패턴으로 추가 예정."
    )
```

picker thread 가 reviewer job 을 꺼내 `_reviewer(pr_number)` 를 호출하면 즉시 raise 되어 `reviewer_failed(classification=unknown_error)` 로 분류된다. 즉 reviewer 결과 메시지 본체가 생성되지 않는다 — picker 가 사용자에게 보내는 것은 "응답 생성 중 오류가 발생했어요" fallback 뿐. PR #43 머지 시 의도적으로 deferred 됐으며, 본 PRD 가 wire 를 완성한다.

### 1.2 두 격차를 한 PRD 로 묶는 근거

두 격차의 통합 작업은 다음을 공유한다.

1. **Claude Agent SDK 통합 흐름** — reviewer wire 는 SDK 신규 세션 호출. write 도구 역시 SDK 호출 결과의 patch 를 적용하는 흐름. 두 작업 모두 `nl_sdk_runtime` 패턴 (NL 분기에서 검증된 SDK 호출 진입점) 의 재사용 대상.
2. **인증·credential 정책** — 구독 모드 우선 / API 키 fallback / 미설정 시 graceful degradation. 두 번 따로 정의하면 정책 분기점이 늘어나 회귀 비용 ↑.
3. **rate limit / quota 분류** — SDK 호출 실패의 분류 (`sdk_timeout`, `unknown_error`, quota 거절) 는 두 작업 공통. 단일 spec 으로 가야 한다.
4. **컴플라이언스 가드** — reviewer 결과 메시지·write 도구 출력물 (커밋 메시지·PR 본문 등) 모두 동일 정적·발사 직전 가드를 통과해야 한다.
5. **destructive 가드 정책** — write 도구는 destructive op 표면이 크다. `dev-relay-agent-integration.md` 의 머지 carve-out 과 비교해 더 보수적인 정책이 필요. 그러나 정책 정의 위치 (`tool_policy.py`) 는 reviewer wire 와 공유.

두 작업을 분리하면 SDK 인증·credential·rate limit·컴플라이언스·destructive 가드 정책을 두 번 따로 정의해야 한다. 통합하면 단일 spec 으로 일관성 확보.

### 1.3 운영 제약 (재인용)

- **1인 MVP** — 사용자 = 이하영. 단일 머신·단일 인스턴스 데몬.
- **회사 Slack 가시성** — 봇 표시명·외부 노출 텍스트에 도메인 키워드 노출 절대 금지.
- **SDK 토큰 비용** — Phase 2 부터 SDK 호출 빈도 ↑. 비용 모니터링 가드 통합은 별도 PRD (`cost-aware-llm-pipeline`).

---

## 2. 봇 네이밍 / 컴플라이언스 제약 재확인

상위 PRD `slack-dev-relay.md` §1 정책을 그대로 승계한다. 본 PRD 가 새 봇·새 표시명·새 채널 라벨을 도입하지 않는다.

- 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` **단일 정의 지점** 그대로 재사용 (별도 키워드 셋 신설 금지).
- 본 PRD 가 새로 도입하는 다음 항목은 모두 같은 가드를 통과해야 한다:
  - write 도구 명령 문법 (`apply patch`, `commit`, `push` — §3.2),
  - patch 적용 결과 사용자 노출 메시지 본문,
  - 자동 생성되는 **커밋 메시지** 본문 (외부 노출 텍스트 — git log 에 영구 보존),
  - reviewer 결과 메시지 본문 (격차 B wire 후 실 SDK 출력 기반),
  - Block Kit 버튼 라벨 / confirm 다이얼로그 본문 (`[패치 적용]`, `[커밋·푸시]`, `[취소]` 등 신규 라벨),
  - 신규 audit kind 명 (§3.7),
  - 본 PRD 본문 자체.
- 본 PRD 본문에서도 봇을 통칭할 때는 "Dev Manager 봇" 으로 부른다.
- **본 PRD 본문에 `FORBIDDEN_KEYWORDS` 키워드 인라인 나열 금지** — 코드 단일 정의 지점만 참조.

---

## 3. 범위 (In Scope)

본 PRD 는 (A) write 도구 추가 + (B) reviewer SDK callable wire 두 묶음을 단일 spec 으로 정의한다. 명령 추가·자동 코드 생성·머지 후속 자동 액션은 §4 비범위.

### 3.1 reviewer SDK callable wire (격차 B — F-3 완수)

#### 3.1.1 트리거 / 진입점

- picker thread 가 `pending` 상태의 `review pr <N>` job 을 꺼낼 때 `_build_reviewer(logger)` 가 반환한 callable 이 실제로 SDK 를 호출한다.
- 호출 패턴: **`nl_sdk_runtime` 의 진입점 재사용** — NL 분기에서 검증된 SDK invocation·error classification·quota 거절 처리 흐름을 그대로 답습한다 (별도 SDK 호출 모듈 신설 금지).
- 세션 정책: reviewer 호출은 **신규 SDK 세션** (NL 분기의 `AgentSessionStore.resume` 사용 안 함). reviewer 마다 독립 컨텍스트로, 사용자 NL turn 과 분리.

#### 3.1.2 인풋

- PR 번호 + 리뷰 instruction (코드 퀄리티 / 아키텍처 / 클린 코드 / 보안 관점, `docs/rules/review.md` 참조).
- PR diff 수집은 SDK 의 builtin tool (`gh pr diff <N>` 동등 동작) 우선 가정. Backend Dev 가 구현 시 가장 단순한 경로 선택.

#### 3.1.3 출력

- `ReviewResult` (현행 타입 — PR #43 정의). 같은 Slack 스레드(`thread_ts`) 로 결과 메시지 1건 발사:
  - 요약 2~3 문장,
  - 발견 사항 최대 3건 (없으면 "특이사항 없음"),
  - Block Kit 버튼 두 개 (`[머지 검토]`, `[상세 보기]`).
- 메시지·버튼 라벨·footer 모두 `slack_renderer` 발사 직전 가드 통과. SDK 가 도메인 키워드를 출력에 포함시킨 경우 가드가 매치하면 발사 차단 + ERROR 로그 + 사용자에게 "응답 생성 중 오류가 발생했어요" 중립 fallback (상위 PRD §3.7 정책 재사용).

#### 3.1.4 인증·credential 정책 (write 도구와 공유)

- **구독 모드 우선** (`ANTHROPIC_API_KEY` 미설정 시) — `claude` CLI 인증 승계. 상위 PRD §3.7 정책 그대로.
- **API 키 모드 fallback** (`ANTHROPIC_API_KEY` 설정 시) — `sk-ant-` prefix 검증 후 사용.
- **인증 실패 graceful degradation** — SDK import 실패 / 인증 거절 / quota 거절 시 `_build_reviewer` 는 `None` 또는 callable 이 `unknown_error` 분류로 raise. 데몬은 시작·동작을 막지 않으며 reviewer 만 비활성 (현행 `_build_reviewer` 의 `ImportError` 분기 동일 정책 승계).

#### 3.1.5 실패 분류 (PR #43 §3.5 표 재사용)

reviewer wire 후 분류 매핑은 PR #43 의 5가지 + `unknown_error` fallback 그대로:

- `destructive_blocked`, `sdk_timeout`, `github_unauthorized`, `github_unprocessable`, `compliance_blocked`, `unknown_error`.

quota 거절은 본 PRD 에서도 `sdk_timeout` 또는 `unknown_error` 로 fallback (전용 분류 신설은 비용 가드 PRD 영역).

### 3.2 write 도구 — 명령 범위 + 문법 (격차 A)

#### 3.2.1 write 도구 종류 (PM 권고 + 사용자 결정 게이트)

**사용자 결정 게이트 1**: write 도구의 범위를 어디까지 둘 것인가.

| 옵션 | 포함 도구 | 장점 | 단점 |
|---|---|---|---|
| (a) | `apply patch` 만 | 가장 보수적. destructive 표면 최소 | 패치 후 사용자가 PC 에서 commit·push 해야 함. 데드타임 회수 효과 제한 |
| **(b)** | `apply patch` + `commit` + `push` | 데드타임 회수 본격화. 모바일에서 end-to-end 마무리 가능 | destructive 표면 ↑ — push 가 force push 가 아니어도 외부 노출 영향 (CI 트리거 등). 커밋 메시지 자동 생성 필요 |
| (c) | (b) + `gh pr create` + 브랜치 관리 | 한 명령으로 PR 까지. full git flow | destructive 표면 가장 큼. PR 본문 자동 작성 = 컴플라이언스 위험 ↑. 브랜치 lifecycle 관리 복잡도 ↑ |

**PM 권고: (b)** — `apply patch` + `commit` + `push` 까지.

근거:

- (a) 만으로는 데드타임 회수 효과가 작다 (격차 A 의 본 PRD 동기 약화).
- (c) 의 `gh pr create` 는 PR 본문 자동 작성을 강제하는데, 본 PRD 의 컴플라이언스 가드 표면이 크게 늘어남 — PR 본문은 GitHub 외부 노출 + 영구 보존. Phase 3 별도 PRD 권장.
- (b) 는 destructive 표면이 명확히 한정 (한 PR 브랜치 한정) + 커밋 메시지 자동 생성만 가드하면 됨. MVP 동시 1건 + 본인 단독 사용에서 사고 표면 작음.

본 PRD 는 권고 (b) 기준으로 §3 이후 항목을 작성. 사용자가 (a) 또는 (c) 를 선택하면 §3.2 ~ §3.7 의 해당 항목을 줄이거나 늘려 재작성.

#### 3.2.2 명령 문법 (PM 권고 + 사용자 결정 게이트)

**사용자 결정 게이트 2**: write 도구 명령 진입을 structured / NL / 둘 다 어디로 둘 것인가.

| 옵션 | 진입 경로 | 장점 | 단점 |
|---|---|---|---|
| (a) | structured 만 (예: `apply patch <text>`, `commit <message>`, `push`) | 파싱 명확. 멱등성 보장. 컴플라이언스 가드 적용 위치 단일 | 모바일에서 긴 patch 텍스트 입력 UX 떨어짐. NL 친화성 X |
| (b) | NL 만 (자연어로 의도 표현 → SDK 가 도구 결정) | UX 자연스러움. "오타 하나 고쳐줘 X.py line 42" 같은 표현 가능 | NL 분기의 SDK 가 임의 도구 실행 결정 → destructive 가드 표면 ↑. 컴플라이언스 위험 |
| **(c)** | **둘 다 (structured 우선, NL 보조)** | structured 가 정확하고 NL 이 편의성 — 사용자가 선호하는 모드 선택 가능 | 두 진입점에서 모두 가드 적용해야 함 (구현 복잡도 ↑) |

**PM 권고: (c)** — structured 우선, NL 보조.

근거:

- (a) 만 두면 patch 텍스트 입력 UX 가 모바일에서 깨진다 (긴 텍스트 + 코드 블록 입력).
- (b) 만 두면 NL 분기의 SDK 가 자율적으로 destructive op 결정 → 가드 표면 ↑.
- (c) 는 structured 가 정확한 멱등 경로를 제공하고, NL 은 사용자 편의 — destructive 가드는 두 경로 모두 동일 정책 (`tool_policy.py` 단일 정의 지점) 으로 통일.

본 PRD 는 (c) 기준으로 §3.2.3 / §3.2.4 명령 정의.

#### 3.2.3 structured write 도구 명령 (3개)

| 명령 | 입력 예 | 동작 |
|---|---|---|
| `apply patch <pr=N>` | `apply patch pr=22` | (1) PR #22 의 컨텍스트 (diff·발견 사항) 로 SDK 호출 → patch 생성 → confirm 다이얼로그 (`[패치 적용]`, `[취소]`) → 사용자 승인 시 로컬 워킹트리에 적용. 적용만 함 (commit 안 함) |
| `commit <pr=N>` | `commit pr=22` | (1) 워킹트리 변경사항 검증 → 커밋 메시지 자동 생성 (SDK + 한글 컨벤션, `AGENTS.md` §"개발자 (Backend/Frontend) 커밋 메시지" 정책) → confirm 다이얼로그 (`[커밋]`, `[취소]`) → 사용자 승인 시 `git commit` |
| `push <pr=N>` | `push pr=22` | (1) 커밋 검증 → confirm 다이얼로그 (`[푸시]`, `[취소]`) → 사용자 승인 시 `git push` (현재 브랜치, force push 금지) |

- **2단계 confirm 필수** — `merge pr <N>` 정책 (상위 PRD §3.5) 그대로 승계. 모든 write 명령은 사용자가 명시적으로 confirm 버튼을 눌러야 실행.
- **PR 컨텍스트 기반** — 모든 write 명령은 PR 번호를 인자로 받으며, 그 PR 의 브랜치에 적용된다. 임의 브랜치 / 임의 파일 직접 수정은 비범위 (§4).
- **NL 자연어 자유 입력 (§3.2.4)** — `pr=N` 인자 강제는 structured 명령에만. NL 진입 시 SDK 가 PR 번호를 추론하거나 사용자에게 되묻는다 — 정책 단일 정의 지점은 NL 분기 (§3.2.4) 본문.

#### 3.2.4 NL 자연어 진입 (보조)

- 기존 NL 분기 (`_handle_natural_language`) 가 의도 분류 단계에서 write 도구 후보를 인식하면, NL 분기 SDK 가 도구 호출을 결정 — `nl_classifier.py` 에 신규 카테고리 추가.
- NL 분기에서 발생한 write 도구 호출도 **§3.2.3 의 confirm 다이얼로그를 통과해야 한다**. NL SDK 가 결정한 호출이라도 사용자 명시 승인 없이 실행 금지.
- NL 분기 직렬화는 `dev-relay-nl-serialize.md` 의 process-wide `threading.Lock` 정책 그대로 — 본 PRD 가 NL 분기 락을 새로 정의하지 않는다.
- structured 와 NL 의 race 표면 — NL 분기에서 write 도구 confirm 다이얼로그를 발사한 뒤 structured 분기에서 동일 PR 의 다른 write 명령이 들어오면? 두 경로 모두 `JobQueue` 의 `running_count >= 1` 가드를 통과해야 하므로 두 번째는 `pending` 으로 큐 적재 (상위 PRD AC-14 정책 승계).

### 3.3 destructive 가드 강화 (write 도구 표면 보강)

write 도구는 destructive op 표면이 머지 1회 동작보다 크다. 본 PRD 는 다음 정책을 추가한다.

#### 3.3.1 정책 단일 정의 지점

- 모든 destructive 분류 정책은 [`ai/dev_relay/tool_policy.py`](../../ai/dev_relay/tool_policy.py) `is_destructive` + 본 PRD 가 추가하는 새 헬퍼 (§3.3.3) 의 **단일 정의 지점** 으로 통일한다. dispatcher·NL 분기·write 도구·reviewer 가 모두 동일 헬퍼를 호출.

#### 3.3.2 write 도구별 화이트리스트·블랙리스트

| 도구 | 허용 | 차단 (destructive_blocked) |
|---|---|---|
| `apply patch` | unified diff 형식의 patch 텍스트만, 적용 대상은 PR 브랜치의 변경 가능 파일 | `.env*`, `.git/**`, `**/secrets/**`, `*.key`, `*.pem`, `**/credentials*` 경로 패치 / patch 텍스트에 `rm -rf`, `> /dev/`, force push 표지 |
| `commit` | 정상 커밋 (메시지 자동 생성). 커밋 메시지에 도메인 키워드 가드 적용 | force commit ammend (HEAD 재작성), `--no-verify` 플래그, sign-off override |
| `push` | 현재 브랜치, fast-forward 또는 일반 push | `--force`, `--force-with-lease`, `--mirror`, `--delete`, push to `main`/`master` 직접, push to 본인 브랜치 외 |

#### 3.3.3 dry-run 모드 (PM 권고)

**PM 권고**: write 도구는 confirm 다이얼로그 단계에서 **dry-run 결과를 함께 표시**.

- `apply patch` confirm 메시지에 변경 파일 목록 + 라인 수 요약 (예: "3 파일, +12/-4 라인 변경").
- `commit` confirm 메시지에 커밋 메시지 본문 + 변경 파일 수.
- `push` confirm 메시지에 push 될 커밋 SHA 목록 + remote 브랜치.

근거: 사용자가 모바일에서 승인 결정을 내릴 때 결과 미리 보기가 없으면 사고 위험 ↑. dry-run 자체는 destructive 표지에 닿지 않으므로 가드 통과 X.

#### 3.3.4 롤백 정책

- `apply patch` 적용 실패 / confirm `[취소]` / 가드 차단 시 워킹트리는 적용 직전 상태 유지 — patch 적용은 `git apply --check` 로 검증 후 적용, 실패 시 미적용 (현재 워킹트리 미변경).
- `commit` 실패 / 가드 차단 시 워킹트리 변경은 그대로 남고 커밋 객체만 미생성. 사용자가 PC 에서 추가 작업 가능.
- `push` 실패 / 가드 차단 시 로컬 커밋은 그대로 남고 remote 만 미변경. 사용자가 PC 에서 재시도 가능.
- **자동 롤백 안 함** — `git reset --hard` 같은 자동 되돌리기는 destructive 가드 표지. 본 PRD 는 적용 단위 atomic 보장만 책임지며, 사용자 명시 명령 없이 워킹트리를 거꾸로 되돌리지 않는다.

### 3.4 인증·credential 정책 (write 도구와 reviewer wire 공유)

§3.1.4 참조. 두 작업이 동일 정책을 공유하므로 본 PRD 가 단일 정의 지점이다.

- 구독 모드 우선 / API 키 fallback / 인증 실패 시 데몬 시작은 막지 않고 해당 도구만 비활성 (`_build_reviewer` 의 ImportError 분기 정책 동일 적용).
- 시작 로그에 `auth_mode=subscription` 또는 `auth_mode=api_key` 1라인 (상위 PRD AC-9 (b) 정책 그대로).
- write 도구도 SDK 호출 (patch 생성·커밋 메시지 생성) 이 필요하므로 인증 미통과 시 비활성. structured 명령 호출 시 즉시 `unknown_error` 분류 + 사용자에게 "SDK 인증이 필요합니다" 안내.

### 3.5 동시성 — write 도구 + reviewer + merge 의 직렬화

- write 도구·reviewer·머지 모두 `JobQueue` 에 적재 → `AgentRunner(max_workers=1)` 가 직렬 실행. 상위 PRD §3.4 정책 그대로.
- write 도구의 confirm 다이얼로그 대기 중 (사용자가 아직 버튼을 누르지 않음) job 상태: `pending_confirm` 신규 도입은 본 PRD 비범위 — 현행 `running` 상태에서 confirm 대기까지 포함 (PR #43 의 머지 confirm 흐름 정책 그대로).
- NL 분기와 write 도구의 상호작용:
  - NL 분기는 `_nl_turn_lock` (`dev-relay-nl-serialize.md`) 으로 process-wide 직렬화.
  - write 도구는 `JobQueue` 로 직렬화.
  - 두 락은 독립 — NL 분기가 write 도구 confirm 다이얼로그를 발사한 뒤에는 NL 락이 release 되고, write 도구 자체는 `JobQueue` job 으로 살아남는다. 이후 사용자가 새 NL 메시지를 보내면 정상 처리됨.

### 3.6 shutdown 보호

write 도구는 destructive 표면이 머지보다 크므로 shutdown 정책을 엄격히 한다.

- **shutdown flag set 후 새 write 명령 진입 거절** — `_nl_shutdown_event` 와 동일 패턴으로 `_write_shutdown_event` 또는 동급 flag 추가. 거절 시 사용자에게 안내 1줄 + 큐 미적재.
- **진행 중 write 작업의 graceful 종료**:
  - patch 적용 / commit 단계: 1초 안에 끝나는 atomic op 이므로 graceful 종료 대상에 포함.
  - push 단계: 외부 네트워크 호출 — `AgentRunner.shutdown(wait=True, timeout=...)` watchdog 정책 (PR #37) 그대로 적용. timeout 초과 시 강제 종료 + 다음 시작 시 `git push --dry-run` 으로 remote 반영 여부 재확인 안내 (자동 reconcile 은 비범위 §4).
- **confirm 대기 중 shutdown** — 사용자가 confirm 버튼을 누르지 않은 상태에서 shutdown 시그널 도달하면 confirm 다이얼로그 무효화. 다음 시작 시 사용자에게 "이전 세션에서 confirm 대기 중이던 write 작업 1건은 무효화됐습니다. 필요하면 다시 명령해 주세요." 안내. 이 안내 자체도 컴플라이언스 가드 통과 필수.

### 3.7 신규 audit kind

상위 PRD §3.6 + PR #43 §3.6 의 audit 형식을 그대로 따르되, 다음 kind 를 추가한다. 모든 kind 식별자는 컴플라이언스 가드 0 hit.

```
reviewer_sdk_invoked          {ts, kind, job_id, pr, session_id}       # 격차 B wire 후 SDK 실 호출 진입
reviewer_sdk_returned         {ts, kind, job_id, pr, duration_s, finding_count}

patch_requested               {ts, kind, job_id, pr, user_id_masked}
patch_generated               {ts, kind, job_id, pr, file_count, lines_added, lines_removed}
patch_confirmed               {ts, kind, job_id, pr, action: applied|cancelled}
patch_applied                 {ts, kind, job_id, pr, files: [..]}
patch_failed                  {ts, kind, job_id, pr, classification}

commit_requested              {ts, kind, job_id, pr, user_id_masked}
commit_message_generated      {ts, kind, job_id, pr}
commit_confirmed              {ts, kind, job_id, pr, action: committed|cancelled}
commit_created                {ts, kind, job_id, pr, sha}
commit_failed                 {ts, kind, job_id, pr, classification}

push_requested                {ts, kind, job_id, pr, user_id_masked}
push_confirmed                {ts, kind, job_id, pr, action: pushed|cancelled}
push_done                     {ts, kind, job_id, pr, remote, branch}
push_failed                   {ts, kind, job_id, pr, classification}
```

- 모든 라인은 ISO-8601 KST timestamp + user_id 마스킹 정책 승계.
- 분류 라벨 (`classification`) 은 §3.1.5 의 5개 + `unknown_error` fallback 그대로 + write 도구 전용 다음 라벨 추가:
  - `patch_apply_failed` — `git apply` 비정상 종료 (충돌·파일 부재 등),
  - `commit_empty_tree` — 스테이지된 변경 없음,
  - `push_rejected` — remote 가 push 거절 (non-fast-forward 등),
  - `write_destructive_blocked` — write 도구 가드가 destructive 분류 차단 (`destructive_blocked` 와 분리해 write 도구 표면을 별도 모니터링).

---

## 4. 비범위 (Out of Scope)

- **다중 사용자·멀티 인스턴스 데몬** — 현 운영 1인 한정.
- **자동 코드 생성** — write 도구는 **사용자 명시 명령에만 반응**. SDK 가 자율적으로 patch 를 생성·적용하는 흐름은 도입하지 않는다 (예: reviewer 가 발견 사항을 자동 fix). NL 분기에서 사용자가 명령한 경우는 §3.2.4 처리 — 자율 트리거가 아니라 명시 의도 기반.
- **`gh pr create` / PR 본문 자동 작성** — §3.2.1 (c) 옵션. Phase 3 별도 PRD.
- **머지 후속 자동 액션** — 릴리즈 노트 자동 생성, deployment trigger, 브랜치 정리 자동화 등. 본 PRD 비범위.
- **임의 브랜치·임의 파일 직접 수정** — write 도구는 PR 브랜치 컨텍스트 한정. PR 외 임의 브랜치 / 메인 직접 수정은 도입하지 않음.
- **자동 롤백 / 자동 되돌리기** — §3.3.4. atomic 보장만 책임지며 사용자 명시 명령 없이 워킹트리를 되돌리지 않음.
- **SDK 비용 모니터링 가드 통합** — `cost-aware-llm-pipeline` 의 가드를 본 PRD 에서 wrap 하지 않음. 별도 후속 PRD.
- **NL 분기 directing write 도구의 모드 분기 (`/dev` slash command 등)** — DM 진입만. Slash command 충돌 회피.
- **`implement <slug>`, `qa <slug>`, `pipeline <slug>` 명령 추가** — 상위 PRD 부록 C. 본 PRD 는 write 도구 3종 + reviewer wire 만.
- **`git rebase`, `git merge` 로컬 명령** — destructive 표면이 크고 충돌 처리 UX 가 모바일에 부적합. 본 PRD 비범위.
- **머지 conflict 자동 해결** — write 도구가 `git apply` 충돌 시 사용자에게 안내만 하고 자동 해결 안 함.

---

## 5. 수용 기준 (Acceptance Criteria)

QA 가 그대로 체크리스트로 사용한다. **재현 절차 + 기대 결과** 형식. 번호는 본 PRD 내부 번호.

### AC-WT-1. reviewer SDK callable wire — F-3 완수

- **재현**: `python -m ai.dev_relay.main` 실행 후 본인 DM 에 `review pr <N>` (실재 open PR) 입력. picker thread 가 job 을 꺼낼 때까지 대기 (5초 이내).
- **기대**:
  - `_build_reviewer` 가 반환한 callable 이 SDK 신규 세션을 실제로 호출 (NotImplementedError raise 안 함).
  - 같은 스레드에 결과 메시지 1건 발사 — 요약 2~3 문장 + 발견 사항 (있으면 최대 3건, 없으면 "특이사항 없음") + `[머지 검토]`, `[상세 보기]` 버튼.
  - audit.jsonl 에 `reviewer_sdk_invoked` → `reviewer_sdk_returned` 두 라인이 순서대로 기록.
  - 결과 메시지·버튼 라벨 도메인 키워드 0 hit.

### AC-WT-2. write 도구 `apply patch` 정상 흐름

- **재현**: 본인 DM 에 `apply patch pr=<N>` 입력. PR 컨텍스트 + reviewer 발견 사항 기반으로 SDK 가 patch 생성.
- **기대**:
  - 1단계: confirm 다이얼로그가 같은 스레드에 발사 — patch 요약 (변경 파일·라인 수) + `[패치 적용]`, `[취소]` 버튼.
  - 2단계: `[패치 적용]` 클릭 시 `git apply --check` 통과 → 워킹트리 적용 → "패치 적용 완료" 안내.
  - audit.jsonl 에 `patch_requested` → `patch_generated` → `patch_confirmed(applied)` → `patch_applied` 라인이 순서대로 기록.
  - 적용된 파일 목록이 `patch_applied` 의 `files` 필드에 정확히 기록.

### AC-WT-3. write 도구 `commit` 정상 흐름

- **재현**: AC-WT-2 적용 직후 본인 DM 에 `commit pr=<N>` 입력.
- **기대**:
  - 1단계: confirm 다이얼로그에 자동 생성된 한글 커밋 메시지 본문 + `[커밋]`, `[취소]` 버튼.
  - 2단계: `[커밋]` 클릭 시 `git commit` 수행 + SHA 노출.
  - 커밋 메시지가 `AGENTS.md` §"개발자 커밋 메시지" 정책 (한글·1줄 위주) + 컴플라이언스 가드 통과.
  - audit.jsonl 에 `commit_requested` → `commit_message_generated` → `commit_confirmed(committed)` → `commit_created` 기록.

### AC-WT-4. write 도구 `push` 정상 흐름

- **재현**: AC-WT-3 커밋 직후 본인 DM 에 `push pr=<N>` 입력.
- **기대**:
  - 1단계: confirm 다이얼로그에 push 될 커밋 SHA 목록 + remote 브랜치 + `[푸시]`, `[취소]` 버튼.
  - 2단계: `[푸시]` 클릭 시 `git push` (force 아닌 일반 push) 수행.
  - audit.jsonl 에 `push_requested` → `push_confirmed(pushed)` → `push_done` 기록.

### AC-WT-5. destructive 가드 — write 도구 표면

- **재현**: 다음 케이스를 strucutured / NL 두 진입점 각각으로 시도.
  - (a) patch 텍스트에 `rm -rf /` 포함,
  - (b) `.env*` 경로 수정 patch,
  - (c) `push --force` 의도가 담긴 NL 메시지 ("force push 해줘" 등),
  - (d) `commit --amend` 의도가 담긴 NL 메시지.
- **기대**: 각 케이스 모두 `tool_policy.py` 의 destructive 가드가 차단 → `write_destructive_blocked` audit 라인 1줄 + 사용자에게 "이 작업은 PC에서 직접 처리해 주세요." 안내. 워킹트리 / 커밋 / remote 변경 0건.

### AC-WT-6. confirm `[취소]` — 작업 중단

- **재현**: AC-WT-2 / AC-WT-3 / AC-WT-4 각각의 1단계 confirm 다이얼로그에서 `[취소]` 클릭.
- **기대**:
  - 봇이 "취소했습니다." 안내 (이유 입력은 강제 안 함, 상위 PRD AC-6 정책 그대로).
  - 워킹트리·커밋·remote 어디에도 부작용 없음.
  - audit.jsonl 에 `*_confirmed(cancelled)` 라인 + 이후 `*_applied` / `*_created` / `*_done` 라인 부재.

### AC-WT-7. NL 자연어 진입 — write 도구 의도 인식 + confirm 강제

- **재현**: 본인 DM 에 자연어로 "PR <N> 에 patch 적용해줘" 입력.
- **기대**:
  - NL 분기 (`_handle_natural_language`) 가 write 도구 카테고리로 분류 → SDK 가 patch 생성 → §3.2.3 의 동일 confirm 다이얼로그 발사.
  - 사용자 명시 confirm 없이 patch 적용 X.
  - NL 분기 직렬화 (`_nl_turn_lock`) 정책 회귀 없음 — AC-NLS-* (PRD `dev-relay-nl-serialize.md`) 모두 0 fail.

### AC-WT-8. 동시성 — write 도구 + reviewer 직렬화

- **재현**: reviewer job (`review pr <M>`) 실행 중에 본인 DM 에 `apply patch pr=<N>` 추가 입력.
- **기대**:
  - 두 번째 명령에 대해 5초 이내 첫 응답 — `TEMPLATE_QUEUE_BUSY` 안내 + 대기 1건.
  - 첫 작업 완료 후 두 번째 job 자동 시작.
  - audit.jsonl 에 두 작업 모두 `command_received` → `job_started` → 도구별 라인 → `job_done` 사이클 기록.

### AC-WT-9. 인증 미통과 시 graceful degradation

- **재현**:
  - (a) `claude` CLI 미로그인 + `ANTHROPIC_API_KEY` 미설정 상태에서 데몬 시작.
  - (b) `ANTHROPIC_API_KEY` 가 잘못된 값 (prefix `sk-ant-` 아님) 상태에서 데몬 시작.
- **기대 (a)**: 데몬은 정상 시작 (start 자체 막지 않음). reviewer / write 도구 호출 시 즉시 `unknown_error` 분류 + 사용자에게 "SDK 인증이 필요합니다" 안내. 데몬 자체는 status / NL fallback 등 SDK 미필요 명령은 계속 응답.
- **기대 (b)**: 상위 PRD AC-9 (c) 그대로 — 한 줄 에러 + exit != 0 (silent 무시 금지).

### AC-WT-10. shutdown 보호 — 진행 중 작업·confirm 대기

- **재현**:
  - (a) `apply patch` 적용 직전 (confirm `[패치 적용]` 클릭 직후 `git apply` 실행 중) SIGTERM 전송.
  - (b) `push` 진행 중 (외부 네트워크 호출 중) SIGTERM 전송.
  - (c) confirm 다이얼로그 발사 후 사용자 미응답 상태에서 SIGTERM 전송.
- **기대 (a)**: `git apply` atomic op 종료까지 graceful 대기 + audit 기록 완료.
- **기대 (b)**: `AgentRunner.shutdown(timeout)` watchdog 정책 그대로 — timeout 내 완료 시 graceful, 초과 시 강제 종료 + 다음 시작 시 reconcile 안내.
- **기대 (c)**: confirm 다이얼로그 무효화 + 다음 시작 시 사용자에게 "이전 세션 confirm 대기 작업은 무효화됐습니다" 안내.

### AC-WT-11. 멱등성 — 동일 client_msg_id 재수신

- **재현**: 동일 `client_msg_id` 를 가진 `apply patch pr=<N>` 이벤트를 두 번 주입 (Slack 재전송 시뮬레이션).
- **기대**: `jobs` 테이블에 새 row 추가 없음. SDK 호출 1번만. 두 번째 이벤트는 INFO 로그 (`duplicate event ignored`).

### AC-WT-12. rate limit — write 도구도 적용

- **재현**: 본인 DM 에 5초 내 4건 이상의 write 명령 입력.
- **기대**: 상위 PRD AC-15 정책 그대로 — 4번째 이후 큐 미적재 + rate limit 안내. SDK 호출 폭증 방지.

### AC-WT-13. audit log 완전성

- **재현**: AC-WT-2 / AC-WT-3 / AC-WT-4 한 사이클 1회 완주.
- **기대**: audit.jsonl 에 §3.7 의 신규 kind 가 다음 시퀀스로 빠짐없이 기록:
  - `patch_requested` → `patch_generated` → `patch_confirmed(applied)` → `patch_applied`
  - `commit_requested` → `commit_message_generated` → `commit_confirmed(committed)` → `commit_created`
  - `push_requested` → `push_confirmed(pushed)` → `push_done`

### AC-WT-14. 컴플라이언스 정적 검사

- **재현**: 본 PRD 본문, `ai/dev_relay/` diff, `ai/tests/dev_relay/` 신규/변경 케이스, 신규 메시지 상수, 신규 audit kind 식별자, 자동 생성된 커밋 메시지, 본 PRD 구현 PR 본문 / 커밋 메시지를 `FORBIDDEN_KEYWORDS` 패턴으로 정적 스캔.
- **기대**: **0 hit**. 기존 `ai/tests/dev_relay/test_compliance.py` 정적 검사가 본 PRD 산출물을 모두 커버하도록 화이트리스트 보강.

### AC-WT-15. 외부 노출 텍스트 (커밋 메시지) 컴플라이언스

- **재현**: AC-WT-3 의 자동 생성 커밋 메시지 본문 (`git log -1 --format=%B`) 를 정적 스캔.
- **기대**: 도메인 키워드 0 hit. 메시지는 한글 1줄 위주 (`AGENTS.md` 정책). SDK 가 도메인 키워드를 출력에 포함시킨 경우 commit 발사 직전 가드가 차단 + `commit_failed(classification=compliance_blocked)` + 사용자에게 "커밋 메시지 생성에 문제가 있어 작업을 중단했어요" 안내.

### AC-WT-16. 회귀 — 기존 PR #43 + NL 분기 직렬화 테스트 0 fail

- **재현**: 기존 `ai/tests/dev_relay/test_agent_integration.py`, `test_handle_command_nl.py`, `test_handle_command_nl_serialize.py`, `test_dispatcher.py`, `test_tool_policy.py` 모든 parametrize 케이스 실행.
- **기대**: 0 fail. 본 PRD 변경이 기존 reviewer/merger 통합·NL 분기·destructive 가드에 회귀를 일으키지 않음.

---

## 6. 가정 · 제약

### 6.1 기술

- Python 3.11+, 상위 PRD §6.1 환경 그대로 승계. 신규 의존성 없음 (`subprocess` + `git` CLI + `gh` CLI 표준 사용).
- `git apply --check` 가 patch 검증의 단일 진입점. 실패 시 미적용.
- `claude-agent-sdk` 가 PR #43 머지 시점 이후로 새 버전이 나왔다면 Backend Dev 가 호환성 회귀 확인 (본 PRD 가 SDK 버전 lock 을 강제하지 않음).
- write 도구의 SDK 호출 (patch 생성·커밋 메시지 생성) 은 `nl_sdk_runtime` 패턴 재사용 — 신규 SDK 호출 모듈 만들지 않는다.

### 6.2 비용 / 한도

- write 도구는 reviewer 보다 SDK 호출 빈도가 낮을 것으로 예상 (사용자가 patch 텍스트를 한 번에 적용하면 1건, reviewer 는 PR 마다 1건). 그러나 NL 분기에서 write 도구 의도 분류가 추가되면 NL turn 마다 분류 비용 발생.
- 구독 모드 (Max 20x) quota 부족 시 §3.1.5 의 `sdk_timeout` / `unknown_error` fallback. 비용 모니터링 가드 통합은 별도 PRD.

### 6.3 보안

- write 도구 호출은 모두 화이트리스트 user_id 한정 (상위 PRD §3.8 정책 그대로).
- 모든 write 작업은 2단계 confirm (structured) + 2단계 confirm (NL 분기 진입) 통과 필수.
- patch 텍스트·커밋 메시지·remote 응답에서 토큰·평문 비밀 노출 차단 (마스킹 정책 그대로).
- `git config` / `gh auth` 같은 인증 컨텍스트 변경 명령은 destructive 가드 차단 — `tool_policy.py` 의 화이트리스트에 명시.

### 6.4 일정 / 운영

- 로컬 데몬 한정. CI / 배포 / 인프라 변경 없음.
- 본 PRD 머지 후 1~2주 모니터링: write 도구 사용 빈도 + `write_destructive_blocked` 발생 빈도 + reviewer SDK 비용. 빈도가 예상 초과 시 비용 가드 PRD 우선순위 상향.

---

## 7. 위험 / 의존

1. **destructive 사고 표면 확대** — write 도구 (특히 `push`) 는 remote 에 도달하면 되돌리기 어렵다. §3.3 의 다층 가드 (블랙리스트·dry-run·confirm·롤백 정책) 가 핵심 방어선. 가드 누락 회귀가 일어나면 사고 비용이 큼.
2. **자동 커밋 메시지의 컴플라이언스 누설** — 자동 생성 커밋 메시지가 git log 에 영구 보존되어 외부 노출 (GitHub Public/Internal 공개 범위에 따름). SDK 출력에 도메인 키워드가 섞이면 commit 발사 직전 가드가 차단해야 한다 (AC-WT-15). 누설 사고 시 영구 재작성 비용 큼.
3. **SDK 토큰 비용 폭증** — write 도구 도입으로 SDK 호출 빈도 ↑ 예상. 비용 가드는 비범위 — 1~2주 모니터링 후 사용자 판단으로 별도 PRD 트리거.
4. **`git apply` 충돌 처리 UX** — 모바일에서 충돌 해결은 불가능. 충돌 발생 시 사용자에게 "PC 에서 처리해 주세요" 안내만 가능. 빈번하면 write 도구 가치 약화 — 1~2주 모니터링 후 NL 분기에서 충돌 가능성을 사전 안내하는 UX 가 필요할 수 있음 (본 PRD 비범위).
5. **NL 분기 + write 도구 의도 분류 회귀** — `nl_classifier.py` 에 신규 카테고리 추가 시 기존 NL 분기 분류가 회귀할 수 있다. AC-WT-16 으로 회귀 검증 + `dev-relay-nl-serialize.md` 의 AC-NLS-* 0 fail 검증.
6. **reviewer SDK wire 실 호출 후 비용·rate limit 모니터링 필요** — 현재 `_build_reviewer` 가 NotImplementedError 라서 실 SDK 호출이 0 건. 본 PRD 머지 후 reviewer 호출 빈도가 사용량의 본격 부분이 됨. 모니터링 가드는 본 PRD 비범위지만 후속 PRD 트리거 시점 명확.
7. **워킹트리 상태 가정** — write 도구는 현재 워킹트리가 PR 브랜치라고 가정. 사용자가 PC 에서 다른 브랜치 체크아웃해 둔 상태면 patch 적용 후 의도 외 브랜치에 변경이 들어간다. 본 PRD 는 `git branch --show-current` 로 진입 시점 브랜치를 검증하고 PR 브랜치와 다르면 거절 — 정확한 검증 로직은 Backend Dev 결정.
8. **multi-process 데몬 배치 시 무효** — `dev-relay-nl-serialize.md` §7 위험 6 그대로. 본 PRD 의 `JobQueue` 는 SQLite 파일 락에 의존하지만 `threading.Lock` (NL 분기) 은 process-local. 단일 인스턴스 운영 전제.

---

## 8. 테스트 전략 개요

QA 가 본 PRD AC 를 검증하기 위한 1차 가이드. 정확한 테스트 항목은 QA 산출물 (`docs/qa/dev-relay-write-tools.md`) 이 주도한다.

### 8.1 자동 (단위 + 통합)

- **신규 테스트 클래스** (`ai/tests/dev_relay/test_write_tools.py` 신규 또는 분할):
  - `TestReviewerSDKWire` — AC-WT-1 (SDK 호출 mock 으로 wire 검증)
  - `TestApplyPatchFlow` — AC-WT-2
  - `TestCommitFlow` — AC-WT-3
  - `TestPushFlow` — AC-WT-4
  - `TestDestructiveGuardWrite` — AC-WT-5 (structured + NL 두 진입점)
  - `TestConfirmCancel` — AC-WT-6
  - `TestNLEntryToWriteTool` — AC-WT-7
  - `TestWriteToolConcurrency` — AC-WT-8
  - `TestAuthGracefulDegradation` — AC-WT-9
  - `TestWriteToolShutdown` — AC-WT-10
  - `TestWriteToolIdempotency` — AC-WT-11
  - `TestWriteToolRateLimit` — AC-WT-12
  - `TestWriteToolAuditCompleteness` — AC-WT-13
  - `TestComplianceStaticScan` — AC-WT-14 / AC-WT-15
- **mock 전략**: SDK 호출은 fake callable (`time.sleep` + 고정 patch 텍스트). `git apply` / `git commit` / `git push` 는 tmp 저장소 fixture 에 실 호출 (격리된 worktree). `gh` CLI 는 mock.
- **회귀**: 기존 `ai/tests/dev_relay/test_agent_integration.py`, `test_handle_command_nl_serialize.py`, `test_dispatcher.py`, `test_tool_policy.py` 모든 케이스 0 fail (AC-WT-16).

### 8.2 수동 (사용자 검증)

상위 PRD 부록 A 셋업 완료 환경에서 모바일 Slack 앱에서 다음 한 사이클을 1회 수행:

- `review pr <N>` → 같은 스레드에서 SDK 실 호출 기반 결과 확인 (AC-WT-1 수동 검증).
- `apply patch pr=<N>` → confirm `[패치 적용]` → 워킹트리 적용 확인 (PC 에서 `git status`).
- `commit pr=<N>` → confirm `[커밋]` → 한글 커밋 메시지 확인 (PC 에서 `git log -1`).
- `push pr=<N>` → confirm `[푸시]` → remote 반영 확인 (GitHub 웹).
- NL 자연어 진입 사이클 1회 ("PR <N> 패치 적용해줘") — confirm 다이얼로그 동일 발사 확인.
- 모든 봇 응답·confirm 본문·자동 커밋 메시지가 도메인 키워드 0 hit 인지 육안 확인.

---

## 9. 사용자 결정 게이트 (구현 진입 전 확정 필요)

본 PRD 초안의 권고는 다음과 같다. 사용자(이하영) 검토 후 결정 / 보완 → §10 의 표 갱신 → impl 진입.

| # | 항목 | PM 권고 | 대안 | 결정 필요 시점 |
|---|---|---|---|---|
| 1 | write 도구 범위 (§3.2.1) | **(b)** apply patch + commit + push | (a) apply patch 만 / (c) (b) + `gh pr create` | impl 진입 전 |
| 2 | 명령 진입 경로 (§3.2.2) | **(c)** structured 우선, NL 보조 | (a) structured 만 / (b) NL 만 | impl 진입 전 |
| 3 | dry-run 표시 (§3.3.3) | **표시 (변경 파일·라인 수·SHA 목록)** | 미표시 (즉시 confirm) | impl 진입 전 |
| 4 | reviewer SDK 인증 정책 (§3.1.4) | **구독 모드 우선 / API 키 fallback / 인증 실패 시 graceful degradation** | 인증 실패 시 데몬 시작 막기 (fail-fast) | impl 진입 전 |

위 4건 모두 PM 권고를 채택하면 §3 ~ §5 본문 그대로 진행 가능. 옵션 변경 시 영향 받는 절을 명시.

---

## 10. PM 결정사항 요약 (구현·QA 가 한눈에 보도록)

| 항목 | 결정 (PM 권고 기준 — 사용자 결정 게이트 §9 통과 후 확정) |
|---|---|
| 본 PRD 책임 범위 | (A) write 도구 (apply patch + commit + push) + (B) reviewer SDK callable wire (F-3) 통합 |
| reviewer SDK 호출 패턴 | `nl_sdk_runtime` 패턴 재사용. 신규 세션, 사용자 NL turn 과 분리 |
| write 도구 범위 | **apply patch + commit + push** (PR 브랜치 컨텍스트 한정) |
| 명령 진입 경로 | **structured 우선 (`apply patch pr=N`, `commit pr=N`, `push pr=N`) + NL 보조** |
| 2단계 confirm | **모든 write 도구 + 기존 머지 정책 그대로**. confirm 다이얼로그에 dry-run 요약 (변경 파일·라인 수·SHA 목록) 포함 |
| destructive 가드 정책 단일 정의 | [`ai/dev_relay/tool_policy.py`](../../ai/dev_relay/tool_policy.py) `is_destructive` + 본 PRD 신규 헬퍼. write 도구별 화이트리스트/블랙리스트 §3.3.2 |
| 자동 롤백 | **없음** — atomic 보장만. 사용자 명시 명령 없이 워킹트리 되돌리기 X |
| 인증·credential 정책 | **구독 모드 우선 / API 키 fallback / 인증 실패 시 graceful degradation** (해당 도구만 비활성, 데몬 시작 안 막음) |
| 동시성 | `JobQueue` + `AgentRunner(max_workers=1)` — 상위 PRD 정책 그대로. NL 분기와는 독립 (`_nl_turn_lock` 별도) |
| shutdown 보호 | atomic op (apply/commit) graceful, push 는 watchdog. confirm 대기 작업은 무효화 + 다음 시작 시 안내 |
| 신규 audit kind | reviewer wire 2종 (`reviewer_sdk_invoked/returned`) + write 도구 13종 (§3.7) |
| 컴플라이언스 정책 단일 정의 | [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 재사용 (별도 셋 신설 금지) |
| 자동 커밋 메시지 정책 | 한글 1줄 위주 (`AGENTS.md` 컨벤션). 발사 직전 컴플라이언스 가드 — 위반 시 `commit_failed(compliance_blocked)` |
| `gh pr create` / PR 본문 자동 작성 | **본 PRD 비범위** — Phase 3 별도 PRD |
| 머지 후속 자동 액션 (릴리즈 노트·deployment) | **본 PRD 비범위** |
| 다중 사용자·멀티 인스턴스 | **본 PRD 비범위** — 1인 단일 인스턴스 전제 |
| SDK 비용 모니터링 가드 통합 | **본 PRD 비범위** — `cost-aware-llm-pipeline` 의 후속 PRD |

---

## 11. 참고

- 상위 PRD: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md)
- 선행 PRD: [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md)
- 인접 PRD: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md), [`docs/prd/dev-relay-nl-serialize.md`](./dev-relay-nl-serialize.md)
- 선행 PR (머지됨): #25 (MVP), #37 (`AgentRunner.shutdown(timeout)` watchdog), #43 (reviewer/merger 통합), #48 (NL 분기 직렬화), #49/#50/#51 (후속)
- 변경 대상 코드:
  - [`ai/dev_relay/main.py`](../../ai/dev_relay/main.py) `_build_reviewer` (격차 B wire)
  - [`ai/dev_relay/dispatcher.py`](../../ai/dev_relay/dispatcher.py) (write 도구 라우팅 추가)
  - [`ai/dev_relay/tool_policy.py`](../../ai/dev_relay/tool_policy.py) (destructive 가드 강화)
  - [`ai/dev_relay/slack_renderer.py`](../../ai/dev_relay/slack_renderer.py) (confirm 다이얼로그·결과 메시지)
  - [`ai/dev_relay/nl_classifier.py`](../../ai/dev_relay/nl_classifier.py) (NL 분기 write 도구 카테고리 추가)
  - `ai/dev_relay/agent_runner.py` (write 도구 SDK 호출 wrapper — `nl_sdk_runtime` 재사용)
- 정책 단일 정의 지점:
  - 컴플라이언스: [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS`
  - destructive: [`ai/dev_relay/tool_policy.py`](../../ai/dev_relay/tool_policy.py) `is_destructive`
  - 화이트리스트: [`ai/dev_relay/auth.py`](../../ai/dev_relay/auth.py)
- `AGENTS.md` — PRD 양식, 라벨 플로우, 컴플라이언스 원칙, DevOps push 게이트, 개발자 커밋 메시지 컨벤션
- 사용자 메모리 노트: 회사 Slack 동료 가시성, 봇 표시명에 트레이딩 도메인 노출 금지
