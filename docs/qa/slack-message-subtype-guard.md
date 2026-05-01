# QA 리포트: slack-message-subtype-guard

> 작성자: QA 에이전트
> 작성일: 2026-05-01
> 대상 PRD: `docs/prd/slack-message-subtype-guard.md`
> 대상 PR: https://github.com/deeptrading-lab/trading-signal-engine/pull/12
> 대상 브랜치: `feature/slack-message-subtype-guard`
> 대상 커밋: `18e77ae`
> 관련 Issue: #5 (P0)
> 실행 환경: Python 3.11.15 / pytest 9.0.3 / Darwin 25.4.0

---

## 0. 실행 요약

- **자동화 테스트**: `ai/tests/` 전체 **130개 PASSED** (`pytest`, 0.19s). 신규 추가 `TestIsHandleableMessageSubtype` **8개 PASSED**.
- **자동 검증 가능 AC** (AC-1, AC-4, AC-5, AC-6, AC-7, AC-8): 모두 **PASS**.
- **사용자 수동 검증 필요 AC** (AC-2 메시지 편집, AC-3 메시지 삭제, AC-6 실 로그 포맷, AC-1 실 e2e): Slack Workspace·실 Socket Mode 연결 의존이라 본 환경에서 실행 불가 → **MANUAL** 분류, 체크리스트 §3 제공.
- **추가 점검** (호출 순서·whitelist 정책·순수 함수성·외부 노출 텍스트): 모두 **PASS**.
- **종합 판정**: 자동 검증 범위 내 실패 0건. 라벨 `qa-auto-passed` 권장 (수동 검증은 사용자 영역).

---

## 1. 수용 기준별 테스트 매핑·결과

| AC | 분류 | 검증 수단 | 결과 |
|----|------|-----------|------|
| **AC-1. 일반 텍스트 메시지 기존 동작 유지** | AUTO + MANUAL | T-1/T-2/T-3 단위 테스트 + `route_command`/`render_ping` 회귀 + 실 DM 수동 | **PASS (auto)** / MANUAL (e2e) |
| AC-2. `message_changed` 무시 | MANUAL | T-4 단위 테스트는 PASS, 실 Slack 편집 동작은 사용자 검증 | **PASS (auto)** / MANUAL (e2e) |
| AC-3. `message_deleted` 무시 | MANUAL | T-5 단위 테스트는 PASS, 실 Slack 삭제 동작은 사용자 검증 | **PASS (auto)** / MANUAL (e2e) |
| **AC-4. `bot_message` subtype 무시** | **AUTO** | T-6 단위 테스트 | **PASS** |
| **AC-5. 알려지지 않은 신규 subtype 보수적 무시** | **AUTO** | T-7 단위 테스트 | **PASS** |
| **AC-6. 무시 시 로그 포맷** | AUTO + MANUAL | `main.py` 로그 호출 코드 리뷰 (포맷 문자열·마스킹·키 3종 포함) | **PASS (코드 리뷰)** / MANUAL (실 stdout) |
| **AC-7. 기존 회귀 0건** | **AUTO** | `pytest ai/tests/` 전체 130개 | **PASS** |
| **AC-8. 외부 노출 텍스트 키워드 0건** | **AUTO** | diff 대상 파일 grep + 정책 키워드 9종 | **PASS** |

---

## 2. 자동 검증 결과

### 2.1 단위 테스트 실행

신규 가드 테스트 단독:

```
$ python -m pytest ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype -v
collected 8 items

ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_event_without_subtype_key_is_handleable PASSED  [ 12%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_event_with_subtype_none_is_handleable PASSED   [ 25%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_event_with_subtype_empty_string_is_handleable PASSED [ 37%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_message_changed_is_not_handleable PASSED        [ 50%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_message_deleted_is_not_handleable PASSED        [ 62%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_bot_message_is_not_handleable PASSED            [ 75%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_unknown_future_subtype_is_not_handleable PASSED [ 87%]
ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype::test_non_mapping_input_is_not_handleable PASSED      [100%]

============================== 8 passed in 0.18s ===============================
```

PRD §3.4 표 기준 매핑:

| PRD 케이스 | 테스트 메서드 | 입력 subtype | 기대 | 결과 |
|---|---|---|---|---|
| T-1 | `test_event_without_subtype_key_is_handleable` | (없음) | `True` | PASS |
| T-2 | `test_event_with_subtype_none_is_handleable` | `None` | `True` | PASS |
| T-3 | `test_event_with_subtype_empty_string_is_handleable` | `""` | `True` | PASS |
| T-4 | `test_message_changed_is_not_handleable` | `message_changed` | `False` | PASS |
| T-5 | `test_message_deleted_is_not_handleable` | `message_deleted` | `False` | PASS |
| T-6 | `test_bot_message_is_not_handleable` | `bot_message` | `False` | PASS |
| T-7 | `test_unknown_future_subtype_is_not_handleable` | `foo_unknown_future` | `False` | PASS |
| (보강) | `test_non_mapping_input_is_not_handleable` | `None` / `str` | `False` | PASS |

PRD가 요구한 최소 5개를 초과해 8개 작성됨 (T-1 ~ T-7 + 비-Mapping 방어). 양호.

전체 회귀:

```
$ python -m pytest ai/tests/ -q
........................................................................ [ 55%]
..........................................................                [100%]
============================= 130 passed in 0.19s ==============================
```

→ 기존 122개 + 신규 8개 = **130개 모두 통과**. AC-7 충족.

---

### 2.2 AC-1 (정상 텍스트 회귀)

T-1·T-2·T-3 단위 테스트로 일반 메시지 이벤트가 가드를 통과해 `True` 반환을 확인. 동시에 `route_command` 회귀(`test_coordinator_handlers.py::TestRouteCommand` 7개) 모두 PASS — `ping → pong`, `status → render_status` 동작 유지.

가드 호출부 (`ai/coordinator/main.py:78-86`)는 라우팅 분기 앞에 `if not is_handleable_...`로 추가됐을 뿐, `True` 경로에서는 기존 `is_allowed_sender` → `route_command(text)` 흐름을 그대로 통과시킴 → 회귀 가능성 없음.

**판정**: PASS (auto 부분).

---

### 2.3 AC-4 / AC-5 (whitelist 정책)

`is_handleable_message_subtype`(`ai/coordinator/auth.py:39-59`):

```python
if not isinstance(event, Mapping):
    return False
subtype = event.get("subtype")
if subtype is None or subtype == "":
    return True
return False
```

- `bot_message` (T-6): `False` 반환 → AC-4 충족.
- `foo_unknown_future` (T-7): `False` 반환 → AC-5 충족.
- 알려진 비핸들러블 4종(`message_changed`, `message_deleted`, `thread_broadcast`, `file_share`)도 모두 `False` 반환 (T-4·T-5 + 정책상 자동 포괄).

**판정**: PASS.

---

### 2.4 AC-6 (로그 포맷 — 코드 리뷰)

`ai/coordinator/main.py:78-86`:

```python
if not is_handleable_message_subtype(event):
    logger.info(
        "처리 대상이 아닌 메시지 이벤트를 무시했습니다 "
        "(subtype=%s, sender=%s, type=%s)",
        event.get("subtype"),
        mask_user_id(event.get("user")),
        event.get("type"),
    )
    return
```

PRD §3.2 / AC-6 요구사항 매핑:

| 요구 | 구현 위치 | 충족 여부 |
|---|---|---|
| INFO 레벨 한 줄 | `logger.info(...)` 단일 호출 | PASS |
| `subtype=<값>` 포함 | format `subtype=%s` | PASS |
| 마스킹된 sender id 포함 | `mask_user_id(event.get("user"))` 사용 (`auth.py:80-86`에서 `U0AE***` 형태) | PASS |
| 이벤트 type 포함 | `type=%s` | PASS |
| 평문 user id 미노출 | `mask_user_id` 경유 (앞 4자만 + `***`) | PASS |
| 평문 메시지 본문 미노출 | `event.get("text")`/`event.get("message")` 미참조 | PASS |
| 토큰 미노출 | 토큰은 `config` 객체에만 존재, 본 로그 라인은 미참조 | PASS |
| 메시지 톤 (PRD §3.2) | "처리 대상이 아닌 메시지 이벤트를 무시했습니다" 정확 일치 | PASS |
| 각 subtype에 대해 한 줄 (rate-limit 별도 X) | 단일 `logger.info` + 즉시 `return`, 큐잉/배치 없음 | PASS |

**판정**: PASS (코드 리뷰 한정). 실 stdout 확인은 §3 수동 체크리스트.

---

### 2.5 AC-7 (회귀 0건)

§2.1 마지막 블록 — `ai/tests/` 전체 **130 passed**. 기존 122 + 신규 8.

**판정**: PASS.

---

### 2.6 AC-8 (외부 노출 텍스트 키워드)

본 PR diff에서 변경된 파일에 한해 금지 키워드 9종 grep:

```
$ git diff main...pr-12 -- ai/coordinator/auth.py ai/coordinator/main.py \
      ai/tests/test_coordinator_auth.py docs/references/slack-coordinator-bot-setup.md \
    | grep -niE 'signal|trade|trading|desk|quant|finance|market|ticker|pnl'
39:@@ -19,7 +19,12 @@ import signal
```

매치 1건은 `import signal` (Python 표준 시그널 모듈 import 라인의 컨텍스트). PRD §AC-8 명시: "코드 내부 식별자(`ai.coordinator`, 모듈 변수명 등)는 검사 대상이 아니다." → 정당한 식별자.

추가 검사 — 변경된 4개 파일 전체 본문 grep:

```
ai/coordinator/main.py:18: import signal
ai/coordinator/main.py:111-157: signal.signal/_install_signal_handlers (Python 표준 모듈 호출)
docs/references/slack-coordinator-bot-setup.md:24: 금지 키워드 정책을 나열하는 정책 문장 (본 PR이 추가한 라인 아님)
```

모두 코드 내부 식별자 또는 정책 문서 자체의 키워드 나열 — 외부 노출 텍스트가 아님. 사용자 응답 메시지나 새 로그 문구에 금지 키워드는 **0건**.

**판정**: PASS.

---

## 2.7 추가 점검 (PRD §3.3 / §6.2 코드 리뷰)

### A. 호출 순서 (PRD §3.3)

`ai/coordinator/main.py` `handle_message_im` (라인 67-101):

| 순서 | 가드 | 라인 | PRD 명세와 일치? |
|---|---|---|---|
| 1 | `is_self_message(event, self_user_id)` | 70 | YES |
| 2 | `event.get("channel_type") != "im"` | 74 | YES |
| 3 | `is_handleable_message_subtype(event)` (+ INFO 로그) | 78-86 | YES |
| 4 | `is_allowed_sender(sender, ...)` | 91 | YES |
| 5 | `route_command(text)` → `say(reply)` | 100-101 | YES |

→ PRD §3.3 명세 순서와 정확히 일치. 특히 subtype 가드가 화이트리스트 검사보다 **앞**에 위치함을 확인 (PRD §6.2의 "화이트리스트 통과 여부와 무관하게 비-handleable 이벤트 즉시 차단" 의도 충족).

**판정**: PASS.

### B. whitelist 정책 검증 (PRD §3.1)

`auth.py:39-59` 로직:

```
1) Mapping 아니면 False (방어)
2) event.get("subtype") 조회
3) subtype 가 None 또는 "" 이면 True
4) 그 외 모두 False
```

- `subtype` 키 부재 → `dict.get("subtype")` 은 `None` → `True` (T-1 검증)
- `subtype = None` → `True` (T-2 검증)
- `subtype = ""` → `True` (T-3 검증)
- 그 외 임의 문자열 → `False` (T-4·T-5·T-6·T-7 검증)

블랙리스트가 아닌 **whitelist** 방식임을 확인. 향후 Slack이 새 subtype을 도입해도 자동으로 차단됨.

**판정**: PASS.

### C. 순수 함수성 (PRD §3.3)

`is_handleable_message_subtype` 본문 분석:
- I/O 호출 없음 (logger·network·file system 미참조).
- 전역 상태 변경 없음.
- 입력 `event` mutate 없음 (`event.get()` 만 사용 — read-only).
- 결정적 (`subtype` 값에만 의존).

→ 순수 함수. 로깅은 PRD 명세대로 호출부(`main.py`)에서만 수행.

**판정**: PASS.

### D. 문서 갱신 (PRD §3.5)

`docs/references/slack-coordinator-bot-setup.md` 라인 226 (diff `-` `+`):

```
- 메시지 subtype 가드 (`message_changed`/`message_deleted`/`thread_broadcast` 무시)
+ 메시지 subtype 가드 — 구현됨 (PRD: [`slack-message-subtype-guard`](../prd/slack-message-subtype-guard.md))
```

→ §7 Out-of-Scope 항목이 PRD §3.5 명세대로 "구현됨" 표기로 갱신됨.

**판정**: PASS.

---

## 3. 사용자 수동 검증 체크리스트

자동화로는 실 Slack Socket Mode 연결을 재현할 수 없으므로 아래 항목은 사용자(이하영) 본인이 직접 수행해야 합니다.

### 사전 준비

- [ ] `.env` 로드 (`source .env`).
- [ ] 데몬 기동: `python -m ai.coordinator.main` (별도 터미널 — stdout 로그 관찰용).
- [ ] 시작 로그에 `Socket Mode 연결을 시도합니다.` 한 줄이 보이는지 확인.

### M-1. AC-1 회귀 — `ping` 정상 동작

- [ ] 코디네이터 봇 DM에 `ping` 입력.
- [ ] **기대**: 5초 이내 `pong` 응답 도착.
- [ ] **기대**: 데몬 stdout 에 "처리 대상이 아닌 메시지 이벤트를 무시했습니다" 로그가 **나오지 않음**.

### M-2. AC-2 — 메시지 편집 무시

- [ ] DM 에 임의 텍스트(예: `안녕`) 전송.
- [ ] (봇이 fallback 응답을 한 번 보낼 수 있음 — 이는 본 PRD 비범위, 정상)
- [ ] 즉시 방금 전송한 메시지를 **편집** (Slack 메시지에 마우스 올리고 ⋯ → "메시지 편집").
- [ ] 본문을 다른 텍스트로 바꿔 저장.
- [ ] **기대**: 편집된 본문에 대해 봇 응답 **없음** (fallback 메시지 발사 X).
- [ ] **기대**: 데몬 stdout 에 다음 형식 로그 한 줄:
      `... INFO ai.coordinator: 처리 대상이 아닌 메시지 이벤트를 무시했습니다 (subtype=message_changed, sender=U0AE***, type=message)`
- [ ] **금지**: 로그에 평문 user id (`U0AE7A54NHL` 전체), 토큰 값, 평문 메시지 본문이 보이지 않아야 함.

### M-3. AC-3 — 메시지 삭제 무시

- [ ] DM 에 임의 텍스트(예: `삭제테스트`) 전송.
- [ ] 방금 전송한 메시지를 **삭제** (⋯ → "메시지 삭제" → 확인).
- [ ] **기대**: 봇 응답 **없음**.
- [ ] **기대**: 데몬 stdout 에 한 줄:
      `... INFO ai.coordinator: 처리 대상이 아닌 메시지 이벤트를 무시했습니다 (subtype=message_deleted, sender=U0AE***, type=message)`
- [ ] **금지**: 평문 user id / 토큰 / 본문 미노출.

### M-4. AC-6 — 로그 포맷 종합 확인

위 M-2·M-3 의 로그 라인을 캡처해 다음 모두 포함되는지 한 번에 확인:

- [ ] `subtype=<값>` (값이 정확히 들어감).
- [ ] `sender=U0AE***` (마스킹된 형태).
- [ ] `type=message`.
- [ ] 로그 레벨이 `INFO`.
- [ ] 한 이벤트당 정확히 한 줄만 출력 (중복 없음).

### M-5. (선택) thread_broadcast / file_share 등

워크스페이스 정책상 재현이 어렵지만 가능하다면:

- [ ] DM 에 파일 첨부(이미지·문서 등) → 봇 응답 없음, 로그에 `subtype=file_share` 한 줄.
- [ ] DM 스레드에 답글 후 "채널에도 게시" 옵션 → `subtype=thread_broadcast` 한 줄.

수동 검증 결과(PASS / FAIL)를 PR #12 코멘트로 남기면, 모두 PASS 시 `qa-passed` 라벨로 갱신 가능합니다.

---

## 4. 에지 케이스 별도 섹션

본 PRD는 백엔드 가드 로직 변경 단건이므로 외부 의존(거래소/뉴스 피드/네트워크) 영향은 거의 없으나 점검:

| 에지 | 영향 | 본 PR 처리 | 결과 |
|---|---|---|---|
| Slack API 페이로드에서 `subtype` 키 자체 누락 | 일반 메시지 케이스 | `dict.get("subtype")` → `None` → `True` 라우팅 | PASS (T-1) |
| `subtype` 값이 `None` (Slack SDK가 명시적으로 빈 값을 보낼 가능성) | 일반 메시지 케이스 | `is None` 체크 → `True` | PASS (T-2) |
| `subtype` 값이 빈 문자열 | 일반 메시지 케이스 (페이로드 변형) | `== ""` 체크 → `True` | PASS (T-3) |
| Slack 가 미래에 새 subtype 추가 | 보수적 무시 (whitelist) | `False` 반환 → 로그 후 무시 | PASS (T-7) |
| `event` 가 dict 아님 (slack-bolt 변종 / 예외 페이로드) | 방어적 차단 | `isinstance(..., Mapping)` 체크 → `False` | PASS (방어 테스트) |
| 네트워크 지연으로 동일 이벤트 재전송 | Slack 측 deduplication 영역, 본 PR 비범위 | 가드는 동일하게 동작 | N/A |
| Slack API 레이트리밋 | `say()` 호출이 실패해도 가드는 영향 없음 (가드는 `say` 이전) | N/A | N/A |
| 데몬 재시작 중 큐잉된 편집/삭제 이벤트 | 재기동 후 정상 가드 적용 | 무상태 함수라 영향 없음 | PASS |

---

## 5. 자동 검증 로그 모음 (재현 명령)

```
$ python -m pytest ai/tests/test_coordinator_auth.py::TestIsHandleableMessageSubtype -v
============================== 8 passed in 0.18s ===============================

$ python -m pytest ai/tests/ -q
============================= 130 passed in 0.19s ==============================

$ git diff main...pr-12 -- ai/coordinator/auth.py ai/coordinator/main.py \
    ai/tests/test_coordinator_auth.py docs/references/slack-coordinator-bot-setup.md \
    | grep -niE 'signal|trade|trading|desk|quant|finance|market|ticker|pnl'
39:@@ -19,7 +19,12 @@ import signal      # ← 코드 내부 식별자(Python 표준 모듈), AC-8 예외
```

---

## 6. 종합 판정

- **자동 검증 가능 AC**: AC-1 / AC-4 / AC-5 / AC-6(코드 리뷰) / AC-7 / AC-8 — 모두 **PASS**.
- **수동 검증 필요**: AC-1(e2e) / AC-2 / AC-3 / AC-6(실 stdout) — 사용자 체크리스트 §3.
- **추가 점검 (호출 순서·whitelist·순수 함수성·문서 갱신)**: 모두 PASS.
- **실패 항목**: 0건.

→ 라벨 권장: **`qa-auto-passed`** (수동 검증 완료 시 PR 코멘트 + `qa-passed` 로 승격).
