# QA 리포트 — dev-relay-pr52-54-followups (F-4 + F-5 묶음 chore)

- **slug**: `dev-relay-pr52-54-followups`
- **PR**: [#56](https://github.com/deeptrading-lab/trading-signal-engine/pull/56) — `feature/dev-relay-pr52-54-followups`
- **QA 일자**: 2026-05-16 (KST)
- **상위 PRD**: 없음 (chore — PR #52 / PR #54 reviewer P2 후속 묶음)
- **참조 PRD**: [`docs/prd/dev-relay-write-tools.md`](../prd/dev-relay-write-tools.md) §3.3.2 (F-5 #2 force-with-lease 정합성 판정 근거)
- **판정**: **PASS** — F-4 4건 + F-5 3건 + 회귀 0 + 컴플라이언스 0 hit

---

## 1. 입력 / 변경 요약

| 항목 | 값 |
|---|---|
| 변경 파일 | `ai/dev_relay/main.py` (+67/-7), `ai/tests/dev_relay/test_pr52_54_followups.py` (신규 +309) |
| 총 diff | +376 / -7 |
| 라벨 (검증 전) | `impl-ready` |
| 신규 의존성 | 없음 |
| 외부 시그니처 변경 | 없음 (`shutdown_dev_relay`, `_spawn_write_worker` 시그니처 그대로) |

---

## 2. F-5 #2 force-with-lease PRD 정합성 판정 (핵심)

### 2.1 PRD §3.3.2 직접 인용

`docs/prd/dev-relay-write-tools.md` §3.3.2 의 write 도구별 화이트리스트/블랙리스트 표 — `push` 행:

| 도구 | 허용 | 차단 (destructive_blocked) |
|---|---|---|
| `push` | 현재 브랜치, fast-forward 또는 일반 push | `--force`, **`--force-with-lease`**, `--mirror`, `--delete`, push to `main`/`master` 직접, push to 본인 브랜치 외 |

PRD 가 `--force-with-lease` 를 명시적으로 차단 대상에 나열한다 (강조 추가).

### 2.2 backend-dev 결정과 PRD 일치 여부

- backend-dev 의 결정: **PRD 정합 유지 (차단)** — reviewer 가 제안한 "안전 변형 허용" 옵션 거절.
- PRD §3.3.2 가 명시 차단 대상으로 나열 → backend-dev 결정 = **PRD 정합**.
- 추가 근거: PR #56 본문 ("F-5 #2") — "PRD §3.3 명시 (`--force-with-lease` 도 destructive)" 로 backend-dev 가 동일한 PRD 조항을 근거로 인용.

### 2.3 판정

**PRD 정합** — `--force-with-lease` 변형 차단 유지 정당. reviewer 권고 ("안전 변형 허용") 는 PRD §3.3.2 위반이므로 채택 거절이 적정.

---

## 3. 수용 기준별 검증 — F-4 (PR #52 P2 4건)

### F-4 #1. walker dict-form 중복 수집 제거

- **재현 절차**:
  1. `pytest tests/dev_relay/test_pr52_54_followups.py::TestWalkerDictDedup -v`
  2. `image.alt_text`, `input.placeholder.text`, `title`/`label`/`hint` (`{type: plain_text, text: "..."}` obj form) 각각 호출 시 `_collect_block_user_facing_text` 결과 내 동일 inner 텍스트가 한 번만 등장하는지 확인.
- **기대 결과**: `collected.count(inner_text) == 1`. dict 분기 `_BLOCK_USER_FACING_NON_TEXT_KEYS` 경로에서 inner 수집 후 `continue` 로 fallthrough 차단.
- **실행 결과**:
  - `test_placeholder_text_collected_once` PASSED
  - `test_image_alt_text_str_direct` PASSED
  - `test_title_label_hint_all_dedup` PASSED
- **소스 확인**: `ai/dev_relay/main.py:2302-2306` (`if isinstance(value, dict): ... collected.append(inner); continue`).

### F-4 #2. `"user"` 키 deprecation 자동 가드

- **재현 절차**:
  1. `pytest tests/dev_relay/test_pr52_54_followups.py::TestUserKeyDeprecationDateGuard -v`
  2. 정적 날짜 비교 — 오늘 (2026-05-16) < 2026-07-13 → PASS. 2026-07-13 도래 시 자동 fail.
- **기대 결과**: deprecation 시점 미도래 동안 PASS. 도래 시 pytest 가 자연 트리거 → retire 작업 강제.
- **실행 결과**: `test_deprecation_date_not_yet_reached` PASSED.

### F-4 #3. `handle_view_details` `masked` 변수 통일

- **재현 절차**:
  1. `ai/dev_relay/main.py:1876-1914` (`handle_view_details`) 코드 인스펙션.
  2. `mask_user_id(user_id)` 호출 횟수 카운트 + `masked` 변수 재사용 확인.
- **기대 결과**: `mask_user_id(user_id)` 가 함수 내 1회만 호출, 그 결과를 `masked` 에 담아 audit `user_id_masked` 필드에 재사용 (F-1 #4 패턴 동일).
- **실행 결과**:
  - `main.py:1883` — `masked = mask_user_id(user_id)` 1회 계산.
  - `main.py:1903` — audit `"user_id_masked": masked` 재사용.
  - 동작 변경 0. 전체 회귀 테스트 658/658 PASS.

### F-4 #4. `classify_merge_rejection` 비-`MergeRejection` 입력 방어

- **재현 절차**:
  1. `pytest tests/dev_relay/test_pr52_54_followups.py::TestClassifyMergeRejectionDefensive -v`
  2. None / dict / str / 임의 객체 / 빈 문자열 입력 시 raise 없이 fallback 분류 반환 확인.
- **기대 결과**: 모든 입력에 대해 raise 0, fallback 분류 반환 (예: `OTHER` / `unknown_error`). 함수 시그니처가 `MergeRejection | BaseException` 이지만 비정상 입력에서도 안전.
- **실행 결과**:
  - `test_none_input` PASSED
  - `test_dict_input` PASSED
  - `test_str_input` PASSED
  - `test_arbitrary_object` PASSED
  - `test_empty_string` PASSED

---

## 4. 수용 기준별 검증 — F-5 (PR #54 P2 3건)

### F-5 #1. `_active_write_workers` + `_join_active_write_workers` graceful join

- **재현 절차**:
  1. `pytest tests/dev_relay/test_pr52_54_followups.py::TestShutdownJoinsActiveWriteWorkers -v`
  2. `_spawn_write_worker` 호출 시 `_active_write_workers` set 에 thread 등록되는지 확인.
  3. `_join_active_write_workers(timeout=...)` 호출 시 정상 thread 회수 + hang thread 격리 검증.
  4. timeout 초과 thread 가 있어도 raise 없음 확인.
- **기대 결과**:
  - spawn → set 에 추가 + 완료 시 discard (`_wrapped` finally 절).
  - timeout 을 thread 수로 균등 분할 → 한 thread 가 hang 해도 다른 thread join 기회 보장.
  - hang thread 는 daemon 강제 회수에 위임 + warning log.
- **실행 결과**:
  - `test_spawn_registers_worker` PASSED
  - `test_shutdown_joins_active_workers` PASSED
  - `test_shutdown_timeout_does_not_raise` PASSED
- **소스 확인**:
  - `main.py:698-699` — `_active_write_workers: set[threading.Thread]` + lock.
  - `main.py:724-740` — `_spawn_write_worker` wrapper closure 가 add/discard.
  - `main.py:743-772` — `_join_active_write_workers` timeout 공평 배분.
  - `main.py:1956-1985` — `shutdown_dev_relay` step 3 (`_join_active_write_workers`) wired.

### F-5 #2. `force-with-lease` 정합성 (PRD 정합 유지)

- **재현 절차**:
  1. §2 PRD §3.3.2 직접 확인 — `--force-with-lease` 가 차단 대상 명시.
  2. `pytest tests/dev_relay/test_pr52_54_followups.py::TestForceWithLeaseBlocked -v`
  3. 6 parametrize + 1 negative — `--force-with-lease`, `force-with-lease`, `_` 변형, 한글 NL 표현, 일부 토큰 (deploy with `--force-with-lease`), 그리고 일반 lease 정책 텍스트 (negative — 차단 안 됨).
- **기대 결과**:
  - `--force-with-lease` 변형 6건 모두 destructive 분기로 차단.
  - `lease 정책 알려줘` 같은 부분 문자열 negative 는 차단 안 됨 (false positive 0).
  - `_DESTRUCTIVE_SINGLE_TOKENS` 가 PRD §3.3.2 의 차단 대상을 정확히 커버.
- **실행 결과**:
  - `test_force_with_lease_variants_blocked[git push --force-with-lease]` PASSED
  - `test_force_with_lease_variants_blocked[git push origin main --force-with-lease]` PASSED
  - `test_force_with_lease_variants_blocked[push --force-with-lease]` PASSED
  - `test_force_with_lease_variants_blocked[force-with-lease 로 푸시]` PASSED
  - `test_force_with_lease_variants_blocked[deploy with --force-with-lease]` PASSED
  - `test_force_with_lease_variants_blocked[git push origin --force_with_lease]` PASSED
  - `test_non_force_token_not_blocked` PASSED
- **소스 확인**: `ai/dev_relay/dispatcher.py:99-107` — `_DESTRUCTIVE_SINGLE_TOKENS` frozenset 에 `--force-with-lease`, `--force_with_lease`, `force-with-lease`, `force_with_lease` 모두 포함.

### F-5 #3. `_resolve_repo_root` 캐시 회귀 가드

- **재현 절차**:
  1. `pytest tests/dev_relay/test_pr52_54_followups.py::TestResolveRepoRootCache -v`
  2. 첫 호출 후 `_repo_root_cache` 모듈 변수에 값이 캐시되는지 확인.
  3. `DEV_RELAY_REPO_ROOT` env override 우선순위 확인.
- **기대 결과**:
  - 첫 호출 후 캐시 hit — 두 번째 호출은 subprocess 없이 캐시 반환.
  - env 명시 시 git toplevel / cwd fallback 보다 우선.
- **실행 결과**:
  - `test_cached_after_first_call` PASSED
  - `test_env_override_takes_precedence` PASSED
- **소스 확인**: `ai/dev_relay/main.py:164` (`_repo_root_cache: Path | None`), `main.py:167-176` (캐시 early-return).

---

## 5. 회귀 / 컴플라이언스

### 5.1 신규 테스트 전수 실행

```
$ cd ai && pytest tests/dev_relay/test_pr52_54_followups.py -v
============================== 21 passed in 0.14s ==============================
```

21건 분포:
- `TestWalkerDictDedup` — 3건
- `TestUserKeyDeprecationDateGuard` — 1건
- `TestClassifyMergeRejectionDefensive` — 5건
- `TestShutdownJoinsActiveWriteWorkers` — 3건
- `TestForceWithLeaseBlocked` — 6 parametrize + 1 negative = 7건
- `TestResolveRepoRootCache` — 2건

### 5.2 dev_relay 전체 회귀

```
$ cd ai && pytest tests/dev_relay/ -q
658 passed in 3.30s
```

PR #48~#55 누적 회귀 0 fail. 외부 시그니처 변경 0 → 호출 측 회귀 없음.

### 5.3 컴플라이언스 정적 검사

```
$ cd ai && pytest tests/dev_relay/test_compliance.py -v
============================== 56 passed in 0.02s ==============================
```

- 신규 소스 (`main.py` 변경분), 신규 테스트 파일 모두 `FORBIDDEN_KEYWORDS` 0 hit.
- 본 QA 리포트 본문도 도메인 키워드 미포함.

---

## 6. 에지 케이스 검토

| 케이스 | 처리 | 검증 |
|---|---|---|
| write worker thread 가 hang 한 상태에서 shutdown | timeout / N 공평 배분 → 다른 thread 회수 가능. hang thread 는 daemon 강제 회수 + warning log | `test_shutdown_timeout_does_not_raise` (timeout=0.01, 무한 루프 thread 1건) |
| `_active_write_workers` 가 빈 상태에서 shutdown | snapshot 빈 → 즉시 return (no-op) | `_join_active_write_workers` 의 early-return 분기 (`if not snapshot: return`) |
| `force-with-lease` 와 무관한 일반 lease 단어 (e.g. "lease 정책 알려줘") | 차단 안 됨 (false positive 회피) | `test_non_force_token_not_blocked` PASSED |
| 한글 NL 표현 ("force-with-lease 로 푸시") | 차단됨 (구조어 매칭) | `test_force_with_lease_variants_blocked[force-with-lease 로 푸시]` PASSED |
| `_repo_root_cache` 가 이미 set 된 상태에서 env 변경 | env override 미반영 (process lifetime cache) — 데몬 재시작 시 재계산 | docstring `main.py:163` 명시 |
| `classify_merge_rejection` 가 None 입력 | raise 없이 `OTHER` 분류 fallback | `test_none_input` PASSED |
| `2026-07-13` 도달 시 deprecation guard | pytest fail 자연 트리거 → 사용자 retire 작업 강제 | guard 메커니즘 동작 (현재는 미도달 PASS) |

---

## 7. 판정

- **F-4 4건**: 모두 통과.
- **F-5 3건**: 모두 통과 (`force-with-lease` 정합성 = PRD 정합 유지 정당).
- **회귀**: 658/658 PASS, 컴플라이언스 56/56 PASS.
- **신규 테스트**: 21건 PASS.
- **실패 항목**: 0건.

**최종 판정: `qa-passed`**.

---

## 8. 명령 기록

```
cd ai && pytest tests/dev_relay/test_pr52_54_followups.py -v  # 21 passed
cd ai && pytest tests/dev_relay/ -q                           # 658 passed
cd ai && pytest tests/dev_relay/test_compliance.py -v         # 56 passed
```

---

## 9. 참고

- PRD: [`docs/prd/dev-relay-write-tools.md`](../prd/dev-relay-write-tools.md) §3.3.2 (force-with-lease 정합성 판정 근거)
- 선행 QA: PR #52 (F-4 모체), PR #54 (F-5 모체)
- `AGENTS.md` — QA 체크리스트 양식, 컴플라이언스 0 hit 원칙
