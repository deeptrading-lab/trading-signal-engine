# QA — dev-relay-audit-followups (chore)

- 입력 PR: **#52** (branch `feature/dev-relay-audit-followups`, head `36c4fa1`, label `impl-ready`)
- PRD: 없음 (chore — PR #50 reviewer P2 4건 + PR #51 reviewer P2 3건 묶음 후속)
- 변경 규모: 9 files, +527/-40
- QA 일자: 2026-05-15
- 판정: **qa-passed**

---

## 범위

| 그룹 | 항목 | 출처 |
|---|---|---|
| F-1 #1 | `nl_agent.py` / `nl_sdk_runtime.py` audit canonical key `user_id_masked` 병기 | PR #50 reviewer P2 |
| F-1 #2 | `test_audit_user_id_masked.py` 정적 스캔 `target_kinds` 셋 갱신 의무 docstring | PR #50 reviewer P2 |
| F-1 #3 | `_append_audit` docstring 에 `"user"` 키 deprecation 시점 명시 (2026-07-13 이후) | PR #50 reviewer P2 |
| F-1 #4 | `main.py` `mask_user_id(user_id)` 중복 호출 → `masked` 단일 변수 통일 (9곳) | PR #50 reviewer P2 |
| F-2 #1 | `merger.py` `classify_merge_rejection` + 7개 `REJECTION_CATEGORY_*` 상수 | PR #51 reviewer P2 |
| F-2 #2 | `_collect_block_user_facing_text` 의 `key=="text"` 중복 수집 단일화 | PR #51 reviewer P2 |
| F-2 #3 | walker 비-text 키 (`alt_text`, `placeholder`, `title`, `label`, `hint`) 방어 | PR #51 reviewer P2 |

---

## 1. 수용 기준 검증

### AC-1 — canonical user 키 적용 (F-1 #1)

- **재현 절차**: `grep -n '"user_id_masked"' ai/dev_relay/nl_agent.py ai/dev_relay/nl_sdk_runtime.py`
- **기대 결과**:
  - `nl_agent.py` 6 hit (라인 233 / 245 / 261 / 275 / 297 / 324) — 6곳 모두 `"user": user_id_masked` 와 `"user_id_masked": user_id_masked` 병기
  - `nl_sdk_runtime.py` 2 hit (라인 91 / 103) — PreToolUse `tool_call` / `tool_denied` audit 신규 `user_id_masked` 단일
  - 신규 `TestNLAgentCanonicalUserKey::test_haiku_branch_canonical_key` PASS
  - 신규 `TestNLAgentCanonicalUserKey::test_sonnet_branch_canonical_key` PASS
- **실제 결과**: 일치, 8 hit + 2 tests PASS

### AC-2 — target_kinds 갱신 의무 docstring (F-1 #2)

- **재현 절차**: `grep -nE 'target_kinds|셋 갱신|set update|kinds set' ai/tests/dev_relay/test_audit_user_id_masked.py`
- **기대 결과**: 클래스 docstring (라인 244-245) + 메서드 docstring (라인 251, 259-260) 에 "신규 audit kind 추가 시 본 셋도 함께 업데이트하라" 명시
- **실제 결과**: 일치
  ```
  244:    **셋 갱신 의무 (PR #50 후속)**: `ai/dev_relay/main.py` 에 신규 audit kind 가
  245:    추가되고 그 record 가 사용자 컨텍스트를 포함하면, 본 클래스의 `target_kinds`
  259:        신규 audit kind 추가 시 본 메서드의 `target_kinds` 셋도 함께 업데이트하라
  260:        (위 클래스 docstring 의 셋 갱신 의무 참조).
  ```

### AC-3 — deprecation 시점 명시 (F-1 #3)

- **재현 절차**: `grep -nE 'deprecation|2026-07-13' ai/dev_relay/main.py`
- **기대 결과**: `_append_audit` docstring 에 `"user"` 키 deprecation 시점 = **2026-07-13 이후** (PR #50 머지 2026-05-13 기준 60일 window) 명시
- **실제 결과**: 일치 (라인 149: `- `"user"` 키 deprecation 시점: **2026-07-13 이후** (PR #50 머지 2026-05-13`)

### AC-4 — mask_user_id 통일 (F-1 #4)

- **재현 절차**: `grep -nE 'mask_user_id' ai/dev_relay/main.py`
- **기대 결과**:
  - `handle_cancel_merge` / `handle_approve_merge` / `handle_merge_review` 3개 핸들러에서 `masked = mask_user_id(user_id)` 1회 계산 후 재사용
  - `mask_user_id(user_id)` 의 즉시 호출 흔적은 없고, audit record 내 `mask_user_id(job.user_id)` 만 잔존 (worker 측 — 별 컨텍스트라 영향 없음)
- **실제 결과**:
  - `masked = mask_user_id(user_id)` 5곳 (라인 299, 507, 728, 750, 921) + `mask_user_id(sender)` 1곳 (라인 654, 다른 변수)
  - 한 핸들러 내 중복 호출 제거 — 확인됨 (handle_approve_merge: 728/750 두 분기에서 각 1회만 호출, 이후 `masked` 재사용)
  - worker 측 `mask_user_id(job.user_id)` 6곳 (1152~1255) — 본 PR 의 변경 범위 외 (job context, user_id 변수 없음)

### AC-5 — merge_failed classification 세분화 (F-2 #1)

- **재현 절차**:
  1. `grep -nE 'classify_merge_rejection|REJECTION_CATEGORY' ai/dev_relay/merger.py`
  2. `cd ai && pytest tests/dev_relay/test_merge_rejection_classify.py -v`
- **기대 결과**:
  - 7개 `REJECTION_CATEGORY_*` 상수 (restart_no_expected / idempotency_mismatch / job_id_mismatch / user_not_allowed / invalid_payload / unexpected_action / other)
  - `classify_merge_rejection(exc)` 헬퍼 정의 (라인 75-)
  - `main.py` `handle_approve_merge` 의 `merge_failed` audit 에 `rejection_reason` 보조 키 추가 (라인 812-820)
  - 신규 13건 (`TestClassifyByMessage` 9건 + `TestClassifyFromValidateApproval` 4건) PASS
- **실제 결과**: 일치, 13/13 PASS, `__all__` exports 도 정상 노출

### AC-6 — walker 중복 수집 refactor (F-2 #2)

- **재현 절차**: `sed -n '1334,1410p' ai/dev_relay/main.py` + `pytest tests/dev_relay/test_post_blocks_guard.py::TestCollectBlockUserFacingText::test_text_object_not_double_collected -v`
- **기대 결과**:
  - `_visit` 내 `key == "text"` 분기: str 값은 즉시 수집 + `continue`, obj 값은 inner.text 수집 + `continue` (이후 `_visit(value)` 재진입 없음)
  - `test_text_object_not_double_collected` PASS (`{type, text}` 객체에서 text 가 한 번만 수집됨)
- **실제 결과**: 일치, PASS

### AC-7 — image/input 블록 비-text 키 방어 (F-2 #3)

- **재현 절차**:
  1. `grep -nE '_BLOCK_USER_FACING_NON_TEXT_KEYS' ai/dev_relay/main.py`
  2. `pytest tests/dev_relay/test_post_blocks_guard.py::TestCollectBlockNonTextKeys -v`
- **기대 결과**:
  - `_BLOCK_USER_FACING_NON_TEXT_KEYS = {"alt_text", "placeholder", "title", "label", "hint"}` 정적 셋 정의 (라인 1325-1331 영역)
  - walker 가 비-text 키에서 `str` 직접·`{type, text}` obj 둘 다 수집
  - 신규 5건 PASS: `test_image_alt_text_collected`, `test_input_placeholder_collected`, `test_actions_select_placeholder_collected`, `test_image_title_collected`, `test_dirty_alt_text_blocks_post`
- **실제 결과**: 일치, 5/5 PASS. `test_dirty_alt_text_blocks_post` 가 `alt_text` 누설 시 `FALLBACK_RESPONSE` text-only fallback 발사 확인.

### AC-8 — SESSION_NOTES 동봉 정합성

- **재현 절차**: `grep -nE 'PR #50|PR #51|PR #52|F-1|F-2|A-5' docs/SESSION_NOTES.md | head -30`
- **기대 결과**: 직전 미커밋 update (PR #50/#51 + A-5 + 누적 follow-up — 205/212/213/214/221/222 라인) + 본 세션 entry (264-290 라인, F-1/F-2 종결) 모두 포함
- **실제 결과**: 일치. 264 라인에 "2026-05-15 — F-1 + F-2 묶음 chore" 헤더, 270-276 라인에 7건 개별 설명, 290 라인에 follow-up 표 종결 표기 (`~~F-1·F-2~~`).

---

## 2. 회귀 테스트

| 스코프 | 커맨드 | 결과 |
|---|---|---|
| 신규 21건 | `pytest tests/dev_relay/test_nl_agent.py tests/dev_relay/test_post_blocks_guard.py tests/dev_relay/test_merge_rejection_classify.py -v` | **51/51 PASS** (기존 + 신규) |
| 신규만 (F-1 canonical) | `pytest tests/dev_relay/test_nl_agent.py::TestNLAgentCanonicalUserKey -v` | **2/2 PASS** |
| 신규만 (F-2 walker) | `pytest tests/dev_relay/test_post_blocks_guard.py -k 'NonText or not_double or ApprovalRestart' -v` | **8/8 PASS** (해당 신규 6건 포함) |
| 신규만 (F-2 classify) | `pytest tests/dev_relay/test_merge_rejection_classify.py -v` | **13/13 PASS** |
| 전체 dev_relay 회귀 | `cd ai && pytest tests/dev_relay/ -q` | **533/533 PASS** (2.48s) |
| 컴플라이언스 | `cd ai && pytest tests/dev_relay/test_compliance.py -v` | **53/53 PASS** — 정적 템플릿 17건 + Block Kit builder 4건 + dev_relay 소스 21파일 (`nl_agent.py`, `nl_sdk_runtime.py`, `main.py`, `merger.py` 포함) 모두 0 hit |

신규 테스트 합계: **21건 = 2 (nl_agent canonical) + 6 (post_blocks: 5 NonText + 1 not_double) + 13 (merge classify)**.

---

## 3. 컴플라이언스 정적 스캔

본 PR 의 신규 식별자·문서 텍스트에 봇 표시명에 노출 금지 키워드 0 hit:

| 식별자 / 토큰 | 결과 |
|---|---|
| `classify_merge_rejection` | 0 hit |
| `REJECTION_CATEGORY_RESTART_NO_EXPECTED` | 0 hit |
| `REJECTION_CATEGORY_IDEMPOTENCY_MISMATCH` | 0 hit |
| `REJECTION_CATEGORY_JOB_ID_MISMATCH` | 0 hit |
| `REJECTION_CATEGORY_USER_NOT_ALLOWED` | 0 hit |
| `REJECTION_CATEGORY_INVALID_PAYLOAD` | 0 hit |
| `REJECTION_CATEGORY_UNEXPECTED_ACTION` | 0 hit |
| `REJECTION_CATEGORY_OTHER` | 0 hit |
| `REJECTION_REASON_RESTART_NO_EXPECTED` | 0 hit |
| `user_id_masked` | 0 hit |
| `rejection_reason` | 0 hit |
| `_collect_block_user_facing_text` | 0 hit |
| `_BLOCK_USER_FACING_NON_TEXT_KEYS` | 0 hit |
| 슬러그 `dev-relay-audit-followups` | 0 hit |

`test_compliance.py::test_dev_relay_source_clean` 21파일도 100% PASS — 본 PR 의 4개 수정 소스 (`nl_agent.py`, `nl_sdk_runtime.py`, `main.py`, `merger.py`) 모두 위반 0.

---

## 4. 에지 케이스

| 케이스 | 절차 | 기대 / 실제 |
|---|---|---|
| audit record 신규 kind 추가 시 셋 미갱신 | `test_audit_user_id_masked` 의 `target_kinds` 셋과 `main.py` 실제 `_append_audit` 호출의 kind 집합이 vary 하면 정적 스캔 테스트가 fail 해야 함 | 현 PR 의 `target_kinds` 갱신 의무 docstring 으로 휴먼 가드 마련. 자동 vary detection 은 별도 issue (스코프 외 — F-1 #2 는 docstring 만 요구) |
| MergeRejection 의 message 가 예상 외 토큰 | `classify_merge_rejection` 의 fallback 카테고리 `other` 로 분류 | `test_other_fallback` PASS — `MergeRejection("totally unknown reason XYZ")` → `"other"` |
| MergeRejection 이 아닌 일반 Exception | `classify_merge_rejection(ValueError("..."))` 도 `"other"` 로 fallback | `TestClassifyByMessage` 의 `test_other_fallback` 가 `MergeRejection` 만 검증하지만, `classify_merge_rejection` 의 signature `MergeRejection \| BaseException` 가 일반 Exception 도 허용. 정적 코드 리뷰로 fallback 안전 확인 |
| Block Kit 트리에 중첩된 `text` 객체 | 한 번만 수집되어야 함 (이전엔 잠재 중복) | `test_text_object_not_double_collected` PASS — 정확히 1 회 수집 |
| `alt_text` 에 forbidden keyword 누설 | `_post_blocks_to_thread` 가 발사 차단 + text-only fallback (`FALLBACK_RESPONSE`) | `test_dirty_alt_text_blocks_post` PASS — blocks 인자 없이 fallback 발사 |
| `placeholder` 가 plain string 직접 | walker 가 str 직접 형태도 수집 | `test_input_placeholder_collected` 검증 — `placeholder: {type: plain_text, text: ...}` obj 형태도 OK |
| F-1 deprecation 60-day window 후 (2026-07-13~) | `"user"` 키 제거 별도 PR 필수 — 본 PR 범위 외 | docstring 에 명시. 다운스트림 분석 도구 마이그레이션 확인 책임 명시됨 |
| worker 측 `mask_user_id(job.user_id)` 중복 | 본 PR 의 F-1 #4 범위 외 (slack handler 만 통일) — worker 측은 `job.user_id` 변수가 함수 scope 외 lazy 로 변할 수 있어 보수적으로 호출 유지 | 정상. 분석상 worker `_append_audit` 호출 6곳 모두 inline 호출, 한 함수 내 중복 없음 |

---

## 5. 판정

| 항목 | 결과 |
|---|---|
| 수용 기준 AC-1 ~ AC-8 | 8/8 PASS |
| 신규 21건 | 21/21 PASS |
| 전체 dev_relay 회귀 | 533/533 PASS |
| 컴플라이언스 (53건 + 신규 식별자 14개 추가 정적 스캔) | 0 hit |
| 실패 | **0건** |

**최종 판정: qa-passed**.

---

## 6. 메모 (다음 세션 follow-up 없음)

본 PR 은 직전 세션 follow-up 표의 F-1 + F-2 종결 PR. PR #50/#51 reviewer P2 7건 모두 docstring / 헬퍼 신설 / 작은 refactor 로 정리됨. 회귀 / 기능 영향 0. 본 QA 결과 기준으로 follow-up 신규 항목 없음.
