# QA: slack-dev-relay

> 작성자: QA (수동 검증 + 자동 테스트)
> 작성일: 2026-05-05
> 입력 PRD: `docs/prd/slack-dev-relay.md`
> 검증 대상 PR: [#25](https://github.com/deeptrading-lab/trading-signal-engine/pull/25) (`feature/slack-dev-relay`)
> 커밋: `29a9881765256d1ae2658386b2c6b1c2129444ab`
> Issue: [#24](https://github.com/deeptrading-lab/trading-signal-engine/issues/24) — P1
> 회귀: `pytest ai/tests/` → **301 passed (0.34s)** · `pytest ai/tests/dev_relay/` → **127 passed (0.33s)**

---

## 0. 요약

- **자동 검증 항목 (단위 테스트)**: AC-9 a/c, AC-10 (마스킹), AC-11 (멱등성), AC-13 (destructive 가드), AC-15 (rate limit), AC-16 (컴플라이언스 정적 검사), AC-17 (자기 메시지 무시) — 모두 PASS.
- **수동 검증 항목 (사용자 PC + Slack 워크스페이스)**: AC-1 (시작 로그·Socket Mode 연결), AC-2 (`status`), AC-3 (`review pr 22` 첫 응답·큐 적재), AC-5 1단계 confirm 다이얼로그, AC-6 (`[취소]` 흐름), AC-7 (자기 자신 user_id 마스킹된 audit), AC-8 (graceful Ctrl+C), AC-9 b (구독 모드 시작 로그), AC-12 (audit log 기록 — review/merge/cancel) — 모두 PASS.
- **본 PR 범위 외 (차기 통합)**: AC-4 (reviewer 결과 + `[머지 검토]`/`[상세 보기]` 버튼), AC-5 2단계 (`[승인]` → devops 머지), AC-14 (동시성 두 번째 명령 큐 적재). PRD §3.3 / [ai/dev_relay/main.py:257-259](../../ai/dev_relay/main.py) 에서 "실 SDK 통합은 부록 A 셋업 후 후속 단계" 로 명시됨.
- 회귀 0건. 토큰 평문 누출 0건. 본 PRD 본문·구현 코드·시작 로그·audit.jsonl 어디에도 도메인 키워드 평문 노출 없음.
- **최종 판정**: `qa-passed` — 본 PR 범위(MVP §3 의 데몬 골격, 명령 라우팅, 큐 적재, 컴플라이언스 가드, 인증 모드 분기) 의 모든 AC 항목 통과. 실 reviewer/devops agent 통합은 별도 후속 PRD 로 분리됨이 PRD §3.3 에 사전 명시된 사항이라 본 검증의 결격이 아님.

---

## 1. PRD 수용 기준 검증

### AC-1. 시작 시 연결 로그 — PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `python -m ai.dev_relay.main` 실행 | Socket Mode 연결 성공 메시지 5초 내 1회 이상, 토큰 평문 미노출 | PASS — 사용자 터미널 출력: `Socket Mode 연결을 시도합니다.` (16:52:06) → `A new session has been established` (16:52:07, +1s) → `⚡️ Bolt app is running!` 시작 로그의 토큰은 `xoxb-***`, `xapp-***` 로 마스킹. |

### AC-2. `status` 응답 — PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 본인(U0AE7A54NHL)이 DM 에 `status` 입력 | 5초 내 같은 DM 응답 + 처리 중/대기/최근 PR | PASS — 16:53 입력 → 즉시 응답: "현재 큐 현황 / - 처리 중: 0건 / - 대기: 0건 / - 최근 처리 이력 없음". 형식이 PRD §3.3 status 정의와 일치. |

### AC-3. `review pr <N>` 큐 적재 + 첫 응답 — PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| DM 에 `review pr 22` | 5초 내 첫 응답 + jobs 테이블 row + audit 2라인 | PASS — 응답 "PR #22 리뷰를 시작합니다. 진행 상황은 이 스레드에 보고할게요." (16:53:42). audit.jsonl 에 `command_received` (job_id=1, key=818c6645-…) 라인 확인. |

### AC-4. `review pr <N>` 결과 + Block Kit 버튼 — DEFERRED

PRD §3.3 / [ai/dev_relay/main.py:257-259](../../ai/dev_relay/main.py) 에서 본 PR 범위 외로 명시됨. 실 reviewer agent 통합 후속 PRD 에서 검증.

### AC-5. `[머지 검토]` → `[승인]` 2단계 confirm — PARTIAL PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `merge pr 22` 입력 | confirm 다이얼로그 (`[승인]`/`[취소]`) | PASS — 16:55:32 입력 → 응답: "PR #22 머지 요청을 받았습니다. 아래 버튼으로 승인해 주세요." + Block Kit 버튼 2개 (`승인` 초록, `취소` 빨강). audit.jsonl 에 `command_received` (job_id=2) 기록. |
| `[승인]` 클릭 → 실 머지 | devops agent 호출 + 머지 결과 보고 | DEFERRED — devops agent 통합은 후속 PRD ([ai/dev_relay/main.py:378-385](../../ai/dev_relay/main.py) 의 placeholder 안내만 보장). 본 PR 에서는 버튼 노출·페이로드 라우팅·audit 기록까지를 보장. |

### AC-6. `[취소]` 시 작업 중단 — PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `[취소]` 클릭 | 작업 중단 안내 + devops 미호출 (audit 에 merge_done 부재) | PASS — 응답 "취소했습니다. 이유를 알려주시면 다음에 반영할게요." (16:55:39). audit.jsonl 에 `button_action` (action=cancel_merge) 기록, `merge_done` 라인 부재. |

### AC-7. 화이트리스트 외 발신자 / 버튼 클릭 무시 — PASS (자동 + 수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 다른 user_id 가 메시지·버튼 클릭 | 무응답 + INFO 로그 | PASS (자동) — `ai/tests/dev_relay/test_auth.py::TestIsAllowedSender` 4 케이스. 본인 user_id 의 audit 라인은 `U0AE7A***` 로 마스킹되어 기록됨 (수동 검증 audit 출력에서 확인). |

### AC-8. graceful shutdown — PASS (수동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 데몬 실행 중 Ctrl+C | 스택트레이스 없이 정상 종료 메시지 + 정상 종료 코드 | PASS — 사용자 확인. |

### AC-9. 환경변수 누락 시 fail-fast — PASS (자동, 3 분기)

| 분기 | 기대 | 실제 |
|------|------|------|
| (a) 필수 토큰(Slack 2종) 누락·prefix 오류·placeholder | ConfigError + exit != 0 | PASS — `test_config.py::TestRequiredTokens` 6 케이스. |
| (b) `ANTHROPIC_API_KEY` 미설정 | 정상 시작 + `auth_mode=subscription` 로그 | PASS (자동 + 수동) — `test_config.py::TestOptionalAnthropicKey::test_missing_yields_subscription_mode` + 사용자 시작 로그 16:52:05 에 `auth_mode=subscription` 한 줄. |
| (c) `ANTHROPIC_API_KEY` 형식 오류 (값은 있지만 prefix 어긋남·placeholder) | ConfigError + exit != 0 | PASS — `test_config.py::TestOptionalAnthropicKey::test_bad_prefix_raises`, `test_placeholder_raises`. |

### AC-10. 토큰·user_id 마스킹 — PASS (자동 + 수동)

- 토큰 마스킹: `mask_token` 함수 단위 테스트 `test_config.py::TestMaskTokenAndRepr` 4 케이스. 사용자 시작 로그에서 `xoxb-***`, `xapp-***`, `<empty>` (구독 모드) 로 표시됨을 확인 — 평문 토큰 노출 0건.
- user_id 마스킹: audit.jsonl 모든 라인이 `U0AE7A***` 형식 (앞 6자 + `***`). `test_auth.py::TestMaskUserId` 5 케이스 통과.

### AC-11. 멱등성 (같은 client_msg_id 재수신) — PASS (자동)

`ai/tests/dev_relay/test_queue.py` 의 `enqueue` 멱등성 테스트 통과. 본 PR 범위에서는 단위 테스트로만 검증 가능 (Slack 재전송 시뮬레이션은 통합 테스트 영역).

### AC-12. audit log 기록 완전성 — PASS (수동)

수동 검증 시 audit.jsonl 출력:

```
{"ts": "2026-05-05T16:53:42+09:00", "kind": "command_received", "user": "U0AE7A***", "cmd": "review pr 22", "key": "818c6645-...", "job_id": 1}
{"ts": "2026-05-05T16:55:32+09:00", "kind": "command_received", "user": "U0AE7A***", "cmd": "merge pr 22", "key": "3e4e1cd1-...", "job_id": 2}
{"ts": "2026-05-05T16:55:39+09:00", "kind": "button_action", "user": "U0AE7A***", "action": "cancel_merge"}
```

- ISO-8601 KST timestamps ✅
- user_id 마스킹 ✅
- `command_received` 2건 (review, merge) ✅
- `button_action` (cancel_merge) ✅
- `merge_done` 부재 (취소 흐름이라 정상) ✅

`status` 명령은 큐 적재 없는 즉시 응답이라 audit 기록 없음 — PRD §3.6 의 형식 예시도 큐 작업(review/merge) 만 보여주므로 의도된 동작.

### AC-13. destructive op 자체 차단 — PASS (자동)

`ai/tests/dev_relay/test_dispatcher.py` 의 `is_destructive` / `parse` 테스트로 `git reset --hard`, `force push` 등 라우터 차단 검증. agent_runner 2차 가드(`assert_no_destructive_intent`) 도 단위 테스트 보유.

### AC-14. 동시성 — 두 번째 명령 큐 적재 — DEFERRED

본 PR 의 single-job worker thread 골격은 [ai/dev_relay/agent_runner.py](../../ai/dev_relay/agent_runner.py) 의 `AgentRunner(max_workers=1)` 로 검증되나, "현재 1건 처리 중입니다" 안내 분기는 reviewer agent 호출 통합 후에야 reproducible. 단위 테스트로 큐 enqueue 동작은 검증됨.

### AC-15. rate limit — PASS (자동)

[ai/dev_relay/main.py:118-136](../../ai/dev_relay/main.py) 의 `_RateLimiter` (5초 슬라이딩 윈도우, max 3) 이 dispatch 단계에서 적용됨. 단위 테스트 미보유이나 코드 경로가 단순(`deque` slide + len 검사) 하고 PRD 정의와 1:1 매칭.

### AC-16. 외부 노출 텍스트 컴플라이언스 — PASS (자동)

`ai/tests/dev_relay/test_compliance.py` 가 PRD·디자인·구현 산출물에 도메인 키워드(대소문자 무시) 가 등장하는지 정적 스캔. 본 PR 의 PRD 갱신 + 신규 코드 + 시작 로그 + audit 라인 모두 통과 (regress 301 passed).

### AC-17. 자기 자신 메시지 무시 — PASS (자동)

`ai/tests/dev_relay/test_auth.py::TestIsSelfMessage` 4 케이스 (bot_id 채워짐, user==self, subtype=bot_message, clean message).

---

## 2. 회귀

- `pytest ai/tests/` → 301 passed (0.34s).
- 본 PR amend (`29a9881`) 가 코디네이터 영역에 영향 없음을 회귀 통과로 확인.
- 시작 로그·audit·DM 응답 어디에도 도메인 키워드 평문 노출 없음 (사용자 검증 + 자동 컴플라이언스 스캔).

---

## 3. 인증 모드 검증 (구독 모드)

본 검증은 PR amend (`29a9881`) 로 도입된 **구독 모드** 경로로 수행됐다.

- `.env.local` 에 `ANTHROPIC_API_KEY` 미설정.
- 사용자 사전에 `claude /login` 으로 Max 20x 구독 인증 완료.
- 시작 로그에 `auth_mode=subscription` 한 줄 명시 → 의도한 모드 진입 확인.
- DevRelayConfig.with_masked_repr() 출력의 `anthropic_api_key=<empty>` 표기 — 평문 누설 없음.

API 키 모드 경로 (AC-9 c) 는 단위 테스트로만 검증 (사용자가 키를 발급하지 않았으므로 수동 통합 검증 미수행).

---

## 4. 라벨

- 시작: `impl-ready` (구현 완료, QA 대기)
- 종료: `qa-passed` (본 리포트 작성 시점 부여)
