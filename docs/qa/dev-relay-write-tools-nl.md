# QA: Dev Manager — write 도구 NL 자율 트리거 (Phase 3)

- **slug**: `dev-relay-write-tools-nl`
- **PRD**: [`docs/prd/dev-relay-write-tools-nl.md`](../prd/dev-relay-write-tools-nl.md) (PR #58 머지)
- **구현 PR**: [#59](https://github.com/musinsa-ds/trading-signal-engine/pull/59) — branch `feature/dev-relay-write-tools-nl-impl`
- **QA**: 이하영 (hayoung.lee2@musinsa.com)
- **QA 일시**: 2026-05-18 KST
- **선행 PR (이미 머지)**: #54 (Phase 2 — write structured 경로 / AC-WT-7 DEFERRED), #48 (NL serialize), #43 (reviewer/merger), #25 (MVP)
- **판정**: **PASS** (AC-WTN-1 ~ AC-WTN-15 전수 통과)

---

## 1. 요약

본 QA 는 PRD `dev-relay-write-tools-nl.md` (Phase 3 — NL 자율 트리거) 의 수용 기준 15건 (AC-WTN-1 ~ AC-WTN-15) 을 자동화 단위·통합 테스트 + 정적 컴플라이언스 + 코드 정합 확인으로 검증했다. 모든 항목 통과. 핵심 격차였던 Phase 2 (PR #54) 의 **AC-WT-7 (NL 자율 트리거 DEFERRED) 가 본 PR 로 완전 해소** 됐음도 `TestACWT7Resolution::test_nl_write_intent_emits_confirm_not_immediate_apply` 로 회귀 가능한 형태로 검증됐다.

회귀 영향:
- `ai/tests/dev_relay/` 전체 703 PASS / 0 FAIL.
- 컴플라이언스 정적 스캔 60 PASS — 본 PRD 본문 / 신규 모듈 / 신규 템플릿 2종 모두 `FORBIDDEN_KEYWORDS` 0 hit.

---

## 2. 실행 명령 / 환경

```
$ git rev-parse HEAD
d44a670 feat(dev-relay): Phase 3 NL 자율 트리거 — write 의도 분류 + structured 변환

$ cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py -v
40 passed in 0.07s

$ cd ai && python -m pytest tests/dev_relay/ -q
703 passed in 3.47s

$ cd ai && python -m pytest tests/dev_relay/test_compliance.py -v
60 passed in 0.03s
```

- Python 3.11.15, pytest 9.0.3 (`.venv` 환경).
- 작업 디렉터리: `/Applications/하영/code_source/trading-signal-engine`.
- PR 체크아웃: `gh pr checkout 59` 완료. `feature/dev-relay-write-tools-nl-impl` 브랜치 HEAD = origin 과 동일.

---

## 3. 수용 기준 매핑표 — 15/15

| AC | 항목 | 자동 테스트 (회피 가능) | 결과 |
|---|---|---|---|
| AC-WTN-1 | `WRITE_REQUEST` 라벨 분류 + `nl_write_classified` audit | `TestWriteRequestLabel`, `TestNLWriteHappyPath::test_write_request_routes_to_conversion` | PASS |
| AC-WTN-2 | NL → structured 변환 정상 흐름 (apply_patch / commit / push) | `TestParseConversionResponse::test_valid_apply_patch/commit/push`, `TestNLWriteHappyPath::test_commit_intent_converts_to_commit_command` | PASS |
| AC-WTN-3 | Phase 2 흐름 재진입 (큐 적재 + handoff audit + `_handle_write_command` 진입) | `TestNLWriteHappyPath::test_write_request_routes_to_conversion`, `TestConvertedCommandRoundTrip` | PASS |
| AC-WTN-4 | 모호한 의도 거절 (parse_error / missing_field / unknown_tool / low_confidence) | `TestNLWriteAmbiguous` (4 parametrize), `TestParseConversionResponse::test_missing_*/test_unknown_tool/test_low_confidence/test_invalid_pr_*` | PASS |
| AC-WTN-5 | confirm `[취소]` — 변환 결과 폐기 (Phase 2 회귀 그대로) | Phase 2 `test_write_command_flow.py` 회귀 — 회귀 0 (전체 703 PASS) | PASS (회귀로 확인) |
| AC-WTN-6 | destructive 가드 다층 (NL 입력 / 분류 / 변환 / dispatcher / Phase 2) | `TestNLWriteDestructiveGuard::test_destructive_nl_input_blocked_pre_classify`, `test_classify_to_unknown_destructive_does_not_convert` | PASS |
| AC-WTN-7 | 동시성 — `_nl_turn_lock` 직렬화 + JobQueue running_count 가드 회귀 | `TestNLTurnLockRegression::test_busy_second_concurrent_nl_rejected`, `test_handle_command_nl_serialize.py` (회귀 0) | PASS |
| AC-WTN-8 | shutdown 보호 — confirm 대기 무효화 (Phase 2 정책 그대로) | Phase 2 `test_shutdown_dev_relay.py` 회귀 0 + `_write_shutdown_flag` guard 본 PR 명시 (`_handle_nl_write_conversion`) | PASS (회귀로 확인) |
| AC-WTN-9 | 멱등성 — 동일 client_msg_id 두 번 → queue row 1건 | `TestNLWriteIdempotency::test_duplicate_client_msg_id_one_queue_row` | PASS |
| AC-WTN-10 | rate limit — NL 자율 트리거에도 5초/3건 적용 | `TestNLWriteRateLimit::test_fourth_message_within_window_rate_limited` | PASS |
| AC-WTN-11 | audit log 완전성 — `nl_write_classified` → `nl_write_converted` → `nl_write_handoff` → `patch_requested` 체인 | `TestNLWriteHappyPath::test_write_request_routes_to_conversion` (kinds 검증 + `user_id_masked` canonical 키 포함) | PASS |
| AC-WTN-12 | 컴플라이언스 정적 검사 — PRD 본문 / 신규 모듈 / 신규 라벨·audit kind | `test_compliance.py::test_prd_write_tools_nl_body_outside_code_is_clean`, `test_dev_relay_source_clean[write_classifier.py]` | PASS |
| AC-WTN-13 | 외부 노출 텍스트 — 변환 결과 prefix + 모호 거절 안내 + 자동 커밋 메시지 | `test_compliance.py::test_static_template_clean[TEMPLATE_NL_CONVERSION_PREFIX]`, `[TEMPLATE_NL_WRITE_AMBIGUOUS]` | PASS |
| AC-WTN-14 | 회귀 — PR #25/#43/#48/#54 + NL 직렬화 + write_tools 전수 통과 | `tests/dev_relay/ -q` 703 PASS (기존 659 → 703, +44 신규, 0 fail) | PASS |
| AC-WTN-15 | AC-WT-7 (PR #54 DEFERRED) 완전 해소 — NL write 의도 → confirm 발사, 사용자 미클릭 시 적용 0 | `TestACWT7Resolution::test_nl_write_intent_emits_confirm_not_immediate_apply` | PASS |

---

## 4. 재현 절차 / 기대 결과 — AC 별 상세

### AC-WTN-1. NL 분류기 — `WRITE_REQUEST` 라벨

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestWriteRequestLabel -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteHappyPath::test_write_request_routes_to_conversion -v
```

**기대**:
- `IntentLabel.WRITE_REQUEST.value == "WRITE_REQUEST"` (식별자 안정).
- `routes_to_write_conversion(IntentLabel.WRITE_REQUEST) is True` — 다른 라벨은 False.
- `CLASSIFY_SYSTEM_PROMPT` 본문에 `WRITE_REQUEST` 분기 정의 + `UNKNOWN_OR_DESTRUCTIVE` fallback 명시.
- "PR 32 에 patch 적용해줘" NL 입력 → classifier 1회 호출 → audit `nl_write_classified` 라인 1줄 (label=WRITE_REQUEST, user_id_masked 포함).

**실제 결과**: 전수 PASS. 분기 회귀 0 (기존 라벨 4종 정상 동작).

---

### AC-WTN-2. NL → structured 변환 정상 흐름

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestParseConversionResponse -v
```

**기대**:
- valid `apply_patch` JSON → `structured_command == "apply patch pr=32"`.
- valid `commit` JSON → `structured_command == "commit pr=7"`.
- valid `push` JSON → `structured_command == "push pr=100"`.
- 코드 펜스로 감싼 JSON 도 정상 추출 (`_JSON_FENCE_RE`).
- threshold 경계값 (정확히 0.7) 은 통과.
- `nl_write_converted` audit 라인에 `tool` / `pr` / `confidence` 기록.

**실제 결과**: 16 케이스 + 통합 happy-path 전수 PASS.

---

### AC-WTN-3. Phase 2 흐름 재진입

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteHappyPath::test_write_request_routes_to_conversion -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestConvertedCommandRoundTrip -v
```

**기대**:
- 변환된 structured_command 가 `dispatcher.parse(...)` 에서 정확히 `APPLY_PATCH_PR` / `COMMIT_PR` / `PUSH_PR` 로 매치.
- `_build_and_send_write_confirm` 진입 시 kwargs 에 `kind`, `pr_number`, `nl_original`, `structured_command` 전달 — Phase 2 worker 가 NL 컨텍스트 인지.
- audit chain — `nl_write_classified` → `nl_write_converted` → `nl_write_handoff` → `patch_requested` 순으로 같은 thread_ts 에 기록.

**실제 결과**: PASS. round-trip 3종 (`apply_patch`/`commit`/`push`) 모두 dispatcher 와 정확 매치.

---

### AC-WTN-4. 모호한 의도 — 변환 거절

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteAmbiguous -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestParseConversionResponse::test_missing_tool -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestParseConversionResponse::test_unknown_tool -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestParseConversionResponse::test_low_confidence -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestParseConversionResponse::test_invalid_pr_negative -v
```

**기대 (각 케이스별)**:
- `not a json` raw → `ConversionFailReason.PARSE_ERROR` + `TEMPLATE_NL_WRITE_AMBIGUOUS` 발사 ("명확하게" 토큰 포함).
- `{"tool": "apply_patch"}` (필드 누락) → `MISSING_FIELD`.
- `{"tool": "create_pr", ...}` (화이트리스트 밖) → `UNKNOWN_TOOL`.
- `confidence: 0.3` → `LOW_CONFIDENCE`.
- `pr: -1 / 0 / "32"` → `INVALID_PR`.
- 모든 거절은 `nl_write_conversion_failed` audit + `reason` 필드 기록 + `_build_and_send_write_confirm` 호출 0건.

**실제 결과**: 4 parametrize × 거절 안내 + 16 단위 케이스 전수 PASS.

---

### AC-WTN-5. confirm `[취소]` 폐기

**재현**: Phase 2 회귀 — `cd ai && python -m pytest tests/dev_relay/test_write_command_flow.py -q`.

**기대**: 취소 시 `patch_confirmed(cancelled)` + 워킹트리·커밋·remote 0 변경. NL 진입 confirm 도 동일 액션 핸들러 (`cancel_write`) 가 처리하므로 Phase 2 정책 그대로 회귀 검증.

**실제 결과**: 전체 703 PASS 안에 Phase 2 cancel 케이스 포함 — 0 fail.

---

### AC-WTN-6. destructive 가드 다층

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteDestructiveGuard -v
```

**기대**:
- (a) NL 텍스트 "PR 32 force push 해줘" → dispatcher `is_destructive` 1차 차단. classifier 호출 0회 + converter 호출 0회.
- (b) classifier 가 `UNKNOWN_OR_DESTRUCTIVE` 반환 → 분류 1회, 변환 0회. confirm 발사 0건. (Haiku 짧은 응답 분기로 fallback.)
- 코드 정합 (`_handle_nl_write_conversion` 본문 검토) — 다층 6단계 (NL 입력 / 분류 / 변환 SDK system_prompt / `parse_conversion_response` / dispatcher 재매치 / Phase 2 tool_policy) 모두 명시.

**실제 결과**: 자동 케이스 + 코드 정합 모두 PASS.

---

### AC-WTN-7. 동시성 — `_nl_turn_lock` 직렬화

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLTurnLockRegression -v
cd ai && python -m pytest tests/dev_relay/test_handle_command_nl_serialize.py -q
```

**기대**:
- lock 점유 상태에서 두 번째 NL 진입 → busy 안내 1줄. classifier 호출 0회.
- 첫 진입의 변환·confirm 발사·worker queue 적재까지 lock 보유 (`_handle_natural_language` 의 `try/finally` 보장).
- NL 분기와 structured 분기는 별도 락 — 같은 PR 에 두 진입이 동시에 진행될 수 있으나 `JobQueue.running_count` 가 적용 게이트 (Phase 2 AC-WT-8) 그대로.

**실제 결과**: PASS. PR #48/#54 직렬화 회귀 0건.

---

### AC-WTN-8. shutdown 보호

**재현**: Phase 2 `test_shutdown_dev_relay.py` 회귀 + 코드 정합:
- `_handle_nl_write_conversion` 첫 부분이 `_write_shutdown_flag.is_set()` 확인 (main.py L624~633).
- `_nl_shutdown_flag` 도 `_handle_natural_language` 진입 시점에 가드.

**기대**: shutdown flag set 이후 변환 호출 자체를 시도하지 않음. confirm 대기 중인 `_write_pending` 은 in-memory — 재시작 시 자연 휘발 + Phase 2 의 "이전 세션 confirm 대기 작업은 무효화" 안내 트리거.

**실제 결과**: PASS. Phase 2 shutdown 회귀 0건.

---

### AC-WTN-9. 멱등성

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteIdempotency -v
```

**기대**: 같은 `client_msg_id` 로 두 번 호출 → 두 번째는 `queue.enqueue(..., created=False)` → handoff audit 발사 0건, queue row 1건 유지.

**실제 결과**: PASS. 두 번 호출 후 `count_by_status` 합계가 정확히 1.

---

### AC-WTN-10. rate limit

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteRateLimit -v
```

**기대**: 5초 안에 4건 NL write 요청 → 4번째 메시지에 `잠시` 토큰 포함 안내. SDK 호출 폭증 방지.

**실제 결과**: PASS. `_RateLimiter` 가 NL 분기 자체에도 그대로 적용 — 분류 호출도 한도 안.

---

### AC-WTN-11. audit log 완전성

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLWriteHappyPath::test_write_request_routes_to_conversion -v
```

**기대**: happy-path 1 사이클 = audit `kinds` 안에 다음이 모두 포함:
- `nl_write_classified`
- `nl_write_converted`
- `nl_write_handoff`
- `patch_requested` (Phase 2 chain 자연 연결)

**실제 결과**: PASS. 4 kind 모두 `user_id_masked` 키 보유 (PR #50/#52 canonical 키 정합).

---

### AC-WTN-12. 컴플라이언스 정적 검사

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_compliance.py -v
```

**기대 / 실제**:
- `test_prd_write_tools_nl_body_outside_code_is_clean` — PRD 본문 (코드 펜스 밖) `FORBIDDEN_KEYWORDS` 0 hit. PASS.
- `test_dev_relay_source_clean[write_classifier.py]` — 신규 모듈 0 hit. PASS.
- 기존 산출물 (PRD `dev-relay-write-tools.md` 외 포함) 모두 0 hit.

---

### AC-WTN-13. 외부 노출 텍스트 (변환 결과 prefix + 모호 거절 안내)

**재현**:
```
cd ai && python -m pytest "tests/dev_relay/test_compliance.py::test_static_template_clean[TEMPLATE_NL_CONVERSION_PREFIX-*]" -v
cd ai && python -m pytest "tests/dev_relay/test_compliance.py::test_static_template_clean[TEMPLATE_NL_WRITE_AMBIGUOUS-*]" -v
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestNLConversionPrefix -v
```

**기대 / 실제**:
- 신규 템플릿 2종 (`TEMPLATE_NL_CONVERSION_PREFIX`, `TEMPLATE_NL_WRITE_AMBIGUOUS`) 컴플라이언스 0 hit. PASS.
- 3 builder (`build_patch_confirm_blocks`, `build_commit_confirm_blocks`, `build_push_confirm_blocks`) 모두 `nl_original` + `structured_command` 전달 시 confirm body 에 prefix (원본/변환) 표시. structured 진입 (kwargs 없음) 에서는 prefix 없음 → Phase 2 회귀 0.
- 자동 커밋 메시지는 Phase 2 정책 그대로 `guard_text_with_urls` 통과 (PR #54 AC-WT-15).

---

### AC-WTN-14. 회귀 — 전체 dev_relay 테스트

**재현**:
```
cd ai && python -m pytest tests/dev_relay/ -q
```

**기대 / 실제**: **703 passed in 3.47s / 0 FAIL**. 본 PR 진입 전 659 → +44 신규 (write_tools_nl 40 + nl_agent +1 + compliance +1 + write_runtime/nl_classifier 회귀 보강).

회귀 대상 (PR #25/#43/#48/#54 + NL 분기) 모두 0 fail. NL serialize / shutdown / 멱등성 / Phase 2 worker / dispatcher / tool_policy / write_tools 회귀 0건.

---

### AC-WTN-15. AC-WT-7 (PR #54 DEFERRED) 완전 해소

**재현**:
```
cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py::TestACWT7Resolution -v
```

**기대**:
- NL 입력 "PR 32 에 patch 적용해줘" → 변환 → confirm 발사 (`_build_and_send_write_confirm` 호출됨).
- 사용자가 미클릭 → `_execute_apply_patch` 호출 0건 (적용 0).
- PR 본문에 "AC-WT-7 DEFERRED 해소" 명시 (PR #59 description Line 1 + AC-WTN-15).

**실제 결과**: PASS. 본 impl 로 AC-WT-7 가 회귀 가능한 형태로 해소됨.

---

## 5. 에지 케이스 점검

PRD §7 (위험·의존) + AGENTS.md QA 가이드의 에지 케이스 별 회귀:

| # | 케이스 | 검증 위치 | 결과 |
|---|---|---|---|
| E-1 | SDK 호출 실패 (RuntimeError) | `TestConvert::test_sdk_exception_falls_back_to_parse_error` | PASS — `PARSE_ERROR` fallback |
| E-2 | LLM 가 코드 펜스로 감싼 JSON 출력 | `TestParseConversionResponse::test_code_fence_wrapped` | PASS — `_JSON_FENCE_RE` 가 추출 |
| E-3 | bool 이 int 의 서브타입 — `pr: true` | `parse_conversion_response` `isinstance(pr, bool)` 명시 차단 (write_classifier.py L174) | PASS (방어 코드) |
| E-4 | tool 화이트리스트 통과했는데 템플릿 매핑 누락 (도구 추가 시) | write_classifier.py L186-188 방어 코드 | PASS (방어 코드) |
| E-5 | 빈 입력 (whitespace only) → LLM 호출 0회 | `TestConvert::test_empty_input_short_circuits` | PASS |
| E-6 | confidence threshold 정확히 0.7 경계값 | `TestParseConversionResponse::test_threshold_boundary_exact` | PASS — 통과 |
| E-7 | dispatcher mismatch (변환된 명령이 정규식 매치 실패) | main.py L692-717 → `dispatcher_mismatch` reason audit | PASS (코드 정합) |
| E-8 | write_converter 미주입 (`nl_runtime["write_converter"] is None`) | main.py L636-653 → `converter_unavailable` reason | PASS (코드 정합) |
| E-9 | queue 미주입 (`queue is None`) | main.py L868-876 → `nl_write_no_queue` context 안내 | PASS (코드 정합) |
| E-10 | NL 자율 변환 confirm 발사 후 같은 PR 에 structured 명령 race | Phase 2 `JobQueue.running_count >= 1` 게이트 회귀 0 | PASS |
| E-11 | 같은 NL turn 동안 추가 메시지 도달 | `TestNLTurnLockRegression` busy 안내 | PASS |
| E-12 | 변환 결과 메시지에 사용자 NL 원본이 그대로 노출되면서 도메인 키워드 누설 | `slack_renderer` 의 발사 직전 `guard_text_with_urls` 통과 (test_compliance.py builder 케이스) | PASS |

거래 도메인 외부 의존 (거래소 서버 다운 / 뉴스 피드 장애 등) 은 본 PR 범위 밖 (Dev Manager 봇 자체 동작). PRD §1.4 / §6.4 — "로컬 데몬 한정, 인프라 변경 없음" 으로 명시.

---

## 6. 실패 항목

없음. AC 15건 전수 통과.

---

## 7. 권고 (다음 사이클 모니터링)

PRD §6.4 / §7 명시 — 본 PR 머지 후 1~2주 모니터링:

1. NL 자율 트리거 사용 빈도 (audit `nl_write_classified` 카운트).
2. 변환 confidence 분포 (`nl_write_converted` 의 confidence 필드 통계) — default 0.7 threshold 조정 근거.
3. `nl_write_conversion_failed` 발생률 + reason 분포 — false-positive 분류 빈도 추적.
4. 사용자 confirm 거절률 (변환 정확도 proxy) — `patch_confirmed(cancelled)` 비중.
5. SDK 비용 — NL 자율 트리거 1건 = 3 SDK 호출 (Haiku 분류 + Sonnet 변환 + Sonnet patch 생성). 1인 사용자 일일 한도 부담 여부.

권고는 별도 PRD (`cost-aware-llm-pipeline`) 영역. 본 QA 의 PASS 판정에 영향 없음.

---

## 8. 판정

**QA = PASS**. PR #59 라벨을 `impl-ready` → `qa-passed` 로 갱신 권고.

- AC 통과: **15/15**.
- 신규 자동 테스트: **40 PASS** (`test_write_tools_nl.py`).
- 회귀: 전체 dev_relay **703 PASS / 0 FAIL**.
- 컴플라이언스: **60 PASS** (PRD 본문 + 신규 모듈 + 신규 템플릿 2종).
- 코드 정합: 다층 destructive 가드 6단계 + `_nl_turn_lock` 보유 중 변환 + 4 종 audit kind + Phase 2 chain 자연 연결 모두 확인.
- Phase 2 (PR #54) 의 AC-WT-7 DEFERRED 는 본 PR 로 회귀 가능한 형태로 완전 해소.

---

## 9. 재검증 — reviewer P1 fix 3건 (2026-05-18 KST, append)

### 9.1 배경

초회 QA (위 §1~§8, 2026-05-18 오전) 에서 PASS 판정 후, reviewer 가 본 PR 에 대해 P1 결함 3건을 식별. 개발자가 fix 3 commit + 회귀 테스트 1 commit 으로 후속 대응. 본 절은 fix 의 회귀 가능 여부와 기존 AC 회귀 영향을 재검증한 결과.

- Fix commits (HEAD = `fab172c`):
  - `aa8f272` — P1-3: write converter SDK timeout 래핑 (`asyncio.wait_for`, default 30s)
  - `b97f3d9` — P1-1: NL write 경로 `running_count >= 1` busy 게이트
  - `eae1728` — P1-2: duplicate enqueue 시 `nl_write_dup_ignored` audit
  - `fab172c` — P1-1/P1-2/P1-3 회귀 테스트 3 클래스 추가 (+284 LOC, 7 케이스)

### 9.2 P1 fix 매핑

| P | 결함 | Fix 위치 | 회귀 테스트 |
|---|---|---|---|
| P1-1 | structured + NL 혼합 시 confirm 다이얼로그 2건 동시 노출 가능 (AC-WTN-7 진술 정합성 깨짐) | `main.py:655-684` — `_handle_nl_write_conversion` 진입 직후 `JobQueue.count_by_status("running") >= 1` 검사. busy 시 audit `kind=nl_write_conversion_failed, reason=busy` + TEMPLATE_NL_BUSY_NOTICE | `TestNLWriteBusyGate::test_running_count_blocks_nl_write_conversion` + `test_running_count_zero_passes_through` |
| P1-2 | duplicate idempotency key 차단 시 `nl_write_converted` 만 남고 `nl_write_handoff` 없는 dangling audit chain | `main.py:770-787` — `queue.enqueue(...)` 반환의 `created=False` 분기에서 `nl_write_dup_ignored` audit 1줄 (job_id/tool/pr 포함) 추가 | `TestNLWriteDupIgnoredAuditChain::test_duplicate_emits_dup_ignored_audit` |
| P1-3 | converter SDK hang 시 `_nl_turn_lock` 보유 상태가 무한 지속 → NL 분기 영구 차단 | `write_runtime.py:27-33, 292-356` — `WRITE_CONVERTER_TIMEOUT_SECONDS=30.0` 상수 + `WriteConverterTimeout` 예외 + `asyncio.wait_for(_drain(), timeout=...)` 래핑. `write_classifier.py:213-226` — `convert()` 가 본 예외를 잡아 `ConversionFailReason.TIMEOUT` 매핑. timeout 시 finally 블록에서 `_nl_turn_lock.release()` 자연 수행 | `TestNLWriteConverterTimeout` 4 케이스 — reason 매핑 / 기타 예외와 분리 / audit 발사 + 락 release / SDK 래퍼 직접 검증 |

### 9.3 재검증 실행

```
$ git rev-parse HEAD
fab172c test(dev-relay): PR #59 P1-1/P1-2/P1-3 회귀 테스트 추가

$ cd ai && python -m pytest tests/dev_relay/test_write_tools_nl.py -v
47 passed in 0.15s     # 40 (기존) + 7 (P1 fix)

$ cd ai && python -m pytest tests/dev_relay/ -q
710 passed in 3.38s    # 기존 703 + 신규 회귀 7 — 0 FAIL

$ cd ai && python -m pytest tests/dev_relay/test_compliance.py -v
60 passed in 0.03s     # FORBIDDEN_KEYWORDS 0 hit (PRD 본문 / 신규 모듈 / 라벨·audit kind)
```

- 작업 디렉터리: `/Applications/하영/code_source/trading-signal-engine`
- Python 3.11.15, pytest 9.0.3 (`.venv`)
- PR 체크아웃: `gh pr checkout 59` — `feature/dev-relay-write-tools-nl-impl` HEAD = `fab172c` (origin 동기).

### 9.4 기존 AC 회귀 영향 검토

| AC | 영향 | 결과 |
|---|---|---|
| AC-WTN-7 (동시성 — `_nl_turn_lock` 직렬화) | **진술 정합성 회복**. 이전 QA 본문 §3 표/§4 AC-WTN-7 는 "NL 분기와 structured 분기는 별도 락 — 같은 PR 에 두 진입이 동시에 진행될 수 있으나 `JobQueue.running_count` 가 적용 게이트 (Phase 2 AC-WT-8)" 로 적은 바 있다. 그러나 PR #59 초회 impl 은 NL 변환 경로에서 `running_count` 게이트를 적용하지 않아 — confirm 발사 직전까지 갈 수 있었고, structured 쪽에서 동시 running 일 때 confirm 2 건이 노출될 가능성이 있었다 (reviewer P1-1 지적). 본 fix 가 NL 변환 진입 직전에 `running_count >= 1` 차단을 적용함으로써 진술이 코드와 일치. `TestNLWriteBusyGate` 가 회귀 안전망. | PASS |
| AC-WTN-9 (멱등성 — 동일 client_msg_id) | duplicate 시 queue row 1건 유지 정책 변경 없음. audit 만 `nl_write_dup_ignored` 1줄 **추가** — chain 가시성 향상. 기존 `test_duplicate_client_msg_id_one_queue_row` 0 fail. | PASS |
| AC-WTN-10 (audit chain 4종) | 5번째 audit kind `nl_write_dup_ignored` 가 duplicate 분기에서만 발사. happy-path (`nl_write_classified` → `nl_write_converted` → `nl_write_handoff` → `patch_requested`) 는 변경 없음. dup 시 chain 은 `nl_write_classified` → `nl_write_converted` → `nl_write_dup_ignored` 로 닫힘 (handoff 없음 — duplicate 이므로 의도된 동작). | PASS — 표현이 "4 종" 에서 "정상 4 종 + dup 분기 1 종" 으로 확장됐을 뿐 회귀 0 |
| AC-WTN-12 (destructive 다층) | NL 변환 진입 가드 6 단계는 그대로. busy 게이트는 destructive 가드 앞 또는 뒤 어느 쪽이든 모두 차단 효과 — code path 검토 결과 destructive 가드 이전 단계에서 동작 (busy 우선 차단 → SDK 토큰 낭비 회피). reviewer 의도와 정합. | PASS |
| 기타 AC-WTN-1~6/8/11/13~15 | 본 fix 가 건드린 코드 경로는 (1) `_handle_nl_write_conversion` 진입 직후 busy 가드, (2) `queue.enqueue` 직후 duplicate 분기 audit, (3) SDK 호출 래퍼 — 각 AC 시나리오와 직교. 자동 테스트 모두 통과. | PASS |

### 9.5 누적 회귀

- PR #25 (MVP) / #43 (reviewer·merger) / #48 (NL serialize) / #50~#52 (audit canonical) / #54 (Phase 2 write 도구) / #55~#56 (정책·후속) — 누적 회귀 테스트 전수 통과 (`tests/dev_relay/ -q` 710 PASS).
- 컴플라이언스 60 PASS 안에 본 fix 가 추가한 `WRITE_CONVERTER_TIMEOUT_SECONDS` / `WriteConverterTimeout` / `nl_write_dup_ignored` / `nl_write_busy` 식별자 0 hit — 봇 표시명 / 외부 노출 텍스트 도메인 키워드 누설 없음.

### 9.6 신규 회귀 테스트 7건 상세

| 클래스 | 케이스 | 검증 포인트 |
|---|---|---|
| `TestNLWriteBusyGate` | `test_running_count_blocks_nl_write_conversion` | running=1 일 때 SDK 호출 0 + audit `reason=busy` + busy 안내 발사 |
| `TestNLWriteBusyGate` | `test_running_count_zero_passes_through` | running=0 일 때 정상 통과 (회귀 안전망) |
| `TestNLWriteDupIgnoredAuditChain` | `test_duplicate_emits_dup_ignored_audit` | duplicate 시 `nl_write_dup_ignored` audit (job_id/tool/pr 포함) + handoff audit 0건 |
| `TestNLWriteConverterTimeout` | `test_timeout_maps_to_timeout_reason` | `WriteConverterTimeout` raise → `ConversionFailReason.TIMEOUT` 매핑 |
| `TestNLWriteConverterTimeout` | `test_other_exception_still_parse_error` | timeout 외 예외는 기존대로 `PARSE_ERROR` fallback (회귀) |
| `TestNLWriteConverterTimeout` | `test_timeout_emits_audit_and_releases_lock` | end-to-end timeout 시 audit `reason=timeout` 발사 + `_nl_turn_lock` release |
| `TestNLWriteConverterTimeout` | `test_make_write_converter_wraps_timeout` | `make_write_converter` 래퍼가 `asyncio.wait_for` 호출 + 초과 시 `WriteConverterTimeout` raise |

### 9.7 재검증 판정

**QA = PASS (재검증)**. fix 3/3 통과. 신규 회귀 테스트 7/7 통과. 누적 dev_relay 회귀 710/710 통과. 컴플라이언스 60/60 통과 — 0 hit. 라벨 갱신: `impl-ready` → `qa-passed`.

기존 §8 판정은 유지되되, AC-WTN-7 진술 정합성이 본 fix 로 회복됐다는 점이 핵심 보완. reviewer P1 지적 사항 (chain dangling / busy 동시 노출 / SDK hang) 이 모두 회귀 가능한 형태로 해소.
