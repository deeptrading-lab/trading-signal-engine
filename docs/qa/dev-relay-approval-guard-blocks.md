# QA: dev-relay-approval-guard-blocks

> 작성자: QA (자동 검증 위주 — chore PR, PRD 없음)
> 작성일: 2026-05-13
> 입력: PR #51 reviewer P2-1·P2-3 후속 chore (PRD 없음 — PR 본문 §검증 항목 기준)
> 검증 대상 PR: [#51](https://github.com/deeptrading-lab/trading-signal-engine/pull/51) (`feature/dev-relay-approval-guard-blocks`, commit `6e8b723`)
> 변경 규모: +420 / -17, 6 files, 1 commit
> 회귀 (dev_relay 전체): `cd ai && pytest tests/dev_relay/ -q` → **512 passed (2.40s, 0 failed)**
> 신규 테스트: `test_post_blocks_guard.py` 10건 + `test_merger.py` 회귀 보강 3건 = **13건**
> 컴플라이언스: `cd ai && pytest tests/dev_relay/test_compliance.py -v` → **53 passed (0.02s, 0 failed)**

---

## 0. 요약

- **자동 검증 통과**: 검증 항목 1 ~ 11 모두 PASS — `validate_approval` 재시작 거절 (P2-1, AC 1·2·3·4) + `_post_blocks_to_thread` blocks 정적 가드 (P2-3, AC 5·6·7) + 회귀 (AC 8·9·10·11).
- **외부 인터페이스**: 신규 식별자 3개 노출 — `merger.REJECTION_REASON_RESTART_NO_EXPECTED`, `slack_renderer.TEMPLATE_RESTART_APPROVAL_REJECTED`, `main._collect_block_user_facing_text` (모듈 내부). 기존 `validate_approval` 시그니처·`_post_blocks_to_thread` 시그니처 0 변경.
- **컴플라이언스**: 신규 식별자·신규 템플릿·신규 테스트 본문·main.py·merger.py·slack_renderer.py 모두 `find_forbidden_keywords` 0 hit. `test_compliance.py::test_static_template_clean[TEMPLATE_RESTART_APPROVAL_REJECTED-...]` PASS, `test_dev_relay_source_clean[main.py|merger.py|slack_renderer.py]` PASS.
- **인접 PR 회귀**: PR #48 `test_handle_command_nl_serialize.py` 9건 / PR #49 `test_shutdown_dev_relay.py` 5건 / PR #50 `test_audit_user_id_masked.py` 5건 = **19/19 PASS** (병합 회귀 0).
- **최종 판정**: `qa-passed` — 11/11 PASS, 회귀 0.

---

## 1. 검증 항목 매핑

### P2-1 (validate_approval 재시작 거절 — `merger.py`)

| # | 항목 | 재현 | 기대 결과 | 실제 결과 |
|---|------|------|----------|----------|
| 1 | `expected_idempotency_key=None` → 즉시 거절 | `test_merger.py::TestValidateApproval::test_expected_idempotency_only_none_rejected` — `expected_idempotency_key=None` 만 지정, 나머지 정상 페이로드 | `MergeRejection` raise + `str(exc) == REJECTION_REASON_RESTART_NO_EXPECTED` | PASS — exception message `"expected approval missing (restart)"` 정확히 일치 |
| 2 | `expected_job_id=None` → 즉시 거절 | `test_merger.py::TestValidateApproval::test_expected_job_id_only_none_rejected` — `expected_job_id=None` 만 지정 | `MergeRejection` + 동일 reason 코드 | PASS — 동일 메시지 |
| — | 양쪽 모두 None (재시작 직후 시나리오) | `test_merger.py::TestValidateApproval::test_expected_none_rejected_restart` — `expected_*` 모두 None | `MergeRejection` + 동일 reason | PASS |
| 3 | 정상 경로 회귀 0 | `test_merger.py::TestValidateApproval::test_happy_path` 외 기존 8건 (wrong action_id, allow-list, invalid PR, idempotency 누락·mismatch, job_id mismatch) | 기존 동작 그대로 (성공·실패 분기 보존) | PASS — 9건 모두 통과 (회귀 0) |
| 4 | `handle_approve_merge` 거절 reason → `TEMPLATE_RESTART_APPROVAL_REJECTED` 안내 | `test_post_blocks_guard.py::TestApprovalRestartGuard::test_restart_session_rejected` + `test_template_restart_rejected_compliance_clean` | 안내 텍스트 발사 + 컴플라이언스 0 hit | PASS — `safe_say` 가 `TEMPLATE_RESTART_APPROVAL_REJECTED` 로 분기 (context=`approve_validate_restart`), 본문 forbidden keyword 0 |

### P2-3 (blocks 정적 가드 — `main.py::_post_blocks_to_thread`)

| # | 항목 | 재현 | 기대 결과 | 실제 결과 |
|---|------|------|----------|----------|
| 5 | blocks 내부 텍스트 forbidden keyword 감지 | `test_post_blocks_guard.py::TestCollectBlockUserFacingText` 3건 — `section.text.text` 수집 / button `text.text` plain text 수집 / `action_id`·`value` 제외 | `_collect_block_user_facing_text` 가 `text.text` (object) + `text` (string list 내부) 만 수집, 내부 식별자 제외 | PASS — walker 가 dict.value·list 재귀 + key=="text" 시 str/dict 양쪽 분기 정확 |
| 5b | section text 위반 → 차단 | `TestPostBlocksGuardViolation::test_dirty_blocks_blocked_and_text_fallback` — section blocks 내 forbidden keyword 삽입 | `chat_postMessage` 호출 시 `blocks` 인자 전달 안 됨, `text=FALLBACK_RESPONSE` 만 발사 + `logger.error("compliance: blocked thread blocks post"...)` 로그 | PASS — text-only fallback 호출 1회 확인, 본래 blocks 미발사 |
| 5c | button label 위반 → 차단 | `TestPostBlocksGuardViolation::test_dirty_button_label_blocked` — actions block 의 button text 에 forbidden keyword | 동일 차단 + fallback | PASS |
| 6 | text-only fallback 발사 + 에러 로그 | 위 5b·5c | `safe_fallback = FALLBACK_RESPONSE`, `chat_postMessage(channel, thread_ts, text=safe_fallback)` 1회 호출 | PASS — fallback 분기 진입 시 blocks 키 자체가 호출 인자에 없음 (early return 후 fallback path) |
| 6b | `text` 인자 자체 위반 → fallback 치환 | `TestPostBlocksGuardViolation::test_dirty_text_argument_replaced_blocks_still_clean` — blocks 정상 + `text` 인자에 forbidden keyword | blocks 는 정상 발사, `text` 만 `FALLBACK_RESPONSE` 로 치환 | PASS — `safe_text = FALLBACK_RESPONSE`, blocks 키 그대로 전달 |
| 7 | 정상 호출 회귀 0 | `TestPostBlocksGuardClean::test_clean_blocks_posted_with_blocks` — `build_review_result_blocks` 출력 그대로 발사 | blocks·text 모두 그대로 전달 (가드 차단 없음) | PASS — `chat_postMessage(channel, thread_ts, text=text, blocks=blocks)` 원형 호출 |
| 7b | SDK 예외 swallow | `TestPostBlocksHandlesSlackException::test_swallows_post_exception` — `chat_postMessage` raise | 예외 잡고 `logger.warning` 만, 호출 측 전파 0 | PASS — `Exception` 캐치 + warning 로그 |

### 회귀 (전체)

| # | 항목 | 명령 | 결과 |
|---|------|------|------|
| 8 | `dev_relay/` 전체 0 fail | `cd ai && pytest tests/dev_relay/ -q` | **512 passed in 2.40s, 0 failed** |
| 9 | 컴플라이언스 0 hit (신규 식별자·템플릿·소스 포함) | `cd ai && pytest tests/dev_relay/test_compliance.py -v` | **53 passed in 0.02s, 0 failed** — `TEMPLATE_RESTART_APPROVAL_REJECTED` 정적 템플릿 검사 통과 + `main.py`/`merger.py`/`slack_renderer.py` 소스 스캔 0 hit |
| 10 | 신규 `test_post_blocks_guard.py` 10건 | `cd ai && pytest tests/dev_relay/test_post_blocks_guard.py -v` | **10 passed in 0.02s** |
| 11 | PR #48 9건 + PR #49 5건 + PR #50 5건 = 19건 회귀 0 | `cd ai && pytest tests/dev_relay/test_handle_command_nl_serialize.py tests/dev_relay/test_shutdown_dev_relay.py tests/dev_relay/test_audit_user_id_masked.py -v` | **19 passed in 1.32s, 0 failed** |

---

## 2. 실행 로그 발췌

### `pytest tests/dev_relay/test_post_blocks_guard.py -v`

```
tests/dev_relay/test_post_blocks_guard.py::TestCollectBlockUserFacingText::test_collects_section_text PASSED
tests/dev_relay/test_post_blocks_guard.py::TestCollectBlockUserFacingText::test_collects_button_plain_text PASSED
tests/dev_relay/test_post_blocks_guard.py::TestCollectBlockUserFacingText::test_ignores_action_id_and_value PASSED
tests/dev_relay/test_post_blocks_guard.py::TestPostBlocksGuardClean::test_clean_blocks_posted_with_blocks PASSED
tests/dev_relay/test_post_blocks_guard.py::TestPostBlocksGuardViolation::test_dirty_blocks_blocked_and_text_fallback PASSED
tests/dev_relay/test_post_blocks_guard.py::TestPostBlocksGuardViolation::test_dirty_button_label_blocked PASSED
tests/dev_relay/test_post_blocks_guard.py::TestPostBlocksGuardViolation::test_dirty_text_argument_replaced_blocks_still_clean PASSED
tests/dev_relay/test_post_blocks_guard.py::TestPostBlocksHandlesSlackException::test_swallows_post_exception PASSED
tests/dev_relay/test_post_blocks_guard.py::TestApprovalRestartGuard::test_restart_session_rejected PASSED
tests/dev_relay/test_post_blocks_guard.py::TestApprovalRestartGuard::test_template_restart_rejected_compliance_clean PASSED
============================== 10 passed in 0.02s ==============================
```

### `pytest tests/dev_relay/test_merger.py -v` (신규 3건 + 회귀 26건)

```
tests/dev_relay/test_merger.py::TestValidateApproval::test_expected_none_rejected_restart PASSED
tests/dev_relay/test_merger.py::TestValidateApproval::test_expected_idempotency_only_none_rejected PASSED
tests/dev_relay/test_merger.py::TestValidateApproval::test_expected_job_id_only_none_rejected PASSED
... (회귀 26건 모두 PASS)
============================== 29 passed in 0.01s ==============================
```

### `pytest tests/dev_relay/ -q`

```
512 passed in 2.40s
```

### `pytest tests/dev_relay/test_compliance.py -v` (발췌)

```
tests/dev_relay/test_compliance.py::test_static_template_clean[TEMPLATE_RESTART_APPROVAL_REJECTED-...] PASSED
tests/dev_relay/test_compliance.py::test_dev_relay_source_clean[main.py] PASSED
tests/dev_relay/test_compliance.py::test_dev_relay_source_clean[merger.py] PASSED
tests/dev_relay/test_compliance.py::test_dev_relay_source_clean[slack_renderer.py] PASSED
============================== 53 passed in 0.02s ==============================
```

---

## 3. 에지 케이스

### 3.1 데몬 재시작 직후 이전 세션 버튼 클릭

- 시나리오: 사용자가 reviewer 응답을 받은 후 데몬 재시작 → 메모리 상의 `expected_idempotency_key` / `expected_job_id` 유실 → 사용자가 이전 메시지의 `[승인 + 머지]` 버튼 클릭.
- 이전 동작 (P2-1 전): `validate_approval` 이 `expected=None` 케이스를 페이로드 자체로 검증해 통과 → 머지 실행. 캐시 유실 + idempotency backstop 미동작이라 중복 머지 위험.
- 현재 동작: `MergeRejection(REJECTION_REASON_RESTART_NO_EXPECTED)` 즉시 거절 + `handle_approve_merge` 가 `TEMPLATE_RESTART_APPROVAL_REJECTED` 로 분기, 사용자에게 "리뷰 결과를 다시 받아 주세요" 안내. 검증: `TestApprovalRestartGuard::test_restart_session_rejected`.

### 3.2 미래 코드 변경으로 dirty blocks 가 발사 경로에 흘러들어옴

- 시나리오: 누군가 `_post_blocks_to_thread` 호출 측에서 `build_review_result_blocks` 우회로 reviewer 원문을 raw 로 끼움.
- 이전 동작 (P2-3 전): 마지막 가드 없음 → 평문 누설.
- 현재 동작: 발사 직전 walker 가 모든 `text` 필드 (section text object, button plain text, accessory text 등) 를 추출 → `find_forbidden_keywords` 일치 시 `chat_postMessage` 인자에서 blocks 제거 + `text=FALLBACK_RESPONSE` 만 발사 + `logger.error("compliance: blocked thread blocks post", extra={"matched": [...]})`. 검증: `TestPostBlocksGuardViolation` 3건.

### 3.3 fallback 문구 자체가 forbidden keyword 일 경우

- 시나리오: 미래에 `FALLBACK_RESPONSE` 가 화이트리스트 외 단어를 포함하도록 변경.
- 현재 동작: `safe_fallback = FALLBACK_RESPONSE if not find_forbidden_keywords(FALLBACK_RESPONSE) else "응답 차단됨"` — 이중 가드. 정적 보호.

### 3.4 Slack API 일시 장애 (rate limit / network)

- `chat_postMessage` raise → `Exception` 캐치 + `logger.warning("chat_postMessage 실패 ...")` 만, 호출 측 전파 0. 검증: `TestPostBlocksHandlesSlackException::test_swallows_post_exception`.
- fallback 발사 경로에서도 동일 try/except 적용 (line 1356-1361) — fallback 자체 실패도 swallow.

### 3.5 호환성 / 회귀

- `_post_blocks_to_thread` 시그니처·`validate_approval` 시그니처 0 변경.
- `build_review_result_blocks` 가 이미 `guard_text` 통과한 정상 경로 회귀 0 — `TestPostBlocksGuardClean::test_clean_blocks_posted_with_blocks` 가 `build_review_result_blocks` 출력 그대로 발사하여 검증.
- 인접 PR (#48 NL 직렬화, #49 shutdown, #50 audit user_id_masked) 회귀 0 — `pytest` 19/19 PASS.

---

## 4. 컴플라이언스 검증

- `TEMPLATE_RESTART_APPROVAL_REJECTED` 본문: `"이전 세션의 승인 요청은 더 이상 처리할 수 없습니다. 리뷰 결과를 다시 받아 주세요."` — forbidden keyword 0.
- `REJECTION_REASON_RESTART_NO_EXPECTED = "expected approval missing (restart)"` — forbidden keyword 0 (영문 식별자, 도메인 키워드 0).
- `_collect_block_user_facing_text` 내부 식별자 (`action_id`, `block_id`, `value`) 수집 제외 검증 — `TestCollectBlockUserFacingText::test_ignores_action_id_and_value` PASS.
- `test_dev_relay_source_clean[main.py|merger.py|slack_renderer.py]` 3건 모두 PASS — 신규 코드 본문 평문 누설 0.
- 본 QA 리포트 자체 봇 표시명·도메인 키워드 평문 노출 0 — 작성 시 검토.

---

## 5. 판정

- **PASS**: 검증 항목 1 ~ 11 모두 통과. 신규 13건 + 회귀 19건 + 컴플라이언스 53건 + dev_relay 전체 512건 모두 0 fail.
- **라벨 변경**: `impl-ready` → `qa-passed`.
