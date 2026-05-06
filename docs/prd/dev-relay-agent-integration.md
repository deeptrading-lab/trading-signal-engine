# PRD: Dev Manager — 에이전트 통합 (deferred AC 결합)

- **slug**: `dev-relay-agent-integration`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-06
- **UI 포함 여부**: **No** (별도 웹/네이티브 UI 없음. 외부 노출은 Slack 메시지·Block Kit 버튼만 — 상위 PRD `slack-dev-relay.md` 와 동일 정책)
- **상위 PRD**: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md)
- **트리거 Issue**: #28 — slack-dev-relay follow-up §2 항목 3
- **선행 PR (이미 머지)**: #25 (`feature/slack-dev-relay`), #37 (`AgentRunner` graceful shutdown)
- **선행 QA 리포트**: [`docs/qa/slack-dev-relay.md`](../qa/slack-dev-relay.md)

---

## 1. 배경 / 문제

상위 PRD `slack-dev-relay.md` 의 MVP 가치 정의는 "사용자가 PC 앞을 떠난 시간의 데드타임을 모바일로 회수한다" 이다. 그 가치가 실제로 발현되는 핵심 경로는 **모바일에서 PR 리뷰를 받고 → 같은 스레드에서 머지를 승인** 하는 한 사이클이다.

선행 PR #25 는 데몬 골격(Socket Mode 연결, 명령 라우팅, 큐 적재, 컴플라이언스 가드, 인증 모드 분기) 을 완성했고 QA 리포트 §0 / §1 에서 17건 AC 중 14건 PASS·3건 DEFERRED 로 머지됐다. 운영 진입에는 막지 않았지만 **DEFERRED 3건이 핵심 사이클의 본체**다 — reviewer/devops 에이전트 호출이 비어 있어 사용자가 명령을 보내도 "접수했습니다" 안내까지만 받고 PC 앞에서 다시 처리해야 한다.

본 PRD 는 이 격차를 채운다. 상위 PRD §3.3 에 사전 명시된 "후속 PRD 통합" 약속의 이행이다.

### 미충족 AC (재인용, 상위 PRD §5)

- **AC-4** — `review pr <N>` 결과 + Block Kit 버튼 (`[머지 검토]`, `[상세 보기]`). 현재 [`ai/dev_relay/main.py`](../../ai/dev_relay/main.py) `_handle_command` 의 review 분기는 큐 적재 + `TEMPLATE_QUEUE_ACCEPTED_REVIEW` 안내까지만. reviewer 에이전트 호출이 비어 있다.
- **AC-5 2단계** — `[승인]` 클릭 시 devops 에이전트가 실제 머지 수행. 현재 `handle_approve_merge` 는 audit 기록 + "승인 접수했습니다" 안내만 출력한다.
- **AC-14** — 동시성 두 번째 명령 큐 적재. `_handle_command` 의 `running_count >= 1` 분기는 코드에 있으나 reviewer 에이전트가 실제로 worker 를 점유하지 않으면 reproducible 하지 않다.

### 이미 사용 가능한 인프라 (재구현 금지)

- **`AgentRunner`** (`ai/dev_relay/agent_runner.py`): single-thread executor + destructive 가드(`assert_no_destructive_intent`) + watchdog 기반 graceful shutdown (PR #37 머지). `run_callable` 로 임의 callable 직렬 실행.
- **`JobQueue`** (`ai/dev_relay/queue.py`): SQLite 기반, idempotency_key, status 전이 (`pending → running → done/failed`).
- **`_handle_command`** 큐 적재 흐름 (`ai/dev_relay/main.py`): review/merge 둘 다 큐에는 들어가나 worker 가 picking 안 함.
- **`audit.jsonl`**, **reactions**, **NL 분기** 는 모두 정상 동작 — 본 PRD 에서 손대지 않는다.

---

## 2. 봇 네이밍 / 컴플라이언스 제약 재확인

상위 PRD §1 ("외부 노출 텍스트 네이밍 제약") 정책을 그대로 승계한다. 본 PRD 는 **새 봇·새 표시명·새 채널 라벨을 도입하지 않는다**. 다만 새로 추가되는 외부 노출 텍스트가 있으므로 다음 정책을 재확인한다.

- 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 단일 정의 지점을 그대로 재사용 (별도 키워드 셋 신설 금지).
- 본 PRD 가 새로 도입하는 다음 항목은 모두 같은 가드를 통과해야 한다:
  - reviewer 결과 메시지 본문(요약·발견 사항·푸터),
  - Block Kit 버튼 라벨(`[머지 검토]`, `[상세 보기]`, `[승인]`, `[취소]`) — 기존 라벨 외 신규 도입 시,
  - 머지 결과 메시지(성공 SHA, 실패 사유 분류 라벨 포함),
  - audit kind 명(`reviewer_started`, `reviewer_done`, …) — audit.jsonl 자체는 로컬 외부 경로지만 정책 일관성을 위해 동일 가드 적용,
  - 본 PRD 본문 자체.
- 본 PRD 본문에서도 봇을 통칭할 때는 "Dev Manager 봇" 으로 부른다.

---

## 3. 범위 (In Scope)

본 PRD 는 deferred AC 3건을 reproducible 하게 통합하는 데 한정한다. 운영 모니터링·로테이션·자동 시작은 별도 PRD (§4 비범위).

### 3.1 Worker 루프 (큐 → AgentRunner picking)

현재 `JobQueue` 는 `pending → running` 전이용 메서드를 보유하지만 `_handle_command` 가 적재만 하고 worker 가 picking 하지 않는다. 본 PRD 는 다음을 추가한다.

- **백그라운드 picker**: 데몬 시작 시 worker thread 1개를 띄워 `pending` 상태의 job 을 oldest-first 로 1건씩 꺼내 `AgentRunner.run_callable` 로 제출한다.
  - 동시 실행 1건 제약은 상위 PRD §3.4 결정사항을 그대로 승계 (`AgentRunner(max_workers=1)` 가 이미 강제).
  - picker 자체는 1초 간격 폴링으로 충분 (MVP 트래픽 1인 단독, 응답성 < 5초 충족).
- **상태 전이**: picker 가 job 을 꺼낼 때 `pending → running`, callable 결과에 따라 `running → done` 또는 `running → failed` 로 갱신.
- **재시작 복구**: 데몬 시작 시 `running` 으로 남은 job 은 기본적으로 `failed` 마킹 + 사용자 안내 (상위 PRD §3.4 정책 승계).
  - **단, 머지 job 의 carve-out**: `merge_started` audit 라인이 있고 `merge_done`/`merge_failed` 가 없는 job 은 GitHub 측에서 이미 머지가 성사됐을 가능성이 있으므로 `failed` 로 단순 마킹하지 않는다. 대신 `unknown` 상태로 남기고 §7.4 의 안내 메시지("이전 세션에서 진행되던 머지 1건의 결과를 확인하지 못했습니다. PR <N> 을 직접 확인해 주세요.") 를 사용자에게 발사한다. reconcile 자동화는 본 PRD 비범위 (§6.3) — 사용자가 GitHub 에서 직접 확인 후 다음 액션 결정.
- **shutdown 보호**: SIGINT/SIGTERM 수신 시 picker 는 즉시 신규 picking 을 중단하고, 진행 중 job 1건은 `AgentRunner.shutdown(wait=True, timeout=...)` 를 통해 graceful 하게 마치도록 한다 (PR #37 watchdog 흐름 활용).

### 3.2 reviewer 에이전트 호출 (AC-4)

- **트리거**: picker 가 `command` 가 `review pr <N>` 형태인 job 을 꺼냈을 때.
- **세션**: Claude Agent SDK 신규 세션을 시작 (NL 분기와 분리 — 본 PRD 의 reviewer 호출은 thread session 을 resume 하지 않는다).
- **인풋**: PR 번호 + 리뷰 instruction (코드 퀄리티 / 아키텍처 / 클린 코드 / 보안 관점, `docs/rules/review.md` 참조). 실제 PR diff 수집은 SDK 가 보유한 `gh` / GitHub API tool 사용을 우선 가정 — 백엔드 구현 시 가장 단순한 경로(예: `gh pr diff <N>` 결과를 prompt 컨텍스트로 주입) 선택.
- **결과 발사**: 같은 Slack 스레드(`thread_ts`) 로 결과 메시지 1건을 발사한다. 메시지에는:
  - 요약 2~3 문장,
  - 발견 사항 최대 3건 (없으면 "특이사항 없음"),
  - Block Kit 버튼 두 개 (`[머지 검토]`, `[상세 보기]`).
- **`[머지 검토]` 버튼 payload**: 기존 `merge_review` action_id 재사용. **value 에 PR 번호를 포함** 해야 한다 — 현재 `handle_merge_review` 는 PR 번호 미보유 (§5 위험 §1 참조).
- **`[상세 보기]` 버튼 payload**: `value` 에 `job=<job_id>` 패턴을 포함시켜, 클릭 핸들러가 audit / 결과 캐시에서 발견 사항 본문을 lookup 한 뒤 같은 스레드에 후속 메시지로 발사한다 (잘림 없이, Block Kit 50개 한도 초과 시 추가 메시지로 분할 — §7.6 참조). 외부 페이지 이동·웹훅 호출 금지 (Slack 외부로 페이로드 누설 방지). 본문 lookup 실패 시 (예: 데몬 재시작으로 캐시 유실) "원본 결과를 더 이상 표시할 수 없습니다. 다시 `review pr <N>` 을 실행해 주세요." 안내 + audit `reviewer_detail_lookup_failed` 1줄 — 이 안내 자체도 컴플라이언스 가드 통과 필수.
- **컴플라이언스 가드**: 메시지·버튼·footer 모두 `slack_renderer` 의 발사 직전 가드 통과. SDK 가 도메인 키워드를 출력에 포함시킨 경우 가드가 매치하면 발사 차단 + ERROR 로그 + 사용자에게 "응답 생성 중 오류가 발생했어요" 중립 fallback (상위 PRD §3.7 정책 재사용).

### 3.3 devops 에이전트 호출 (AC-5 2단계)

- **트리거**: `handle_approve_merge` 가 `[승인]` 버튼 클릭을 받았을 때.
- **인풋**: 버튼 payload 의 `value` 에서 PR 번호와 `idempotency_key:job_id` 를 복원.
- **수행**: PR 머지 (예: `gh pr merge <N> --squash --delete-branch` 또는 동등 동작). 정확한 머지 전략은 `AGENTS.md` §"DevOps" 의 push 게이트 정책과 정합되어야 한다 — Backend Dev 가 구현 시 저장소 컨벤션을 따라 단일 전략(squash 우선) 을 선택하고 PR 본문에 명시.
- **destructive 가드와의 협업** (중요):
  - `assert_no_destructive_intent` 는 dispatcher 와 SDK 입출력 텍스트에 대해 destructive 표지를 검사한다. 머지는 **의도적 destructive op** 이므로 본 가드를 그대로 적용하면 차단된다.
  - 결정 (PM): 머지 호출은 `AgentRunner.run_callable` **를 거치지 않고 별도 경로**로 실행한다. 이유는 (a) 머지가 SDK 출력의 텍스트에 의존하지 않는 결정형 op 이고, (b) `AgentRunner` 의 destructive 가드는 SDK 출력의 후속 명령 제안을 막기 위한 안전망이지 사용자가 명시적으로 승인한 머지를 막기 위한 것이 아니기 때문이다.
  - 머지 경로는 별도 함수 `_perform_merge(pr_number, idempotency_key, job_id)` 로 분리하고, dispatcher 의 destructive 가드 화이트리스트에 `merge` 명령은 이미 허용되어 있음을 재확인 (현행 `is_destructive` 는 `git reset --hard`, `force push`, `branch -D`, `clean -f` 등을 막을 뿐 `gh pr merge` 는 막지 않는다 — 회귀 테스트로 보장).
  - **추가 안전망**: `_perform_merge` 는 `[승인]` 버튼 페이로드 검증(화이트리스트 user_id, action_id 매칭, value 의 idempotency_key 일치) 을 통과한 경우에만 호출된다. 외부에서 임의 호출 가능한 entry point 가 되어선 안 된다.
- **결과 발사**: 같은 스레드에 머지 결과 메시지.
  - 성공: 머지 SHA + 머지 전략 + 브랜치 정리 결과 1줄.
  - 실패: 분류 라벨(예: `permission_denied`, `mergeable_state=behind`, `checks_failed`, `network_error`) + 원문 sanitize 후 1~2 문장.

### 3.4 동시성 (AC-14)

- **시나리오 reproducibility**: §3.1 worker 루프 도입 후, `review pr 22` 호출이 SDK 응답 대기 중일 때 두 번째 `review pr 23` 명령이 들어오면:
  1. 첫 명령이 `running` 으로 picker 에게 점유됨.
  2. 두 번째 명령이 `_handle_command` 진입 시 `running_count >= 1` 분기에 도달.
  3. 봇이 `TEMPLATE_QUEUE_BUSY.format(pending=N)` 안내 발사 + 두 번째 job 은 `pending` 상태로 적재.
  4. 첫 작업 완료 후 picker 가 두 번째 job 을 자동 시작.
- **테스트 전략**: 통합 테스트에서 SDK 호출을 sleep 으로 대체한 fake callable 을 주입해 reproducibility 확보 (§7 참조).

### 3.5 결과 / 실패 발사

모든 외부 발사는 같은 `thread_ts` 를 유지한다 (NL 분기와 동일 패턴). 실패 분류는 다음 5가지로 한정 — 그 외는 `unknown_error` 로 fallback.

| 분류 | 트리거 | 사용자 노출 메시지 (예시) |
|------|--------|---------------------------|
| `destructive_blocked` | `assert_no_destructive_intent` raise | "이 작업은 PC에서 직접 처리해 주세요." |
| `sdk_timeout` | SDK 호출이 watchdog timeout 초과 | "응답이 지연되어 작업을 중단했어요. 다시 시도해 주세요." |
| `github_unauthorized` | `gh` / API 401·403 | "PR 접근 권한이 없습니다. 토큰 권한을 확인해 주세요." |
| `github_unprocessable` | `gh` / API 422 (mergeable=false 등) | "머지 조건을 충족하지 못했습니다 (예: 충돌·체크 실패)." |
| `compliance_blocked` | `slack_renderer` 가드가 발사 차단 | "응답 생성 중 오류가 발생했어요. 다시 시도해 주세요." |

각 분류는 audit 에 별도 kind 로 기록 (§3.6).

### 3.6 신규 audit kind

상위 PRD §3.6 의 audit 형식을 그대로 따르되, 다음 kind 를 추가한다.

```
reviewer_started              {ts, kind, job_id, pr}
reviewer_done                 {ts, kind, job_id, pr, duration_s, finding_count}
reviewer_failed               {ts, kind, job_id, pr, classification}   # §3.5 표의 분류
reviewer_detail_lookup_failed {ts, kind, job_id, pr}                   # [상세 보기] 클릭 시 본문 lookup 실패 (§3.2)
merge_started                 {ts, kind, job_id, pr}
merge_done                    {ts, kind, job_id, pr, sha, strategy}
merge_failed                  {ts, kind, job_id, pr, classification}
```

- 모든 라인은 ISO-8601 KST timestamp + user_id 마스킹 정책 승계.
- `reviewer_*` kind 는 `command_received(review pr N)` 와 `job_started/job_done` 사이에 끼어든다 (이중 기록 X — `job_started/done` 은 worker 루프 단의 generic 라이프사이클이고 `reviewer_*` 는 reviewer 호출 단의 도메인 이벤트).

---

## 4. 비범위 (Out of Scope)

- **운영 모니터링 일반** — quota 진단, audit 로테이션, launchd plist 자동 설치, 비용 가드 통합. 모두 별도 PRD.
- **상위 PRD §4 의 비범위 항목** — 트레이딩 코어 명령, 클라우드 배포, 멀티유저, Slash 커맨드, 채널 멘션 응답, 토큰 회전 자동화 — 본 PRD 에서도 그대로 비범위.
- **`implement <slug>`, `qa <slug>`, `pipeline <slug>` 명령 추가** — 상위 PRD 부록 C 의 향후 확장. 본 PRD 는 기존 3개 명령(`status`, `review pr <N>`, `merge pr <N>`) 의 deferred 통합만 다룬다.
- **NL 분기와의 통합** — `dev-relay-natural-language.md` 가 도입한 자연어 진입과 본 PRD 의 reviewer/devops 호출은 **별도 경로**다. NL 세션에서 reviewer 를 호출하는 시나리오는 후속 PRD.
- **머지 전략 다중화** — squash / merge commit / rebase 중 단일 전략 채택 (Backend Dev 결정). 다중 전략 선택 UI 는 본 PRD 범위 밖.
- **머지 후속 자동 액션** — branch 정리 외 추가 작업(릴리즈 노트 자동 생성, deployment trigger 등) 은 본 PRD 범위 밖.
- **PR diff 수집 방법의 정확한 명세** — `gh pr diff` 인지 GitHub API 인지 SDK 의 builtin tool 인지는 Backend Dev 가 구현 시 결정. PRD 는 의도만 고정.

---

## 5. 수용 기준 (Acceptance Criteria)

상위 PRD AC-4 / AC-5(2단계) / AC-14 를 그대로 reuse 하고, 본 PRD 가 추가로 보장해야 하는 항목을 신규 AC 로 명시한다. 번호는 본 PRD 내부 번호 (상위 PRD AC 번호와 분리).

### AC-INT-1 (= 상위 AC-4). reviewer 결과 + Block Kit 버튼

- **재현**: 본인이 DM 에 `review pr <N>` 입력 후, 선행 큐 적재 안내(상위 AC-3) 다음 reviewer 처리 종료까지 대기.
- **기대**:
  - 같은 스레드에 결과 메시지 1건이 발사된다.
  - 메시지에는 (a) 2~3 문장 요약, (b) 발견 사항 최대 3건(없으면 "특이사항 없음"), (c) `[머지 검토]` `[상세 보기]` 버튼 두 개 가 모두 포함된다.
  - audit.jsonl 에 `reviewer_started` → `reviewer_done` 두 라인이 순서대로 기록된다.
  - `[머지 검토]` 버튼의 payload `value` 에 PR 번호가 포함되어 있다 (이후 AC-INT-2 의 사전조건).

### AC-INT-2 (= 상위 AC-5 2단계). `[승인]` → 실 머지

- **재현**: AC-INT-1 결과의 `[머지 검토]` 클릭 → confirm 다이얼로그 (`[승인]` `[취소]`) 등장 → `[승인]` 클릭.
- **기대**:
  - devops 호출 경로(`_perform_merge`) 가 `gh pr merge` 동등 동작을 수행해 PR 이 실제로 머지된다.
  - 같은 스레드에 머지 결과 메시지(성공 SHA + 전략 / 또는 §3.5 분류 + 사유) 가 발사된다.
  - audit.jsonl 에 `button_action(merge_review)` → `button_action(approve_merge)` → `merge_started` → `merge_done` (또는 `merge_failed`) 가 순서대로 기록된다.
  - 머지 실패 시 사용자에게 노출되는 메시지는 §3.5 표의 분류 라벨 중 하나에 매핑된다.

### AC-INT-3 (= 상위 AC-14). 동시성 두 번째 명령 큐 적재

- **재현**: AC-INT-1 의 reviewer 처리 진행 중에 본인이 `review pr <M>` 추가 입력.
- **기대**:
  - 두 번째 명령에 대해 5초 이내 첫 응답: `TEMPLATE_QUEUE_BUSY` 본문 + 대기 1건.
  - 첫 작업 완료 후 두 번째 job 이 자동으로 `running` 으로 전이.
  - audit.jsonl 에 두 작업 모두 `command_received` → `job_started` → `reviewer_*` → `job_done` 사이클이 기록.

### AC-INT-4. Worker 루프 가용성

- **재현**: 데몬 시작 직후 `pending` 으로 남아 있는 job 이 없을 때, `review pr <N>` 명령 1건 입력.
- **기대**:
  - 5초 이내 picker 가 `pending → running` 전이를 수행 (job 이 picker 의 다음 폴링 주기 안에 잡힌다).
  - shutdown 시 picker 는 신규 picking 을 중단하고, 진행 중 job 은 `AgentRunner.shutdown(wait=True, timeout=...)` 의 watchdog 정책을 그대로 따른다.

### AC-INT-5. 실패 분류 보고

- **재현**: 다음 시나리오를 fake/mock 으로 강제 — (a) SDK callable 이 `DestructiveOperationBlocked` raise, (b) SDK 호출 timeout, (c) `gh` 401, (d) `gh` 422, (e) `slack_renderer` 가드가 발사 차단.
- **기대**: 각 시나리오마다 §3.5 표의 분류에 정확히 매칭되는 사용자 노출 메시지 + audit `reviewer_failed` 또는 `merge_failed` 라인이 기록된다. 분류 외 케이스는 `unknown_error` 로 fallback.

### AC-INT-6. audit 신규 kind 기록

- **재현**: AC-INT-1 + AC-INT-2 정상 흐름 1회 완주.
- **기대**: audit.jsonl 에 §3.6 의 6개 신규 kind (`reviewer_started`, `reviewer_done`, `reviewer_failed`, `merge_started`, `merge_done`, `merge_failed`) 중 정상 흐름에 해당하는 4개 (`reviewer_started`, `reviewer_done`, `merge_started`, `merge_done`) 가 모두 등장.

### AC-INT-7. destructive 가드 회귀

- **재현**: 본인이 DM 에 `git reset --hard HEAD~5`, `force push main` 등 dispatcher 1차 차단 대상 입력.
- **기대**:
  - dispatcher 가 unknown command fallback 또는 destructive_blocked 로 처리 (상위 AC-13 회귀).
  - 본 PRD 가 도입한 `_perform_merge` 경로가 위 입력으로 절대 호출되지 않음 (단위 테스트로 보장).
  - `gh pr merge` 호출은 dispatcher 가드를 우회하지 않으며, `is_destructive` 는 `gh pr merge` 를 destructive 로 분류하지 않음을 회귀 테스트로 명시.

### AC-INT-8. 컴플라이언스 회귀

- **재현**: AC-INT-1 ~ AC-INT-6 의 모든 봇 응답 텍스트, 신규 Block Kit 버튼 라벨, audit 신규 kind 명, 본 PRD 본문, 본 PRD 구현 PR 본문, 커밋 메시지를 정적 스캔.
- **기대**: 도메인 키워드(대소문자 무시) 단 한 곳도 등장하지 않음. `ai/tests/dev_relay/test_compliance.py` 의 정적 검사가 본 PRD 의 신규 산출물도 커버하도록 확장됐다.

---

## 6. 가정 · 제약

### 6.1 기술

- 상위 PRD §6.1 의 환경(Python 3.11+, `slack-bolt`, `claude-agent-sdk`, `sqlite3` 표준 라이브러리) 그대로 승계. 신규 의존성 추가 없음.
- `gh` CLI 가 로컬에 설치·인증되어 있어야 한다 (`gh auth status` 통과). 인증되어 있지 않으면 `_perform_merge` 는 즉시 `github_unauthorized` 분류로 실패하고 사용자에게 안내.
- Claude Agent SDK 인증은 상위 PRD 의 구독 모드 / API 키 모드 분기를 그대로 사용. 본 PRD 가 모드를 새로 추가하지 않는다.

### 6.2 비용 / 한도

- reviewer 호출은 PR 1건당 SDK 토큰 비용을 발생시킨다. MVP 동시 1건 + 본인 단독 사용 가정에서 일일 호출 수는 제한적이지만, 비용 모니터링 가드는 본 PRD 범위 밖 (별도 PRD `cost-aware-llm-pipeline` 통합).
- 구독 모드(Max 20x) 는 quota 가 있으므로 watchdog timeout 도달이 아닌 quota 거절도 발생할 수 있다. 본 PRD 는 quota 거절을 §3.5 의 `sdk_timeout` 또는 `unknown_error` 로 fallback 처리하며, quota 진단 자체는 별도 PRD.

### 6.3 보안

- 머지는 사용자가 명시적으로 `[승인]` 을 누른 경우에만 실행. 자동 머지 경로는 도입하지 않음.
- `_perform_merge` 는 외부 임의 호출 가능한 entry point 가 아님 — Slack `block_actions` 핸들러 내에서만 호출되며, 호출 직전 화이트리스트 + payload 일치 검증을 통과해야 한다 (상위 PRD §3.5 의 replay 방지 정책 그대로 승계).
- shutdown 중 진행 중인 머지는 `AgentRunner.shutdown(wait=True, timeout=...)` 의 watchdog 정책을 따른다 — `gh pr merge` 호출이 외부 네트워크에 도달한 후 응답을 못 받고 timeout 되는 경우, 머지가 실제로 완료됐는지 여부는 다음 데몬 시작 시 `gh pr view <N> --json mergedAt` 로 재확인하는 reconcile 단계가 권장되지만 본 PRD 는 그 reconcile 을 강제하지 않는다 (별도 PRD).

### 6.4 일정 / 운영

- 로컬 데몬이므로 배포·CI 변경 없음. DevOps 의 push 게이트(`AGENTS.md`) 는 평소대로.
- 본 PRD 머지 후 상위 Issue #28 §2 항목 3 은 종료된 것으로 간주. 동일 Issue 의 항목 1·2 (있는 경우) 는 본 PRD 와 무관.

---

## 7. 위험 / 의존

1. **`merge_review` 버튼 payload 에 PR 번호 부재** (현행 `ai/dev_relay/main.py` `handle_merge_review`):
   - 현재 payload 검증 흐름은 user_id·action_id 만 보고 PR 번호 / `idempotency_key:job_id` 매핑이 없다.
   - 본 PRD 는 `[머지 검토]` 버튼을 reviewer 결과 메시지에서 발사할 때 `value` 에 `pr=<N>;key=<idempotency_key>;job=<job_id>` 패턴을 포함시켜야 한다. confirm 다이얼로그 발사 → `[승인]` 클릭 → `_perform_merge` 까지 PR 번호가 전파되어야 함.
   - 회귀 위험: 기존 `merge pr <N>` 단독 호출 흐름의 confirm 다이얼로그도 동일 patten 으로 통일 (이미 일부 사용 중인지 Backend Dev 가 첫 단계로 확인 필요).
2. **Claude Agent SDK 토큰·구독 한도**: 위 §6.2 참조. quota 거절 시 사용자에게 노출되는 메시지가 도메인 키워드를 포함하지 않도록 `slack_renderer` 가드가 SDK 출력의 raw 메시지를 직접 노출하지 않고 분류 라벨만 노출해야 한다.
3. **GitHub `gh` CLI 권한**: §6.1 참조. `gh auth status` 미통과 시 fail-fast 가 아니라 `_perform_merge` 호출 시점에 `github_unauthorized` 로 분류 (데몬 시작 자체는 막지 않음 — reviewer 만 사용하는 사용자도 있을 수 있음).
4. **shutdown 중 진행 중 머지 보호**: 위 §6.3 참조. 본 PRD 는 reconcile 을 강제하지 않으며, shutdown 시점에 `merge_started` 후 `merge_done`/`merge_failed` 가 기록되지 않은 job 은 다음 시작 시 사용자에게 "이전 세션에서 진행되던 머지 1건의 결과를 확인하지 못했습니다. PR <N> 을 직접 확인해 주세요." 안내. 이 안내 자체가 도메인 키워드를 포함하지 않도록 컴플라이언스 가드 통과 필수.
5. **destructive 가드 회귀 — `gh pr merge` 분류**: 본 PRD 는 `gh pr merge` 가 dispatcher 의 destructive 분류에 들어가지 않음을 가정한다. 현행 `is_destructive` 가 이를 보장하는지 Backend Dev 첫 단계로 회귀 테스트 추가.
6. **reviewer 결과의 길이 한계**: Slack 단일 메시지 본문은 약 40k 자, Block Kit 블록은 50개 한도. 발견 사항이 길면 `[상세 보기]` 후속 메시지로 분할 (§3.2 명시).
7. **NL 분기와의 의존 회피**: 본 PRD 의 reviewer/devops 호출은 NL 세션 (`AgentSessionStore`) 에 영향을 주지 않으며, NL 세션 만료 정책과 별개로 동작해야 한다. 단위 테스트로 회귀 보장.

---

## 8. 테스트 전략 개요

QA 가 본 PRD AC 를 검증하기 위한 1차 가이드. 정확한 테스트 항목은 QA 산출물(`docs/qa/dev-relay-agent-integration.md`) 이 주도한다.

### 8.1 자동 (단위 + 통합)

- **단위**: picker 의 `pending → running → done/failed` 전이 (fake `JobQueue` + fake callable), `_perform_merge` 의 화이트리스트·payload 검증, §3.5 실패 분류 매핑, audit 신규 kind 6종 직렬화.
- **통합 (mock 기반)**: Claude Agent SDK 호출과 `gh` 호출을 mock 으로 대체한 채 다음 시나리오 1회 완주 — `review pr <N>` → 결과 메시지 + 버튼 → `[머지 검토]` → `[승인]` → 머지 결과. 동시성 시나리오 (AC-INT-3) 도 fake callable 의 sleep 으로 강제.
- **회귀**: 기존 301 PASS 테스트 (PR #25 기준) + AgentRunner 추가 테스트가 본 PRD 변경 후에도 0 fail 유지. 컴플라이언스 정적 검사가 본 PRD 본문·신규 audit kind·신규 메시지를 모두 커버.

### 8.2 수동 (사용자 검증)

상위 PRD 부록 A 셋업이 완료된 환경에서 다음 한 사이클을 1회 수행 — 모바일 Slack 앱에서 `review pr <N>` → 같은 스레드에서 reviewer 결과 + 발견 사항 + 버튼 확인 → `[머지 검토]` → confirm → `[승인]` → 같은 스레드에서 머지 결과 확인. 결과 메시지·버튼 라벨·실패 분류 라벨이 도메인 키워드를 포함하지 않음을 육안 확인.

---

## 9. 참고

- 상위 PRD: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md)
- 선행 QA 리포트: [`docs/qa/slack-dev-relay.md`](../qa/slack-dev-relay.md)
- 트리거 Issue: #28 (저장소 Issues 탭에서 동일 번호 검색)
- 선행 PR (이미 머지): #25, #37
- 인접 PRD: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md) — NL 분기 (본 PRD 와 별도 경로)
- 정책 단일 정의 지점: [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS`
- AgentRunner 인프라: [`ai/dev_relay/agent_runner.py`](../../ai/dev_relay/agent_runner.py)
- JobQueue 인프라: [`ai/dev_relay/queue.py`](../../ai/dev_relay/queue.py)
- 명령 라우팅 / dispatcher: [`ai/dev_relay/dispatcher.py`](../../ai/dev_relay/dispatcher.py), `_handle_command` in [`ai/dev_relay/main.py`](../../ai/dev_relay/main.py)
- `AGENTS.md` — PRD 양식, 라벨 플로우, 컴플라이언스 원칙, DevOps push 게이트

---

## 10. PM 결정사항 요약 (구현·QA 가 한눈에 보도록)

| 항목 | 결정 |
|------|------|
| 본 PRD 의 책임 범위 | 상위 PRD AC-4 / AC-5(2단계) / AC-14 의 reproducible 통합만 |
| Worker 루프 도입 위치 | 데몬 시작 시 백그라운드 thread 1개 — picker. `JobQueue.pending` 을 1초 폴링 |
| reviewer 호출 패턴 | `AgentRunner.run_callable` 경유. 입력은 PR 번호 + 리뷰 instruction, 출력은 같은 스레드 메시지 + Block Kit 버튼 |
| 머지 호출 패턴 | `_perform_merge` — `AgentRunner` 우회. dispatcher destructive 가드는 `gh pr merge` 를 차단하지 않음 (회귀 테스트로 보장) |
| `[머지 검토]` 버튼 payload | `value` 에 `pr=<N>;key=<idempotency_key>;job=<job_id>` 포함 — 현행 부재 항목 보강 |
| 실패 분류 라벨 (§3.5) | 5개 (`destructive_blocked`, `sdk_timeout`, `github_unauthorized`, `github_unprocessable`, `compliance_blocked`) + `unknown_error` fallback |
| audit 신규 kind | 6개 (`reviewer_started/done/failed`, `merge_started/done/failed`) |
| 운영 모니터링 / launchd / 비용 가드 | **본 PRD 비범위** — 별도 PRD |
| NL 분기와의 결합 | **본 PRD 비범위** — NL 세션은 reviewer/devops 호출에 영향을 주지 않음 |
| 머지 전략 | **squash 고정** — `git log --oneline main` 최근 12 PR 모두 squash 패턴(`(#NN)` 단일 커밋). `gh pr merge <N> --squash --delete-branch` 동등 동작 사용 |
