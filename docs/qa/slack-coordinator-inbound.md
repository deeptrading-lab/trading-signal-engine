# QA 리포트: slack-coordinator-inbound

> 작성자: QA 에이전트
> 작성일: 2026-05-01
> 대상 PRD: `docs/prd/slack-coordinator-inbound.md`
> 대상 PR: https://github.com/deeptrading-lab/trading-signal-engine/pull/3
> 대상 브랜치: `feature/slack-coordinator-inbound`
> 대상 커밋: `4916358`
> 실행 환경: Python 3.11.15 / pytest 9.0.3 / Darwin 25.4.0

---

## 0. 실행 요약

- **자동화 테스트**: `ai/tests/test_coordinator_*.py` 53개 모두 PASSED (`pytest`, 0.21s).
  전체 `ai/tests/` 회귀 122개도 PASSED (0.19s).
- **자동 검증 가능 AC** (AC-7 / AC-8 / AC-9): 모두 PASS.
- **사용자 수동 검증 필요 AC** (AC-1 ~ AC-6): Slack Workspace·실 Socket Mode 연결 의존이라 본 환경에서 실행 불가 → MANUAL 분류, 체크리스트 §3 제공.
- **부수 점검** (`.gitignore` `.env`, 토큰 하드코딩 grep, 외부 노출 텍스트 키워드 grep): 모두 PASS.
- **종합 판정**: 자동 검증 범위 내 실패 0건. 라벨은 `qa-auto-passed` 권장 (수동 검증은 PM/사용자 영역).

---

## 1. 수용 기준별 테스트 매핑·결과

| AC | 분류 | 검증 수단 | 결과 |
|----|------|-----------|------|
| AC-1. 시작 시 연결 로그 | MANUAL | 사용자 수동 (실 Socket Mode 연결 필요) | MANUAL |
| AC-2. `ping` → `pong` | MANUAL+AUTO | 슬랙 실 DM 수동 + `route_command` 단위 | PASS (auto) / MANUAL (e2e) |
| AC-3. `status` 응답 4종 정보 | MANUAL+AUTO | 슬랙 실 DM 수동 + `render_status` 단위 | PASS (auto) / MANUAL (e2e) |
| AC-4. 알 수 없는 명령·정규화 | MANUAL+AUTO | 슬랙 실 DM 수동 + `normalize_command`/`route_command` 단위 | PASS (auto) / MANUAL (e2e) |
| AC-5. 화이트리스트 외 발신자 | MANUAL+AUTO | `is_allowed_sender` 단위 + 로그 시뮬레이션 + 실 사용자 수동 | PASS (auto) / MANUAL (e2e) |
| AC-6. graceful shutdown | MANUAL | `Ctrl+C` 시그널 핸들러 (실 프로세스 필요) | MANUAL |
| **AC-7. 환경변수 누락 fail-fast** | **AUTO** | `load_config` 단위 + `run()` 직접 호출 4 케이스 | **PASS** |
| **AC-8. 외부 노출 텍스트 키워드 금지** | **AUTO** | `assert_no_forbidden_keywords` 단위 + 모든 응답·로그 텍스트 grep | **PASS** |
| **AC-9. 자기 자신 메시지 무시** | **AUTO** | `is_self_message` 단위 + 4 시나리오 직접 호출 | **PASS** |

---

## 2. 자동 검증 결과 (AC-7 / AC-8 / AC-9 + 부수 점검)

### 2.1 단위 테스트 실행

```
$ python -m pytest ai/tests/test_coordinator_auth.py \
    ai/tests/test_coordinator_config.py \
    ai/tests/test_coordinator_handlers.py -v
...
ai/tests/test_coordinator_auth.py::TestIsAllowedSender::test_allowed_user_returns_true PASSED
... (53 lines)
============================== 53 passed in 0.21s ==============================
```

전체 `ai/tests/` 회귀:

```
$ python -m pytest ai/tests/ -v
============================= 122 passed in 0.19s ==============================
```

**결과: 53/53 (코디네이터) + 회귀 영향 0 — PASS.**

### 2.2 AC-7: 환경변수 누락·prefix 오류 fail-fast (PASS)

단위 테스트(`TestLoadConfig`):
- `test_missing_bot_token_raises` — PASSED
- `test_missing_app_token_raises` — PASSED
- `test_empty_bot_token_raises` — PASSED
- `test_wrong_bot_token_prefix_raises` — PASSED
- `test_wrong_app_token_prefix_raises` — PASSED
- `test_error_message_does_not_contain_token_value` — PASSED (토큰 값 노출 없음)
- `test_masked_repr_does_not_leak_token` — PASSED (`xoxb-***`/`xapp-***`만 노출)

엔트리포인트 통합 호출 (`run()` 직접 호출, 4 케이스):

```
CASE [only bot, missing app] exit=2
  -> [코디네이터] 시작 실패: 환경변수 SLACK_APP_TOKEN 이 설정되지 않았습니다.
CASE [only app, missing bot] exit=2
  -> [코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 이 설정되지 않았습니다.
CASE [wrong bot prefix] exit=2
  -> [코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 의 prefix 가 올바르지 않습니다 (기대: 'xoxb-').
CASE [wrong app prefix] exit=2
  -> [코디네이터] 시작 실패: 환경변수 SLACK_APP_TOKEN 의 prefix 가 올바르지 않습니다 (기대: 'xapp-').
```

- 한 줄 메시지로 어떤 변수·왜 실패했는지 명시됨.
- 비정상 종료 코드 `2` (PRD `exit code != 0` 충족).
- 토큰 값 노출 없음 (단위 테스트 `test_error_message_does_not_contain_token_value` 가 강제 검증).
- 판정: **PASS**.

### 2.3 AC-8: 외부 노출 텍스트 네이밍 컴플라이언스 (PASS)

단위 테스트 `assert_no_forbidden_keywords` 로 다음 출력 모두 검사:
- `render_ping()` → `pong`
- `render_status()`(주입된 fixture 값 + 실제 값 모두)
- `render_fallback()`
- `route_command()` 7가지 입력 (`ping`/`status`/`asdf`/`help`/`  PING  `/`""`/`None`)

추가 grep (`ai/coordinator/main.py` 의 `logger.*`/`print` 문자열 8개):

```
forbidden=None  text='자기 식별자 조회 실패: %s'
forbidden=None  text='허용되지 않은 발신자 메시지를 무시했습니다 (sender=%s, type=%s)'
forbidden=None  text='종료 시그널 수신(%s) — 코디네이터를 정리 중입니다.'
forbidden=None  text='코디네이터를 시작합니다. %s'
forbidden=None  text='Socket Mode 연결을 시도합니다.'
forbidden=None  text='키보드 인터럽트로 종료합니다.'
forbidden=None  text='예상치 못한 종료: %s'
forbidden=None  text='코디네이터를 정리했습니다.'
```

- 8개 모두 금지어(`signal`/`trade`/`trading`/`desk`/`quant`/`finance`/`market`/`ticker`/`pnl`) 미포함.
- 봇 자기 지칭은 `코디네이터` 중립어 사용 (사용자 메모리 §봇 네이밍 제약과 일치).
- 참고: `ai/coordinator/main.py` 의 `import signal` / `signal.signal(...)` / `_install_signal_handlers` 는 **Python 표준 라이브러리 식별자** 이며 사용자 노출 문자열이 아니다 (PRD AC-8: 코드 내부 식별자 검사 대상 아님).
- `ai/coordinator/handlers.py:5-6` 의 docstring 안에 등장하는 `signal/trade/desk/quant/finance/market/ticker/pnl` 은 **금지 키워드를 나열한 정책 주석**이며 사용자 응답 경로에 흐르지 않는다.
- 판정: **PASS**.

### 2.4 AC-9: 자기 자신 메시지 무시 (PASS)

단위 테스트(`TestIsSelfMessage`):
- `test_event_with_bot_id_is_self` — PASSED
- `test_event_with_bot_message_subtype_is_self` — PASSED
- `test_event_user_matches_self_bot_user_id` — PASSED
- `test_normal_user_event_is_not_self` — PASSED
- `test_no_self_id_and_no_bot_id_is_not_self` — PASSED
- `test_non_mapping_input_is_not_self` — PASSED

직접 호출 4 시나리오:

```
event={'bot_id': 'B123', ...} self_id=None expected=True got=True -> PASS
event={'subtype': 'bot_message', ...} self_id=None expected=True got=True -> PASS
event={'user': 'U_BOT'} self_id=U_BOT expected=True got=True -> PASS
event={'user': 'U_PM','text':'ping'} self_id=U_BOT expected=False got=False -> PASS
```

- `ai/coordinator/main.py::handle_message_im` 첫 줄에서 `is_self_message` 가 True 면 `return` 하여 `say` 호출 자체가 일어나지 않는다 → 에코 루프 차단.
- 판정: **PASS**.

### 2.5 부수 점검

#### 2.5.1 `.gitignore` 에 `.env` 패턴 포함 (PASS)

```
$ grep -nE '^\\.env' .gitignore
33:.env
34:.env.*
```

`.env` 본체 + `.env.*` 변형 모두 무시. (`.env.example` 은 `!` 예외로 허용 — PRD §6.3 준수.)

#### 2.5.2 토큰 하드코딩 grep (PASS)

```
$ grep -inE "xoxb-[a-zA-Z0-9_-]+|xapp-[a-zA-Z0-9_-]+" \
    --include="*.py" --include="*.md" --include="*.txt" \
    --include="*.yml" --include="*.yaml" --include="*.json" -r ai/ docs/ .gitignore
ai/tests/test_coordinator_config.py:15:VALID_BOT = "xoxb-fake-bot-token-123"
ai/tests/test_coordinator_config.py:16:VALID_APP = "xapp-fake-app-token-456"
ai/tests/test_coordinator_config.py:52: "SLACK_BOT_TOKEN": "xapp-wrong-prefix",
ai/tests/test_coordinator_config.py:64: "SLACK_APP_TOKEN": "xoxb-wrong-prefix",
ai/tests/test_coordinator_config.py:72: secret_value = "xoxb-super-secret-token-DO-NOT-LEAK"
ai/tests/test_coordinator_config.py:108: "SLACK_BOT_TOKEN": "xoxb-very-secret-bot",
ai/tests/test_coordinator_config.py:109: "SLACK_APP_TOKEN": "xapp-very-secret-app",
docs/references/slack-mcp-setup.md:86: # xoxb-12345... 같이 앞부분만 보이면 OK
```

- 모든 매치는 **fake 테스트 픽스처** 또는 **셋업 가이드의 형식 예시**이며 실제 토큰이 아님.
- 진짜 토큰이 새거나 커밋된 흔적 없음.
- 판정: **PASS**.

#### 2.5.3 외부 노출 텍스트 키워드 grep (PASS)

`route_command` 의 7개 입력에 대한 응답 + `main.py` 의 8개 로그 문자열 = 총 15개 문자열에서 `signal/trade/trading/desk/quant/finance/market/ticker/pnl` 검색 결과 **0건**.

(상세는 §2.3 참고.)

#### 2.5.4 AC-5 INFO 로그 형식 (사전 검증)

수동 검증 환경 없이도 `is_allowed_sender` + `mask_user_id` 로그 경로를 직접 호출:

```
LOG OUTPUT:
허용되지 않은 발신자 메시지를 무시했습니다 (sender=U_OU***, type=message)

forbidden_keyword_in_log= False
contains_user_id_partial= True   (마스킹된 prefix 일부)
contains_full_user_id= False     (전체 user id 노출 없음)
```

- PRD AC-5 "INFO 로그에 발신자 user id 일부, 이벤트 타입" 충족.
- 금지 키워드 미포함.

---

## 3. 사용자 수동 검증 체크리스트 (AC-1 ~ AC-6)

> 사용자 본인(이하영, `U0AE7A54NHL`) 환경에서만 검증 가능. PRD §부록 A 절차로 데몬을 띄운 뒤 아래 체크리스트를 순서대로 진행한다.

### 사전 준비

- [ ] PRD §6.2 사전조건 완료: Socket Mode 활성화, App-Level Token 발급, Bot Token Scopes(`im:history`/`im:read`/`im:write`/`chat:write`/`app_mentions:read`), `message.im` 이벤트 구독, 봇 재설치.
- [ ] `.env` 또는 셸 rc 에 `SLACK_BOT_TOKEN=xoxb-...`, `SLACK_APP_TOKEN=xapp-...`, (선택) `SLACK_ALLOWED_USER_IDS=U0AE7A54NHL` 설정.
- [ ] `pip install -r ai/requirements.txt` 로 `slack-bolt>=1.18` 설치.

### AC-1. 시작 시 연결 로그
- [ ] `python -m ai.coordinator.main` 실행 후 5초 이내 로그에 `Socket Mode 연결을 시도합니다.` + slack-bolt 자체 연결 성공 로그(`connected` / `socket mode established` 류) 1회 이상 출력.
- [ ] 로그·표준 출력에 `xoxb-...` / `xapp-...` 토큰 값이 **노출되지 않음**. `CoordinatorConfig(bot_token=xoxb-***, app_token=xapp-***, ...)` 형식으로 마스킹.

### AC-2. `ping` → `pong`
- [ ] 본인이 `Hayoung AI Coordinator` DM에 `ping` 입력.
- [ ] 5초 이내 같은 DM에 `pong` 텍스트 회신 도착.

### AC-3. `status` 응답
- [ ] 본인 DM에 `status` 입력.
- [ ] 5초 이내 응답이 도착하며 본문에 다음 4종 모두 포함:
  - 가동시간 `Nd HH:MM:SS` 형식 (예: `0d 00:01:23`)
  - 호스트명 (로컬 머신 hostname)
  - 현재 시각 KST ISO-8601 (`2026-05-01T19:32:58+09:00` 형식, `+09:00` offset)
  - Python 버전 (`3.11.x`)
- [ ] 응답 첫 줄에 `코디네이터 상태` (트레이딩 도메인 키워드 미포함).

### AC-4. 알 수 없는 명령·정규화
- [ ] `  ping ` (공백) 입력 → `pong` 회신.
- [ ] `PING` (대문자) 입력 → `pong` 회신.
- [ ] `asdf` / `help` / `안녕` 입력 → 사용 가능한 명령 안내 응답(`ping`/`status` 두 항목 포함).

### AC-5. 화이트리스트 외 발신자
- [ ] (가능하면) 다른 동료가 같은 봇 DM에서 `ping` 전송.
  - 대안: `SLACK_ALLOWED_USER_IDS` 를 다른 임의 ID로 일시 변경 후 본인이 `ping` 전송 → 동일하게 무시되는지 확인.
- [ ] 슬랙 클라이언트 측에 응답 **도착하지 않음**.
- [ ] 데몬 로그에 `허용되지 않은 발신자 메시지를 무시했습니다 (sender=U***, type=message)` INFO 라인 1회 기록 (전체 user id 노출 없음, 금지 키워드 없음).

### AC-6. graceful shutdown
- [ ] 데몬 실행 터미널에서 `Ctrl+C` 입력.
- [ ] 로그에 `종료 시그널 수신(2) — 코디네이터를 정리 중입니다.` + `코디네이터를 정리했습니다.` 출력.
- [ ] **스택 트레이스 없이** 프로세스가 정상 종료 (exit code 0). 데몬이 hang 되지 않음.

---

## 4. 에지 케이스 (참고)

본 PRD는 단순 인바운드 응답 데몬으로 외부 거래소·뉴스 피드와 결합하지 않는다. 그래도 다음 운영 시나리오를 점검:

| 시나리오 | 기대 동작 | 검증 방법 |
|----------|-----------|-----------|
| 네트워크 단절 (Wi-Fi off) | slack-bolt SocketModeClient 가 자동 재연결 시도 (PRD §3.1 — 기본 동작에 위임) | 수동: 데몬 실행 중 Wi-Fi off → 재접속 시 정상 동작 |
| App-Level Token 만료/회수 | `not_allowed_token_type` 등 401 류 에러로 시작 시 raise → `run()` 의 최상위 트랩이 `예상치 못한 종료: <ExceptionName>` INFO 로그 후 exit 1 | 수동: 잘못된 `xapp-` 값으로 실행 시 동작 확인 |
| 동시 다중 메시지 (2개 이상 사용자가 동시에 ping) | slack-bolt 기본 worker pool 처리, 응답 누락 없음 (PRD §3.2 동시성) | MANUAL — PRD 상 추가 튜닝 없음 |
| 노트북 절전 후 복귀 | Slack Socket Mode 재전송 정책 (PRD §6.1 — 별도 보장 X). 큐잉되지 않은 이벤트는 손실 가능 | INFORMATIONAL — PRD 명시 |
| `app_mention` 이벤트 수신 | `ignore_mentions` 핸들러가 즉시 return (PRD §3.1 / §6.3) | 수동: 채널에서 봇 멘션 → 응답 없음 확인 (선택) |
| 빈 메시지 / `text` 필드 누락 | `route_command` 가 `None` 도 fallback 으로 안전 처리 (단위 테스트 `test_none_falls_back`) | AUTO — PASS |
| 매우 긴 메시지 입력 | `normalize_command` 는 `.strip().lower()` 만 → 길이 제한 없음. 응답은 명령 미일치 시 fallback | INFORMATIONAL — DoS 가능성은 화이트리스트로 차단 (1인 사용 가정) |

---

## 5. 종합 판정 및 권고사항

### 판정

| 항목 | 결과 |
|------|------|
| 자동 검증 (AC-7 / AC-8 / AC-9 + 부수 점검) | **PASS** (실패 0건) |
| 단위 테스트 53/53 + 회귀 122/122 | **PASS** |
| 사용자 수동 검증 (AC-1 ~ AC-6) | **MANUAL — 사용자 환경에서 §3 체크리스트 진행 필요** |

### 권고

1. **PR #3 라벨 갱신**: `qa-auto-passed` 적용. (수동 검증 완료 후 사용자 또는 PM 판단으로 `qa-passed` 로 승격.)
2. PRD 부록 A.1 절차대로 본인 환경에서 §3 체크리스트 6개 항목을 완료한 뒤 머지/배포 흐름으로 진행.
3. 향후 PRD에서 `app_mention` 응답이 도입되면 **AC-8 외부 노출 키워드 검사**를 해당 응답 텍스트에도 적용하도록 단위 테스트 확장 필요. 현재는 `ignore_mentions` 핸들러가 빈 함수라 위험 없음.
4. (선택) `_resolve_self_user_id` 의 광범위 `except Exception` 은 단위 테스트 미커버 영역. 실 운영 중 `auth.test` 실패 시에도 데몬은 계속 동작하지만 자기 메시지 무시는 `bot_id`·`subtype` 두 경로로만 이루어지므로 기능 손실은 없음 — 다음 PRD에서 보강 가능.

---

## 부록. 실행한 명령 모음

```
git checkout feature/slack-coordinator-inbound
python -m pytest ai/tests/test_coordinator_auth.py ai/tests/test_coordinator_config.py ai/tests/test_coordinator_handlers.py -v
python -m pytest ai/tests/ -v
grep -inE "xoxb-[a-zA-Z0-9_-]+|xapp-[a-zA-Z0-9_-]+" --include="*.py" --include="*.md" --include="*.txt" -r ai/ docs/ .gitignore
grep -inE "(signal|trade|trading|desk|quant|finance|market|ticker|pnl)" --include="*.py" -r ai/coordinator/
grep -nE "^\.env" .gitignore
python -c "from ai.coordinator import main; ...  # AC-7 4 케이스 직접 호출"
python -c "from ai.coordinator.handlers import ...  # AC-8 grep"
python -c "from ai.coordinator.auth import ...     # AC-9 4 시나리오"
```
