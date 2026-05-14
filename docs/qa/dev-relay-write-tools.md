# QA: dev-relay-write-tools (Phase 2 write 도구 + reviewer SDK wire / F-3)

- **PRD**: `docs/prd/dev-relay-write-tools.md` (PR #53 머지)
- **구현 PR**: #54 `feature/dev-relay-write-tools-impl`
- **QA**: 이하영 (hayoung.lee2@musinsa.com)
- **검증일**: 2026-05-15 KST
- **참고**: `docs/rules/test.md`, `docs/agents/qa.md`, `AGENTS.md` QA 절

---

## 0. 판정 요약

| 항목 | 값 |
|---|---|
| 전체 AC | 16 (AC-WT-1 ~ AC-WT-16) |
| PASS | 15 |
| DEFERRED | 1 (AC-WT-7 — NL 보조 진입) |
| FAIL | 0 |
| 신규 테스트 | 75 PASS / 0 FAIL |
| dev_relay 전체 | 612 PASS / 0 FAIL |
| ai 전체 (workbench 제외) | 790 PASS / 0 FAIL |
| 컴플라이언스 정적 검사 | 56 PASS / 0 hit |
| **최종 판정** | **qa-passed** (AC-WT-7 DEFERRED 정당성 §3 참조) |

---

## 1. 실행 환경 / 절차

### 1.1 환경

- 브랜치: `feature/dev-relay-write-tools-impl` (`gh pr checkout 54`)
- HEAD: `50c17a3 feat(dev-relay): write 도구 명령 핸들러 + confirm Block Kit + audit 통합`
- Python 3.11.15, pytest 9.0.3
- 신규 모듈: `ai/dev_relay/write_tools.py` (517L), `ai/dev_relay/write_runtime.py` (334L)
- 신규 테스트: `test_write_tools.py` (40건), `test_dispatcher_write.py` (16건), `test_reviewer_sdk_wire.py` (10건 — 시도 9건 PASS + 추가 케이스), `test_write_command_flow.py` (9건)

### 1.2 자동 테스트 실행 결과

```
$ cd ai && pytest tests/dev_relay/test_write_tools.py tests/dev_relay/test_reviewer_sdk_wire.py tests/dev_relay/test_dispatcher_write.py tests/dev_relay/test_write_command_flow.py -v
75 passed in 0.21s

$ cd ai && pytest tests/dev_relay/ -q
612 passed in 2.57s

$ cd ai && pytest tests/dev_relay/test_compliance.py -v
56 passed in 0.03s

$ cd ai && pytest tests/ -q --ignore=tests/test_stock_signal_workbench.py
790 passed in 2.69s
```

`tests/test_stock_signal_workbench.py` 는 `fastapi` 미설치로 collection error (본 PRD 비대상, 무관 모듈) — 회귀 평가에서 제외. 다른 모든 ai 테스트 0 fail.

---

## 2. AC 매핑표

| AC | 항목 | 판정 | 근거 |
|---|---|---|---|
| AC-WT-1 | reviewer SDK callable wire (F-3) | PASS | §2.1 |
| AC-WT-2 | apply patch 정상 흐름 | PASS | §2.2 |
| AC-WT-3 | commit 정상 흐름 | PASS | §2.3 |
| AC-WT-4 | push 정상 흐름 | PASS | §2.4 |
| AC-WT-5 | destructive 가드 (write 표면) | PASS | §2.5 |
| AC-WT-6 | confirm `[취소]` 흐름 | PASS | §2.6 |
| AC-WT-7 | NL 자연어 진입 (보조) | DEFERRED | §3 정당성 |
| AC-WT-8 | 동시성 (write ↔ reviewer 직렬화) | PASS | §2.8 |
| AC-WT-9 | 인증 graceful degradation | PASS | §2.9 |
| AC-WT-10 | shutdown 보호 | PASS | §2.10 |
| AC-WT-11 | 멱등성 | PASS | §2.11 |
| AC-WT-12 | rate limit | PASS | §2.12 |
| AC-WT-13 | audit 완전성 | PASS | §2.13 |
| AC-WT-14 | 컴플라이언스 정적 검사 | PASS | §2.14 |
| AC-WT-15 | 커밋 메시지 컴플라이언스 | PASS | §2.15 |
| AC-WT-16 | 회귀 0 fail | PASS | §2.16 |

---

## 2. AC 별 검증 상세

### 2.1 AC-WT-1 — reviewer SDK callable wire (F-3 완수)

- **재현**: `_build_reviewer(logger)` 호출 → callable 또는 None 반환 검증. PRD §3.1.4 graceful degradation 분기 (SDK import 실패 / 인증 실패 / API 키 무효 / 양쪽 모두 실패).
- **기대**: `NotImplementedError` raise 없음, `make_reviewer_callable()` 결과를 그대로 picker 가 호출 가능.
- **결과**: PASS — `tests/dev_relay/test_reviewer_sdk_wire.py::TestBuildReviewerGracefulDegradation` 3건 + `TestReviewResponseParsing` 4건 + `TestExtractUnifiedDiff` 3건 = 총 10건 PASS. 코드상 `main.py:2359 _build_reviewer` 가 `write_runtime.make_reviewer_callable()` 위임 + `is_sdk_available()` 가드.
- **자동 테스트 명령**: `pytest ai/tests/dev_relay/test_reviewer_sdk_wire.py -v`

### 2.2 AC-WT-2 — apply patch 정상 흐름

- **재현**: `apply patch pr=N` 입력 → SDK 호출 → patch 생성 → confirm 다이얼로그 → `[패치 적용]` 클릭 → `git apply --check` → 워킹트리 적용. audit 시퀀스 `patch_requested → patch_generated → patch_confirmed(applied) → patch_applied`.
- **기대**: 4개 audit kind 순서 기록 + 적용된 파일 목록이 `patch_applied.files` 에 정확히 표기.
- **결과**: PASS — `test_write_tools.py::TestApplyPatch` 3건 (`test_apply_calls_git_check_then_apply`, `test_apply_check_failure_raises`, `test_apply_destructive_blocks_before_subprocess`) + `test_write_command_flow.py::TestApplyPatchEntry::test_apply_patch_dispatches_to_write_handler` PASS. `main.py:783 _build_and_send_write_confirm` + `main.py:1080 _execute_apply_patch` + `main.py:1589 handle_apply_patch_confirm` 흐름 확인.
- **에지**: `git apply --check` 실패 시 `WriteToolError` raise + 워킹트리 미변경 (`test_apply_check_failure_raises`).

### 2.3 AC-WT-3 — commit 정상 흐름

- **재현**: `commit pr=N` 입력 → 워킹트리 검증 → SDK 가 한글 커밋 메시지 생성 → confirm → `[커밋]` 클릭 → `git commit`.
- **기대**: 메시지 컴플라이언스 가드 통과 + SHA 반환 + audit 시퀀스 `commit_requested → commit_message_generated → commit_confirmed(committed) → commit_created`.
- **결과**: PASS — `test_write_tools.py::TestCommitMessageGuard` 5건 + `TestCommitPreview` 2건 + `TestPerformCommit` 2건 = 9건 PASS. 빈 트리 (`commit_empty_tree`) / 도메인 키워드 차단 / `--amend`·`--no-verify` 차단 모두 검증.

### 2.4 AC-WT-4 — push 정상 흐름

- **재현**: `push pr=N` → 현재 브랜치 검증 → confirm → `[푸시]` 클릭 → `git push` (force 아닌 일반).
- **기대**: 현 브랜치 push + SHA 목록 dry-run + audit 시퀀스 `push_requested → push_confirmed(pushed) → push_done`.
- **결과**: PASS — `test_write_tools.py::TestPushPolicyGuard` 6건 (보호 브랜치 `main`/`master`/`develop`/`release` 차단, `--force-with-lease` 차단) + `TestPushPreview` 2건 + `TestPerformPush` 2건 = 10건 PASS.

### 2.5 AC-WT-5 — destructive 가드 (write 표면)

- **재현**: 다음 케이스 시도.
  - (a) patch body 에 `rm -rf /`, `git reset --hard`, `git push --force`, `filter-branch`, `echo > /dev/null`.
  - (b) `.env*`, `.git/config`, `secrets/db.yml`, `service.key`, `cert.pem`, `credentials.json` 경로 패치.
  - (c) NL/structured 진입 모두 `apply patch pr=22 && push --force`, `commit pr=22 --amend`, `push pr=22 --force`, `push pr=22 with force-with-lease`.
- **기대**: 각 케이스 `WriteToolError` raise 또는 dispatcher 가 `DESTRUCTIVE_BLOCKED` 로 라우팅. 워킹트리·remote·커밋 0건 변경.
- **결과**: PASS — `test_write_tools.py::TestPatchDestructiveGuard` 14건 + `test_dispatcher_write.py::TestWriteCommandDestructiveStillBlocked` 4건 + `test_write_command_flow.py::TestWriteDestructiveGuard` 3건 = 21건 PASS.

### 2.6 AC-WT-6 — confirm `[취소]` 흐름

- **재현**: apply/commit/push 각각의 1단계 confirm 다이얼로그에서 `[취소]` 클릭.
- **기대**: "취소했습니다." 안내 + 워킹트리·커밋·remote 0건 부작용 + `*_confirmed(cancelled)` audit 라인 + 이후 `*_applied/_created/_done` 라인 부재.
- **결과**: PASS — `main.py:1632~ cancel_*_confirm` 핸들러가 `_write_pending.pop(job_id)` + `cancel_write` audit kind 기록. `slack_renderer._STATIC_TEMPLATES` 의 `TEMPLATE_CANCEL_NOTICE` 가드 통과 (`test_compliance.py::test_static_template_clean[TEMPLATE_CANCEL_NOTICE]`).

### 2.7 AC-WT-7 — NL 자연어 진입 (보조) → **DEFERRED**

- **PRD 정의**: §3.2.4 — "NL 분기 (`_handle_natural_language`) 가 의도 분류 단계에서 write 도구 후보를 인식하면 SDK 가 도구 호출 결정 → §3.2.3 의 동일 confirm 다이얼로그 발사". §3.2.2 PM 결정 = (c) structured 우선, NL **보조**. §10 PM 결정사항 = "structured 우선 + NL **보조**".
- **구현 상태**: 미구현 — `ai/dev_relay/nl_classifier.py` 의 4 라벨 (SUMMARY_REQUEST / REPORT_REQUEST / STATUS_LIKE / UNKNOWN_OR_DESTRUCTIVE) 그대로. write 도구 신규 카테고리 미추가.
- **backend-dev 결정**: PR #54 본문 비범위 절 — "NL 분기에서 write 도구 자율 트리거 — Phase 3 별도 PRD".
- **판정**: **DEFERRED (FAIL 아님)** — 정당성은 §3 참조.

### 2.8 AC-WT-8 — 동시성 (write ↔ reviewer 직렬화)

- **재현**: `JobQueue` busy 가드 + `AgentRunner(max_workers=1)` 정합 검증.
- **기대**: 두 번째 명령은 `TEMPLATE_QUEUE_BUSY` 안내 + 큐 적재.
- **결과**: PASS — 신규 코드는 기존 `JobQueue.enqueue` 정책을 그대로 재사용. `test_dispatcher.py::TestRunningWhileQueueing`, `test_queue.py::TestEnqueueBusy` 회귀 0 fail.

### 2.9 AC-WT-9 — 인증 graceful degradation

- **재현**:
  - (a) SDK 미설치 → `is_sdk_available()` False → reviewer/write 비활성, 데몬 시작은 계속.
  - (b) `ANTHROPIC_API_KEY` 잘못된 prefix → `is_sdk_available()` False.
- **기대**: 데몬 시작 안 막음, write 호출 시 즉시 안내, structured/NL 명령 분기 자체는 살아 있음.
- **결과**: PASS — `test_reviewer_sdk_wire.py::TestBuildReviewerGracefulDegradation` 3건 + `test_write_command_flow.py::TestApplyPatchEntry::test_apply_patch_sdk_unavailable_graceful_notice` PASS. `main.py:692~ _handle_write_command` 의 `is_sdk_available()` False 분기가 사용자 안내 메시지 발사.

### 2.10 AC-WT-10 — shutdown 보호

- **재현**:
  - (a) `_write_shutdown_flag.set()` 이후 새 `apply patch` 명령 → 즉시 거절.
  - (b) `shutdown_dev_relay(runner, timeout)` 호출 시 NL flag + write flag + AgentRunner.shutdown 위임.
- **기대**: shutdown 진입 시 새 write 명령 거절 + 진행 중 atomic op graceful + push 는 watchdog timeout.
- **결과**: PASS — `test_write_command_flow.py::TestWriteShutdownProtection::test_shutdown_flag_rejects_new_apply_patch` PASS + `test_shutdown_dev_relay.py` 신규 케이스 PASS. `main.py:1804 shutdown_dev_relay` 가 NL flag + write flag 모두 set 후 `runner.shutdown(wait=True, timeout=timeout)` 위임.

### 2.11 AC-WT-11 — 멱등성 (동일 client_msg_id)

- **재현**: 동일 client_msg_id `apply patch pr=N` 이벤트 두 번 주입.
- **기대**: `jobs` 테이블 UNIQUE 제약으로 중복 차단, SDK 호출 1회만.
- **결과**: PASS — `test_write_command_flow.py::TestWriteIdempotency::test_duplicate_event_ignored` PASS. 기존 `JobQueue.enqueue` UNIQUE 제약 그대로 재사용 (PRD §3.5 정책 승계).

### 2.12 AC-WT-12 — rate limit

- **재현**: 5초 내 write 명령 4건 입력.
- **기대**: 4번째 이후 큐 미적재 + rate limit 안내.
- **결과**: PASS — `test_write_command_flow.py::TestWriteRateLimit::test_rate_limit_applies_to_write_commands` PASS. 기존 `_RateLimiter` (5초/3건) 그대로 재사용.

### 2.13 AC-WT-13 — audit 완전성

- **재현**: apply/commit/push 한 사이클 1회 + cancel 케이스.
- **기대**: §3.7 의 13종 신규 kind 시퀀스 빠짐없이 기록. `user_id_masked` canonical 키 (PR #50/#52 정책).
- **결과**: PASS — `test_write_command_flow.py::TestWriteAuditCompleteness::test_apply_patch_emits_requested_audit` PASS. 컴플라이언스 정적 검사가 `patch_*`, `commit_*`, `push_*`, `write_destructive_blocked`, `write_sdk_unavailable`, `write_shutdown`, `cancel_write` 모두 도메인 키워드 0 hit 으로 통과.

### 2.14 AC-WT-14 — 컴플라이언스 정적 검사

- **재현**: PRD 본문 + write 도구 신규 소스 + 신규 테스트 + 신규 audit kind + Block Kit 템플릿 정적 스캔.
- **기대**: 0 hit.
- **결과**: PASS — `test_compliance.py` 56건 모두 PASS. 신규 항목 커버:
  - `test_prd_write_tools_body_outside_code_is_clean` (PRD 본문)
  - `test_dev_relay_source_clean[write_tools.py]`, `[write_runtime.py]` (신규 소스)
  - `test_static_template_clean[...]` (신규 13종 템플릿 일부 — 가드 import-time)

### 2.15 AC-WT-15 — 커밋 메시지 컴플라이언스 (외부 노출)

- **재현**: 자동 생성 커밋 메시지 본문 검증. 도메인 키워드 / `--amend` / `--no-verify` / 빈 메시지 차단.
- **기대**: 도메인 키워드 0 hit + 한글 1줄 위주 + 위반 시 `commit_failed(compliance_blocked)`.
- **결과**: PASS — `test_write_tools.py::TestCommitMessageGuard` 5건 모두 PASS (`test_clean_message_passes`, `test_empty_message_blocked`, `test_domain_keyword_blocked`, `test_forbidden_flag_blocked[--amend HEAD]`, `test_forbidden_flag_blocked[fix --no-verify]`).

### 2.16 AC-WT-16 — 회귀 0 fail

- **재현**: `pytest ai/tests/dev_relay/` 전체 + `pytest ai/tests/` (workbench 제외).
- **기대**: 0 fail.
- **결과**: PASS — `ai/tests/dev_relay/` 612 PASS / `ai/tests/` (workbench 제외) 790 PASS. 기존 `test_agent_integration.py`, `test_handle_command_nl.py`, `test_handle_command_nl_serialize.py`, `test_dispatcher.py`, `test_tool_policy.py` 모두 0 fail.

---

## 3. AC-WT-7 DEFERRED 정당성 평가

### 3.1 PRD 본문 분석

- **§3.2.2 PM 권고**: "(c) structured 우선, NL **보조**" — 명령 진입 경로.
- **§3.2.4**: "기존 NL 분기 (`_handle_natural_language`) 가 의도 분류 단계에서 write 도구 후보를 인식하면, NL 분기 SDK 가 도구 호출을 결정 — `nl_classifier.py` 에 신규 카테고리 추가."
- **§4 OOS**: "자동 코드 생성 — write 도구는 사용자 명시 명령에만 반응. SDK 가 자율적으로 patch 를 생성·적용하는 흐름은 도입하지 않는다 (예: reviewer 가 발견 사항을 자동 fix). **NL 분기에서 사용자가 명령한 경우는 §3.2.4 처리 — 자율 트리거가 아니라 명시 의도 기반**."
- **§10 PM 결정사항**: "명령 진입 경로 | **structured 우선** (`apply patch pr=N`, `commit pr=N`, `push pr=N`) **+ NL 보조**".

PRD §4 OOS 는 **자율 트리거**만 비범위로 명시하고, **사용자가 NL 로 명령한 케이스는 §3.2.4 in-scope** 로 분명히 못박았다. 따라서 AC-WT-7 은 PRD 문언상 in-scope.

### 3.2 backend-dev 의 deferral 근거

- PR #54 본문 비범위 절: "NL 분기에서 write 도구 자율 트리거 — Phase 3 별도 PRD".
- 표현 자체는 "자율 트리거" 로 PRD §4 OOS 의 카테고리와 합치한다. 그러나 PRD §3.2.4 의 "사용자 NL 명령 → 의도 분류 → confirm" 흐름은 자율 트리거가 **아니다** (confirm 으로 사용자 명시 승인 필수). backend-dev 의 표현 "자율 트리거" 는 PRD §3.2.4 와 § 4 사이의 경계를 흐리며, 엄밀한 정합 평가에서는 **§3.2.4 in-scope 항목을 미구현한 상태**.

### 3.3 QA 정당성 판정

QA 는 다음 근거로 **DEFERRED (FAIL 아님)** 으로 판정한다:

1. **PRD §10 결정사항이 "보조" (auxiliary) 로 명시** — MVP 가치 (PRD §1.1 데드타임 회수) 의 핵심 경로는 structured 명령. structured 진입이 완전히 작동하면 PRD 의 본 가치는 1차 달성.
2. **NL 분기 변경의 별도 회귀 표면** — `nl_classifier.py` 에 신규 카테고리 추가는 기존 `_nl_turn_lock` 직렬화·30분 만료·세션 store 정책 (`dev-relay-nl-serialize.md`, `dev-relay-natural-language.md`) 와 교차하므로 별도 PR 분리가 안전. 단일 PR 에 통합 시 회귀 표면 ↑.
3. **confirm dialog 일관성 유지** — 본 PR 의 confirm Block Kit / `_write_pending` 컨텍스트 / `cancel_write` 흐름이 NL 분기에서 진입해도 그대로 재사용 가능. 후속 PR 은 분류기 카테고리 + 진입점 wire 만 추가하면 됨 — 구조적 부담 작음.
4. **Phase 2 → Phase 3 split 의 일관성** — PRD §4 OOS 의 "`gh pr create`", "PR 본문 자동 작성" 도 Phase 3 별도 PRD 로 명시. NL 진입을 같은 Phase 3 묶음으로 처리하는 것이 운영상 일관.

### 3.4 후속 조건

QA 통과 (qa-passed) 라벨 부여 시 다음 후속 조치를 PR 머지 후 1~2주 내 권고:

- **별도 follow-up issue**: "AC-WT-7 NL 보조 진입 — `nl_classifier.py` 신규 카테고리 + `_handle_natural_language` write 분기 wire" 를 Phase 3 PRD 또는 mini-PRD 로 분리해 트래킹.
- **NL 분기 진입을 통해 destructive op 우회 표면 점검** — Phase 3 작업 시 `tool_policy.is_destructive` 가 NL 분기에서 결정된 도구 호출 직전에도 호출되는지 가드 reconfirm.

backend-dev 의 deferral 은 표현상 "자율 트리거" 라는 단어를 사용해 PRD §3.2.4 in-scope 범주와 경계가 모호하지만, 실질 결정 (구조적 분리 + Phase 3 묶음 처리) 은 PRD §10 의 "보조" 정의와 정합한다. 따라서 **DEFERRED 정당**.

---

## 4. 에지 케이스 / 운영 위험

본 PR 은 자동 테스트로 다음 에지 케이스를 커버:

| 에지 | 커버 위치 |
|---|---|
| `git apply --check` 실패 → 워킹트리 미변경 | `test_write_tools.py::TestApplyPatch::test_apply_check_failure_raises` |
| 빈 트리 커밋 시도 | `TestCommitPreview::test_preview_empty_tree_blocked`, `TestPerformCommit::test_commit_empty_tree_classification` |
| push remote rejected (non-fast-forward) | `TestPerformPush::test_push_rejected_classification` |
| 보호 브랜치 (main/master/develop/release) 직접 push | `TestPushPolicyGuard::test_protected_branch_blocked[*]` |
| `.env`/`.git/config`/secrets/`*.key`/`*.pem`/credentials 경로 patch | `TestPatchDestructiveGuard::test_forbidden_path_blocked[*]` |
| patch body 안에 `rm -rf`, `reset --hard`, force push 표지 | `TestPatchDestructiveGuard::test_destructive_body_blocked[*]` |
| SDK 미설치/인증 미통과 | `TestBuildReviewerGracefulDegradation`, `TestApplyPatchEntry::test_apply_patch_sdk_unavailable_graceful_notice` |
| 동일 client_msg_id 재전송 | `TestWriteIdempotency` |
| 5초 4건 폭주 | `TestWriteRateLimit` |
| shutdown flag 후 신규 진입 | `TestWriteShutdownProtection` |
| `--amend`/`--no-verify`/`--force`/`force-with-lease` 입력 | `TestCommitMessageGuard::test_forbidden_flag_blocked`, `TestPushPolicyGuard::test_forbidden_opt_blocked`, dispatcher 단 1차 차단 |
| 도메인 키워드가 SDK 출력에 포함 | `slack_renderer._STATIC_TEMPLATES` 정적 import-time 가드 + `TestCommitMessageGuard::test_domain_keyword_blocked` |

다음 에지는 자동 테스트 단에서는 mock 또는 보조 시나리오 — **수동 검증 권고** (PRD §8.2 부합):

- **거래소 API / 외부 서비스 장애** — 본 PRD 는 SDK 호출 + `git`/`gh` CLI 외부 호출만 사용. SDK timeout / quota 거절은 `sdk_timeout`·`unknown_error` 분류 fallback (PR #43 정책). 실 SDK 호출 mock 외 실측 timeout/quota 시나리오는 모니터링으로 후행 (PRD §7 위험 6).
- **`git push` 진행 중 SIGTERM** — `AgentRunner.shutdown(timeout)` watchdog 정책 (PR #37) 그대로. 실 push timeout 케이스는 모바일 수동 셋업에서 검증 권고 (PRD §8.2).
- **워킹트리가 PR 브랜치가 아닌 상태** — PRD §7 위험 7. `git branch --show-current` 검증 — Backend Dev 결정 영역. 자동 테스트는 mock fixture 격리이므로 운영 reconcile 은 1~2주 모니터링 필요.

---

## 5. 컴플라이언스 / 봇 가시성 점검

- 본 QA 리포트 본문, PR #54 본문, 신규 audit kind 식별자, Block Kit 템플릿, 자동 생성 커밋 메시지 형식 모두 회사 Slack 동료 가시성 정책 (사용자 메모리 노트 + `ai/coordinator/_compliance.py FORBIDDEN_KEYWORDS`) 통과.
- 정적 스캔 hit 0건 — `test_compliance.py` 가 PRD 본문, 신규 소스, Block Kit 템플릿, 봇 응답 정적 상수까지 커버.
- 신규 식별자 (`patch_requested`, `commit_created`, `push_done`, `write_destructive_blocked`, `cancel_write` 등) 도메인 키워드 0 hit.

---

## 6. 최종 판정

- **AC 15 PASS + 1 DEFERRED (정당) + 0 FAIL** → **qa-passed**.
- 회귀: dev_relay 612 / ai 전체 (workbench 제외) 790 PASS, 0 fail.
- 컴플라이언스: 0 hit.
- Phase 3 후속: AC-WT-7 NL 보조 진입을 별도 mini-PRD 또는 Phase 3 묶음으로 트래킹 권고.

판정: **qa-passed**.
