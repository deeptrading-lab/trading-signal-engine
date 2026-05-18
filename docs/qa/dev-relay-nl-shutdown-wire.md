# QA: dev-relay-nl-shutdown-wire (chore)

> 작성자: QA (자동 검증)
> 작성일: 2026-05-13
> 입력: chore — PRD 없음. PR #48 reviewer P2-1 / P2-2 후속.
> 검증 대상 PR: [#49](https://github.com/deeptrading-lab/trading-signal-engine/pull/49) (`feature/dev-relay-nl-shutdown-wire`)
> 변경 규모: +162 / -1, 3 files, 1 commit (`1d59691`)
> 회귀 (dev_relay 전체): `python -m pytest ai/tests/dev_relay/ -q` → **494 passed (2.43s, 0 failed)**
> 회귀 (컴플라이언스): `python -m pytest ai/tests/dev_relay/test_compliance.py -v` → **52 passed (0.02s, 0 hit)**
> 회귀 (PR #48 NL serialize): `python -m pytest ai/tests/dev_relay/test_handle_command_nl_serialize.py -v` → **9 passed (1.30s, 0 failed)**

---

## 0. 요약

- chore PR 이므로 PRD AC 매핑 대신 PR #48 reviewer 가 남긴 P2 메모 2건을 검증 항목으로 변환했다.
- **신규 테스트 5/5 PASS** (`test_shutdown_dev_relay.py`) — `shutdown_dev_relay` 헬퍼의 4 가지 동작 (flag set / runner 위임 / idempotent / logger optional + INFO emit) 모두 통과.
- **회귀 0건** — `ai/tests/dev_relay/` 494 전건 PASS, 컴플라이언스 52 PASS (`main.py` 신규 코드 포함 0 hit).
- **PR #48 의 NL serialize 9건 0 fail** — shutdown flag set 후 새 진입 거절 (AC-NLS-9 (b)) 회귀 보존.
- **SESSION_NOTES** — 2026-05-13 entry 가 정상 append 됨 (직전 2026-05-07 entry 구조 동일, 다음 세션 follow-up 표 A-3~C-3 으로 갱신).
- **최종 판정**: `qa-passed`.

---

## 1. 검증 항목 매핑 (reviewer P2 → 테스트)

### 핵심 (P2-2 — `_nl_shutdown_flag.set()` 호출 측 통합)

| # | 검증 항목 | 재현 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| 1 | `shutdown_dev_relay()` 호출 후 `_nl_shutdown_flag.is_set()` == True | `test_shutdown_dev_relay.py::test_sets_nl_shutdown_flag` — 헬퍼 호출 전후 flag 상태 비교 | 호출 전 `False`, 호출 후 `True` | flag 가 정확히 set | PASS |
| 2 | `AgentRunner.shutdown(timeout=...)` 위임 정상 | `test_delegates_to_runner_shutdown` — 헬퍼 호출 후 runner 에 새 task 제출 시 RuntimeError | runner 가 closed 상태로 전이, `run_callable` 두 번째 제출 거절 | RuntimeError 발생 (closed 검증) | PASS |
| 3 | shutdown 호출 후 새 NL 진입 즉시 거절 (PR #48 AC-NLS-9 (b) 회귀) | `test_handle_command_nl_serialize.py::TestNLSerializeShutdown::test_shutdown_flag_rejects_new_entry` | flag set 상태에서 새 NL 진입 시 `TEMPLATE_NL_BUSY` 발사 + `nl_busy_rejected` audit | 정상 거절 + audit 기록 | PASS |
| 4 | `run()` finally 절에서 헬퍼 호출 — 데몬 정상 종료 흐름 회귀 0 | `ai/dev_relay/main.py:1422-1426` 정적 검증 + 전체 회귀 | finally 절이 `shutdown_dev_relay(runner, timeout=_SHUTDOWN_TIMEOUT_S, logger=logger)` 를 호출 | 호출 라인 존재 확인. 본 모듈은 외부 연결로 단위 테스트 대상이 아니지만 (모듈 docstring 명시), `_SHUTDOWN_TIMEOUT_S=30.0` 그대로 사용 + `_nl_shutdown_flag` 모듈 스코프 단일 인스턴스 wire 확인. dev_relay 회귀 494 PASS. | PASS |

### 부수 (P2-1 — 코멘트 보강)

| # | 검증 항목 | 재현 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| 5 | `_emit_nl_busy_notice` fallback path 동작 변경 없음 — 가드 위반 시 audit 만 기록 + 사용자 무발사 (PR #48 동작 회귀) | `test_handle_command_nl_serialize.py::TestNLSerializeAudit::test_busy_audit_record_fields_exact` + `main.py:449-467` 정적 검증 | 가드 위반 시 `say()` 호출 안 함, `nl_busy_rejected` audit 1줄만 기록 | 동작 동일. PR #48 의 코드 흐름 변경 없이 인라인 코멘트만 보강 (`main.py:451-453`) | PASS |
| 6 | docstring/코멘트 컴플라이언스 0 hit | `test_compliance.py::test_dev_relay_source_clean[main.py]` | `find_forbidden_keywords(main.py)` 가 빈 리스트 반환 | PASS — main.py 평문 0 hit (P2-1 신규 코멘트 포함) | PASS |

### 정책 (D-1 — SESSION_NOTES 동봉)

| # | 검증 항목 | 재현 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| 7 | `docs/SESSION_NOTES.md` 2026-05-13 entry 추가 + 직전 entry(2026-05-07) 형식 따르는지, follow-up 표 갱신됐는지 | `docs/SESSION_NOTES.md:203-239` 정독 | 5 섹션 (요약/처리한 일/결정·합의 사항/다음 세션 시작 포인트/미결·블록) + follow-up 표 갱신 (A/B/C 그룹) | 5 섹션 완비. follow-up 표가 직전 1~8번 일부 종결분 반영해 A-3~C-3 으로 갱신 (1번 = PR #48 종결, 5번 P2-1/P2-2 = 본 PR 종결). 정책 (단독 PR 금지) 명시. | PASS |
| 8 | SESSION_NOTES 본문 컴플라이언스 0 hit (정적 스캐너 통과) | `test_compliance.py` 가 SESSION_NOTES 를 dev_relay source 스캔 대상에서 제외하므로, 외부 노출 산출물 기준 미회귀 — 본 PR 의 신규 entry 가 도입한 키워드 0건 (`signal`/`trading` 등 기존 entry 에 이미 포함된 URL·repo 명만 등장, 신규 표현 0건) | 신규 entry 가 베이스라인 keyword set 외의 도메인 키워드를 추가하지 않음 | 베이스라인 일치 — 본 entry 의 도메인 키워드는 슬러그명 `dev-relay-nl-shutdown-wire` / `dev-relay-nl-serialize` (PRD 슬러그) 등 코드/repo 식별자 한정 | PASS |

### 회귀

| # | 검증 항목 | 명령 | 결과 | 판정 |
|---|---|---|---|---|
| 9 | `ai/tests/dev_relay/` 전체 0 fail | `python -m pytest ai/tests/dev_relay/ -q` | **494 passed in 2.43s** | PASS |
| 10 | `test_compliance.py` 0 hit | `python -m pytest ai/tests/dev_relay/test_compliance.py -v` | **52 passed in 0.02s** | PASS |
| 11 | PR #48 의 `test_handle_command_nl_serialize.py` 9건 0 fail | `python -m pytest ai/tests/dev_relay/test_handle_command_nl_serialize.py -v` | **9 passed in 1.30s** | PASS |

---

## 2. 실행 로그 (요약)

### 신규 테스트

```
ai/tests/dev_relay/test_shutdown_dev_relay.py::TestShutdownDevRelayWiring::test_sets_nl_shutdown_flag PASSED
ai/tests/dev_relay/test_shutdown_dev_relay.py::TestShutdownDevRelayWiring::test_delegates_to_runner_shutdown PASSED
ai/tests/dev_relay/test_shutdown_dev_relay.py::TestShutdownDevRelayWiring::test_idempotent_double_call PASSED
ai/tests/dev_relay/test_shutdown_dev_relay.py::TestShutdownDevRelayWiring::test_logger_optional PASSED
ai/tests/dev_relay/test_shutdown_dev_relay.py::TestShutdownDevRelayWiring::test_logger_info_message_emitted PASSED
============================== 5 passed in 0.02s ===============================
```

### 전체 회귀

```
ai/tests/dev_relay/ → 494 passed in 2.43s
```

### 컴플라이언스

```
ai/tests/dev_relay/test_compliance.py → 52 passed in 0.02s
(test_dev_relay_source_clean[main.py] PASS 포함)
```

### PR #48 NL serialize 회귀 (`shutdown_flag_rejects_new_entry` 포함)

```
ai/tests/dev_relay/test_handle_command_nl_serialize.py → 9 passed in 1.30s
```

---

## 3. 에지 케이스 검증

본 chore PR 은 외부 의존(거래소·뉴스 피드·네트워크) 흐름을 건드리지 않으므로 표준 에지 케이스는 비범위. 본 PR 한정 에지 케이스만 검증:

| 케이스 | 검증 방법 | 결과 |
|---|---|---|
| `shutdown_dev_relay` 다중 호출 (한 데몬에 SIGINT → finally 진입 후 사용자가 SIGTERM 추가 전송 시나리오) | `test_idempotent_double_call` — 같은 runner 로 헬퍼 2회 호출 | PASS — `Event.set` 이 idempotent (이미 set 상태면 no-op), `AgentRunner.shutdown` 도 closed 재호출 시 early return |
| `logger=None` 호출 (`run()` 외부에서 직접 호출 시) | `test_logger_optional` | PASS — INFO 라인 생략 + 정상 wire 동작 |
| 진행 중 NL turn 1건 graceful 종료 (flag set 이전 락 획득한 turn) | `test_handle_command_nl_serialize.py::TestNLSerializeShutdown::test_in_flight_turn_completes_gracefully` (PR #48 회귀 보존) | PASS — `try/finally` 가 락 release 강제 |

---

## 4. 판정

- 핵심 4/4, 부수 2/2, 정책 2/2, 회귀 3/3 — 총 **11/11 PASS**.
- 실패 0건.
- **최종**: `qa-passed`.
