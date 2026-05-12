# QA: dev-relay-audit-user-id (chore)

> 작성자: QA (자동 검증)
> 작성일: 2026-05-13
> 입력: chore — PRD 없음. PR #25 reviewer Concern C-2 후속 (SESSION_NOTES 2026-05-13 follow-up A-3 그룹).
> 검증 대상 PR: [#50](https://github.com/deeptrading-lab/trading-signal-engine/pull/50) (`feature/dev-relay-audit-user-id`)
> 변경 규모: +338 / -0, 2 files, 1 commit (`804f038`)
> 회귀 (dev_relay 전체): `cd ai && pytest tests/dev_relay/ -q` → **499 passed (2.46s, 0 failed)**
> 회귀 (ai 전체): `cd ai && pytest tests/ -q` → **677 passed (2.75s, 0 failed)**
> 회귀 (컴플라이언스): `cd ai && pytest tests/dev_relay/test_compliance.py -v` → **52 passed (0.03s, 0 hit)**
> 회귀 (PR #48 NL serialize + PR #49 shutdown): **14 passed (1.33s, 0 failed)**

---

## 0. 요약

- chore PR 이라 PRD AC 매핑 대신 reviewer Concern (C-2) 후속 누락 17곳 매핑표를 검증 항목으로 변환.
- 신규 테스트 **5/5 PASS** (`test_audit_user_id_masked.py`) — 단위 (dispatcher 2건) + 통합 (NL session 2건) + 정적 스캐너 (1건).
- 정책: **기존 `"user"` 키 back-compat 유지 + `"user_id_masked"` canonical 신규** (다운스트림 0 회귀). 시스템 audit (사용자 컨텍스트 없음) Option A — 본 PR 범위에서 해당 0건.
- `_append_audit` 정의 1 + inline 호출 **22건** 중, 사용자 컨텍스트 있는 **20곳** 의 record 전부 `user_id_masked` 포함. 변수 경유 2건 (closure pass-through, SDK hook) 은 호출 측에서 record 를 만들고 `user_id_masked` 인자를 전달 — 검증 범위는 main.py 직접 emit 으로 한정.
- 신규 audit kind 추가 0, 외부 시그니처 변경 0, 신규 의존성 0.
- **컴플라이언스 0 hit** — `main.py` / 신규 테스트 / 본 QA 리포트 모두 정적 스캐너 통과.
- **최종 판정**: `qa-passed`.

---

## 1. 검증 항목 매핑 (reviewer Concern C-2 → 테스트)

### 핵심 — `_append_audit` 호출 22 inline 중 사용자 컨텍스트 있는 20곳 (17 fix + 3 기존 OK) 매핑

정적 스캔 (`grep -n "_append_audit" ai/dev_relay/main.py` + 블록 추출) 결과:

| # | 라인 | kind | 기존 `user` 키 | 신규 `user_id_masked` | 결과 |
|---|---|---|---|---|---|
| 1 | 293 | `destructive_blocked` | True (기존) | True | OK |
| 2 | 359 | `command_received` | True (기존) | True | OK |
| 3 | 462 | `nl_busy_rejected` | False | True (PR #48 기존) | OK |
| 4 | 556 | `session_started` | False | True (신규 fix) | OK |
| 5 | 573 | `session_resumed` | False | True (신규 fix) | OK |
| 6 | 724 | `button_action` (`cancel_merge`) | True (기존) | True (신규 fix) | OK |
| 7 | 745 | `button_action` (`approve_merge`) | True (기존) | True (신규 fix) | OK |
| 8 | 798 | `merge_failed` | False | True (신규 fix) | OK |
| 9 | 816 | `merge_started` | False | True (신규 fix) | OK |
| 10 | 830 | `merge_failed` | False | True (신규 fix) | OK |
| 11 | 849 | `merge_done` | False | True (신규 fix) | OK |
| 12 | 874 | `merge_failed` | False | True (신규 fix) | OK |
| 13 | 901 | `button_action` (`merge_review`) | True (기존) | True (신규 fix) | OK |
| 14 | 952 | `reviewer_detail_lookup_failed` | False | True (신규 fix) | OK |
| 15 | 1119 | `reviewer_started` | False | True (신규 fix) | OK |
| 16 | 1131 | `reviewer_failed` | False | True (신규 fix) | OK |
| 17 | 1156 | `reviewer_failed` | False | True (신규 fix) | OK |
| 18 | 1177 | `reviewer_failed` | False | True (신규 fix) | OK |
| 19 | 1198 | `reviewer_failed` | False | True (신규 fix) | OK |
| 20 | 1220 | `reviewer_done` | False | True (신규 fix) | OK |
| 변수 경유 | 533 | (closure pass-through) | n/a | 호출 측 record 에서 키 보장 | 범위 외 |
| 변수 경유 | 1059 | (`make_sonnet_responder` audit hook) | n/a | hook 시그니처 `user_id_masked` 인자 | 범위 외 |

**합계 (inline 22)** — 사용자 컨텍스트 있는 record 20곳 모두 `user_id_masked` 키 보유. 변수 경유 2건은 hook factory 측에서 record 가 구성되므로 본 PR 범위 (main.py 직접 emit) 밖.

> 참고: session_* / merge_* / reviewer_* 계열은 **기존 `"user"` 키 자체가 없었던** record. C-2 의 의도가 "기존 record 에 `user` 키만 있고 canonical key 가 없음" 보다 "사용자 컨텍스트 있는 record 에 마스킹된 식별자 자체가 누락" 이었으므로, 이 그룹은 `"user_id_masked"` 만 추가하면 충분 (back-compat 영향 0). 본 PR 정책 부합.

### 핵심 — 자동화 테스트 (신규 5건)

| # | 검증 항목 | 재현 절차 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| T1 | `destructive_blocked` audit 에 `user_id_masked` 필드 존재 + 원본 user_id 노출 0 | `_handle_command(text="git reset --hard HEAD~5", user_id="U0AE7A54NHL", ...)` → audit.jsonl read | record `kind="destructive_blocked"`, `user_id_masked` truthy, `!= "U0AE7A54NHL"` | record 1건 발견, 마스킹값 != raw | PASS |
| T2 | `command_received` audit 에 `user_id_masked` 필드 존재 + 원본 노출 0 | `_handle_command(text="review pr 22", user_id="U0AE7A54NHL", ...)` → audit.jsonl read | 동일 | PASS | PASS |
| T3 | `session_started` audit 에 `user_id_masked` 필드 존재 (신규 fix) | `_handle_natural_language(text="요약해줘", user_id="U0AE7A54NHL", ...)` + fake_runtime | record `kind="session_started"`, `user_id_masked` truthy, `!= raw` | PASS | PASS |
| T4 | `session_resumed` audit 에 `user_id_masked` 필드 존재 (신규 fix) | sessions.start() 사전 적재 후 `_handle_natural_language(... thread_ts="1.1" ...)` | record `kind="session_resumed"`, `user_id_masked` truthy, `!= raw` | PASS | PASS |
| T5 | **정적 스키마 회귀 방어** — `main.py` 의 모든 inline `_append_audit({...})` 블록에서 13개 대상 kind 가 모두 `user_id_masked` 키 포함 | `Path(main_mod.__file__).read_text()` 후 `_append_audit(` 블록 추출 → kind 라벨 grep → 누락 검출 | 13개 target_kinds (`destructive_blocked`, `command_received`, `session_started`, `session_resumed`, `button_action`, `merge_started`, `merge_done`, `merge_failed`, `reviewer_started`, `reviewer_done`, `reviewer_failed`, `reviewer_detail_lookup_failed`, `nl_busy_rejected`) 누락 0 | 누락 0건 | PASS |

### 부수 — 정책 부합

| # | 검증 항목 | 재현 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| 6 | 신규 audit kind 추가 0건 | commit diff 정독 + `grep -n '"kind"' ai/dev_relay/main.py` | kind 값 변경 0 | 변경 0건 (record 보강만) | PASS |
| 7 | 외부 시그니처 변경 0건 (헬퍼 함수 호출 측 회귀 0) | `git show 804f038 -- ai/dev_relay/main.py` | `def _append_audit` / `def _handle_command` / `def _handle_natural_language` / `def shutdown_dev_relay` / `_build_nl_runtime` 등 시그니처 동일 | 시그니처 diff 0 | PASS |
| 8 | 신규 의존성 0건 | commit diff 의 import 추가 | `ai/dev_relay/main.py` 추가 import 0 | 0 | PASS |
| 9 | `user_id_masked` 값이 `mask_user_id(user_id)` 결과와 일치 (6자 prefix 마스킹 정책) | `python -c "from ai.dev_relay.main import mask_user_id; print(mask_user_id('U0AE7A54NHL'))"` 및 신규 테스트 assertion (`!= "U0AE7A54NHL"`) | 마스킹된 prefix 형태 (`U0AE7A***`), raw 일치 0 | `U0AE7A***` (6자 prefix + `***`) | PASS |
| 10 | back-compat — `button_action` / `destructive_blocked` / `command_received` 등 기존 `"user"` 키 보유 record 가 신규 fix 후에도 `"user"` 키 유지 | 정적 스캔 매핑표 (#1, #2, #6, #7, #13) | 양 키 공존 | 공존 확인 (예: L298 `"user": masked` + L299 `"user_id_masked": masked`) | PASS |

### 회귀

| # | 검증 항목 | 명령 | 결과 | 판정 |
|---|---|---|---|---|
| 11 | `ai/tests/dev_relay/` 전체 0 fail | `cd ai && pytest tests/dev_relay/ -q` | **499 passed in 2.46s** | PASS |
| 12 | `ai/tests/` 전체 0 fail | `cd ai && pytest tests/ -q` | **677 passed in 2.75s** | PASS |
| 13 | `test_compliance.py` 0 hit (main.py / 신규 테스트 컴플라이언스) | `cd ai && pytest tests/dev_relay/test_compliance.py -v` | **52 passed in 0.03s** | PASS |
| 14 | PR #48 NL serialize 9건 + PR #49 shutdown 5건 회귀 보존 | `cd ai && pytest tests/dev_relay/test_handle_command_nl_serialize.py tests/dev_relay/test_shutdown_dev_relay.py -v` | **14 passed in 1.33s** | PASS |
| 15 | 신규 `test_audit_user_id_masked.py` 5건 모두 PASS | `cd ai && pytest tests/dev_relay/test_audit_user_id_masked.py -v` | **5 passed in 0.03s** | PASS |

---

## 2. 에지 케이스

본 PR 은 audit record schema 보강이라 외부 I/O (Slack/거래소/네트워크/API rate limit) 영향 0. 다만 audit.jsonl 자체 흐름과 다운스트림 분석기 관점의 에지를 별도 검토:

| # | 에지 케이스 | 재현 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| E1 | audit.jsonl 신규 파일 권한 0600 (`_append_audit` 의 PRD §3.8) — 본 PR 이 record schema 만 바꿔도 권한 회귀 0 | `cd ai && pytest tests/dev_relay/test_audit_perm.py -v` | `os.stat(path).st_mode & 0o777 == 0o600` | (`test_audit_perm` 가 dev_relay/ 회귀 499 PASS 안에 포함) | PASS |
| E2 | 기존 다운스트림 분석기 (PR #25 의 audit_recovery) 가 `"user"` 키만 읽어도 회귀 0 | `cd ai && pytest tests/dev_relay/ -q` 안 audit_recovery 관련 케이스 | back-compat — `"user"` 키 보존된 record (`destructive_blocked` / `command_received` / `button_action`) 정상 파싱 | PASS (499 회귀 중 포함) | PASS |
| E3 | 변수 경유 audit (closure pass-through L533 / SDK hook L1059) 의 record schema | nl_agent.py / nl_sdk_runtime.py 정적 검토 | nl_agent.py 의 record 는 `"user"` 키 사용 (이미 마스킹된 `user_id_masked` 인자 → record["user"]). 본 PR 범위 밖이므로 canonical key 미적용은 follow-up 으로 분리 | nl_agent.py 의 `"user"` 6곳 모두 `user_id_masked` 인자값 — 마스킹 정책 일관 | OUT-OF-SCOPE (정책 부합) |
| E4 | mask_user_id 가 짧은 user_id 처리 시 빈 record 방어 | `python -c "from ai.dev_relay.main import mask_user_id; print(repr(mask_user_id('U0')))"` | `'***'` (raw 노출 0) | `'***'` | PASS |
| E5 | concurrent multi-thread audit append 시 race — record schema 변경이 atomic write 회귀 유발 0 | `_append_audit` 의 `with path.open("a")` 는 OS file append 보장 — schema 변경은 줄 단위 JSON 1건이라 영향 0 | record 1줄 = 1 JSON, 누락·중복 0 | 정적 검토만 (별도 stress test 없음) | OK (검토만) |

---

## 3. 실행 로그 (요약)

```text
$ git show --stat 804f038 | head -6
commit 804f038ef17181317d5231d21ee549f0a415cb04
Date:   Wed May 13 00:34:00 2026 +0900
    chore(dev-relay): audit record 에 user_id_masked 누락 fix
 ai/dev_relay/main.py                            |  19 ++
 ai/tests/dev_relay/test_audit_user_id_masked.py | 319 ++++++++++++++++++++++++

$ cd ai && pytest tests/dev_relay/test_audit_user_id_masked.py -v
... 5 passed in 0.03s

$ cd ai && pytest tests/dev_relay/ -q
... 499 passed in 2.46s

$ cd ai && pytest tests/ -q
... 677 passed in 2.75s

$ cd ai && pytest tests/dev_relay/test_compliance.py -v
... 52 passed in 0.03s

$ cd ai && pytest tests/dev_relay/test_handle_command_nl_serialize.py \
                tests/dev_relay/test_shutdown_dev_relay.py -v
... 14 passed in 1.33s
```

---

## 4. 판정

- 모든 검증 항목 통과 (15/15) + 신규 테스트 5/5 PASS + 회귀 0건.
- 정적 스키마 스캐너 (T5) 가 follow-up PR 에서도 누락 회귀를 잡도록 13개 target kind 를 박제 — schema 회귀 방어 자산 확보.
- **PR 라벨**: `impl-ready` → `qa-passed`.

### Follow-up (본 PR 범위 외, 다음 세션 이월)

- `ai/dev_relay/nl_agent.py` / `nl_sdk_runtime.py` 의 SDK responder 측 audit record 는 `"user"` 키만 사용 (마스킹값 일관) — canonical `"user_id_masked"` 적용은 별도 PR. 본 PR 정책상 main.py 직접 emit 범위로 한정.
- 신규 audit kind 추가 시 `test_audit_user_id_masked.py::TestAuditSchemaRegression::test_all_target_kinds_carry_user_id_masked_when_emitted_from_main` 의 `target_kinds` 셋도 함께 갱신해야 함 — 컨벤션으로 SESSION_NOTES 메모 권장.
