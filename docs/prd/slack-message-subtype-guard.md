# PRD: Slack 메시지 subtype 가드 추가

- **slug**: `slack-message-subtype-guard`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-01
- **UI 포함 여부**: **No** (백엔드 데몬 가드 로직 변경. 별도 화면 변화 없음)
- **관련 Issue**: [#5 Slack 메시지 subtype 가드 추가](https://github.com/deeptrading-lab/trading-signal-engine/issues/5)
- **출처**: PR #3 리뷰 발견 1, 가이드 [`docs/references/slack-coordinator-bot-setup.md`](../references/slack-coordinator-bot-setup.md) §7 Out-of-Scope

---

## 1. 배경 / 문제

### 1.1 현재 동작
`ai/coordinator/main.py`의 `handle_message_im` 클로저(라인 62-90)는 Slack에서 들어오는 `message.im` 이벤트를 받으면 다음만 검사하고 곧장 `route_command(text)` 를 호출한다.

1. `is_self_message(event, self_user_id)` — 봇 자기 자신이 보낸 메시지인지
2. `event.get("channel_type") == "im"` — DM 채널인지
3. `is_allowed_sender(sender, allowed_user_ids)` — 화이트리스트 발신자인지

이 세 가드를 통과하면 `text = event.get("text") or ""` 를 그대로 라우팅한다.

### 1.2 무엇이 문제인가
Slack은 일반 사용자 메시지뿐 아니라 다양한 **subtype** 이벤트를 같은 `message.im` 채널로 흘려보낸다. 대표적으로:

| subtype | 발생 상황 | 현재 코드의 반응 |
|---|---|---|
| `message_changed` | 사용자가 자기 DM 메시지를 **편집** | `text` = 편집된 새 본문 → fallback("사용 가능한 명령") 응답 발사 |
| `message_deleted` | 사용자가 자기 DM 메시지를 **삭제** | `text` = 빈 문자열 → fallback 응답 발사 |
| `thread_broadcast` | 스레드 답글을 채널에도 동시 게시 | 본문이 그대로 라우팅 (의도 없는 응답) |
| `file_share` | 파일 첨부 | `text`가 파일 캡션이라 보통 fallback 발사 |
| `bot_message` | 외부 통합·다른 봇이 DM에 게시 | `is_self_message`가 일부 잡지만, `bot_id`가 없는 변종에 노출 가능 |
| `channel_join` / `channel_leave` 등 | 시스템 메시지 | text가 시스템 안내라 fallback 발사 |

### 1.3 왜 P0인가
사용자가 DM에서 자기 메시지를 **편집·삭제하는 것은 일상적인 동작**이다. 현재 구현에서는 이 동작이 매번 `사용 가능한 명령: ping, status` fallback 응답을 유발해, **봇과의 1:1 DM 채널이 노이즈로 가득 찬다**. 이는 사용자 경험을 직접 망가뜨리며, 동료 가시성 있는 회사 Slack 워크스페이스(무신사/29CM)에서 봇 DM이 비정상적으로 보이는 부수효과도 있다.

### 1.4 외부 노출 텍스트 제약 (재확인)
- 봇 응답·로그·문서·커밋·PR 본문에서 트레이딩 도메인 키워드 금지: `signal`, `trade`, `trading`, `desk`, `quant`, `finance`, `market`, `ticker`, `pnl`.
- 본 PRD에서 봇은 "코디네이터" 로 통칭한다.
- 자세한 원칙은 `docs/prd/slack-coordinator-inbound.md` §3.3 / AC-8 참고.

---

## 2. 목표

`message.im` 이벤트 중 **사용자가 직접 입력한 일반 텍스트 메시지**에 대해서만 명령 라우팅이 일어나고, 그 외 subtype은 조용히 무시(no-op + INFO 로그)되도록 가드를 추가한다.

성공 정의:

- 사용자가 DM에서 메시지를 편집·삭제해도 봇이 응답하지 않는다.
- 정상 입력(`ping`, `status`, 임의 텍스트)은 기존과 동일하게 동작 (회귀 0건).
- 알려지지 않은 새 subtype도 보수적으로 무시된다 (whitelist 방식).

---

## 3. 범위 (In scope)

### 3.1 subtype 화이트리스트 도입

명령 라우팅 **응답 대상**(handleable):
- `subtype` 키가 이벤트에 **없는** 경우 (= 일반 사용자 메시지)
- `subtype`이 `None`인 경우
- `subtype`이 빈 문자열(`""`)인 경우

**무시 대상**(non-handleable, 응답하지 않음):
- 위에 해당하지 않는 모든 subtype.
- 대표 케이스(테스트로 명시 커버):
  `message_changed`, `message_deleted`, `thread_broadcast`, `file_share`, `bot_message`, `channel_join`, `channel_leave`
- 알려지지 않은 임의 subtype(예: `subtype=foo`)도 보수적으로 무시.

### 3.2 무시 사유 로깅

INFO 레벨로 한 줄 로깅. 토큰·평문 식별자 미노출.

- 포함: subtype 값, 마스킹된 sender id (`mask_user_id` 재사용), 이벤트 type
- 메시지 톤: "처리 대상이 아닌 메시지 이벤트를 무시했습니다"
- 노이즈가 너무 많아질 수 있으므로 **각 subtype에 대해 한 줄**만 남긴다 (rate limit 별도 X).

### 3.3 코드 위치

`ai/coordinator/auth.py` 에 **순수 함수**를 추가한다:

```python
def is_handleable_message_subtype(event: Mapping[str, Any]) -> bool: ...
```

- 입력: slack-bolt가 전달하는 `event` dict
- 출력: bool (True면 명령 라우팅 진행, False면 무시)
- 부수효과 없음 (로깅은 main.py 호출부에서 수행)

`ai/coordinator/main.py` 의 `handle_message_im` 호출부에서 기존 가드 사이에 끼워 넣는다:

```
1. is_self_message → return
2. channel_type != "im" → return
3. is_handleable_message_subtype(event) == False → INFO 로그 + return  ← 신규
4. is_allowed_sender → return (기존)
5. route_command(text)
```

> NOTE: subtype 가드는 화이트리스트 검사보다 **앞에** 둔다. 비-handleable 이벤트는 화이트리스트 통과 여부와 무관하게 무시되어야 하며(예: 본인이 자기 메시지를 삭제해도 응답 X), 화이트리스트 외 발신자의 system message로 인한 불필요한 분기를 줄인다. (단, `is_self_message`는 더 앞에 둔다 — 봇 자기 에코 방지가 우선.)

### 3.4 단위 테스트 추가

`ai/tests/test_coordinator_auth.py` 에 `is_handleable_message_subtype` 테스트 케이스 **최소 5개** 추가. 네트워크/slack-bolt 호출 없음 (순수 함수 테스트).

필수 커버 케이스:

| # | 입력 event | 기대 |
|---|---|---|
| T-1 | `{"type": "message", "text": "ping"}` (subtype 키 없음) | `True` |
| T-2 | `{"type": "message", "subtype": None, "text": "ping"}` | `True` |
| T-3 | `{"type": "message", "subtype": "", "text": "ping"}` | `True` |
| T-4 | `{"type": "message", "subtype": "message_changed", ...}` | `False` |
| T-5 | `{"type": "message", "subtype": "message_deleted"}` | `False` |
| T-6 | `{"type": "message", "subtype": "bot_message", ...}` | `False` |
| T-7 | `{"type": "message", "subtype": "foo_unknown_future"}` | `False` (보수적 거부) |

권장: T-1~T-7 모두 명시적으로 작성 (총 7개).

### 3.5 문서

- `docs/references/slack-coordinator-bot-setup.md` §7 Out-of-Scope 항목에서 "메시지 subtype 가드" 줄을 제거하거나 "구현됨 (PRD: slack-message-subtype-guard)" 표기로 갱신.
  - 본 PRD는 **개발자 작업의 일부로 §7 갱신을 포함**한다 (별도 docs PR 분리하지 않음).

---

## 4. 비범위 (Out of Scope)

- `handle_message_im` 클로저를 모듈 함수로 추출하거나 dispatcher 패턴으로 리팩터하는 작업 — Issue **#6**의 영역. 본 PRD는 가드 함수 추가와 호출만 한다.
- `app_mention` 이벤트의 subtype 처리 — 현재 `ignore_mentions` 핸들러가 무조건 무시하므로 영향 없음.
- 그룹 DM(`mpim`) / 채널 메시지에 대한 가드 — 기존 `channel_type == "im"` 체크로 이미 차단됨. 본 PRD에서는 그 가드를 그대로 둔다.
- subtype별 **차별 처리**(예: `message_changed` 일 때 편집 전/후 비교 응답) — MVP 범위 아님.
- 무시 카운터 메트릭/대시보드 — 현재 메트릭 인프라 미도입.
- 새로운 응답 메시지 추가 — 본 PRD는 **응답을 줄이는** 변경이지 늘리는 변경이 아니다.

---

## 5. 수용 기준 (Acceptance Criteria)

QA가 그대로 체크리스트로 사용한다. **재현 절차 + 기대 결과** 형식.

### AC-1. 일반 텍스트 메시지는 기존 동작 유지
- **재현**: 본인(`U0AE7A54NHL`)이 코디네이터 봇 DM에 `ping` 입력.
- **기대**: 5초 이내 `pong` 응답이 도착한다 (PRD `slack-coordinator-inbound` AC-2 회귀 없음). `subtype` 키가 없는 이벤트가 정상 라우팅된다.

### AC-2. 메시지 편집(`message_changed`)은 무시
- **재현**: 본인 DM에서 임의 메시지 전송 → 즉시 해당 메시지를 **편집**.
- **기대**: 봇은 편집된 본문에 대해 **응답하지 않는다**. 데몬 로그에 INFO 레벨로 한 줄, `subtype=message_changed` 와 마스킹된 sender id가 기록된다. 토큰·평문 ID 미노출.

### AC-3. 메시지 삭제(`message_deleted`)는 무시
- **재현**: 본인 DM에서 임의 메시지 전송 → 해당 메시지를 **삭제**.
- **기대**: 봇은 응답하지 않는다. INFO 로그에 `subtype=message_deleted` 가 한 줄 기록된다.

### AC-4. `bot_message` subtype은 무시
- **재현**: 단위 테스트로 `{"subtype": "bot_message", "user": "U_OTHER", ...}` 이벤트를 `is_handleable_message_subtype` 에 전달.
- **기대**: 함수가 `False` 를 반환한다. 통합 검증으로, 화이트리스트 통과 여부와 무관하게 `route_command` 가 호출되지 않는 것을 확인 (mock 또는 dispatcher 추출 후 #6에서 통합 테스트로 보강 가능 — 본 PRD에서는 단위 테스트로 충분).

### AC-5. 알려지지 않은 새 subtype도 보수적으로 무시
- **재현**: 단위 테스트로 `{"subtype": "foo_unknown_future"}` 이벤트 전달.
- **기대**: 함수가 `False` 반환. 응답 발사 없음. 보수적(whitelist) 정책이 적용됨을 확인.

### AC-6. 무시 시 로그 포맷
- **재현**: AC-2 또는 AC-3 시나리오 실행 후 데몬 stdout/로그 확인.
- **기대**: 한 줄에 다음이 모두 포함:
  - `subtype=<값>` (예: `subtype=message_changed`)
  - 마스킹된 sender id (예: `sender=U0AE***`)
  - 이벤트 type (`type=message`)
- **금지**: 토큰 값, 평문 user id 전체, 평문 메시지 본문 노출.

### AC-7. 기존 회귀 0건
- **재현**: 본 PRD 구현 후 `ai/tests/` 전체 단위 테스트 실행 (`pytest ai/tests/`).
- **기대**: 기존 단위 테스트(약 53개) 및 회귀 영역(약 122개)이 모두 통과한다. 신규 추가 테스트(7개)도 모두 통과.

### AC-8. 외부 노출 텍스트 컴플라이언스
- **재현**: 본 PRD 구현으로 추가/변경된 모든 사용자 노출 문자열(없음 — 응답 메시지는 추가되지 않음), 로그 메시지, 신규 코드 주석, 문서를 검사.
- **기대**: 다음 키워드가 단 한 곳도 등장하지 않는다(대소문자 무시):
  `signal`, `trade`, `trading`, `desk`, `quant`, `finance`, `market`, `ticker`, `pnl`.
- **참고**: 코드 내부 식별자(`ai.coordinator`, 모듈 변수명 등)는 검사 대상이 아니다.

---

## 6. 가정 · 제약

### 6.1 기술

- **slack-bolt 1.28.0** 의 이벤트 페이로드 구조에 의존. 향후 메이저 업그레이드 시 subtype 필드 의미가 바뀌면 본 가드의 재검토가 필요(가능성 낮음 — Slack API 자체의 안정 영역).
- **Python 3.11+** (`ai/` 디렉토리 컨벤션, `docs/prd/cost-aware-llm-pipeline.md` §6 정렬).
- 단위 테스트는 **순수 함수 테스트**만으로 검증 가능 — slack-bolt 실제 호출 없음, 네트워크 mock 불필요.
- 신규 의존성 추가 없음 (`ai/requirements.txt` 변경 없음).

### 6.2 안전성

- **whitelist 정책**: 알려진 정상 케이스(subtype 부재/None/빈 문자열)만 허용하고 그 외는 거부. 향후 Slack이 새 subtype을 추가하더라도 봇이 자동으로 잘못된 응답을 발사할 위험 없음.
- **화이트리스트 검사보다 subtype 가드를 앞에 둔다** — 비-handleable 이벤트가 화이트리스트 통과 여부와 무관하게 즉시 차단되어야 하므로(자기 메시지 삭제 시에도 응답 금지). 단, `is_self_message` 는 그보다 더 앞에 둔다 (에코 루프 방지가 최우선).

### 6.3 일정 / 운영

- 로컬 데몬 변경. 배포 인프라 변경 없음. CI 변경 없음.
- 사용자 1인(이하영) 단독 사용을 가정 (PRD `slack-coordinator-inbound` §6.4 동일).

### 6.4 의존 / 선후관계

- 본 PRD는 **PR #3(slack-coordinator-inbound) 머지 완료를 전제**로 한다.
- 본 PRD 구현은 Issue **#6**(dispatcher 추출)과 **독립**적으로 진행 가능하다. 둘 다 `handle_message_im` 을 건드리지만, 본 PRD는 가드 함수 추가 + 호출 1줄 삽입만 하므로 #6의 추출 작업과 충돌 영역이 작다. 머지 순서는 작은 변경(본 PRD)을 먼저 머지하면 #6의 리팩터 부담이 줄어든다.

---

## 7. 참고

- 저장소 루트 [`AGENTS.md`](../../AGENTS.md) — PRD 양식, 라벨 플로우
- [`docs/agents/pm.md`](../agents/pm.md) — PM 작성 원칙
- [`docs/prd/slack-coordinator-inbound.md`](./slack-coordinator-inbound.md) — 선행 PRD (현재 가드의 출발점)
- [`docs/references/slack-coordinator-bot-setup.md`](../references/slack-coordinator-bot-setup.md) §7 Out-of-Scope — 본 작업의 출처 항목
- 관련 코드:
  - `ai/coordinator/main.py:62-90` — 가드 호출 삽입 위치
  - `ai/coordinator/auth.py` — 신규 함수 `is_handleable_message_subtype` 추가 위치
  - `ai/tests/test_coordinator_auth.py` — 단위 테스트 추가 위치
- GitHub Issue: [#5 Slack 메시지 subtype 가드 추가](https://github.com/deeptrading-lab/trading-signal-engine/issues/5) (라벨: `enhancement`, `priority:P0`)
- 후속/연관 Issue: #6 (dispatcher 추출 — 본 PRD 비범위)
- Slack API 레퍼런스: https://api.slack.com/events/message — 메시지 subtype 카탈로그
- 사용자 메모리 노트: 회사 Slack 동료 가시성, 봇 표시명에 트레이딩 도메인 노출 금지

---

## 부록 A. 의사 코드 (참고용; 구현 강제 아님)

> 개발자 가이드라인 수준. 실제 구현 시 시그니처·로깅 포맷은 동등 의미면 변경 가능.

```python
# ai/coordinator/auth.py
def is_handleable_message_subtype(event: Mapping[str, Any]) -> bool:
    """
    명령 라우팅 대상 이벤트인지 판정.
    일반 사용자 텍스트 메시지(subtype 부재/None/빈 문자열)만 True.
    그 외 모든 subtype(message_changed, message_deleted, thread_broadcast,
    file_share, bot_message, channel_join, ... 미지의 신규 subtype 포함)은 False.
    """
    if not isinstance(event, Mapping):
        return False
    subtype = event.get("subtype")
    if subtype is None or subtype == "":
        return True
    return False
```

```python
# ai/coordinator/main.py — handle_message_im 내부
if is_self_message(event, self_user_id):
    return
if event.get("channel_type") != "im":
    return
if not is_handleable_message_subtype(event):
    logger.info(
        "처리 대상이 아닌 메시지 이벤트를 무시했습니다 "
        "(subtype=%s, sender=%s, type=%s)",
        event.get("subtype"),
        mask_user_id(event.get("user")),
        event.get("type"),
    )
    return
sender = event.get("user")
if not is_allowed_sender(sender, config.allowed_user_ids):
    ...
text = event.get("text") or ""
reply = route_command(text)
say(reply)
```
