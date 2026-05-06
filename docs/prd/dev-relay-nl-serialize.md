# PRD: Dev Manager — 자연어 분기 process-wide 직렬화

- **slug**: `dev-relay-nl-serialize`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-07
- **UI 포함 여부**: **No** (외부 노출은 NL 분기 거절 안내 1줄만 — 상위 PRD `slack-dev-relay.md` / `dev-relay-natural-language.md` 와 동일 정책. 별도 웹/네이티브 UI 없음.)
- **상위 PRD**: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md) (NL 분기 — 본 PRD 직렬화 대상)
- **인접 PRD**: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md), [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md)
- **관련 이슈/PR**: PR #43 (structured 분기 직렬화 — 본 PRD 의 사촌 작업)
- **대상 파일**: `ai/dev_relay/main.py:417-509` (`_handle_natural_language`)

---

## 1. 배경 / 문제

선행 PRD [`dev-relay-natural-language.md`](./dev-relay-natural-language.md) 에서 도입한 NL 분기 (`_handle_natural_language`, [`ai/dev_relay/main.py:417-509`](../../ai/dev_relay/main.py)) 는 Slack Bolt 이벤트 핸들러의 threaded executor 위에서 **직접 동시 실행** 된다. structured 분기(`status`, `review pr <N>`, `merge pr <N>`) 는 PR #43 으로 `JobQueue` + `AgentRunner` (`max_workers=1`) 직렬화가 완료됐지만, NL 분기는 그 경로 밖에 있어 직렬화 대상이 아니다.

코드 검토(2026-05-06) 로 확인된 race 4건:

1. **같은 thread_ts 동시 NL 메시지 — read-then-write race**. `existing = sessions.get(thread_ts, channel_id)` (`main.py:438`) 과 `sessions.start(...)` (`main.py:469`) 사이에 SDK 호출 (수 초) 이 들어간다. 같은 스레드에 두 메시지가 거의 동시에 도착하면 두 핸들러가 모두 `existing=None` 또는 같은 `existing.session_id` 를 읽고 → SDK 호출 (병렬) → `sessions.start(...)` 두 번 호출 → 한쪽 SDK `session_id` 가 덮어쓰임, `turn_count` 리셋, 컨텍스트 손실.
2. **응답 발사 순서 보장 안 됨**. 늦게 시작한 SDK 호출이 먼저 끝나면 `say(safe, thread_ts=thread_ts)` 가 거꾸로 발사 — 사용자 입장에서 두 번째 질문에 대한 답이 먼저 오고 첫 번째 답이 나중에 오는 UX 깨짐.
3. **audit.jsonl interleaving 잠재성**. `_append_audit` 는 락 없이 `f.write` 만 호출. 단일 line write 는 OS 레벨에서 보통 atomic 이지만, 동시 핸들러가 늘어날수록 잠재 회귀 표면이 커진다.
4. **SDK quota / API 호출 동시 발생**. 사용자가 빠르게 메시지를 연속 보내면 SDK 가 동시 세션 호출을 받는데, 비용·rate limit 측면에서 의도치 않은 폭증 가능.

structured 분기는 PR #43 으로 단일 worker 큐를 통과하므로 위 4건이 발생할 수 없다. NL 분기만 잔존하는 상태이며, 본 PRD 가 이를 닫는다.

### 1.1 옵션 비교 (사용자 결정 = C)

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | NL 분기를 `JobQueue` 에 통합 (별도 NL worker 분리) | 일관성 높음. 큐 관측성·shutdown 흐름 통합 | 코드 복잡도 큼. NL 응답이 여러 메시지를 차례로 발사하는 흐름이 worker 모델과 매끄럽지 않음. 1인 MVP 단계 비용 과다 |
| B | `thread_ts` 별 lock map (per-thread mutex) | 다른 스레드끼리는 병렬 가능 → UX 응답성 좋음 | 락 맵 lifecycle 비용 (만료·GC). 1인 MVP 단계 다중 스레드 동시성 이득 작음. 다중 사용자 시점에 어차피 재설계 |
| **C** | **process-wide `threading.Lock` 1개** | structured (`max_workers=1`) 와 정책 통일. 락 1개로 단순. 테스트·관측 쉬움. 1인 MVP 단계 충분 | NL 동시 처리 불가 — busy 시 즉시 거절 UX 가 필요 |

사용자(이하영) 가 옵션 **C** 를 선택. 근거: 1인 MVP 단계라 동시 NL 처리 능력보다 race 차단과 코드 단순성이 우선. 다중 사용자 시점에는 옵션 A 또는 B 로 재설계 예정 — 본 PRD 비범위.

UX 보정: NL turn 진행 중에 새 NL 메시지가 도달하면 **즉시 안내 + 거절** (큐 적재 안 함). 사용자는 잠시 후 재시도하면 되며, 대기 큐가 없으니 응답 지연 누적도 없다.

---

## 2. 봇 네이밍 / 컴플라이언스 제약 재확인

상위 PRD `slack-dev-relay.md` §1 ("외부 노출 텍스트 네이밍 제약") 정책을 그대로 승계한다. 본 PRD 는 새 봇·새 표시명·새 채널 라벨을 도입하지 않는다. 다만 본 PRD 에서 새로 도입되는 식별자·메시지·audit kind 는 모두 컴플라이언스 가드 통과 대상이다.

- 정책 단일 정의 지점: [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 그대로 재사용 (별도 키워드 셋 신설 금지).
- 본 PRD 본문에서도 봇을 통칭할 때는 "Dev Manager 봇" 으로 부른다.
- 신규 안내 메시지(`TEMPLATE_NL_BUSY`) 본문 예시: "지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요." — 외부 노출 텍스트로서 컴플라이언스 가드 0 hit 통과 필수.
- 신규 audit kind `nl_busy_rejected` 식별자 자체도 본 PRD 본문·코드·테스트에서 0 hit 유지.
- 본 PRD 본문 자체에 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 의 어떤 키워드도 등장하지 않도록 0 hit 유지 (구체 키워드 목록은 코드 단일 정의 지점만 참조 — PRD 본문에는 인라인 나열 금지).

---

## 3. 범위 (In Scope)

본 PRD 는 NL 분기 (`_handle_natural_language`) 의 **process-wide 단일 mutex 직렬화** 에 한정한다.

### 3.1 메커니즘 — `threading.Lock` 단일 인스턴스

- 모듈 스코프 (`ai/dev_relay/main.py`) 또는 `build_app` 컨테이너에 `threading.Lock` 인스턴스 **1개** 를 생성. 이름 예: `_nl_turn_lock` (식별자 자체도 컴플라이언스 0 hit).
- `_handle_natural_language` 진입 직후 `_nl_turn_lock.acquire(blocking=False)` 시도.
  - **acquire 성공**: 현행 흐름 그대로 진행 (existing 조회 → SDK 호출 → session 갱신 → 메시지 발사). 함수 종료 시점(정상·예외 모두) 에 `release()` 보장 — `try/finally` 또는 context manager.
  - **acquire 실패 (이미 누가 락 보유 중)**: 즉시 `TEMPLATE_NL_BUSY` 안내 메시지를 `say(..., thread_ts=thread_ts)` 로 발사하고 함수 즉시 반환. SDK 호출·session 갱신·후속 audit 라인 모두 발생하지 않음. (단, `nl_busy_rejected` audit 라인 1줄은 기록 — §3.4 참조.)
- `blocking=False` 선택 근거: 사용자 결정(§1.1) 대로 큐 적재 없이 즉시 거절. `blocking=True` 로 대기시키면 Slack Bolt executor 스레드를 계속 점유해 worker pool 고갈 + 응답 지연 누적 → UX 악화.

### 3.2 busy 시 정책 — 즉시 안내 + 거절

- busy 발생 시 사용자에게 정확히 1개 메시지 (`TEMPLATE_NL_BUSY`) 를 발사. 추가 응답·메시지 chunk 없음.
- 메시지는 **요청이 도착한 thread_ts** 에 묶어 발사. (기존 NL 응답 정책과 동일 — `main.py:506-509` 의 `say(safe, thread_ts=thread_ts)` 정책 승계.)
- 메시지 본문 예: "지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요." — 정확한 문구는 구현 단계에서 컴플라이언스 가드 통과를 보장하며 결정. 본 PRD 는 "도메인 키워드 0 hit" "20~60자 한국어 1줄" 만 명시.
- 발사 직전 `guard_text_with_urls` 또는 `safe_say` 동급 가드를 거쳐 컴플라이언스 0 hit 검증 (이중 layer). 가드 위반이면 fallback 으로 무발사 + 에러 로그 (외부 노출 사고 절대 금지).
- NL 큐 미도입 — 거절된 메시지는 어디에도 적재되지 않는다. 사용자가 잠시 후 재전송해야 한다 (PM 권고 옵션 1).

### 3.3 structured ↔ NL 상호 직렬화 — 비범위 (별도 락)

- structured 분기는 PR #43 의 `JobQueue` + `AgentRunner(max_workers=1)` 가 직렬화. NL 분기는 본 PRD 의 `_nl_turn_lock` 가 직렬화. **두 락은 독립** — structured 진행 중 NL 진입은 차단되지 않으며, 그 반대도 동일.
- 근거: (a) structured 와 NL 의 race 표면이 다르다 (structured 는 PR/이슈 외부 액션, NL 은 SDK session 매핑). (b) 두 분기 동시 진행이 일으키는 race 사례는 코드 검토상 발견되지 않음. (c) 통합 직렬화는 옵션 A 와 같아 코드 복잡도 폭증.
- 따라서 AC-NLS-4 (structured 진행 중 NL — 회귀) 는 **NL 가 정상 처리됨** 이 기대 동작이다. 본 PRD 는 두 분기 상호 차단을 의도하지 않는다.

### 3.4 audit kind 신규 — `nl_busy_rejected`

busy 거절이 발생한 경우, audit.jsonl 에 다음 1줄 record 를 append.

```json
{"ts": "<ISO-KST>", "kind": "nl_busy_rejected", "thread_ts": "<thread_ts>", "user_id_masked": "<masked>"}
```

- `kind` 식별자는 컴플라이언스 가드 0 hit. (`busy`, `rejected`, `nl` 모두 도메인 키워드 아님 — 가드 통과 확인 필수.)
- `_append_audit` 헬퍼 그대로 사용 — 별도 직렬화 기법 도입 없음.
- 사용 목적: (a) busy 발생 빈도 모니터링. (b) 후속 PRD (다중 사용자·옵션 A/B 재설계) 의 입력 데이터.

### 3.5 shutdown 보호

데몬 shutdown (`SIGTERM` / `SIGINT` / `AgentRunner.shutdown(timeout)` 호출) 시점에 NL turn 이 진행 중이면 다음을 보장한다.

- **진행 중 1건 graceful 종료**: 락을 보유한 NL turn 은 SDK 호출 완료 + 응답 발사 + session 갱신 + audit 기록까지 완수한 뒤 락을 release.
- **새 진입 거절**: shutdown flag (모듈/컨테이너 스코프 `threading.Event` 또는 동급) 가 set 된 이후 `_handle_natural_language` 진입은 락 acquire 시도 이전에 즉시 거절 (`TEMPLATE_NL_BUSY` 또는 별도 shutdown notice — 본 PRD 는 동일 메시지 재사용을 기본으로 한다. 사용자 결정 변경 시 §10 갱신).
- shutdown timeout 내에 진행 중 turn 이 끝나지 않으면 watchdog 이 강제 종료 (PR #37 의 `AgentRunner.shutdown(timeout)` watchdog 정책 그대로). 본 PRD 는 watchdog 자체를 새로 정의하지 않음 — 기존 메커니즘 재사용.

### 3.6 외부 인터페이스·운영 영향

- `_handle_natural_language` 의 외부 시그니처 변경 없음. 호출 측(`build_app` 의 Slack Bolt 핸들러 등록부) 에 lock 인스턴스 주입 1곳만 추가.
- `say` 호출 정책·`thread_ts` 처리·기존 audit kind 변경 없음.
- `JobQueue` / `AgentRunner` 변경 없음.
- 신규 의존성 없음 — `threading` 표준 라이브러리.

---

## 4. 비범위 (Out of Scope)

- **옵션 B (thread_ts 별 lock map)** — 본 PRD 는 process-wide 단일 락만. per-thread 동시성은 다중 사용자 시점 후속 PRD 에서.
- **NL 메시지 큐 / 대기 적재** — busy 시 즉시 거절 정책. 큐 적재·재시도·예약은 도입하지 않음.
- **structured ↔ NL 상호 직렬화** — §3.3 근거대로 비범위.
- **SDK quota / rate limit 진단·튜닝** — `_RateLimiter` (5초/3건) 는 그대로. 본 PRD 는 race 차단만.
- **multi-process 데몬 직렬화** — `threading.Lock` 은 단일 process 내에서만 유효. 멀티 프로세스 / 멀티 인스턴스 데몬 배치는 본 PRD 비범위.
- **shutdown watchdog 자체 재정의** — PR #37 의 `AgentRunner.shutdown(timeout)` watchdog 그대로 재사용. 본 PRD 는 NL 분기 진입 거절 가드만 추가.
- **busy 안내 메시지 다국어화 / 풍부한 안내** — 한국어 1줄, 컴플라이언스 가드 통과 본문 1종만. 다국어·도움말 링크·재시도 시각 안내는 비범위.
- **NL 분기 외 경로 race 점검** — `dev-relay-agent-integration.md` 의 reviewer/devops 호출 경로는 PR #43 으로 직렬화 완료. 본 PRD 와 독립.

---

## 5. 수용 기준 (Acceptance Criteria)

검증은 단위 테스트 + 통합 테스트로 자동화한다. 각 AC 는 §8 에서 테스트 매핑.

### AC-NLS-1. 같은 thread_ts 동시 두 NL — 두 번째 거절

- **재현**: 같은 `thread_ts` + `channel_id` 로 두 NL 이벤트를 거의 동시에 (sub-100ms 간격) `_handle_natural_language` 에 주입. SDK 호출은 mock 으로 1초 지연.
- **기대**:
  - 첫 번째 호출: `_nl_turn_lock` acquire 성공 → SDK 호출 1건 발생 → 정상 응답 발사.
  - 두 번째 호출: acquire 실패 → `TEMPLATE_NL_BUSY` 1줄 발사 → SDK 호출 0건. `sessions.start` / `sessions.resume` 호출 0건.
  - 전체 SDK 호출 횟수 = 1.
  - audit.jsonl 에 `nl_busy_rejected` 1줄 + 정상 turn 의 `llm_invoked` 등 기존 라인 정상 기록.

### AC-NLS-2. 다른 thread_ts 동시 두 NL — 두 번째 거절 (process-wide)

- **재현**: 서로 다른 `thread_ts` 로 두 NL 이벤트를 거의 동시에 주입.
- **기대**: AC-NLS-1 과 동일 — process-wide 락이므로 다른 스레드라도 두 번째는 거절. SDK 호출 1건.
- 사용자(이하영) 가 옵션 C 를 선택한 시점에 이 동작에 동의함을 §1.1 에서 명시. 옵션 B 로 재설계 시 본 AC 가 변경된다.

### AC-NLS-3. turn 종료 후 새 NL 정상 처리

- **재현**: NL turn 1건이 정상 종료 (락 release) 된 후, 새 NL 이벤트 주입.
- **기대**: 두 번째 NL 도 acquire 성공 → SDK 호출 1건 → 정상 응답. busy 거절 안 됨.

### AC-NLS-4. structured 진행 중 NL — 회귀 (별도 경로)

- **재현**: `JobQueue` 에 적재된 structured 명령 (`review pr <N>`) 이 `AgentRunner` 에서 실행 중인 시점에 NL 이벤트 주입. structured 는 mock 으로 5초 지연.
- **기대**: NL 이 즉시 처리됨 (락 미충돌, §3.3 정책). SDK 호출 정상 발사. busy 거절 안 됨.

### AC-NLS-5. rate_limiter 협업 — rate limit 우선 도달 시 NL busy 미발사

- **재현**: 사용자 NL 이 5초 내 4번째 도달 (`_RateLimiter` 5초/3건 초과). 락은 비어 있음.
- **기대**: rate_limiter 가 먼저 발동해 rate limit 안내 메시지 발사. `TEMPLATE_NL_BUSY` 미발사. `nl_busy_rejected` audit 미기록. 즉, **rate limit 가드와 lock 가드가 중복으로 발사되지 않는다.** rate limit 가드가 먼저 적용되도록 호출 순서 보장.

### AC-NLS-6. audit `nl_busy_rejected` 1줄 기록

- **재현**: AC-NLS-1 또는 AC-NLS-2 시나리오에서 거절 1건 발생.
- **기대**: audit.jsonl 에 `kind="nl_busy_rejected"` line 정확히 1줄 추가. 필드: `ts`, `kind`, `thread_ts`, `user_id_masked`. 추가 필드 0개 (스키마 일관성).

### AC-NLS-7. 컴플라이언스 정적 검사

- **재현**: `_compliance.py` 의 `FORBIDDEN_KEYWORDS` 셋을 패턴으로 사용해 다음을 정적 스캔 — 본 PRD 본문, `ai/dev_relay/main.py` diff, `ai/tests/dev_relay/` 신규/변경 케이스, 신규 메시지 상수 (`TEMPLATE_NL_BUSY`), 신규 audit kind 식별자(`nl_busy_rejected`), 관련 PR 제목·본문, 커밋 메시지.
- **기대**: 0 hit. 기존 `ai/tests/dev_relay/test_compliance.py` 의 정적 검사가 신규 변경을 자동 커버하는지 확인 (개별 파일 화이트리스트 누락 시 보강).

### AC-NLS-8. 회귀 — 기존 NL + structured 테스트 0 fail

- **재현**: 기존 `ai/tests/dev_relay/test_handle_command_nl.py` (있으면), `test_agent_integration.py`, `test_dispatcher.py`, `test_tool_policy.py` 모든 케이스 실행.
- **기대**: 0 fail. 본 PRD 변경이 기존 단일 NL 흐름 / structured 흐름에 회귀를 일으키지 않음.

### AC-NLS-9. shutdown — 진행 중 1건 graceful, 새 진입 거절

- **재현**:
  - (a) NL turn 진행 중 (SDK mock 2초 지연) shutdown flag set → 진행 중 turn 은 응답 발사·세션 갱신·audit 기록 완료 후 락 release.
  - (b) shutdown flag set 이후 새 NL 이벤트 주입 → 즉시 거절 + busy 안내 (또는 본 PRD §3.5 에 정의된 동일 메시지). SDK 호출 0건, 세션 갱신 0건.

---

## 6. 가정 · 제약

### 6.1 기술

- Python 3.11+, `threading` 표준 라이브러리. 신규 의존성 없음.
- 변경 영향 범위는 `ai/dev_relay/main.py` 의 `_handle_natural_language` + `build_app` 의 lock 인스턴스 주입 부 + 신규 메시지 상수 1곳. 호출 측 (Slack Bolt 핸들러 등록부) 외 다른 모듈 변경 없음.
- `threading.Lock` 은 단일 process 한정. 멀티 프로세스 데몬 배치 시 본 직렬화는 무효 — §4 비범위.
- Slack Bolt 의 threaded executor 는 default 다중 worker. 본 PRD 가 도입하는 `_nl_turn_lock` 이 그 위에 단일 직렬화 layer 를 얹는다.

### 6.2 보안 / 컴플라이언스

- 본 PRD 는 외부 노출 텍스트 1종 (`TEMPLATE_NL_BUSY`) 을 신규 도입한다. 컴플라이언스 가드 0 hit 통과를 AC-NLS-7 으로 검증.
- 신규 audit kind 식별자(`nl_busy_rejected`) 는 외부 노출이 아니지만, 본 PRD 본문·코드·테스트 모두에서 가드 0 hit 유지를 동일 AC 로 검증.
- 락 보유 중 예외 발생 시 `try/finally` 로 release 보장. 미release 회귀가 발생하면 데몬 전체 NL 분기가 영구 차단되므로 보수적으로 finally 절 필수 — 코드 리뷰 게이트 포인트로 명시.

### 6.3 일정 / 운영

- 로컬 데몬 코드 한정. CI / 배포 / 인프라 변경 없음.
- 로컬 audit.jsonl 형식은 신규 kind 1종 추가 — 분석 스크립트가 unknown kind 를 무시하면 호환. 새 분석 스크립트는 `nl_busy_rejected` 를 인지해 빈도 보고에 포함할 수 있다 (선택, 본 PRD 비범위).
- 머지 후 1~2주간 `nl_busy_rejected` 발생 빈도를 사용자(이하영) 본인이 가볍게 모니터링 — 빈도가 높으면 옵션 A/B 재설계 우선순위 상향.

### 6.4 비용

- SDK 토큰 비용 영향 없음 (busy 거절은 SDK 호출 전 차단). 오히려 동시 SDK 호출 가능성을 0 으로 만들어 비용 폭증 위험을 줄인다.
- `threading.Lock` 자체 비용은 무시 가능 (μs 단위 acquire/release).

---

## 7. 위험 / 의존

1. **락 미release 회귀** — `_handle_natural_language` 내부에서 예외 발생 시 락이 release 되지 않으면 데몬의 NL 분기 전체가 영구 차단된다. 1차 방어는 `try/finally` 또는 context manager 강제. 2차 방어는 단위 테스트에 "예외 발생 → 락 release 검증" 케이스 포함 (AC-NLS-3 의 변형 — `run_turn` 이 raise 하는 시나리오).
2. **rate_limiter 와 lock 가드 발사 중복** — 호출 순서가 잘못되면 rate limit 안내 + busy 안내 둘 다 발사될 수 있다. AC-NLS-5 로 명시 검증. 권장 순서: rate_limiter → lock acquire → SDK.
3. **shutdown 흐름과 락 release 경쟁** — shutdown flag 가 set 되는 시점과 진행 중 turn 의 락 release 가 경쟁할 수 있다. AC-NLS-9 (a) 로 graceful 종료를 명시 검증. watchdog timeout (PR #37) 보다 짧은 시간 내 turn 종료가 정상 케이스, 초과 시 강제 종료는 watchdog 책임.
4. **busy 메시지 자체가 race 를 유발하는 경우** — `say(TEMPLATE_NL_BUSY, thread_ts=...)` 가 외부 API 호출인데, 거절 빈도가 높으면 Slack rate limit 표면이 늘어난다. 1인 MVP 단계에서는 무시 가능. 다중 사용자 시점에는 옵션 B 로 재설계되어야 함.
5. **`_append_audit` 자체 락 부재** — 본 PRD 가 NL 분기 직렬화로 동시 audit 기록 가능성을 줄여주지만, structured 분기와 동시 audit 기록은 여전히 가능. 단일 line write 가 보통 atomic 이므로 본 PRD 비범위 — 별도 PRD 에서 `_append_audit` 자체에 `threading.Lock` 추가가 필요하면 후속 작업.
6. **multi-process 데몬 배치 시 무효** — 본 PRD 의 `threading.Lock` 은 process-local. 운영자가 데몬을 멀티 인스턴스로 배치하면 직렬화가 무효화된다. 현재 운영은 단일 인스턴스이며, 멀티 인스턴스 배치는 §4 비범위. 운영 가이드(`docs/HANDOFF.md` 또는 `README.md`) 에 "본 데몬은 단일 인스턴스 전제" 한 줄 추가 권장 (구현 단계 선택).

---

## 8. 테스트 전략 개요

QA 가 본 PRD AC 를 검증하기 위한 1차 가이드. 정확한 테스트 항목은 QA 산출물(`docs/qa/dev-relay-nl-serialize.md`) 이 주도한다.

### 8.1 자동 (단위 / 통합)

- **신규 테스트 클래스** (`ai/tests/dev_relay/test_handle_command_nl_serialize.py` 신규 또는 `test_handle_command_nl.py` 확장):
  - `TestNLSerializeSameThread` — AC-NLS-1
  - `TestNLSerializeDifferentThread` — AC-NLS-2
  - `TestNLSerializeSequential` — AC-NLS-3 (정상 종료 후 재진입)
  - `TestNLSerializeStructuredCoexist` — AC-NLS-4 (별도 락 검증)
  - `TestNLSerializeRateLimitInterop` — AC-NLS-5 (rate_limiter 우선)
  - `TestNLSerializeAudit` — AC-NLS-6 (audit kind 1줄)
  - `TestNLSerializeShutdown` — AC-NLS-9 (graceful + 새 진입 거절)
  - `TestNLSerializeLockReleaseOnException` — §7 위험 1번 (예외 시 락 release)
- **mock 전략**: `run_turn` 을 `time.sleep` mock 으로 감싸 SDK 호출 지연 시뮬. `threading.Thread` 2개로 동시 진입 재현. `_append_audit` 는 in-memory list 캡처 mock.
- **회귀**: 기존 `ai/tests/dev_relay/test_handle_command_nl.py`, `test_agent_integration.py`, `test_dispatcher.py`, `test_tool_policy.py` 모든 parametrize 케이스 0 fail (AC-NLS-8).
- **컴플라이언스 정적 검사**: `test_compliance.py` 의 파일 스캔 화이트리스트에 본 PRD 산출물(`docs/prd/dev-relay-nl-serialize.md`) + 신규 메시지 상수 + 신규 audit kind 포함 확인 (AC-NLS-7).

### 8.2 수동 (사용자 검증)

상위 PRD 부록 A 셋업이 완료된 환경에서 모바일 Slack 앱에서 다음 한 사이클을 1회 수행:

- 같은 스레드에 자연어 메시지 2개를 빠르게 (1~2초 간격) 연속 전송 → 첫 번째는 정상 응답, 두 번째는 즉시 busy 안내 1줄 수신.
- 첫 번째 응답 완료를 기다린 후 같은 스레드에 새 자연어 전송 → 정상 응답 (회귀 확인).
- structured 명령 (`review pr <N>`) 진행 중에 새 스레드에서 자연어 전송 → 자연어가 즉시 처리됨 (별도 락 확인).

---

## 9. 참고

- 상위 PRD: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md)
- 인접 PRD: [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md), [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md)
- 사촌 PR: PR #43 (structured 분기 직렬화), PR #37 (`AgentRunner.shutdown(timeout)` watchdog)
- 변경 대상 코드: [`ai/dev_relay/main.py`](../../ai/dev_relay/main.py) `_handle_natural_language` (라인 417-509)
- 테스트 패턴 참조: [`ai/tests/dev_relay/test_handle_command_nl.py`](../../ai/tests/dev_relay/test_handle_command_nl.py) (있으면), [`ai/tests/dev_relay/test_agent_integration.py`](../../ai/tests/dev_relay/test_agent_integration.py)
- 정책 단일 정의 지점: [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS`
- `AGENTS.md` — PRD 양식, 라벨 플로우, 컴플라이언스 원칙

---

## 10. PM 결정사항 요약 (구현·QA 가 한눈에 보도록)

| 항목 | 결정 |
|---|---|
| 본 PRD 책임 범위 | NL 분기 (`_handle_natural_language`) 의 process-wide 단일 mutex 직렬화 |
| 메커니즘 | `threading.Lock` 1개, `acquire(blocking=False)` 패턴, `try/finally` release 강제 |
| busy 시 정책 | 즉시 `TEMPLATE_NL_BUSY` 안내 1줄 발사 + 거절. NL 큐 미도입 (PM 권고 옵션 1) |
| structured ↔ NL 상호 직렬화 | **비범위** — 별도 락이라 동시 진행 가능 (AC-NLS-4) |
| 신규 audit kind | `nl_busy_rejected` 1줄. 필드: `ts`, `kind`, `thread_ts`, `user_id_masked` |
| 신규 메시지 상수 | `TEMPLATE_NL_BUSY` — 한국어 1줄, 컴플라이언스 0 hit |
| rate_limiter 와의 상호작용 | rate_limiter 가 먼저 적용. lock 가드는 그 다음. busy 안내 중복 발사 금지 (AC-NLS-5) |
| shutdown 보호 | 진행 중 1건 graceful 종료, 새 진입 거절. watchdog 자체는 PR #37 재사용 |
| 외부 인터페이스 변경 | **없음** — `_handle_natural_language` 시그니처·`JobQueue`·`AgentRunner`·기존 audit kind 모두 그대로 |
| 운영 모니터링 | 머지 후 1~2주간 `nl_busy_rejected` 발생 빈도 사용자 본인 모니터링 → 후속 옵션 A/B 재설계 입력 |
| 다중 사용자 / 멀티 인스턴스 | 본 PRD 비범위. `threading.Lock` 은 단일 process 한정 |
