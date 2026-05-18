# PRD: Dev Manager — write 도구 NL 자율 트리거 (Phase 3)

- **slug**: `dev-relay-write-tools-nl`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-16
- **UI 포함 여부**: **No** (별도 웹/네이티브 UI 없음. 외부 노출은 Slack DM 텍스트·Block Kit confirm 다이얼로그만 — 상위 PRD `slack-dev-relay.md` 와 동일 정책)
- **상위 PRD (Phase 2 직접 부모)**: [`docs/prd/dev-relay-write-tools.md`](./dev-relay-write-tools.md) (§3.2.4 + §10 에서 NL 진입을 "보조" 로 정의하고 본 PRD 로 분리 명시)
- **인접 PRD**: [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md), [`docs/prd/dev-relay-nl-serialize.md`](./dev-relay-nl-serialize.md), [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md)
- **선행 PR (이미 머지)**: #54 (Phase 2 — write 도구 structured 경로 + AC-WT-7 NL 자율 트리거 DEFERRED), #48 (NL 분기 process-wide 직렬화), #43 (reviewer/merger 통합), #25 (MVP 데몬)
- **대상 코드**: `ai/dev_relay/nl_classifier.py` (라벨 추가), `ai/dev_relay/main.py` `_handle_natural_language` (write 분류 후 변환 + worker spawn), `ai/dev_relay/dispatcher.py` (NL → structured 변환 후 재진입 경로), `ai/dev_relay/write_runtime.py` / `ai/dev_relay/write_tools.py` (재사용)

---

## 1. 배경 / 문제

### 1.1 현재 상태 (Phase 2 머지 후)

PR #54 (`dev-relay-write-tools`) 가 머지되면서 Phase 2 본체는 reproducible 한 상태다. 구체적으로:

- structured write 명령 3종 (`apply patch pr=<N>`, `commit pr=<N>`, `push pr=<N>`) 정상 동작.
- 모든 write 명령은 dry-run 요약 + 2단계 confirm + 적용 흐름.
- destructive 가드·컴플라이언스 가드·audit·shutdown·rate_limiter·멱등성 모두 통과.
- 화이트리스트 user_id 단일 사용자 한정.

그러나 Phase 2 PR #54 는 **AC-WT-7 (NL 자연어 진입 — write 도구 의도 인식 + confirm 강제)** 를 의도적으로 DEFERRED 처리했다. 근거는 다음과 같다:

- structured 경로의 dry-run + confirm 흐름이 안정화되기 전 NL 자율 트리거를 묶으면 destructive 표면이 폭증한다.
- NL 분류기에 write 카테고리 추가 → NL 분기 회귀 위험 분리.
- structured 경로의 audit·가드 정책이 fix 된 후 NL 변환 결과가 같은 가드를 그대로 통과하는지 검증해야 한다.

본 PRD 가 Phase 3 로서 AC-WT-7 의 DEFERRED 를 완전 해소한다.

### 1.2 격차 — NL 진입 시 write 의도가 사장됨

현재 NL 분기 (`_handle_natural_language`, `ai/dev_relay/main.py:560-684`) 는 read-only 도구만 사용한다. 사용자가 NL 로 write 의도를 표현해도 (예: "PR 32 에 오타 수정 patch 적용해줘") read-only 도구 세션이 응답할 뿐이며, 실제 patch 적용을 시도하지 않는다. 사용자는 다시 structured 명령 (`apply patch pr=32`) 을 직접 입력해야 한다.

전형적 시나리오:

- 모바일에서 reviewer 결과를 본 뒤 NL 로 "여기 리뷰 코멘트대로 PR 32 에 patch 적용" 작성 → 봇이 안내만 하고 끝남 → 사용자가 다시 `apply patch pr=32` 입력 → confirm → 적용.
- NL 가 더 자연스러운 입력인데 두 번 입력하는 비용 발생.
- 모바일에서 structured 문법 ("pr=N" 인자 형식) 을 외워야 한다는 UX 부담.

### 1.3 본 PRD 의 책임 범위

본 PRD 는 다음 한 가지를 해소한다:

- NL 입력 → write 의도 자동 분류 → structured 명령 자동 변환 → **Phase 2 (PR #54) 의 dry-run + 2단계 confirm 흐름 그대로 재진입**.

핵심 원칙: **NL 자율 트리거가 만든 변환 결과도 사용자 명시 confirm 없이 적용되지 않는다.** NL 분류 단계만 자동화하고, 적용은 Phase 2 의 동일한 게이트를 통과한다.

### 1.4 운영 제약 (재인용)

- **1인 MVP** — 사용자 = 이하영. 단일 머신·단일 인스턴스 데몬.
- **회사 Slack 가시성** — 봇 표시명·외부 노출 텍스트에 도메인 키워드 노출 절대 금지.
- **SDK 토큰 비용** — NL 분류 호출 + write 변환 호출 + 적용 호출의 3단계 호출 체인이 NL turn 마다 발생할 수 있음. 비용 모니터링 가드는 별도 PRD (`cost-aware-llm-pipeline`).

---

## 2. 봇 네이밍 / 컴플라이언스 제약 재확인

상위 PRD `slack-dev-relay.md` §1 정책을 그대로 승계한다. 본 PRD 가 새 봇·새 표시명·새 채널 라벨을 도입하지 않는다.

- 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` **단일 정의 지점** 그대로 재사용 (별도 키워드 셋 신설 금지).
- 본 PRD 가 새로 도입하는 다음 항목은 모두 같은 가드를 통과해야 한다:
  - 새 NL 의도 라벨 식별자 (§3.1),
  - NL → structured 변환 결과 사용자 노출 메시지 (변환 투명성 표시, §3.3),
  - 자동 생성 커밋 메시지·patch 내용 (Phase 2 와 동일 정책 — 본 PRD 가 새로 만들지 않고 같은 가드 통과),
  - 모호한 의도 거절 안내 메시지 본문 (§3.4),
  - 신규 audit kind 명 (§3.6),
  - 본 PRD 본문 자체.
- 본 PRD 본문에서도 봇을 통칭할 때는 "Dev Manager 봇" 으로 부른다.
- **본 PRD 본문에 `FORBIDDEN_KEYWORDS` 키워드 인라인 나열 금지** — 코드 단일 정의 지점만 참조.

---

## 3. 범위 (In Scope)

본 PRD 는 (A) NL 분류기에 write 카테고리 추가 + (B) NL → structured 변환 + (C) Phase 2 흐름 재진입 세 묶음을 단일 spec 으로 정의한다.

### 3.1 NL 분류기 확장 (§3.2.4 의 카테고리 추가)

#### 3.1.1 분류기 선택 — PM 권고 (사용자 결정 게이트 1)

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **(a)** | **기존 `nl_classifier.py` (Haiku 4.5) 확장 — 라벨 추가** | 인프라 공유. 분류 1회로 read·write 분기 모두 처리. 토큰 비용 ↓ | 라벨이 늘어 분류 정확도 마진 감소 가능 |
| (b) | 신규 write 전용 분류기 모듈 도입 (2단계 분류) | read·write 분류 정확도 독립 튜닝 가능 | NL turn 마다 분류 호출 2회 → 비용·지연 ↑ |

**PM 권고: (a)** — 기존 `nl_classifier` 확장. 근거:

- DRY 원칙 — NL 분기 진입점·`_nl_turn_lock`·audit 흐름 공유.
- 토큰 비용 ↓ — 분류 호출 1회 추가 vs 2회.
- 1인 MVP 단계 분류 정확도 마진은 사용자 confirm 단계에서 흡수 가능 (오분류여도 confirm 에서 사용자가 차단).

본 PRD 는 (a) 기준으로 §3.1.2 이후 작성.

#### 3.1.2 신규 라벨

`IntentLabel` enum 에 다음 1개 라벨 추가 (정확한 식별자는 컴플라이언스 가드 0 hit 확보):

```
WRITE_REQUEST   # 사용자 NL 입력이 patch / commit / push 의도를 표현
```

분류 매핑:

- patch 적용·코드 수정 의도 ("PR <N> 에 patch 적용해줘", "PR <N> 오타 고쳐줘") → `WRITE_REQUEST`
- commit / push 의도 ("PR <N> 커밋 해줘", "PR <N> 푸시해줘") → `WRITE_REQUEST`
- 기존 라벨 (`SUMMARY_REQUEST`, `REPORT_REQUEST`, `STATUS_LIKE`, `UNKNOWN_OR_DESTRUCTIVE`) 의미는 그대로.
- destructive 의도 표지 (force push, rebase, reset --hard, .env 수정 등) 는 분류 단계에서 `UNKNOWN_OR_DESTRUCTIVE` 로 fallback — 기존 정책 그대로 (`CLASSIFY_SYSTEM_PROMPT` 보강).

분류 프롬프트 (`CLASSIFY_SYSTEM_PROMPT`) 에 `WRITE_REQUEST` 정의 1줄 추가. 라벨 외 출력 금지 정책은 그대로.

#### 3.1.3 분류 후 라우팅

```
NL turn
  ├─ _nl_turn_lock acquire (기존 그대로)
  ├─ [Haiku] 분류
  │   ├─ WRITE_REQUEST   → 본 PRD 신규 분기 (§3.2)
  │   ├─ SUMMARY_REQUEST / REPORT_REQUEST → 기존 Sonnet 분기
  │   ├─ STATUS_LIKE     → 기존 Haiku 짧은 응답
  │   └─ UNKNOWN_OR_DESTRUCTIVE → 기존 Haiku 거부 안내
  └─ _nl_turn_lock release
```

### 3.2 NL → structured 변환 (격차 핵심)

#### 3.2.1 변환 단계

`WRITE_REQUEST` 라벨이 떨어지면 다음 흐름:

1. **변환 SDK 호출** — Haiku 또는 Sonnet (PM 권고 §3.2.2) 으로 NL 텍스트 → structured 명령 변환.
   - 입력: 사용자 NL 텍스트 + 최근 스레드 컨텍스트 (`thread_ts` 의 직전 reviewer 결과 등).
   - 출력: 구조화 JSON — `{"tool": "apply_patch" | "commit" | "push", "pr": <int>, "confidence": <0..1>}` 형태. 추가 자유 텍스트 출력 금지.
2. **변환 결과 검증** — 출력 JSON 형식·필드·범위 검증. 형식 위반은 §3.4 모호 처리로 fallback.
3. **structured 명령 문자열 합성** — 검증된 JSON 을 dispatcher 가 기존 정규식으로 매치할 수 있는 문자열로 합성 (예: `apply patch pr=32`).
4. **사용자 확인 메시지** (§3.3) — 변환 결과 표시 + Phase 2 의 dry-run + confirm 흐름 발사.
5. **Phase 2 흐름 재진입** — 합성된 structured 명령을 `dispatcher.parse(...)` 에 그대로 통과시켜 기존 `_spawn_write_worker` 경로로 전달.

#### 3.2.2 변환 SDK 모델 선택

| 옵션 | 모델 | 장점 | 단점 |
|---|---|---|---|
| (a) | Haiku 4.5 | 분류와 같은 모델 — 인프라 공유, 비용 ↓ | 변환 정확도가 PR 번호 추론·tool 선택에 불충분할 수 있음 |
| **(b)** | **Sonnet 4.6** | 변환 정확도 ↑. 스레드 컨텍스트 종합 가능 | 토큰 비용 ↑ (turn 마다 Sonnet 추가 호출) |

**PM 권고: (b) Sonnet 4.6**. 근거:

- 변환 오류 (예: tool 오분류·PR 번호 추론 실패) 의 사고 비용 > 토큰 비용 차이.
- 사용자 confirm 단계에서 차단되어 destructive 사고로 이어지진 않으나, 변환 정확도 낮으면 confirm 거절률 ↑ → UX 악화 → NL 자율 트리거 가치 자체가 사라짐.
- 1인 사용자 NL turn 빈도는 하루 수 건 수준. 비용 폭증 위험 작음.

본 PRD 는 (b) 기준으로 §3 이후 작성. 사용자가 (a) 를 선택하면 §3.5 비용 항목만 갱신.

#### 3.2.3 변환 가능한 도구 범위

Phase 2 의 3개 도구 그대로 — `apply_patch`, `commit`, `push`. 본 PRD 가 새 도구를 도입하지 않는다.

- 단일 패치 단위로 변환 (다중 파일 일괄 변경은 Phase 2 와 동일하게 1 patch = 1 명령으로 표현).
- 다중 도구 chain (예: "patch 적용하고 commit 까지" 한 메시지) 처리:
  - PM 권고 — **첫 도구만 변환** (`apply_patch`). 사용자에게 "patch 적용 후 commit / push 는 별도로 명령해 주세요" 안내 1줄. 한 NL turn 에서 다중 도구 chain 자동 실행은 destructive 가드 표면 ↑.
  - 사용자가 chain 을 명시적으로 원하면 structured 경로에서 순차 명령 입력 (Phase 2 와 동일).

### 3.3 사용자 확인 UX — 변환 투명성

#### 3.3.1 변환 결과 표시 — PM 권고 (사용자 결정 게이트 2)

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **(a)** | **dry-run confirm 다이얼로그에 변환된 structured 명령을 함께 표시** | 사용자가 변환 정확성 즉시 확인 가능. 오변환 차단율 ↑ | confirm 메시지 길이 ↑ |
| (b) | 변환 결과 숨김 (Phase 2 와 동일한 dry-run 표시만) | confirm 메시지 짧음 | 사용자가 어떤 명령으로 변환됐는지 모름 — 오변환 인지 불가 |

**PM 권고: (a)**. 근거: 변환 투명성. 사용자가 "이렇게 변환됐는데 진짜 맞아?" 를 confirm 단계에서 확인 가능. 오변환 차단의 핵심 게이트.

confirm 다이얼로그 본문 예시 (정확한 문구는 구현 단계에서 컴플라이언스 가드 통과 보장):

```
[NL 자율 변환 결과]
원본: "PR 32 에 오타 수정 patch 적용해줘"
변환: apply patch pr=32

[dry-run 요약 — Phase 2 정책 그대로]
3 파일, +12/-4 라인 변경
- ai/dev_relay/dispatcher.py
- ai/dev_relay/main.py
- ai/dev_relay/nl_classifier.py

[패치 적용]  [취소]
```

#### 3.3.2 동작 흐름

- 변환 + dry-run 표시까지는 한 메시지 (Phase 2 confirm 다이얼로그와 동일 위치).
- 사용자가 `[취소]` 클릭 시 워킹트리·커밋·remote 모두 변경 없음 (Phase 2 AC-WT-6 정책 그대로).
- 사용자가 `[패치 적용]` 클릭 시 Phase 2 의 `_spawn_write_worker` 흐름 그대로 실행.

### 3.4 모호한 의도 처리 — PM 권고 (사용자 결정 게이트 3)

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **(a)** | **변환 거절 + "더 명확하게 작성해주세요" 안내** | 단순. MVP 안전 default | 사용자 추가 입력 필요 |
| (b) | classifier 추가 질문 (multi-turn) — "어떤 PR? 어떤 파일?" | UX 자연스러움 | NL 분기 multi-turn 분기 추가 → 직렬화·세션 lifecycle 복잡도 ↑ |
| (c) | 가장 합리적 추론 + 사용자 확인 | 한 메시지로 완결 | 추론 오류가 confirm 단계에서야 노출 — UX 마찰 |

**PM 권고: (a)**. 근거:

- MVP 단계 단순성 — multi-turn 분기는 NL 직렬화 락 정책과 상호작용해 race 표면 확대.
- 변환 SDK 가 `confidence < 0.7` 또는 JSON 형식 위반·필수 필드 (`tool`, `pr`) 누락 시 즉시 거절.
- 사용자가 "PR 번호를 알려주세요" 같은 안내 1줄 받고 재입력 → 두 번째 NL turn 에서 정상 변환.

거절 조건:

- 변환 SDK 출력 JSON 파싱 실패.
- 필수 필드 (`tool`, `pr`) 누락.
- `tool` 값이 화이트리스트 (`apply_patch`, `commit`, `push`) 밖.
- `confidence < 0.7` (threshold 는 1~2주 모니터링 후 조정 — 본 PRD 는 default 0.7 명시).

거절 안내 메시지 본문은 컴플라이언스 가드 0 hit + 한국어 1~2줄. 정확한 문구는 구현 단계에서 결정.

### 3.5 destructive 가드 / 컴플라이언스 — 다층 가드

본 PRD 는 새 가드를 도입하지 않고 Phase 2 의 다층 가드를 그대로 통과시킨다. 가드 적용 지점:

1. **NL 입력 단계** — `is_destructive(user_text)` 호출. force push·rebase·reset 의도 표현 시 `UNKNOWN_OR_DESTRUCTIVE` 분류 fallback (§3.1.2).
2. **변환 결과 단계** — 변환 SDK 출력 JSON 의 `tool` / `pr` 검증 (§3.4). 추가로 변환 결과 메시지·confirm 다이얼로그 본문이 컴플라이언스 가드 통과.
3. **structured 재진입 단계** — Phase 2 의 `tool_policy.py` `is_destructive` + 화이트리스트/블랙리스트 (PR #54 §3.3.2) 그대로 통과. NL 진입이라고 가드 우회 0건.
4. **적용 직전 단계** — Phase 2 의 dry-run + confirm + atomic 보장 (PR #54 §3.3.4) 그대로.

### 3.6 신규 audit kind

Phase 2 의 audit kind (PR #54 §3.7) 를 그대로 따르되, NL 자율 트리거 진입을 추적할 다음 kind 추가. 모든 kind 식별자는 컴플라이언스 가드 0 hit.

```
nl_write_classified           {ts, kind, thread_ts, user_id_masked, label, confidence}
nl_write_converted            {ts, kind, thread_ts, user_id_masked, tool, pr, confidence}
nl_write_conversion_failed    {ts, kind, thread_ts, user_id_masked, reason}
nl_write_handoff              {ts, kind, thread_ts, user_id_masked, job_id, tool, pr}
```

- `nl_write_classified` — NL 분기에서 `WRITE_REQUEST` 라벨이 떨어진 시점.
- `nl_write_converted` — 변환 SDK 호출 후 검증 통과 시점.
- `nl_write_conversion_failed` — §3.4 거절 조건 매치 시점. `reason` 값: `parse_error`, `missing_field`, `unknown_tool`, `low_confidence`.
- `nl_write_handoff` — 변환된 structured 명령이 Phase 2 `_spawn_write_worker` 에 전달된 시점. 이 라인 이후의 audit 는 Phase 2 의 `patch_requested` / `commit_requested` / `push_requested` 가 이어진다 (즉 두 PRD 의 audit 가 한 thread_ts 에서 자연스럽게 연결).

### 3.7 동시성 — NL 자율 트리거와 write worker queue

- NL 분기는 `_nl_turn_lock` (process-wide `threading.Lock`, `dev-relay-nl-serialize.md` 정책 그대로) 보유.
- 변환 + 사용자 확인 메시지 발사까지 lock 보유.
- 사용자가 `[패치 적용]` 클릭하면 그 클릭 이벤트는 **별도 Slack action handler** 가 받음 → `_spawn_write_worker` 호출 (Phase 2 정책 그대로).
- 즉 NL turn 자체는 변환·확인 메시지 발사로 종료 (lock release). 실제 적용은 Phase 2 worker thread.
- race 표면:
  - NL turn 진행 중 (변환 SDK 호출 중) 새 NL 메시지 도달 → 기존 `_nl_turn_lock` 의 `acquire(blocking=False)` 가 거절 → `TEMPLATE_NL_BUSY` 안내 (기존 정책 회귀 없음).
  - NL turn 종료 후 confirm 대기 중 새 NL 메시지 도달 → 정상 처리 (lock 이미 release). confirm 다이얼로그는 in-memory `_write_pending` 에 남아 있어 클릭 시 정상 동작.
  - 같은 PR 에 NL 자율 트리거 + structured 명령 동시 진행 → Phase 2 `JobQueue` 의 `running_count >= 1` 가드 그대로 (AC-WT-8 정책 회귀 없음).

### 3.8 shutdown 보호

- `_nl_shutdown_flag` 와 `_write_shutdown_flag` 두 flag 가 모두 Phase 2 시점에 존재.
- shutdown flag set 이후 NL 분기 진입은 기존 정책 그대로 거절 (`dev-relay-nl-serialize.md` §3.5 회귀 없음).
- 변환 결과 confirm 다이얼로그 발사 후 shutdown 시그널 도달 시:
  - 사용자가 아직 클릭 안 함 → confirm 다이얼로그 무효화. 다음 시작 시 "이전 세션 NL 자율 변환 confirm 대기 작업은 무효화됐습니다" 안내 (Phase 2 §3.6 패턴 그대로).
  - 사용자가 클릭한 상태면 Phase 2 worker thread 가 진입했으므로 Phase 2 의 shutdown 정책 그대로.

### 3.9 rate limit / 멱등성

- NL 분기 자체에 기존 rate limit 정책 (`dev-relay-natural-language.md` AC-12) 그대로 적용. NL 자율 트리거는 NL turn 의 일부이므로 별도 limit 신설 X.
- 변환 결과 적용 후 같은 `client_msg_id` 재수신 시 → Phase 2 `patch_requested` 멱등성 (AC-WT-11) 그대로 통과.

---

## 4. 비범위 (Out of Scope)

- **사용자 명시 의도 없는 자동 코드 생성** — NL 메시지가 명확한 write 의도일 때만 트리거 (`WRITE_REQUEST` 라벨 + `confidence ≥ 0.7`). 봇이 reviewer 발견 사항을 보고 자율적으로 patch 를 만드는 흐름은 도입하지 않음.
- **다중 파일 일괄 변경** — 단일 patch 단위 (Phase 2 와 동일). NL 으로 "여러 PR 에 한 번에 적용" 같은 표현은 §3.4 모호 거절.
- **다중 도구 chain 자동 실행** — §3.2.3. 첫 도구만 변환하고 chain 은 사용자 명시 명령으로 유도.
- **자동 PR 생성·머지** — Phase 2 와 동일 — 사용자 명시 명령 필요. NL 으로 "PR 만들어줘" 같은 의도는 §3.2.3 화이트리스트 밖이므로 §3.4 거절.
- **다국어** — 한국어/영어만. 기존 NL 분기 정책 그대로.
- **multi-turn 모호 처리 (option b)** — §3.4. PM 권고는 single-turn 거절.
- **변환 SDK 의 자율 도구 호출** — 변환 SDK 는 read·write 도구 호출 0건. 순수 분류·합성 함수.
- **새 봇 명령 추가** — 본 PRD 는 NL 분기 분류 라벨 1개 추가만. structured 명령 신설 X.
- **SDK 비용 모니터링 가드 통합** — `cost-aware-llm-pipeline` 영역. 별도 PRD.
- **다중 사용자·멀티 인스턴스** — 1인 단일 인스턴스 전제. 기존 정책 그대로.
- **변환 정확도 자동 학습·튜닝** — 1~2주 모니터링 + 사용자 confirm 거절률 기반 수동 조정.

---

## 5. 수용 기준 (Acceptance Criteria)

QA 가 그대로 체크리스트로 사용한다. **재현 절차 + 기대 결과** 형식.

### AC-WTN-1. NL 분류기 — `WRITE_REQUEST` 라벨 분류

- **재현**: 본인 DM 에 자연어 "PR <N> 에 patch 적용해줘" 입력 (실재 open PR).
- **기대**:
  - `nl_classifier` 가 `WRITE_REQUEST` 라벨 반환.
  - audit.jsonl 에 `nl_write_classified` 라인 1줄 + `label=WRITE_REQUEST` + `confidence` 필드.
  - 기존 라벨 (`SUMMARY_REQUEST`, `REPORT_REQUEST`, `STATUS_LIKE`) 회귀 0건 — 각각의 NL 입력에 대해 기존 라벨이 그대로 떨어진다.

### AC-WTN-2. NL → structured 변환 정상 흐름

- **재현**: AC-WTN-1 와 동일 입력.
- **기대**:
  - 변환 SDK (Sonnet) 호출 → JSON 출력 → 검증 통과.
  - audit.jsonl 에 `nl_write_converted` 라인 + `tool=apply_patch` + `pr=<N>` + `confidence`.
  - 같은 스레드에 사용자 확인 메시지 발사 — §3.3.1 형식 (원본 NL + 변환 결과 + dry-run 요약 + `[패치 적용]`, `[취소]` 버튼).
  - 변환 결과 메시지·버튼 라벨·footer 도메인 키워드 0 hit.

### AC-WTN-3. Phase 2 흐름 재진입 — 적용까지

- **재현**: AC-WTN-2 의 확인 메시지에서 `[패치 적용]` 클릭.
- **기대**:
  - audit.jsonl 에 `nl_write_handoff` 라인 → Phase 2 의 `patch_requested` → `patch_generated` → `patch_confirmed(applied)` → `patch_applied` 가 순서대로 이어짐.
  - 워킹트리에 patch 적용 확인.
  - Phase 2 AC-WT-2 의 모든 검증 항목 회귀 0건.

### AC-WTN-4. 모호한 의도 — 변환 거절

- **재현**: 다음 케이스 각각 입력.
  - (a) PR 번호 없는 입력: "patch 적용해줘"
  - (b) tool 불명: "PR 32 좀 어떻게 해줘"
  - (c) 화이트리스트 밖 의도: "PR 32 만들어줘" (gh pr create)
  - (d) destructive 의도: "PR 32 강제 푸시해줘"
- **기대**:
  - (a)~(c): `nl_write_conversion_failed` audit + 사용자에게 "더 명확하게 작성해주세요" 안내 1~2줄. 워킹트리 변경 0건.
  - (d): NL 분류 단계에서 `UNKNOWN_OR_DESTRUCTIVE` fallback (기존 정책 회귀 없음). 변환 SDK 호출 0건.

### AC-WTN-5. 사용자 confirm `[취소]` — 변환 결과 폐기

- **재현**: AC-WTN-2 의 확인 메시지에서 `[취소]` 클릭.
- **기대**:
  - 봇이 "취소했습니다." 안내 (이유 입력 강제 X — Phase 2 정책 그대로).
  - 워킹트리·커밋·remote 어디에도 부작용 없음.
  - audit.jsonl 에 `patch_confirmed(cancelled)` 라인 (Phase 2 정책 그대로) + `patch_applied` 라인 부재.

### AC-WTN-6. destructive 가드 — NL 진입 시에도 차단

- **재현**: NL 으로 다음 입력.
  - (a) "PR 32 에 .env 파일 수정 patch 적용해줘"
  - (b) "PR 32 amend 커밋 해줘"
  - (c) "PR 32 force push 해줘"
- **기대**:
  - 분류 단계 또는 변환 결과 검증 단계 또는 Phase 2 `tool_policy.py` 가드 중 한 곳에서 차단.
  - audit.jsonl 에 `nl_write_conversion_failed` 또는 `write_destructive_blocked` (Phase 2) 라인 1줄.
  - 사용자에게 "이 작업은 PC에서 직접 처리해 주세요" 안내 (Phase 2 §3.3 정책 그대로).
  - 워킹트리·커밋·remote 변경 0건.

### AC-WTN-7. 동시성 — NL 자율 트리거 + structured 명령 race

- **재현**: NL 자율 트리거 confirm 다이얼로그 발사 후, 같은 PR 에 대해 structured `apply patch pr=<N>` 명령 추가 입력.
- **기대**:
  - 두 번째 명령은 Phase 2 `JobQueue` 의 `running_count >= 1` 가드 적용 → `pending` 적재 또는 `TEMPLATE_QUEUE_BUSY` 안내 (Phase 2 AC-WT-8 정책 그대로).
  - 첫 번째 confirm 미클릭 상태에서도 in-memory `_write_pending` 의 무결성 유지.
  - NL 분기 직렬화 (`_nl_turn_lock`) 회귀 없음 — AC-NLS-* (`dev-relay-nl-serialize.md`) 0 fail.

### AC-WTN-8. shutdown 보호 — confirm 대기 무효화

- **재현**: NL 자율 트리거 confirm 다이얼로그 발사 후 사용자 미클릭 상태에서 SIGTERM 전송 → 데몬 재시작.
- **기대**:
  - confirm 다이얼로그 무효화 (in-memory `_write_pending` 휘발).
  - 재시작 후 사용자 클릭 시 "이전 세션 confirm 대기 작업은 무효화됐습니다" 안내 (Phase 2 정책 그대로).
  - 워킹트리·커밋·remote 변경 0건.

### AC-WTN-9. 멱등성 — 동일 client_msg_id 재수신

- **재현**: 동일 `client_msg_id` 를 가진 NL 메시지를 두 번 주입 (Slack 재전송 시뮬레이션).
- **기대**:
  - 변환 SDK 호출 1번만. 두 번째는 INFO 로그 (`duplicate event ignored`).
  - `nl_write_classified` / `nl_write_converted` audit 라인 각 1줄.
  - confirm 다이얼로그 1건만 발사.

### AC-WTN-10. rate limit — NL 자율 트리거도 적용

- **재현**: 본인 DM 에 5초 내 4건 이상의 write 의도 NL 메시지 입력.
- **기대**: `dev-relay-natural-language.md` AC-12 의 NL rate limit 정책 그대로 — 4번째 이후 큐 미적재 + rate limit 안내. SDK 호출 폭증 방지.

### AC-WTN-11. audit log 완전성

- **재현**: AC-WTN-2 → AC-WTN-3 한 사이클 1회 완주.
- **기대**: audit.jsonl 에 다음 시퀀스로 빠짐없이 기록:
  - `nl_write_classified` → `nl_write_converted` → `nl_write_handoff` → `patch_requested` → `patch_generated` → `patch_confirmed(applied)` → `patch_applied`

### AC-WTN-12. 컴플라이언스 정적 검사

- **재현**: 본 PRD 본문, `ai/dev_relay/nl_classifier.py` / `main.py` diff, `ai/tests/dev_relay/` 신규/변경 케이스, 신규 메시지 상수, 신규 audit kind 식별자, 신규 라벨 식별자, 본 PRD 구현 PR 본문 / 커밋 메시지를 `FORBIDDEN_KEYWORDS` 패턴으로 정적 스캔.
- **기대**: **0 hit**. 기존 `ai/tests/dev_relay/test_compliance.py` 정적 검사가 본 PRD 산출물을 모두 커버하도록 화이트리스트 보강.

### AC-WTN-13. 외부 노출 텍스트 (변환 결과 + 자동 커밋 메시지) 컴플라이언스

- **재현**:
  - (a) AC-WTN-2 의 변환 결과 confirm 메시지 본문 정적 스캔.
  - (b) AC-WTN-3 이후 NL 자율 트리거 commit 사이클의 자동 생성 커밋 메시지 (`git log -1 --format=%B`) 정적 스캔.
- **기대 (a)**: 도메인 키워드 0 hit. 변환 결과 표시가 SDK 출력 그대로 노출되지 않고 `slack_renderer` 의 발사 직전 가드를 통과.
- **기대 (b)**: Phase 2 AC-WT-15 정책 그대로 — 0 hit. 가드 위반 시 `commit_failed(compliance_blocked)`.

### AC-WTN-14. 회귀 — 기존 PR #25/#43/#48/#54 + NL 분기 직렬화 테스트 0 fail

- **재현**: 기존 `ai/tests/dev_relay/test_agent_integration.py`, `test_handle_command_nl.py`, `test_handle_command_nl_serialize.py`, `test_dispatcher.py`, `test_tool_policy.py`, `test_write_tools.py` (PR #54 신규) 모든 parametrize 케이스 실행.
- **기대**: 0 fail. 본 PRD 변경이 기존 NL 분기·structured write 도구·destructive 가드·NL 직렬화에 회귀를 일으키지 않음.

### AC-WTN-15. AC-WT-7 (PR #54 DEFERRED) 완전 해소

- **재현**: Phase 2 PRD `docs/prd/dev-relay-write-tools.md` AC-WT-7 의 기대 동작 (NL 분기에서 write 도구 카테고리 분류 → SDK 가 patch 생성 → §3.2.3 의 동일 confirm 다이얼로그 발사 → 사용자 명시 confirm 없이 적용 X) 을 실재 NL 입력으로 실행.
- **기대**: AC-WT-7 의 모든 기대 동작 통과. 본 PRD 머지 후 Phase 2 PRD 의 AC-WT-7 DEFERRED 가 해소됐음을 PR 본문에 명시.

---

## 6. 가정 · 제약

### 6.1 기술

- Python 3.11+. Phase 2 환경 그대로 승계.
- 신규 의존성 없음 — `nl_classifier` 확장 + 변환 SDK 호출 wrapper 만 추가.
- 변환 SDK 호출은 `nl_sdk_runtime` 패턴 재사용 (Phase 2 와 동일). 신규 SDK 호출 모듈 만들지 않는다.
- 변환 SDK 출력은 strict JSON. 자유 텍스트 출력은 §3.4 거절 트리거.
- `_handle_natural_language` 의 `_nl_turn_lock` 생명주기 변경 없음 — 본 PRD 가 새 분기를 락 범위 내에 추가.

### 6.2 비용 / 한도

- NL 자율 트리거가 발생할 때 한 turn 에 다음 호출 발생:
  - Haiku 분류 1회 (~300/10 tokens — 기존 정책 그대로),
  - Sonnet 변환 1회 (~1k~3k/100 tokens — 신규),
  - Sonnet patch 생성 1회 (Phase 2 정책 — `_spawn_write_worker` 내부).
- 즉 NL 자율 트리거 1건 = SDK 호출 3건. 1인 사용자 하루 수 건 수준이면 비용 폭증 위험 작음.
- 구독 모드 (Max 20x) quota 부족 시 Phase 2 의 `sdk_timeout` / `unknown_error` fallback 그대로.
- 비용 가드 통합은 별도 PRD.

### 6.3 보안

- NL 자율 트리거도 화이트리스트 user_id 한정 (상위 PRD §3.8 정책 그대로).
- 모든 적용은 2단계 confirm 통과 필수 (NL 진입 + structured 진입 동일).
- patch 텍스트·커밋 메시지·변환 결과 메시지에서 토큰·평문 비밀 노출 차단 (마스킹 정책 그대로).
- 변환 SDK 가 도메인 키워드를 출력에 포함시킨 경우 발사 직전 가드가 차단 (Phase 2 §3.7 패턴).

### 6.4 일정 / 운영

- 로컬 데몬 한정. CI / 배포 / 인프라 변경 없음.
- 본 PRD 머지 후 1~2주 모니터링:
  - NL 자율 트리거 사용 빈도,
  - 변환 confidence 분포 (default 0.7 threshold 조정 근거),
  - `nl_write_conversion_failed` 발생률,
  - 사용자 confirm 거절률 (변환 정확도 proxy).
- 사용 빈도 / 거절률이 예상 초과 시 §3.2.2 변환 모델 / §3.4 threshold 조정 후속 PRD 트리거.

---

## 7. 위험 / 의존

1. **NL 분류 오류** — write 의도 아닌 메시지가 `WRITE_REQUEST` 로 분류될 위험. 사용자 confirm 단계에서 차단 가능. 1~2주 모니터링에서 false-positive 분류 빈도 추적 → 분류 프롬프트 강화 또는 confidence threshold 상향.
2. **변환 정확도 오류** — Sonnet 변환이 잘못된 tool / 잘못된 PR 번호 출력. confirm 단계에서 차단 가능. §3.3 의 변환 결과 표시가 오변환 인지의 핵심 게이트.
3. **destructive op 사고 표면** — NL 진입은 사용자가 자연어로 destructive 의도를 표현할 수 있는 표면을 노출. 다층 가드 (§3.5) 의 어느 하나가 누락되면 사고 가능성 ↑. AC-WTN-6 의 회귀 검증 필수.
4. **컴플라이언스 누설** — NL 입력 자체에 도메인 키워드가 포함될 수 있음 (사용자 본인이 작성). 변환 결과 confirm 메시지가 NL 원본을 그대로 노출 (§3.3.1) 하므로 발사 직전 가드 필수. AC-WTN-13 (a) 의 회귀 검증.
5. **SDK 비용** — NL 자율 트리거 1건 = 3 SDK 호출. 빈도 폭증 시 quota 부담 ↑. 1~2주 모니터링 후 비용 가드 PRD 우선순위 상향 결정.
6. **회귀 위험** — Phase 2 흐름과의 정합. AC-WTN-14 의 회귀 검증 필수.
7. **multi-turn 모호 처리 미도입에 따른 UX 부담** — §3.4 거절 시 사용자가 재입력. 빈도가 사용자 부담 수준이면 §3.4 의 옵션 (b) multi-turn 분기로 후속 PRD 트리거.
8. **변환 SDK output 형식 위반 빈도** — Sonnet 가 strict JSON 출력을 일관되게 유지하지 못할 가능성. JSON 파싱 실패 → `nl_write_conversion_failed` 빈도가 예상 초과 시 변환 프롬프트 강화 (Backend Dev 가 구현 단계에서 결정 — 본 PRD 가 프롬프트 텍스트를 강제하지 않음).
9. **다중 인스턴스 데몬 배치 시 무효** — `dev-relay-nl-serialize.md` §7 위험 6 그대로. 본 PRD 의 `_write_pending` in-memory + `_nl_turn_lock` process-local. 단일 인스턴스 전제.

---

## 8. 테스트 전략 개요

QA 가 본 PRD AC 를 검증하기 위한 1차 가이드. 정확한 테스트 항목은 QA 산출물 (`docs/qa/dev-relay-write-tools-nl.md`) 이 주도한다.

### 8.1 자동 (단위 + 통합)

- **신규 테스트 클래스** (`ai/tests/dev_relay/test_write_tools_nl.py` 신규 또는 `test_nl_classifier.py` 확장):
  - `TestNLClassifierWriteLabel` — AC-WTN-1
  - `TestNLToStructuredConversion` — AC-WTN-2
  - `TestNLPhase2Handoff` — AC-WTN-3
  - `TestNLAmbiguousIntent` — AC-WTN-4
  - `TestNLConfirmCancel` — AC-WTN-5
  - `TestNLDestructiveGuard` — AC-WTN-6
  - `TestNLStructuredConcurrency` — AC-WTN-7
  - `TestNLShutdownProtection` — AC-WTN-8
  - `TestNLIdempotency` — AC-WTN-9
  - `TestNLRateLimit` — AC-WTN-10
  - `TestNLAuditCompleteness` — AC-WTN-11
  - `TestNLComplianceStaticScan` — AC-WTN-12 / AC-WTN-13
- **mock 전략**: 변환 SDK 호출은 fake callable (`time.sleep` + 고정 JSON). Phase 2 worker thread 는 PR #54 의 mock 패턴 그대로 재사용. `git apply` / `git commit` 는 tmp 저장소 fixture.
- **회귀**: AC-WTN-14 의 6개 기존 테스트 모듈 전수 통과.

### 8.2 수동 (사용자 검증)

상위 PRD 부록 A 셋업 완료 환경에서 모바일 Slack 앱에서 다음 사이클을 1회 수행:

- NL 으로 "PR <N> 에 오타 수정 patch 적용해줘" 입력 → 변환 결과 confirm 다이얼로그 확인 → `[패치 적용]` 클릭 → 워킹트리 적용 확인 (PC `git status`).
- 모호 입력 "patch 적용해줘" 입력 → 거절 안내 확인.
- destructive 의도 입력 "PR <N> force push" → 차단 확인.
- 같은 스레드에 후속 NL "commit 해줘" 입력 → 변환 결과 + Phase 2 commit 사이클 확인.
- 모든 봇 응답·confirm 본문·변환 결과 표시·자동 커밋 메시지가 도메인 키워드 0 hit 인지 육안 확인.

---

## 9. 사용자 결정 게이트 (구현 진입 전 확정 필요)

본 PRD 초안의 권고는 다음과 같다. 사용자(이하영) 검토 후 결정 / 보완 → §10 의 표 갱신 → impl 진입.

| # | 항목 | PM 권고 | 대안 | 결정 필요 시점 |
|---|---|---|---|---|
| 1 | NL 분류 모델·접근법 (§3.1.1) | **(a) 기존 `nl_classifier` 확장 — 라벨 1개 추가** | (b) 신규 write 전용 분류기 (2단계) | impl 진입 전 |
| 2 | 변환 결과 사용자 표시 (§3.3.1) | **(a) confirm 다이얼로그에 변환된 structured 명령 함께 표시 (변환 투명성)** | (b) 변환 결과 숨김 (dry-run 만 표시) | impl 진입 전 |
| 3 | 모호한 의도 처리 (§3.4) | **(a) 변환 거절 + 재작성 안내 (single-turn)** | (b) multi-turn 분기 / (c) 합리적 추론 + 확인 | impl 진입 전 |

위 3건 모두 PM 권고를 채택하면 §3 ~ §5 본문 그대로 진행 가능.

부수적 항목 (PM 권고 default 채택 — 사용자가 명시적으로 뒤집지 않으면 default 그대로):

- 변환 SDK 모델 (§3.2.2): **Sonnet 4.6** (변환 정확도 우선).
- 변환 confidence threshold (§3.4): **0.7** (1~2주 모니터링 후 조정).
- 다중 도구 chain 처리 (§3.2.3): **첫 도구만 변환 + 후속 명령 유도**.

---

## 10. PM 결정사항 요약 (구현·QA 가 한눈에 보도록)

| 항목 | 결정 (PM 권고 기준 — 사용자 결정 게이트 §9 통과 후 확정) |
|---|---|
| 본 PRD 책임 범위 | Phase 2 (PR #54) DEFERRED 된 AC-WT-7 (NL 자율 트리거) 완전 해소 |
| NL 분류기 접근 | **기존 `nl_classifier` 확장 — `WRITE_REQUEST` 라벨 1개 추가** |
| 변환 SDK 모델 | **Sonnet 4.6** (변환 정확도 우선) |
| 변환 결과 표시 | **confirm 다이얼로그에 원본 NL + 변환된 structured 명령 함께 표시** (투명성) |
| 모호 의도 처리 | **single-turn 거절 + 재작성 안내** (multi-turn 분기 비범위) |
| 변환 confidence threshold | **0.7** default (1~2주 모니터링 후 조정) |
| 다중 도구 chain | **첫 도구만 변환** + 후속 명령 유도 |
| Phase 2 흐름 재진입 | dispatcher 정규식 매치 → `_spawn_write_worker` (Phase 2 정책 그대로) |
| 2단계 confirm | **Phase 2 정책 그대로** — NL 진입이어도 사용자 명시 confirm 필수 |
| destructive 가드 | **다층** — NL 입력 / 변환 결과 / structured 재진입 / 적용 직전 (Phase 2 단일 정의 지점 재사용) |
| 컴플라이언스 가드 단일 정의 | [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 재사용 |
| 신규 audit kind | 4종 — `nl_write_classified`, `nl_write_converted`, `nl_write_conversion_failed`, `nl_write_handoff` |
| 동시성 | NL 분기 `_nl_turn_lock` + Phase 2 `JobQueue` 독립 운영 (회귀 0건) |
| shutdown 보호 | confirm 대기 작업은 무효화 + 다음 시작 시 안내 (Phase 2 정책 그대로) |
| 자동 코드 생성 | **비범위** — 사용자 명시 NL 의도 + confirm 필수 |
| 다중 파일 일괄·다중 도구 chain | **비범위** |
| `gh pr create` / PR 본문 자동 작성 | **비범위** (Phase 2 와 동일 — 별도 PRD) |
| 다중 사용자·멀티 인스턴스 | **비범위** — 1인 단일 인스턴스 전제 |
| SDK 비용 모니터링 가드 통합 | **비범위** — `cost-aware-llm-pipeline` 의 후속 PRD |
| Phase 2 AC-WT-7 DEFERRED 해소 | **본 PRD 머지로 완전 해소** (AC-WTN-15 명시) |

---

## 11. 참고

- 상위 PRD (Phase 2 직접 부모): [`docs/prd/dev-relay-write-tools.md`](./dev-relay-write-tools.md) — 특히 §3.2.4 (NL 보조 진입 정의) + §10 (Phase 3 분리 명시) + AC-WT-7 (DEFERRED)
- 인접 PRD:
  - [`docs/prd/dev-relay-natural-language.md`](./dev-relay-natural-language.md) — NL 분기 기본 정책
  - [`docs/prd/dev-relay-nl-serialize.md`](./dev-relay-nl-serialize.md) — `_nl_turn_lock` 정책
  - [`docs/prd/dev-relay-agent-integration.md`](./dev-relay-agent-integration.md) — reviewer/merger 통합
  - [`docs/prd/slack-dev-relay.md`](./slack-dev-relay.md) — MVP / 봇 네이밍·컴플라이언스 정책 단일 정의
- 선행 PR (머지됨): #25 (MVP), #43 (reviewer/merger), #48 (NL 분기 직렬화), #54 (Phase 2 write 도구 — AC-WT-7 DEFERRED 본 PRD 가 해소)
- 변경 대상 코드:
  - [`ai/dev_relay/nl_classifier.py`](../../ai/dev_relay/nl_classifier.py) — `WRITE_REQUEST` 라벨 추가, `CLASSIFY_SYSTEM_PROMPT` 보강
  - [`ai/dev_relay/main.py`](../../ai/dev_relay/main.py) `_handle_natural_language` — `WRITE_REQUEST` 분기 + 변환 + Phase 2 handoff
  - [`ai/dev_relay/dispatcher.py`](../../ai/dev_relay/dispatcher.py) — NL → structured 변환 후 정규식 재매치 경로 (또는 직접 `_write_pending` 적재)
  - [`ai/dev_relay/write_runtime.py`](../../ai/dev_relay/write_runtime.py) / [`write_tools.py`](../../ai/dev_relay/write_tools.py) — 본 PRD 가 새 함수 신설 없이 그대로 재사용
  - `ai/dev_relay/nl_sdk_runtime.py` — 변환 SDK 호출 wrapper (`nl_sdk_runtime` 패턴 재사용)
- 정책 단일 정의 지점:
  - 컴플라이언스: [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS`
  - destructive: [`ai/dev_relay/tool_policy.py`](../../ai/dev_relay/tool_policy.py) `is_destructive`
  - 화이트리스트: [`ai/dev_relay/auth.py`](../../ai/dev_relay/auth.py)
- `AGENTS.md` — PRD 양식, 라벨 플로우, 컴플라이언스 원칙, DevOps push 게이트, 개발자 커밋 메시지 컨벤션
- 사용자 메모리 노트: 회사 Slack 동료 가시성, 봇 표시명에 트레이딩 도메인 노출 금지
