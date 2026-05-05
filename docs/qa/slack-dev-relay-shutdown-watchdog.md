# QA: slack-dev-relay shutdown watchdog (PR #37)

- **slug**: `slack-dev-relay-shutdown-watchdog`
- **PR**: [#37 fix(dev-relay): AgentRunner.shutdown(timeout) watchdog 보강](https://github.com/deeptrading-lab/trading-signal-engine/pull/37)
- **브랜치**: `feature/slack-dev-relay-shutdown-watchdog`
- **HEAD**: `5c54a86`
- **PRD 참조**: [`docs/prd/slack-dev-relay.md`](../prd/slack-dev-relay.md) §3.7 (graceful shutdown 30초 timeout), AC-8
- **선행 이슈**: Issue #28 follow-up 항목 2
- **QA**: Codex (자동), 2026-05-06
- **판정**: **qa-passed**

---

## 1. 변경 범위 요약

| 파일 | 변경 |
|------|------|
| `ai/dev_relay/agent_runner.py` | `AgentRunner.shutdown(wait, timeout)` 의 timeout 인자를 실제로 강제 — 별도 daemon thread (`dev-relay-agent-shutdown`) 가 `executor.shutdown(wait=True)` 를 돌리고 `thread.join(timeout)` 로 대기, 만료 시 `executor.shutdown(wait=False)` + WARNING 로그 |
| `ai/dev_relay/main.py` | docstring 한 줄 정정 (PR #36 nit 이월) — 코드 동작 무변경 |
| `ai/tests/dev_relay/test_agent_runner_shutdown.py` | 신규, 4 케이스 (빠른/느린/None/wait=False) |

호출부 `ai/dev_relay/main.py:809` (`runner.shutdown(wait=True, timeout=_SHUTDOWN_TIMEOUT_S)` — 30초) 는 손대지 않음 → 회귀 위험 최소.

---

## 2. 자동화 테스트 결과

### 2.1 타겟 테스트

```
$ python -m pytest -q ai/tests/dev_relay/test_agent_runner_shutdown.py
....                                                                     [100%]
4 passed in 0.51s
```

| 테스트 | AC | 결과 |
|--------|-----|------|
| `test_fast_task_completes_within_timeout` | AC-1 (빠른 task 정상 종료) | PASS |
| `test_slow_task_triggers_force_shutdown` | AC-2 (느린 task 강제 종료 + WARNING) | PASS |
| `test_no_timeout_does_not_register_watchdog` | AC-3 (timeout=None 호환) | PASS |
| `test_wait_false_skips_watchdog` | AC-4 (wait=False 호환) | PASS |

### 2.2 전체 회귀

```
$ python -m pytest -q
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
........................................................................ [ 98%]
.........                                                                [100%]
513 passed in 0.72s
```

회귀 없음. AC-5 (호출부 finally 무사) 충족.

---

## 3. 수용 기준 매핑

| AC | 재현 절차 | 기대 결과 | 자동 검증 | 결과 |
|----|----------|----------|-----------|------|
| **AC-1. 빠른 task 정상 종료** | `runner.run_callable` 로 `time.sleep(0.05)` 콜러블 등록 후 `runner.shutdown(wait=True, timeout=1.0)` | shutdown 이 0.5초 안에 반환, future.result == "ok", `forcing` WARNING 0건 | `test_fast_task_completes_within_timeout` | PASS |
| **AC-2. 느린 task 강제 종료** | `time.sleep(2.0)` 콜러블 등록 후 `runner.shutdown(wait=True, timeout=0.2)` | shutdown 이 0.5초 안에 반환 (~0.2~0.3s), `shutdown timeout exceeded (0.2s) — forcing` WARNING 정확히 1건 | `test_slow_task_triggers_force_shutdown` | PASS |
| **AC-3. timeout=None 호환** | `runner.shutdown(wait=True)` (기존 호출 형태) | watchdog thread 미등록, 정상 종료, WARNING 0건 | `test_no_timeout_does_not_register_watchdog` | PASS |
| **AC-4. wait=False 호환** | `time.sleep(0.5)` 등록 + `runner.shutdown(wait=False, timeout=0.1)` | timeout 인자 무시·즉시 반환 (0.1초 미만), WARNING 0건 | `test_wait_false_skips_watchdog` | PASS |
| **AC-5. 회귀 보호 (main.py:809 finally)** | `python -m pytest -q` 전체 실행 | 513 passed, failure 0 | 전체 회귀 | PASS |

추가 정적 확인:
- `ai/dev_relay/main.py:803-812` finally 블록은 `handler.close()` / `runner.shutdown(...)` 두 호출을 각각 `try/except Exception: pass` 로 감싸 예외 누수가 없음. watchdog 실패 케이스에서도 종료 코드 0 으로 빠지는 흐름 유지.
- `_SHUTDOWN_TIMEOUT_S = 30.0` (main.py:83) 상수는 PRD §3.7 30초 timeout 명세와 정확히 일치.

---

## 4. 에지 케이스 점검

| 시나리오 | 처리 | 검증 방식 |
|----------|------|-----------|
| **timeout 만료 직후 task 가 끝남 (race)** | watchdog 이 force `shutdown(wait=False)` 호출 — 이미 끝난 worker thread 에는 no-op. WARNING 1건은 로그로만 남으므로 사용자 영향 없음 | `test_slow_task_triggers_force_shutdown` 가 `len(forced) == 1` 로 정확성 검증 |
| **shutdown 중복 호출** | `_lock` + `_closed` 가드로 두 번째 호출은 즉시 반환 | 기존 코드 (`with self._lock: if self._closed: return`) 보존 |
| **Claude Agent SDK 호출이 무한 블록 (네트워크 hang)** | watchdog thread 가 daemon=True 이므로 프로세스 종료를 막지 않음. ThreadPoolExecutor 가 worker thread 자체를 강제 종료할 수단은 없으나, 데몬 thread 라 `sys.exit` 시 함께 회수됨 | docstring 에 명시. `test_slow_task_triggers_force_shutdown` 가 시뮬레이션 (2초 sleep > 0.2초 timeout) |
| **wait=False + 진행 중 task 존재** | 신규 task 만 거절, 진행 task 는 background 진행. `_closed=True` 로 다음 호출에서 no-op | `test_wait_false_skips_watchdog` 가 0.5초 sleep task 가 살아있는 상황에서 즉시 반환 검증 |
| **timeout=0.0 같은 극단값** | `thread.join(0.0)` 즉시 반환 → drainer 가 살아있다고 판정 → force shutdown 분기 진입 | 본 PR 범위는 30초 고정 호출부라 미커버. `test_slow_task_triggers_force_shutdown` 의 0.2초 케이스가 사실상 동일 분기 |
| **이벤트 루프(slack-bolt) 가 SIGINT 직전 발사한 future** | finally 의 `runner.shutdown(timeout=30.0)` 가 30초 내 처리되면 정상 drain, 초과 시 WARNING 후 종료 코드 0 유지 | main.py:803-812 정적 검토 + 전체 회귀 |
| **거래소 서버 다운 / 네트워크 지연 / API 레이트리밋 / 뉴스 피드 장애** | 본 PR 범위(thread 풀 생명주기) 와 직접 인과 없음. dev-relay 데몬은 외부 거래소 호출 없음 (Slack + Claude Agent SDK 만). Claude Agent SDK 호출이 외부 의존성 hang 으로 길어지더라도 watchdog 이 30초 cap 으로 보장 | 위 "Claude Agent SDK 호출 무한 블록" 항목으로 갈음 |

---

## 5. 실행 환경

- Python: 시스템 default (`python -m pytest`)
- 작업 디렉토리: `/Applications/하영/code_source/trading-signal-engine`
- 브랜치: `feature/slack-dev-relay-shutdown-watchdog` @ `5c54a86`
- 커맨드:
  ```
  git fetch origin
  git checkout feature/slack-dev-relay-shutdown-watchdog
  python -m pytest -q ai/tests/dev_relay/test_agent_runner_shutdown.py
  python -m pytest -q
  ```

---

## 6. 결론

- 자동화 테스트 4/4, 전체 회귀 513/513 통과.
- AC 5 항목 모두 충족 (실패 0건).
- `qa-passed` 라벨 부여.
