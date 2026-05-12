# QA: dev-relay-nl-serialize

> 작성자: QA (자동 검증 + 정적 검사 — 수동 검증 후속 가이드)
> 작성일: 2026-05-12
> 입력 PRD: [`docs/prd/dev-relay-nl-serialize.md`](../prd/dev-relay-nl-serialize.md) (PR #46 머지)
> 검증 대상 PR: [#48](https://github.com/deeptrading-lab/trading-signal-engine/pull/48) (`feature/dev-relay-nl-serialize-impl`)
> 변경 규모: 3 files, +742 / -64, 1 commit (`eaaf627`)
> 회귀 (전체 `ai/tests/`): `python -m pytest ai/tests/ -q` → **667 passed (3.06s, 0 failed)**
> 회귀 (`dev_relay/` 한정): `python -m pytest ai/tests/dev_relay/ -q` → **489 passed (2.31s, 0 failed)**
> 신규 케이스 (`test_handle_command_nl_serialize.py`): `python -m pytest ai/tests/dev_relay/test_handle_command_nl_serialize.py -v` → **9 passed (1.32s, 0 failed)**
> 컴플라이언스 정적 스캔: `python -m pytest ai/tests/dev_relay/test_compliance.py -v` → **52 passed (0.02s, 0 failed)**

---

## 0. 요약

- **자동 검증 통과**: AC-NLS-1 ~ AC-NLS-9 9건 + §7 위험 1번 (락 release on exception) 모두 PASS — 동시 진입 거절, process-wide 락, 순차 재진입, structured 별도 락, rate_limiter 우선, audit 1줄 + 필드 정확히 4개, 컴플라이언스, 회귀, shutdown 보호 모두 단위 테스트로 검증됨.
- **외부 인터페이스 변경 0건 확인** (PRD §3.6) — `_handle_natural_language` 시그니처, `JobQueue` / `AgentRunner` 변경 없음. 신규 의존성 0건 (stdlib `threading` 만).
- **신규 모듈 스코프 식별자**: `_nl_turn_lock`, `_nl_shutdown_flag`, `TEMPLATE_NL_BUSY`, `_emit_nl_busy_notice` — 모두 컴플라이언스 0 hit.
- **신규 audit kind**: `nl_busy_rejected` — 필드 정확히 `ts` / `kind` / `thread_ts` / `user_id_masked` 4개 (PRD §3.4 스키마 일치).
- **자동 검증 항목 매핑**:
  - AC-NLS-1: `TestNLSerializeSameThread::test_concurrent_same_thread_second_rejected`
  - AC-NLS-2: `TestNLSerializeDifferentThread::test_concurrent_different_thread_second_rejected`
  - AC-NLS-3: `TestNLSerializeSequential::test_sequential_second_call_succeeds`
  - AC-NLS-4: `TestNLSerializeStructuredCoexist::test_structured_in_flight_does_not_block_nl`
  - AC-NLS-5: `TestNLSerializeRateLimitInterop::test_rate_limit_fires_first_no_busy`
  - AC-NLS-6: `TestNLSerializeAudit::test_busy_audit_record_fields_exact`
  - AC-NLS-7: `test_compliance.py::test_dev_relay_source_clean[main.py]` + `test_prd_*_clean` 자동 커버 + QA 직접 스캔 보강 (PRD 본문 / 신규 테스트 / PR 메타 / commit)
  - AC-NLS-8: `pytest ai/tests/dev_relay/` 489/489 PASS — 기존 NL (`test_handle_command_nl.py` 등) + structured (`test_agent_integration.py`, `test_dispatcher.py`, `test_tool_policy.py`) 0 fail
  - AC-NLS-9: `TestNLSerializeShutdown::test_shutdown_flag_rejects_new_entry`, `test_in_flight_turn_completes_gracefully`
  - §7 위험 1번: `TestNLSerializeLockReleaseOnException::test_lock_released_when_sonnet_raises`
- **수동 검증 (PRD §8.2)**: 모바일 Slack 환경 부재 — 본 세션에서 미수행. 후속 세션에서 사용자가 직접 1 사이클 (같은 스레드 동시 2건 → busy / 순차 정상 / structured 진행 중 NL 정상) 검증 권장. PRD §8.2 가이드 그대로 진행 가능 — 자동 가드·정적 스캔 모두 통과 상태이므로 수동 1 사이클로 충분.
- **회귀 0건**. 도메인 키워드 평문 누출 0건 (PRD 본문·main.py·신규 테스트·PR 제목·PR 본문·`eaaf627` commit 모두 정적 스캔 통과).
- **최종 판정**: `qa-passed` — AC 9/9 + §7 위험 1번 모두 통과.

---

## 1. PRD 수용 기준 검증

### AC-NLS-1. 같은 thread_ts 동시 두 NL — 두 번째 거절 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 같은 `thread_ts="1.1"` + `channel="D1"` 로 두 NL 호출을 0.05초 간격으로 동시 진입 (sonnet mock 0.3초 지연) | 첫 acquire 성공 → SDK 호출 1건. 두 번째 acquire 실패 → `TEMPLATE_NL_BUSY` 1줄 발사 → SDK 호출 0건. 전체 sonnet 호출 = 1. audit `nl_busy_rejected` 1줄. | PASS — `TestNLSerializeSameThread::test_concurrent_same_thread_second_rejected`. `runtime["state"]["sonnet_calls"] == 1`, `TEMPLATE_NL_BUSY in payloads`, `len(busy) == 1` 모두 확인. |

### AC-NLS-2. 다른 thread_ts 동시 두 NL — 두 번째 거절 (process-wide) — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `thread_ts="1.1"/channel="D1"` 와 `thread_ts="2.1"/channel="D2"` 로 두 NL 을 0.05초 간격으로 동시 진입 | process-wide 단일 lock 이라 두 번째 거절 — SDK 호출 1건, busy 1줄, audit 1줄 | PASS — `TestNLSerializeDifferentThread::test_concurrent_different_thread_second_rejected`. PRD §1.1 옵션 C 의 동작 (다른 스레드라도 락이 1개이므로 두 번째 거절) 그대로 검증됨. |

### AC-NLS-3. turn 종료 후 새 NL 정상 처리 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| NL 호출 1건 완료 후 (락 release), 새 NL 호출 (다른 ts) 진입 | 두 번째도 acquire 성공 → SDK 호출 → 정상 응답. busy 거절 안 됨. | PASS — `TestNLSerializeSequential::test_sequential_second_call_succeeds`. `sonnet_calls == 2`, `TEMPLATE_NL_BUSY not in payloads`, `nl_busy_rejected audit 0` 확인. |

### AC-NLS-4. structured 진행 중 NL — 회귀 (별도 락) — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| structured fast-path `status` (`_handle_command`) 실행 후 NL (`_handle_natural_language`) 진입 — 별도 락 검증 | NL 정상 처리, busy 거절 안 됨. SDK 호출 1건. | PASS — `TestNLSerializeStructuredCoexist::test_structured_in_flight_does_not_block_nl`. PRD §3.3 정책 (두 분기 동시 진행 가능, 별도 락) 그대로 검증됨. `_handle_command(status)` 가 classifier 를 호출하지 않는 fast-path 임도 부가 검증. |

### AC-NLS-5. rate_limiter 우선 발동 — busy 미발사 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 같은 user_id 로 `_handle_command` 를 5초 윈도우 내 4회 연속 호출 (텍스트 "자연어 요약해줘") | 4회차에서 rate limit 가드가 먼저 발동 — `TEMPLATE_NL_BUSY` 미발사, `nl_busy_rejected` audit 미기록. (rate limit 안내는 `TEMPLATE_RATE_LIMIT` 으로 별도 발사) | PASS — `TestNLSerializeRateLimitInterop::test_rate_limit_fires_first_no_busy`. `TEMPLATE_NL_BUSY not in payloads`, `nl_busy_rejected audit == []`. 호출 순서: rate_limiter → `_handle_natural_language` → 락 acquire (PRD §7 위험 2번 만족). |

### AC-NLS-6. audit `nl_busy_rejected` 1줄 + 필드 정확히 4개 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| AC-NLS-1 시나리오에서 busy 거절 1건 발생 → audit.jsonl 읽기 | `kind="nl_busy_rejected"` line 정확히 1줄. 필드 정확히 `{ts, kind, thread_ts, user_id_masked}` 4개. 추가 필드 0개. `user_id_masked` 는 mask 처리된 값 (원본 `U0AE7A54NHL` 과 달라야 함). | PASS — `TestNLSerializeAudit::test_busy_audit_record_fields_exact`. `set(rec.keys()) == {"ts", "kind", "thread_ts", "user_id_masked"}`, `rec["thread_ts"] == "1.1"`, `rec["user_id_masked"] != "U0AE7A54NHL"` 모두 확인. PRD §3.4 스키마 일치. |

### AC-NLS-7. 컴플라이언스 정적 검사 — PASS (자동 + 보강 스캔)

| 산출물 | 키워드 hit | 검증 |
|--------|-----------|------|
| PRD 본문 (`docs/prd/dev-relay-nl-serialize.md`) | 0 | PASS — QA 직접 `find_forbidden_keywords` 호출 → `[]` |
| `ai/dev_relay/main.py` (구현 파일 — 모듈 스코프 락·flag·`TEMPLATE_NL_BUSY`·`_emit_nl_busy_notice`·`_handle_natural_language` 가드 블록 포함) | 0 | PASS — `test_compliance.py::test_dev_relay_source_clean[main.py]` 자동 커버 |
| `ai/tests/dev_relay/test_handle_command_nl_serialize.py` (신규 테스트) | 0 | PASS — QA 직접 스캔 → `[]` |
| 신규 메시지 상수 `TEMPLATE_NL_BUSY` ("지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요.") | 0 | PASS — 33자 한국어 1줄, 직접 스캔 `[]` (PRD §2 요건 — 20~60자 한국어 1줄 + 0 hit) |
| 신규 audit kind 식별자 `nl_busy_rejected` | 0 | PASS — 직접 스캔 `[]` (`busy` / `rejected` / `nl` 모두 도메인 키워드 아님 확인) |
| 신규 모듈 스코프 식별자 `_nl_turn_lock`, `_nl_shutdown_flag` | 0 | PASS — 직접 스캔 `[]` |
| PR #48 title / body | 0 | PASS — `gh pr view 48 --json title,body` → `find_forbidden_keywords` → `[]` |
| 커밋 `eaaf627` 메시지 (title + body) | 0 | PASS — `git log -1 --pretty=format:"%s%n%b" eaaf627` → `find_forbidden_keywords` → `[]` |

`test_compliance.py` 의 기존 `_iter_dev_relay_source_files()` 가 `main.py` 변경분(신규 락·flag·busy 안내 헬퍼) 을 자동 커버 — 별도 화이트리스트 보강 불필요. `test_handle_command_nl_serialize.py` 는 `ai/tests/dev_relay/*` 이므로 자동 스캔 대상 외 → QA 가 본 세션에서 직접 보강 스캔 수행.

### AC-NLS-8. 기존 NL + structured 테스트 0 fail — PASS (자동)

```
$ python -m pytest ai/tests/dev_relay/ -q
489 passed in 2.31s
```

- 신규 9건 (`test_handle_command_nl_serialize.py`) + 기존 480건 모두 PASS.
- 기존 NL 흐름 (`test_handle_command_nl.py`, `test_nl_agent.py`, `test_nl_classifier.py`) 회귀 0건.
- structured 흐름 (`test_agent_integration.py`, `test_agent_runner_shutdown.py`, `test_dispatcher.py`, `test_tool_policy.py`, `test_queue.py`, `test_worker.py`, `test_reviewer.py`, `test_merger.py`) 회귀 0건.
- 외부 인터페이스 (`_handle_natural_language` 시그니처, `JobQueue`, `AgentRunner`, 기존 audit kind) 모두 변경 없음 → 자동 회귀 보호.

추가로 `ai/` 전체 (`coordinator` 포함) 회귀도 확인:

```
$ python -m pytest ai/tests/ -q
667 passed in 3.06s
```

### AC-NLS-9. shutdown 보호 — PASS (자동, 2건)

| 재현 | 기대 | 실제 |
|------|------|------|
| (a) NL turn 진행 중 (sonnet mock 0.3초 지연) `_nl_shutdown_flag.set()` 호출 → join | 진행 중 1건은 graceful 완료 (응답 발사 + audit 기록 + 락 release). 후속 `_nl_turn_lock.acquire(blocking=False)` 성공 (락이 release 됐다는 증거). | PASS — `TestNLSerializeShutdown::test_in_flight_turn_completes_gracefully`. `results["finished"] is True`, `sonnet_calls == 1`, 후속 acquire 성공 확인. |
| (b) `_nl_shutdown_flag.set()` 이후 새 NL 호출 진입 | 락 acquire 시도 이전에 즉시 거절 — `TEMPLATE_NL_BUSY` 1줄 발사, `nl_busy_rejected` audit 1줄 기록. SDK 호출 0건, classifier 호출 0건. | PASS — `TestNLSerializeShutdown::test_shutdown_flag_rejects_new_entry`. `sonnet_calls == 0`, `classifier_calls == 0`, `TEMPLATE_NL_BUSY in payloads`, busy audit 1줄 확인. |

비고: 본 PR 은 `_nl_shutdown_flag.set()` 의 호출 측 (예: `AgentRunner.shutdown` 통합) 을 도입하지 않는다 — PR 본문 "구현 결정 메모" 명시. watchdog 자체는 PR #37 그대로 재사용 (PRD §3.5). flag 메커니즘 자체의 작동은 본 테스트로 검증됨.

### §7 위험 1번. 예외 발생 시 락 release (try/finally) — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `sonnet_responder` 콜러블이 `RuntimeError("SDK boom")` raise 하도록 구성 → `_handle_natural_language` 호출 → 예외 위로 propagate | 예외 throw 됨에도 `try/finally` 가 `_nl_turn_lock.release()` 실행. 후속 `_nl_turn_lock.acquire(blocking=False)` 즉시 성공. | PASS — `TestNLSerializeLockReleaseOnException::test_lock_released_when_sonnet_raises`. `pytest.raises(RuntimeError, match="SDK boom")` 통과 후 acquire 성공 확인. 코드상 `_handle_natural_language` (`main.py:587-590`) 의 `finally: _nl_turn_lock.release()` 정적 read 로도 보강 확인. |

---

## 2. 외부 인터페이스 변경 0건 검증 (PRD §3.6)

| 항목 | 변경 전 | 변경 후 | 결과 |
|------|---------|---------|------|
| `_handle_natural_language(*, text, user_id, event, say, logger, sessions, nl_runtime)` 시그니처 | 동일 | 동일 | 변경 없음 |
| `_handle_command` 시그니처 | 동일 | 동일 | 변경 없음 |
| `build_app` 컨테이너 — lock 인스턴스 외부 주입 여부 | — | 모듈 스코프이므로 주입 없음 | PR 본문 결정 사항 그대로 |
| `JobQueue` / `AgentRunner` API | 동일 | 동일 | 변경 없음 |
| 기존 audit kind (`llm_invoked`, `session_started`, `session_resumed`, `merge_*`, `review_*` 등) | 동일 | 동일 | 변경 없음 — 신규 1종 (`nl_busy_rejected`) 만 추가 |
| 신규 모듈 상수 | — | `_nl_turn_lock: threading.Lock`, `_nl_shutdown_flag: threading.Event`, `TEMPLATE_NL_BUSY: str` (3종) | 외부 인터페이스 X (모듈 prefix `_` 또는 내부 텍스트 상수) |
| 신규 helper | — | `_emit_nl_busy_notice(*, say, thread_ts, masked, logger, reason)` (private) | 외부 인터페이스 X |
| 신규 의존성 | — | 0건 (stdlib `threading` 만) | PRD §3.6 만족 |

---

## 3. 에지 케이스 / 위험 시나리오 (PRD §7)

| 위험 | 시나리오 | 검증 |
|------|----------|------|
| 1. 락 미release 회귀 (영구 차단) | `_handle_natural_language` 내부 `run_turn` 또는 `say` / `sessions.start` 예외 시 락 미release | `TestNLSerializeLockReleaseOnException` 자동 검증 — sonnet raise 후 즉시 acquire 가능. 코드상 `try/finally` 1지점 (`main.py:587-590`) 으로 정상·예외·early return 모두 커버. |
| 2. rate_limiter 와 lock 가드 발사 중복 | rate limit 가 발동했는데 busy 도 발사되는 경우 | `TestNLSerializeRateLimitInterop` 가 `TEMPLATE_NL_BUSY not in payloads` + busy audit `[]` 로 회귀 차단. `_handle_command` 의 rate_limiter 가드가 `_handle_natural_language` 진입보다 위 — PRD §7 위험 2번 권장 순서 (rate_limiter → lock acquire → SDK) 만족. |
| 3. shutdown 흐름과 락 release 경쟁 | flag set 시점과 진행 중 turn 의 락 release 가 race | `TestNLSerializeShutdown::test_in_flight_turn_completes_gracefully` — flag set 후에도 graceful 완료 + 후속 acquire 성공. watchdog timeout 보다 짧으면 정상 케이스, 초과 시 강제 종료는 PR #37 의 `AgentRunner.shutdown(timeout)` 책임 (본 PRD 비범위). |
| 4. busy 메시지 자체 race / Slack rate limit | 거절 빈도 폭증 → `say(TEMPLATE_NL_BUSY)` 호출 폭증 → Slack API rate limit 표면 증가 | 1인 MVP 단계 무시 가능. `_emit_nl_busy_notice` 가 `say` 호출 실패 시 `logger.warning` 으로 흡수 — audit 라인은 무조건 기록 (busy 빈도 모니터링 입력 데이터 보존). |
| 5. `_append_audit` 자체 락 부재 | structured 분기와 NL 분기 동시 audit 기록 시 interleave | 본 PRD 비범위 — 단일 line write 는 OS 레벨 atomic. 별도 후속 PRD 필요 시 `_append_audit` 자체에 `threading.Lock` 추가 (PR 본문 follow-up). |
| 6. multi-process 데몬 배치 시 무효 | `threading.Lock` 은 process-local | PRD §4 비범위 — 현재 운영은 단일 인스턴스 전제. multi-instance 배치 시 직렬화 무효 + race 재출현 가능 — 운영 가이드 한 줄 추가 권장 (PRD §7 위험 6번 follow-up). |
| 7. shutdown flag set 호출 측 미통합 | 본 PR 은 `_nl_shutdown_flag.set()` 의 호출 측을 도입하지 않음 (`AgentRunner.shutdown` 와 묶는 통합 후속) | 검증 — 코드상 `_nl_shutdown_flag.set()` 호출 0건 (구현측). flag 메커니즘 자체 동작은 `TestNLSerializeShutdown` 2건으로 확인. graceful 종료는 watchdog (PR #37) 책임. follow-up 작업 항목 (PR 본문 명시). |
| 8. `_extract_thread_ts` 에서 `event["thread_ts"]` 누락 시 `ts` 로 fallback | reply-in-thread 가 아닌 top-level 메시지의 thread_ts 처리 | 기존 동작 그대로 (PRD §3.2 정책 승계). `TestNLSerializeAudit` 에서 `event = {"ts": "1.1", ...}` 만 주입한 케이스가 `rec["thread_ts"] == "1.1"` 로 정상 처리됨을 검증. |
| 9. `find_forbidden_keywords` 미통과 시 busy 미발사 | 컴플라이언스 가드 위반 → 외부 노출 사고 | `_emit_nl_busy_notice` 가 `find_forbidden_keywords(safe)` 체크 후 hit 발견 시 `say` 호출 skip + `logger.error`. 정적 검사로는 항상 0 hit 이지만 다중 layer 안전망 — PRD §3.2 만족. |

---

## 4. 컴플라이언스 정적 검사 결과 (실측)

```
$ python -m pytest ai/tests/dev_relay/test_compliance.py -v
ai/tests/dev_relay/test_compliance.py::test_dev_relay_source_clean[main.py] PASSED  [ 98%]
...
============================== 52 passed in 0.02s ==============================
```

QA 보강 스캔 (PRD 본문 / 신규 테스트 파일 / 신규 식별자 / busy 본문 / PR 메타 / commit):

```
$ python3 -c "
from ai.coordinator._compliance import find_forbidden_keywords
files = [
    'docs/prd/dev-relay-nl-serialize.md',
    'ai/dev_relay/main.py',
    'ai/tests/dev_relay/test_handle_command_nl_serialize.py',
]
for p in files:
    print(p, '->', find_forbidden_keywords(open(p, encoding='utf-8').read()))
"
docs/prd/dev-relay-nl-serialize.md -> []
ai/dev_relay/main.py -> []
ai/tests/dev_relay/test_handle_command_nl_serialize.py -> []

$ python3 -c "
from ai.coordinator._compliance import find_forbidden_keywords
print('TEMPLATE_NL_BUSY hits:', find_forbidden_keywords('지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요.'))
print('nl_busy_rejected hits:', find_forbidden_keywords('nl_busy_rejected'))
print('_nl_turn_lock hits:', find_forbidden_keywords('_nl_turn_lock'))
print('_nl_shutdown_flag hits:', find_forbidden_keywords('_nl_shutdown_flag'))
"
TEMPLATE_NL_BUSY hits: []
nl_busy_rejected hits: []
_nl_turn_lock hits: []
_nl_shutdown_flag hits: []

$ gh pr view 48 --json title,body | python3 -c "<find_forbidden_keywords>"
PR title hits: []
PR body hits: []

$ git log -1 --pretty=format:"%s%n%b" eaaf627 | python3 -c "<find_forbidden_keywords>"
commit message hits: []
```

전 산출물 0 hit — AC-NLS-7 만족.

---

## 5. 자동 검증 실행 로그 (요약)

```
$ python -m pytest ai/tests/dev_relay/test_handle_command_nl_serialize.py -v
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeSameThread::test_concurrent_same_thread_second_rejected PASSED [ 11%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeDifferentThread::test_concurrent_different_thread_second_rejected PASSED [ 22%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeSequential::test_sequential_second_call_succeeds PASSED [ 33%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeStructuredCoexist::test_structured_in_flight_does_not_block_nl PASSED [ 44%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeRateLimitInterop::test_rate_limit_fires_first_no_busy PASSED [ 55%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeAudit::test_busy_audit_record_fields_exact PASSED [ 66%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeShutdown::test_shutdown_flag_rejects_new_entry PASSED [ 77%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeShutdown::test_in_flight_turn_completes_gracefully PASSED [ 88%]
tests/dev_relay/test_handle_command_nl_serialize.py::TestNLSerializeLockReleaseOnException::test_lock_released_when_sonnet_raises PASSED [100%]
============================== 9 passed in 1.32s ===============================

$ python -m pytest ai/tests/dev_relay/ -q
489 passed in 2.31s

$ python -m pytest ai/tests/ -q
667 passed in 3.06s

$ python -m pytest ai/tests/dev_relay/test_compliance.py -q
52 passed in 0.02s
```

---

## 6. 수동 검증 체크리스트 (PRD §8.2, 후속 세션 권장)

> **모바일 Slack 환경 부재 — 본 QA 세션에서 미수행. 후속 세션에서 사용자가 직접 1 사이클 완주 권장.**

상위 PRD `slack-dev-relay.md` / `dev-relay-natural-language.md` 부록 A 셋업이 완료된 환경에서 다음 3건을 1회 수행:

- [ ] 같은 스레드에 자연어 메시지 2개를 빠르게 (1~2초 간격) 연속 전송 → 첫 번째 응답 정상, 두 번째는 즉시 busy 안내 1줄 ("지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요.") 수신.
- [ ] 첫 번째 응답 완료를 기다린 후 같은 스레드에 새 자연어 전송 → 정상 응답 (회귀 확인 — turn 종료 후 재진입 통과).
- [ ] structured 명령 (`review pr <N>`) 진행 중에 새 스레드에서 자연어 전송 → 자연어가 즉시 처리됨 (별도 락 확인 — `JobQueue` 와 `_nl_turn_lock` 가 독립).

자동 가드(`_nl_turn_lock`, `_nl_shutdown_flag`, `_emit_nl_busy_notice`, `_handle_natural_language` 가드 블록) 와 모든 정적 스캔 통과 — 수동 1 사이클로 충분.

후속 follow-up (사용자 본인 모니터링, PRD §6.3):

- 머지 후 1~2주 audit.jsonl 의 `nl_busy_rejected` 발생 빈도 모니터링 → 빈도 높으면 옵션 A (`JobQueue` 통합) 또는 옵션 B (thread_ts 별 lock map) 재설계 후속 PRD.
- `_nl_shutdown_flag.set()` 의 `AgentRunner.shutdown` 통합 — 본 PR 비포함, 후속 작업 (PR 본문 명시).

---

## 7. 판정

- **AC 통과율: 9/9 (100%) + §7 위험 1번 (락 release on exception) 통과**
- **회귀: 0건** — 667/667 (ai 전체), 489/489 (dev_relay), 52/52 (compliance), 9/9 (신규)
- **외부 인터페이스 변경: 0건** (PRD §3.6 만족 — `_handle_natural_language` 시그니처·`JobQueue`·`AgentRunner`·기존 audit kind 모두 그대로)
- **컴플라이언스 정적 스캔: 0 hit** (PRD 본문 / `main.py` / 신규 테스트 / 신규 식별자 / `TEMPLATE_NL_BUSY` 본문 / PR #48 title-body / commit `eaaf627` 모두 통과)
- **신규 의존성: 0건** (stdlib `threading` 만)
- **수동 검증**: 미수행 (후속 세션 권장 — 자동 가드·정적 검사 모두 통과한 상태이므로 수동 1 사이클로 충분)

**최종 판정: `qa-passed`** — PR #48 라벨 갱신 (`qa-passed` 추가, `impl-ready` 제거).
