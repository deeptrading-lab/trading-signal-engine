# QA 리포트: cost-aware-llm-pipeline

> 작성자: QA 에이전트
> 작성일: 2026-04-25
> 대상 PRD: `docs/prd/cost-aware-llm-pipeline.md`
> 대상 PR: https://github.com/deeptrading-lab/trading-signal-engine/pull/1
> 대상 브랜치: `feature/cost-aware-llm-pipeline`
> 대상 커밋: `b889875`
> 실행 환경: Python 3.9.6 / pytest 8.4.2 / darwin 25.3.0

---

## 0. 실행 요약

- 자동화 테스트: **65 / 65 PASSED** (`python3 -m pytest ai/tests/ -v`, 0.28s)
- PRD AC 25개 (R1–R6, C1–C5, T1–T7, P1–P3, I1–I4, D1–D3) 모두 **자동화 또는 스모크 테스트로 커버**됨
- 실패 0건, 미커버 0건
- edge case(거래소 피드 장애·네트워크 지연·레이트리밋·예산 폭주·뉴스 피드 버스트) 점검: 본 모듈은 LLM 호출 경로 한정이라, 외부 피드 장애는 상위 파이프라인 책임. 단 "레이트리밋 폭주"·"예산 폭주"는 본 모듈에서 의도한 대로 동작하는 것을 확인.
- **판정: qa-passed 권장**

---

## 1. 수용 기준별 테스트 매핑·결과

### 1.1 모델 라우팅 (AC-R)

| AC | 재현 절차 | 기대 결과 | 자동화 테스트 | 결과 |
|----|-----------|-----------|----------------|------|
| AC-R1 | `select_model(text_length=10_000, item_count=0)` 호출 | `Model.SONNET` 반환 | `ai/tests/test_router.py::TestRouter::test_router_sonnet_by_text_length` | PASSED |
| AC-R2 | `select_model(text_length=9_999, item_count=29)` 호출 | `Model.HAIKU` 반환 | `test_router_haiku_below_threshold` | PASSED |
| AC-R3 | `select_model(text_length=0, item_count=30)` 호출 | `Model.SONNET` 반환 | `test_router_sonnet_by_item_count` | PASSED |
| AC-R4 | `select_model(text_length=0, item_count=29)` 호출 | `Model.HAIKU` 반환 | `test_router_haiku_by_item_count_below` | PASSED |
| AC-R5 | `select_model(50_000, 100, force=Model.HAIKU)` 호출 | `Model.HAIKU` 반환 (force 우선) | `test_router_force_overrides_threshold` | PASSED |
| AC-R6 | 동일 인자를 3회 반복 호출 (5_000/10, 10_000/0, 0/30, 50_000/100+HAIKU) | 3회 모두 동일 결과 (결정적) | `test_router_deterministic` + 경계값·force variant | PASSED |

보강 테스트(결정적 동작 확인을 강화):
- `test_router_boundary_text_length` (10_000 경계, 9_999, 10_001)
- `test_router_boundary_item_count` (30 경계, 29, 31)
- `test_router_force_with_haiku/sonnet/opus`

### 1.2 CostTracker (AC-C)

| AC | 재현 절차 | 기대 결과 | 자동화 테스트 | 결과 |
|----|-----------|-----------|----------------|------|
| AC-C1 | `CostTracker(budget_usd=1.0)`에 `.add(1000, 500, usd=0.4)` | 원본 `usd_spent` 그대로, 새 인스턴스 `usd_spent==0.4` | `test_cost_tracker_immutability` | PASSED |
| AC-C2 | `CostTracker(budget_usd=1.0).add(..., usd=1.1)` | `BudgetExceededError` raise | `test_cost_tracker_budget_exceeded` | PASSED |
| AC-C3 | 누적 합이 정확히 `budget_usd == 1.0`이 되는 `add` | 성공 (strict `>` 의미) | `test_cost_tracker_budget_exact_match`, `test_cost_tracker_budget_validation_boundary` | PASSED |
| AC-C4 | `tracker.usd_spent = 99` | `FrozenInstanceError` | `test_cost_tracker_frozen` | PASSED |
| AC-C5 | `tracker.new_attribute = "x"` | `AttributeError` (__slots__) | `test_cost_tracker_slots` | PASSED |

주의: `ai/llm/cost_tracker.py`는 Python 3.10 미만에서 `slots=True`를 제외하도록 조건부 처리되어 있다. 이번 실행 환경(Python 3.9.6)에서도 `AttributeError`는 frozen dataclass의 `__setattr__` 차단으로 충족되어 AC-C5가 통과한다. 실제 운영(Python 3.11+) 환경에서는 `__slots__`가 정식으로 적용되어 동일 결과. PRD의 "가정·제약"(Python 3.11+)과 일치한다.

보강 테스트: `test_cost_tracker_model_based_pricing`, `test_cost_tracker_sonnet_pricing`, `test_cost_tracker_cumulative`, `test_cost_tracker_cannot_mix_usd_and_model`, `test_cost_tracker_must_specify_usd_or_model`.

### 1.3 좁은 재시도 (AC-T)

| AC | 재현 절차 | 기대 결과 | 자동화 테스트 | 결과 |
|----|-----------|-----------|----------------|------|
| AC-T1 | `APIConnectionError` 3회 → 4회째 성공으로 mock, `@narrow_retry` 래핑 후 호출 | 최종 성공 반환, 호출 횟수 4 | `test_retry_retryable_succeed_on_fourth` + 실 SDK 예외로 스모크 재확인(아래) | PASSED |
| AC-T2 | `RateLimitError` 계속 발생 | 5회 시도 후 raise (6회째 호출 없음) | `test_retry_retryable_max_retries` + 실 SDK 예외 스모크 | PASSED |
| AC-T3 | `InternalServerError` 동일 정책 | AC-T1/T2와 같은 재시도 | `test_retry_another_retryable` | PASSED |
| AC-T4 | `AuthenticationError` raise | 재시도 없이 1회 | `test_retry_non_retryable_no_retry` + 실 SDK 예외 스모크 | PASSED |
| AC-T5 | `BadRequestError` raise | 재시도 없이 1회 | `test_retry_other_error_no_retry` + 실 SDK 예외 스모크 | PASSED |
| AC-T6 | 재시도 간격 측정 (sleep 훅) | 간격이 지수적으로 증가 (1초→2초→4초 하한 0.8/1.6/3.2s) | `test_retry_exponential_backoff` | PASSED |
| AC-T7 | 누적 대기 합산 | ≤ 60초 | `test_retry_max_total_wait` | PASSED |

추가 검증 (QA가 로컬 파이썬 스모크로 확인):
- 실제 `anthropic.APIConnectionError` 3회 후 성공 시 호출 4회 (`AC-T1 real: result=success, calls=4`)
- 실제 `anthropic.RateLimitError` 연속 발생 시 5회로 종료 (`AC-T2 real: calls=5`)
- 실제 `anthropic.AuthenticationError`, `BadRequestError` 각각 1회만 호출 (`AC-T4/T5 real: calls=1`)

**참고**: `test_retry.py`의 대부분 테스트는 테스트용 헬퍼 `narrow_retry_test` (커스텀 `RetryableError`/`NonRetryableError`)로 로직을 검증한다. 실제 `@narrow_retry`는 Anthropic SDK 예외 타입에 직접 의존하고 그 동작을 위 스모크 테스트로 보완 확인했다. `TestNarrowRetryDecorator` 클래스가 래핑·인자 전달 같은 기본 동작도 보장한다.

### 1.4 프롬프트 캐싱 (AC-P)

| AC | 재현 절차 | 기대 결과 | 자동화 테스트 | 결과 |
|----|-----------|-----------|----------------|------|
| AC-P1 | `build_system_block("x"*1200)` | `cache_control: {"type":"ephemeral"}` 포함 | `test_cache_control_long_prompt` | PASSED |
| AC-P2 | `build_system_block("x"*500)` | `cache_control` 키 없음 | `test_no_cache_control_short_prompt` | PASSED |
| AC-P3 | 반환 블록 구조 검증 (`type=text`, `text=<str>`, cache_control 구조) | Anthropic Messages API 형식 | `test_cache_output_format` | PASSED |

보강 테스트: `test_cache_control_exact_threshold` (1000자 경계), `test_no_cache_control_just_below_threshold`, 빈 prompt, multiline prompt, unicode prompt.

### 1.5 통합 래퍼 (AC-I)

| AC | 재현 절차 | 기대 결과 | 자동화 테스트 | 결과 |
|----|-----------|-----------|----------------|------|
| AC-I1 | mock client 설정 → `invoke_llm("분석해줘", [], tracker, budget_usd=10.0)` | HAIKU 선택, usage(1000 in + 500 out) → $0.0035 누적, 원본 tracker 불변 | `test_invoke_short_prompt_haiku_selection` | PASSED |
| AC-I2 | `budget_usd=0.002`로 호출 | `BudgetExceededError` raise | `test_invoke_budget_exceeded` | PASSED |
| AC-I3 | `system_prompt="x"*1200`로 호출 후 `client.messages.create` 호출 인자 캡처 | `system=[..., cache_control={"type":"ephemeral"}]` 포함 | `test_invoke_cache_control_in_request` | PASSED |
| AC-I4 | 짧은 prompt + `force=Model.SONNET` | 호출 인자에 `model="sonnet"`, SONNET 단가 적용 | `test_invoke_force_sonnet` | PASSED |

보강 테스트: 긴 텍스트 자동 SONNET, 많은 아이템 자동 SONNET, usage 없는 응답, 빈 system_prompt, 클라이언트 주입/조회, 누적 비용 2회 호출.

**AC-I2 주의**: 현재 구현(`invoke_llm`)은 SDK를 먼저 호출하고 응답 usage를 바탕으로 `tracker.add()`에서 `BudgetExceededError`를 발생시키는 구조다. 즉, "예산 초과가 감지되는 시점"은 그 호출의 usage가 반환된 뒤다. PRD AC-I2의 "예산 초과 시 그 **이후** 추가 SDK 호출은 발생하지 않는다"는 엄밀한 의미로는 만족된다(예외가 raise되면 이후 `invoke_llm`은 호출되지 않음). 호출 자체를 **사전 차단**하려면 호출 전에 최대치 추정 비용으로 pre-check를 넣는 개선이 가능하다 → 본 PRD 범위 밖(후속 과제 제안).

### 1.6 문서·경로 (AC-D)

| AC | 재현 절차 | 기대 결과 | 결과 |
|----|-----------|-----------|------|
| AC-D1 | `ls ai/llm/` 및 `ai/__init__.py` 확인 | 모든 구현 모듈이 `ai/` 하위 (router.py, cost_tracker.py, retry.py, cache.py, pricing.py, invoke.py) | PASSED (수동 확인) |
| AC-D2 | `docs/rules/ai.md` 확인 | "비용 가드레일" 섹션 존재, PRD `docs/prd/cost-aware-llm-pipeline.md` 링크 | PASSED (수동 확인, ai.md L7–L55) |
| AC-D3 | `python3 -c "from ai import BudgetExceededError; print(issubclass(BudgetExceededError, Exception))"` | `True`, import 성공 | PASSED (수동 확인, 출력 `True`) |

---

## 2. 자동화 실행 로그

커맨드:

```bash
python3 -m pytest ai/tests/ -v
```

결과 요약:

```
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
collecting ... collected 65 items

ai/tests/test_cache.py::TestCache::test_cache_control_long_prompt PASSED [  1%]
ai/tests/test_cache.py::TestCache::test_no_cache_control_short_prompt PASSED [  3%]
... (중략: 65개 모두 PASSED) ...
ai/tests/test_router.py::TestRouter::test_router_force_with_opus PASSED  [100%]

============================== 65 passed in 0.28s ==============================
```

테스트 내역 분포:
- test_cache.py: 8 tests PASSED
- test_cost_tracker.py: 11 tests PASSED
- test_invoke.py: 10 tests PASSED
- test_pricing.py: 13 tests PASSED
- test_retry.py: 12 tests PASSED (9 TestRetry + 3 TestNarrowRetryDecorator)
- test_router.py: 11 tests PASSED

QA 추가 스모크 (실제 anthropic 예외로 `@narrow_retry` 검증):

```
AC-T1 real: result=success, calls=4
AC-T2 real: calls=5
AC-T4 real: calls=1
AC-T5 real: calls=1
```

모두 기대 동작과 일치.

---

## 3. edge case (트레이딩 도메인 맥락)

본 모듈(`ai/llm/`)은 **LLM 호출 경로 한정** 가드이다. 거래소·뉴스 피드 레이어의 장애는 상위 파이프라인 책임이지만, 그 장애가 LLM 호출에 전이될 때 본 모듈이 어떻게 동작하는지 검토한다.

| 시나리오 | 전이 경로 | 본 모듈 기대 동작 | 검증 방법/상태 |
|----------|-----------|-------------------|-----------------|
| **거래소(KIS/CEX) 서버 다운** | LLM 호출에는 직접 영향 없음. 단, 상위 노드가 비어있는 items로 `invoke_llm` 호출 가능 | `items=[]`, 짧은 prompt → 라우팅은 `HAIKU`로 결정적 선택. 무의미한 호출 자체를 막는 것은 상위 파이프라인 책임 | `test_invoke_short_prompt_haiku_selection`이 `items=[]` 케이스 커버. **권장**: 상위 파이프라인에서 거래소 다운 감지 시 LLM 노드 스킵 로직(후속 PRD) |
| **네트워크 지연 (긴 레이턴시)** | Anthropic SDK가 `APIConnectionError`·타임아웃을 던짐 | `@narrow_retry`의 재시도 3종 allow-list에 걸려 지수 백오프 후 재시도. 총 대기 ≤ 60초 상한 | AC-T1·T7 커버. 지터 ±20%로 thundering herd 완화 확인 (`_exponential_backoff_wait`로 스모크: 0.88/2.04/4.59/8.67/17.24s 샘플) |
| **API 레이트리밋** | `anthropic.RateLimitError` | 5회 재시도 후 전파. 총 누적 대기 60초 상한 | AC-T2·T7. 스모크에서 실 SDK 예외로도 확인 |
| **뉴스 피드 버스트 → LLM 호출 폭주** | 수많은 `invoke_llm` 호출이 짧은 시간에 누적 | `CostTracker`가 매 호출마다 예산 누적을 strict 비교하여 초과 시 `BudgetExceededError` 즉시 raise. 호출자는 파이프라인 중단 | AC-C2·I2. 불변 설계로 race 위험 감소 |
| **뉴스 피드 장애 (빈 데이터)** | 짧은 prompt/빈 items가 LLM에 투입 | 모델 라우팅은 결정적으로 HAIKU → 비용 최소화. usage 없는 응답도 처리 가능 | AC-R4, `test_invoke_no_usage_info`에서 usage=None 안전 처리 확인 |
| **인증 키 만료/무효 (401)** | `anthropic.AuthenticationError` | 재시도 없이 1회 후 raise → 불필요한 재시도 폭주 방지 | AC-T4. 실 SDK 예외 스모크 |
| **잘못된 프롬프트/검증 오류 (400)** | `anthropic.BadRequestError` | 재시도 없이 1회 후 raise | AC-T5. 실 SDK 예외 스모크 |
| **프롬프트 caching write 비용** | 1,000자 이상 system prompt는 `cache_control: ephemeral` 부착 | 캐시 write/read 단가 분리 회계는 PRD 범위 외(가정·제약 §6), 현재는 입력 토큰 전체 단가로 근사 계산 | 의도된 설계. 후속 PRD에서 분리 권장 |
| **예산 경계값 (정확히 같음)** | 누적 == budget | 성공 (strict `>` 정의) | AC-C3 |
| **지터 -20%로 실질 대기가 너무 짧음** | 초기 1초 * 0.8 = 0.8초 | 하한 보장, 음수 방지(`max(0.0, ...)`) | `retry.py` L80 `wait_time = max(0.0, wait_time)` 로 보호 |
| **재시도 누적이 60초 넘을 수 있는 시나리오** | attempt 4에서 base_wait = 1*2^4 = 16s, 누적 1+2+4+8+16 = 31s 근사 (지터 포함) | 60초 하드 상한 추가 검사 (`total_wait + wait_time > 60`) → 초과 시 즉시 raise | `retry.py` L83-85 + AC-T7 커버 |
| **환경변수 기반 예산 설정** | `AI_DAILY_BUDGET_USD` 등 | PRD는 "구현자 재량"으로 열어둠. 현재 테스트에서는 직접 주입 | 테스트는 직접 주입 방식만 검증. 환경변수 통합은 후속 통합 PR에서 검토 권장 |
| **LangGraph 노드 상태 전파** | `(state, tracker) -> (state, tracker)` 권장 | `invoke_llm`이 `(response, new_tracker)` 튜플 반환으로 패턴 호환 | 통합 래퍼 시그니처로 확인 |

**도메인 관점 결론**: 레이트리밋·인증오류·예산폭주는 본 모듈에서 **PRD 의도대로 안전하게 차단**된다. 거래소·뉴스 피드 자체 장애는 상위 파이프라인에서 별도 가드가 필요하나 본 PRD 범위 밖이다.

---

## 4. 실패 항목

없음.

---

## 5. 보류·후속 제안 (QA 관점, 비블록)

본 PRD 통과 조건과 무관한 개선 아이디어. 해당 항목은 qa-passed 판정을 막지 않는다.

1. `invoke_llm`에서 **SDK 호출 전 pre-check**로 예산 초과 감지하면 실제 API 호출을 1회 더 절감 가능 (max_tokens 최대치 가정). AC-I2의 엄밀한 "사전 차단"을 원한다면.
2. `@narrow_retry` 핵심 경로를 **실제 anthropic 예외 mock**으로 직접 검증하는 테스트를 `test_retry.py`에 추가(현재는 QA 스모크로만 확인). 회귀 방지에 도움.
3. 캐시 write/read 단가 **분리 회계** (PRD 가정·제약에서 후속 과제로 명시).
4. `CostTracker`의 환경변수 (`AI_DAILY_BUDGET_USD`) **기본값 주입 헬퍼** 추가.
5. Python 3.9에서의 `slots=True` 우회 코드를 프로젝트 최소 버전을 3.11+로 고정하고 단순화.

---

## 6. 판정

- PRD AC 25개 전부 자동화 테스트 또는 QA 스모크로 검증 완료.
- `python3 -m pytest ai/tests/ -v`: **65 passed, 0 failed**.
- 실패·미커버 항목 없음.
- edge case 검토 결과 본 모듈 책임 내에서 안전 동작 확인.

**권장 라벨: qa-passed**

---

## 2차 QA (커밋 913c775)

> 작성자: QA 에이전트
> 작성일: 2026-04-25
> 대상 커밋: `913c775` "ai: 리뷰 지적 반영 (messages 스펙·재시도 exact-match·테스트 복제본 제거 등)"
> 이전 판정: 1차 `qa-passed` → 리뷰어 `review-changes-requested` (지적 15건) → backend-dev 15/15 반영
> 실행 환경: `.venv/bin/python` = Python 3.11.15 / pytest 9.0.3 / darwin 25.3.0
> 참고: PRD §6 "Python 3.11+" 제약에 맞는 런타임에서 2차 회귀를 돌렸다(1차는 시스템 Python 3.9.6이었음).

### 2-0. 실행 요약

- 자동화 테스트: **69 / 69 PASSED** (`.venv/bin/python -m pytest ai/tests/ -v`, 0.25s)
- 1차 25개 AC **회귀 전부 유지** (특히 시그니처 축소된 `CostTracker.add()` AC-C1~C5, DI 적용된 `invoke_llm` AC-I1~I4).
- 이번 커밋에 추가된 신규 테스트 4개 전부 PASS.
- 소스 레벨 snap 확인(M5·M1·M3) 3/3 통과.
- 신규 팩토리 `CostTracker.from_usage()` 는 AC-C 규약(불변성·strict `>` 예산·BudgetExceededError) 을 내부적으로 `add()` 에 위임하여 **동일 보장**을 유지.
- **판정: qa-passed 권장** (실패 0건, 누락 0건)

### 2-1. 1차 AC 회귀 결과 (델타 중심)

| AC 군 | 1차 커버 | 2차 상태 | 회귀 포인트 |
|-------|----------|----------|-------------|
| AC-R1~R6 (라우팅) | PASS | PASS | `test_router.py` 11 tests 변경 없음. |
| AC-C1 (불변성) | PASS | PASS | `add(*, input_tokens, output_tokens, usd)` 엄격 시그니처로 축소. `test_cost_tracker_immutability`, `test_cost_tracker_add_requires_usd_keyword` 로 방어. 원본 `usd_spent==0.0` 유지, 새 인스턴스에만 `0.4` 반영 확인. |
| AC-C2 (초과 예외) | PASS | PASS | `test_cost_tracker_budget_exceeded`. `new_spent > budget_usd` strict 비교. |
| AC-C3 (경계 == 허용) | PASS | PASS | `test_cost_tracker_budget_exact_match`, `test_cost_tracker_budget_validation_boundary`. |
| AC-C4 (FrozenInstanceError) | PASS | PASS | `test_cost_tracker_frozen`. |
| AC-C5 (__slots__) | PASS | PASS | 2차는 Python 3.11 환경이라 `__slots__` 가 정식으로 적용됨. `test_cost_tracker_has_slots` 로 slots 존재 확인 + `test_cost_tracker_slots` 로 차단 예외(AttributeError/TypeError) 확인. PRD "Python 3.11+" 제약과 일치. |
| AC-T1~T7 (좁은 재시도) | PASS | PASS | 12 tests 모두 실 Anthropic SDK 예외(`APIConnectionError`, `RateLimitError`, `InternalServerError`, `AuthenticationError`, `BadRequestError`)를 직접 사용하도록 재작성됨. 1차에서 QA 스모크로만 커버하던 영역이 자동화로 승격. AC-T6 지수 백오프 하한(0.8/1.6/3.2/6.4s) 및 AC-T7 60초 상한 모두 보존. |
| AC-P1~P3 (캐싱) | PASS | PASS | `test_cache.py` 변경 없음. 8 tests PASS. |
| AC-I1 (HAIKU 라우팅·비용) | PASS | PASS | `test_invoke_short_prompt_haiku_selection`. DI 적용(`client=mock_client`) 후에도 HAIKU 선택·$0.0035 누적·원본 불변 보장. 신규 assert 추가: `messages == [{"role":"user","content":prompt}]`. |
| AC-I2 (예산 초과 전파) | PASS | PASS | `test_invoke_budget_exceeded`. SDK 호출 1회 후 응답 usage 기반 `tracker.add()` 에서 raise (1차 동일 해석). |
| AC-I3 (cache_control 부착) | PASS | PASS | `test_invoke_cache_control_in_request`. |
| AC-I4 (force 우선) | PASS | PASS | `test_invoke_force_sonnet`. `call_kwargs["model"]=="sonnet"` 검증. |
| AC-D1~D3 | PASS | PASS | `ai/` 하위 유지. `from ai import BudgetExceededError` 재검증 OK(`issubclass(..., Exception)==True`). |

### 2-2. 신규 4개 테스트 요약

1. **`test_invoke_messages_payload_spec`** (AC-I / M5)
   - `invoke_llm(prompt="테스트 프롬프트", ...)` 호출 후 `client.messages.create` 의 `messages` 인자가 정확히 `[{"role": "user", "content": "테스트 프롬프트"}]` 형식인지 검증.
   - 리뷰 지적 M5(messages 페이로드가 Anthropic API 스펙과 다를 가능성) 회귀 방지.

2. **`test_invoke_default_max_tokens`** + **`test_invoke_max_tokens_kwargs_override`**
   - 기본값은 `max_tokens=2048`, 사용자가 `kwargs`로 `max_tokens=4096`을 넣으면 덮어쓰여짐 (`setdefault` 기반).
   - 리뷰 지적: 기존 구현이 하드코딩으로 kwargs와 충돌해 `TypeError` 가능 → `kwargs.setdefault("max_tokens", 2048)` 로 해소.

3. **`test_invoke_no_usage_info`** (Mi2 경고 로깅)
   - `response.usage = None` 인 mock 응답에서 `ai.llm.invoke` 로거에 "usage/cost not tracked" 경고가 기록되고 tracker 는 변경되지 않음.
   - 리뷰 지적: usage=None 케이스에서 silent fallback 되는 위험 → 경고 로깅으로 가시화.

4. **`test_retry_exact_match_no_subclass_retry`** (M1 exact-match)
   - `AuthenticationError` (SDK 상 `APIStatusError` 하위)를 `@narrow_retry` 래핑한 함수에서 raise → **호출 횟수 정확히 1회** 로 즉시 전파.
   - 리뷰 지적: `isinstance` 체크가 서브클래스까지 재시도 대상에 포함시킬 위험 → `type(e) not in RETRYABLE_EXCEPTIONS` exact-match 로 변경. PRD "정확히 3종" 제약의 방어선.

### 2-3. 소스 레벨 snap 확인 (grep)

| 지적 | 커맨드 | 기대 | 결과 |
|------|--------|------|------|
| M5 messages 스펙 | `grep -n "role.*user.*content" ai/llm/invoke.py` | 매치 1건 이상 | **PASS** — L79 주석, L80 `messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]` |
| M1 재시도 exact-match | `grep -n "type(e) not in RETRYABLE_EXCEPTIONS" ai/llm/retry.py` | 매치 1건 이상 | **PASS** — L78 `if type(e) not in RETRYABLE_EXCEPTIONS:` |
| M3 테스트 복제본 제거 | `grep -n "narrow_retry_test" ai/tests/test_retry.py` | 매치 **없음** | **PASS** — grep EXIT=1 (no match). 1차에서 `narrow_retry_test` 커스텀 헬퍼로 커버하던 12개 테스트가 모두 실 SDK 예외 기반으로 재작성됨. |

### 2-4. 신규 팩토리 `CostTracker.from_usage()` 검증

PRD 엄격 시그니처(`add(*, input_tokens, output_tokens, usd)` 에서 `usd` 필수)를 유지하기 위해, 모델 단가 기반 자동 계산 흐름은 **별도 클래스메서드 팩토리**로 분리됨. 기존 AC-C와 충돌하지 않음:

- 내부적으로 `calculate_cost(model, ...)` 로 USD 값을 산출한 뒤 **`tracker.add(..., usd=cost)` 로 위임**. 불변성·strict 예산 비교·BudgetExceededError 전파가 전부 `add()` 를 통과.
- 수동 재현:
  ```
  t = CostTracker(budget_usd=1.0)
  n = CostTracker.from_usage(t, Model.HAIKU, input_tokens=1000, output_tokens=500)
  # t.usd_spent=0.0 (불변), n.usd_spent=0.0035, t is not n
  CostTracker.from_usage(CostTracker(budget_usd=0.001), Model.SONNET, 1000, 500)
  # → BudgetExceededError: Budget exceeded: $0.0105 > $0.0010
  ```
- 자동화 커버: `test_cost_tracker_from_usage_haiku`, `test_cost_tracker_from_usage_sonnet` PASS.
- AC 회귀 영향: **없음**. AC-C1~C5 모두 이전과 동일 통과.

### 2-5. 자동화 실행 로그 (2차)

커맨드:

```
.venv/bin/python -m pytest ai/tests/ -v
```

요약:

```
platform darwin -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0
collected 69 items

ai/tests/test_cache.py ................. 8 PASSED
ai/tests/test_cost_tracker.py .......... 11 PASSED (1차 대비 +2: from_usage_haiku/sonnet, add_requires_usd_keyword 추가)
ai/tests/test_invoke.py ................ 12 PASSED (1차 대비 +2: max_tokens_kwargs_override, default_max_tokens, messages_payload_spec 등)
ai/tests/test_pricing.py ............... 13 PASSED
ai/tests/test_retry.py ................. 14 PASSED (TestRetry 11 + TestNarrowRetryDecorator 3; 전부 실 SDK 예외 기반 재작성)
ai/tests/test_router.py ................ 11 PASSED

============================== 69 passed in 0.25s ==============================
```

1차 65개 → 2차 69개 (+4건, 실패 0건).

### 2-6. edge case 델타 (이번 라운드 변경점 한정)

1차 §3(edge case) 는 재작성하지 않고, 2차 코드 변경으로 생긴 **새 리스크만** 델타로 추가.

| 신규 리스크 시나리오 | 원인(이번 커밋의 변경) | 본 모듈 실제 동작 | 검증·권장 |
|----------------------|-------------------------|-------------------|-----------|
| **`invoke_llm(..., client=None)` + `ANTHROPIC_API_KEY` 미설정** | DI 도입(`client` 파라미터 신설), client=None 분기에서 `Anthropic()` 생성자 호출. | SDK 측 `TypeError("Could not resolve authentication method...")` 가 동기적으로 raise. `@narrow_retry`는 `type(e) not in RETRYABLE_EXCEPTIONS` 이므로 **재시도 없이 1회 전파**. 불필요한 API 호출/재시도 폭주 없음. | 스모크로 확인 완료(출력: `expected: no API key → TypeError ...`). **권장**: `ai/` 상위 레이어에 API 키 미설정 조기 검증(guard) 추가(본 PRD 범위 밖). |
| **SDK 예외 계층 변경 시 재시도 누수/차단** | M1으로 `isinstance → type()` exact-match 로 변경됨. | SDK에서 기존 `APIConnectionError/RateLimitError/InternalServerError`의 **서브클래스**가 새로 생기면 자동으로 allow-list 에 포함되지 않아 **즉시 전파**. 반대로 일시 장애를 놓칠 위험이 생김. | `retry.py` L25~27 주석에 "SDK 업그레이드 시 RETRYABLE_EXCEPTIONS 검증 필수" 명시됨. `requirements.txt` 의 anthropic 버전 고정 여부 확인 권장(본 QA 범위 밖). CI에서 SDK upgrade 체크 추가 시 회귀 방지. |
| **`response.usage is None` 시 silent 진행** | Mi2로 경고 로깅 추가. | `new_tracker = tracker` (원본 유지) + `logger.warning(...)`. 이전 QA에서 "`test_invoke_no_usage_info` 로 안전 처리 확인" 이라 했던 부분이 **경고까지 공식화**. | `test_invoke_no_usage_info` 에서 `caplog`로 warning 캡처 검증. 운영상 알림 연동은 후속 과제. |
| **`kwargs`에 `max_tokens` 중복 지정** | M5 관련: `setdefault("max_tokens", 2048)` 로 해소. | 사용자가 `max_tokens=4096` 전달 시 그대로 덮어씀. TypeError 없음. | `test_invoke_max_tokens_kwargs_override` + `test_invoke_default_max_tokens` 두 방향 모두 PASS. |
| **`from_usage` 가 예산 초과를 건너뛰는 오해** | 신규 팩토리 도입. | 내부에서 `add()` 를 호출하므로 strict `>` 예산 검증이 동일하게 동작(스모크로 `BudgetExceededError` 재현). | `test_cost_tracker_from_usage_*` PASS; 별도 AC 충돌 없음. |

1차 edge case(거래소 다운·네트워크 지연·레이트리밋·피드 버스트·401/400·캐시 과금·경계값·지터·LangGraph 호환)는 **회귀 없음**.

### 2-7. 실패 항목 (2차)

없음.

### 2-8. 2차 판정

- 1차 25개 AC 회귀: **전부 유지 (PASS)**.
- 신규 4개 테스트: **전부 PASS** (messages 스펙 / max_tokens setdefault / usage=None warning / exact-match 서브클래스).
- pytest: **69 passed, 0 failed** (Python 3.11.15).
- 소스 snap(M5·M1·M3): **3/3 통과**.
- `CostTracker.from_usage` 팩토리: AC-C 규약과 충돌 없음(내부 `add()` 위임).
- 델타 edge case 5건 모두 의도된 안전 동작 확인.

**권장 라벨: qa-passed** (gh CLI 미설치로 라벨 자동 갱신 불가 — 수동 적용 필요)

