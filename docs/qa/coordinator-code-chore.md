# QA — Coordinator Code Chore (#6 + #10 + #7 묶음)

> 검증 대상 PR: [#20](https://github.com/deeptrading-lab/trading-signal-engine/pull/20) (`feature/coordinator-code-chore`)
> 커밋: `94164042c102f116ca9d83e5c7f2d3399b1863ae`
> Issues: [#6](https://github.com/deeptrading-lab/trading-signal-engine/issues/6) (P2 dispatcher 테스트), [#10](https://github.com/deeptrading-lab/trading-signal-engine/issues/10) (P2 placeholder 가드), [#7](https://github.com/deeptrading-lab/trading-signal-engine/issues/7) (P2 미사용 import)
> PRD: [`docs/prd/coordinator-code-chore.md`](../prd/coordinator-code-chore.md)
> 검증일: 2026-05-01
> 검증자: QA agent
> 검증 환경: macOS Darwin 25.4.0, Python 3.11.15, pytest 9.0.3

> 본 리포트도 도메인 키워드 평문은 직접 나열하지 않는다. 정의 SSoT 는 `ai/coordinator/_compliance.FORBIDDEN_KEYWORDS` 한 곳이며, 검사 결과 인용 시 grep 출력 영역에 한정한다.

---

## 1. 요약

P2 코드 정리 3건 묶음 PR. 변경 파일 7개 (`main.py`, `config.py`, `handlers.py`, `.env.example`, 테스트 3종) 단일 커밋. PRD AC-1 ~ AC-9 중 AC-1·2·3·4·5·6·7·8·9 모두 **자동 검증으로 PASS**. AC-3 의 데몬 non-zero exit 까지 `python -m ai.coordinator.main` 직접 실행으로 확인되어 보조 수동 시나리오는 사용자 회귀 (데몬 기동 + ping/pong) 1건만 남음.

**판정**: `qa-auto-passed` (자동 검증 9/9 PASS, 수동 1건 사용자 몫).

---

## 2. AC별 자동 검증 결과

| AC | 항목 | 검증 방법 | 결과 |
|---|---|---|---|
| AC-1 | `_dispatch_message` 모듈 함수 존재 + `handle_message_im` 호출 | 코드 리뷰 (`main.py:92-142`, `:159-166`) | **PASS** |
| AC-2 | `test_coordinator_dispatch.py` 통합 테스트 5개 통과 | pytest 단독 실행 | **PASS** (5 passed) |
| AC-3 | placeholder 토큰으로 데몬 시작 시 ConfigError + non-zero exit | `python -m ai.coordinator.main` 실행 | **PASS** (exit_code=2) |
| AC-4 | placeholder 가드 단위 테스트 추가 + 두 토큰 모두 커버 | pytest `TestPlaceholderGuard` 3종 | **PASS** (3 passed) |
| AC-5 | `.env.example:18` 코멘트 가이드 §3-2 참조 형태로 정리 | `.env.example` 직접 확인 | **PASS** |
| AC-6 | `handlers.py` 의 `import sys` 부재 + 테스트 `timedelta` 미사용 정리 | grep 0건 | **PASS** |
| AC-7 | 회귀 — `pytest ai/tests/` 174 통과 | pytest 전체 실행 | **PASS** (174 passed in 0.30s) |
| AC-8 | PRD/PR/커밋 본문 도메인 키워드 평문 0건 | `_compliance.find_forbidden_keywords` 적용 | **PASS** (저장소 URL 슬러그 노트) |
| AC-9 | PR 본문에 `Closes #6` `Closes #10` `Closes #7` 포함 | `gh pr view 20 --json body` | **PASS** (3 라인 모두 확인) |

---

### AC-1 — `_dispatch_message` 모듈 함수 존재 + wrapper 호출

**재현 절차**:
```bash
sed -n '92,142p;159,166p' ai/coordinator/main.py
```

**기대 결과**: 모듈 레벨에 `_dispatch_message(event, *, say, logger, config, self_user_id, safe_say_fn=None)` 정의가 있고, `handle_message_im` 클로저는 본문이 1회 호출(얇은 wrapper)이다.

**실제 결과** — `main.py:92-142`에 모듈 함수 정의 존재. `handle_message_im` (`:159-166`) 본문은 단일 `_dispatch_message(...)` 호출만 포함:

```python
@app.event("message")
def handle_message_im(event: dict, say: Any, logger: logging.Logger = logger) -> None:
    _dispatch_message(
        event,
        say=say,
        logger=logger,
        config=config,
        self_user_id=self_user_id,
    )
```

**판정**: PASS

---

### AC-2 — 통합 테스트 5개 통과

**재현 절차**:
```bash
python -m pytest ai/tests/test_coordinator_dispatch.py -v
```

**기대 결과**: 5건(정상 ping / 자기 메시지 / 비-IM / 비처리 subtype / 비허용 발신자) 모두 PASS.

**실제 결과**:
```
ai/tests/test_coordinator_dispatch.py::TestNormalPing::test_im_ping_invokes_safe_say_with_pong PASSED
ai/tests/test_coordinator_dispatch.py::TestSelfMessageIgnored::test_bot_id_present_skips_dispatch PASSED
ai/tests/test_coordinator_dispatch.py::TestNonImChannelIgnored::test_channel_type_channel_skips_dispatch PASSED
ai/tests/test_coordinator_dispatch.py::TestUnhandleableSubtypeIgnored::test_message_changed_skips_dispatch_and_logs_info PASSED
ai/tests/test_coordinator_dispatch.py::TestDisallowedSenderIgnored::test_unknown_user_skips_dispatch_and_logs_info PASSED
============================== 5 passed in <0.2s ==============================
```

PRD §3.1의 시나리오 5종 전부 커버. mock `say`/`safe_say_fn`/`logger` fixture 기반으로 클로저 분기를 직접 검증한다.

**판정**: PASS

---

### AC-3 — placeholder 토큰으로 데몬 시작 시 ConfigError + non-zero exit

**재현 절차**:
```bash
SLACK_BOT_TOKEN="xoxb-여기에붙여넣기" SLACK_APP_TOKEN="xapp-여기에붙여넣기" \
  python -m ai.coordinator.main
echo "exit_code=$?"
```

**기대 결과**: stderr 한 줄 안내(`[코디네이터] 시작 실패: ... placeholder ...`) 후 exit code != 0. 토큰 값은 출력되지 않는다.

**실제 결과**:
```
[코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 가 placeholder 값입니다. .env 를 실제 토큰으로 채우세요.
exit_code=2
```

`config.py:100-104`의 `_PLACEHOLDER_TOKENS` 가드가 prefix 검사를 통과한 placeholder 를 차단했고, `main.run()`의 `ConfigError` 트랩(`:226-229`)이 stderr 한 줄 + return 2 흐름을 정상 수행했다. 토큰 값은 메시지에 포함되지 않는다.

**판정**: PASS

---

### AC-4 — placeholder 가드 단위 테스트 추가 + 두 토큰 모두 커버

**재현 절차**:
```bash
python -m pytest ai/tests/test_coordinator_config.py::TestPlaceholderGuard -v
```

**기대 결과**: bot/app 두 토큰 placeholder + 정상 토큰 통과의 3건 PASS.

**실제 결과**:
```
ai/tests/test_coordinator_config.py::TestPlaceholderGuard::test_bot_token_placeholder_raises PASSED
ai/tests/test_coordinator_config.py::TestPlaceholderGuard::test_app_token_placeholder_raises PASSED
ai/tests/test_coordinator_config.py::TestPlaceholderGuard::test_real_tokens_pass_placeholder_guard PASSED
============================== 3 passed in <0.2s ==============================
```

각 테스트는 에러 메시지에 `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` 환경변수명, `placeholder` 키워드, `.env` 안내가 포함됨을 단언한다.

**판정**: PASS

---

### AC-5 — `.env.example:18` 코멘트 정리

**재현 절차**:
```bash
sed -n '17,19p' .env.example
```

**기대 결과**: 작업 노트 표현(예: "TODO 본인 user id 확인" 류) 없이 가이드 §3-2 참조 형태로 정리.

**실제 결과** — `.env.example:17-19`:
```
# 응답 허용 사용자 ID (콤마로 구분, 화이트리스트)
# 본인 user id 확인 방법은 docs/references/slack-coordinator-bot-setup.md §3-2 참조
SLACK_ALLOWED_USER_IDS=U0AE7A54NHL
```

가이드 문서 §3-2 경로가 명시 참조로 들어가 있고 작업 노트 표현은 제거됐다.

**판정**: PASS

---

### AC-6 — `import sys` 제거 + `timedelta` 제거

**재현 절차**:
```bash
grep -n "^import sys" ai/coordinator/handlers.py
grep -n "timedelta" ai/tests/test_coordinator_handlers.py
```

**기대 결과**: 두 grep 모두 0건.

**실제 결과**:
```
$ grep -n "^import sys" ai/coordinator/handlers.py
(no output)

$ grep -n "timedelta" ai/tests/test_coordinator_handlers.py
(no output)
```

`handlers.py:13`에서 `import sys` 제거 확인 (사용처 없음). 테스트의 `from datetime import datetime, timezone` 은 유지(검증 단언에서 사용)하되 미사용 `timedelta` 만 제거된 것으로 grep 0건이 일관된다. 기존 `handlers.py:15` 의 `from datetime import datetime, timezone, timedelta` 는 `KST = timezone(timedelta(hours=9), ...)` 에서 직접 사용되므로 유지(범위 외).

**판정**: PASS

---

### AC-7 — 기존 + 신규 테스트 모두 통과 (174/174)

**재현 절차**:
```bash
python -m pytest ai/tests/ -v
```

**기대 결과**: 모든 테스트 PASS (PRD 기준 174건; 기존 166 + 신규 8 = 174).

**실제 결과**:
```
============================= 174 passed in 0.30s ==============================
```

신규 추가분 = `test_coordinator_dispatch.py` 5종 + `TestPlaceholderGuard` 3종 = 8건. 합계 174 일치.

**판정**: PASS

---

### AC-8 — PRD/PR/커밋 본문 도메인 키워드 평문 0건

**재현 절차**:
```python
from ai.coordinator._compliance import find_forbidden_keywords
import subprocess

# PRD
with open('docs/prd/coordinator-code-chore.md') as f:
    print('PRD:', find_forbidden_keywords(f.read()))

# 커밋 본문
msg = subprocess.check_output(['git','log','-1','--format=%B','9416404']).decode()
print('Commit:', find_forbidden_keywords(msg))

# PR 본문
import json
body = json.loads(subprocess.check_output(['gh','pr','view','20','--json','body']))['body']
print('PR:', find_forbidden_keywords(body))
```

**기대 결과**: 세 영역 모두 0건. 단, GitHub 저장소 URL 슬러그(`deeptrading-lab/trading-signal-engine`)는 외부 식별자 평문이라 정책 외 회색지대로 둔다 (PR #14 QA 선례 일관).

**실제 결과**:
```
PRD: ['signal', 'trading']     # 두 매치 모두 같은 줄, GitHub 저장소 URL 슬러그
Commit: []
PR: []
```

PRD 매치 위치 — `docs/prd/coordinator-code-chore.md:5`:
```
- **Issues**: [#6](https://github.com/deeptrading-lab/trading-signal-engine/issues/6), [#10](...), [#7](...)
```
모든 매치가 GitHub URL 슬러그 안의 저장소 이름(`trading-signal-engine`)에서 발생. 본문 자유 텍스트에는 키워드 평문 노출 0건. PRD §1 첫 줄에 "본 PRD 본문에서 도메인 키워드 평문 노출은 회피하며 ..." 메타 표현이 명시되어 있어 정책 의도와 일치하며, PR #14 / #16 QA 에서 동일 회색지대를 PASS 처리한 선례를 따른다.

**판정**: PASS (저장소 URL 슬러그 회색지대 노트, 본문 자유 텍스트 0건).

---

### AC-9 — PR 본문에 3개 `Closes` 라인 포함

**재현 절차**:
```bash
gh pr view 20 --json body --jq '.body' | grep -E "^Closes #"
```

**기대 결과**:
```
Closes #6
Closes #10
Closes #7
```

**실제 결과**: 위와 정확히 일치. 머지 시 GitHub 가 자동으로 세 이슈를 close 처리한다.

**판정**: PASS

---

## 3. 에지 케이스 (자동 검증)

| 시나리오 | 검증 | 결과 |
|---|---|---|
| 봇 자기 메시지 (`bot_id` 채워짐) | `TestSelfMessageIgnored` | PASS — `safe_say_fn` 미호출 |
| 비-IM 채널 (`channel_type=channel`) | `TestNonImChannelIgnored` | PASS — `safe_say_fn` 미호출 |
| 비처리 subtype (`message_changed`) | `TestUnhandleableSubtypeIgnored` | PASS — INFO 로그 + `safe_say_fn` 미호출 |
| 비허용 발신자 (`UUNKNOWN1`) | `TestDisallowedSenderIgnored` | PASS — INFO 로그 + `safe_say_fn` 미호출 |
| placeholder 두 토큰 모두 fail-fast | `TestPlaceholderGuard` 2종 | PASS — `ConfigError` 메시지에 환경변수명·`placeholder`·`.env` 포함 |
| 정상 토큰은 가드 통과 (false positive 없음) | `test_real_tokens_pass_placeholder_guard` | PASS |
| 토큰 마스킹 — 에러 메시지에 토큰 값 미노출 | `test_error_message_does_not_contain_token_value` (회귀) | PASS |
| dotenv 자동 로딩 회귀 | `test_coordinator_main_dotenv.py` 7종 (회귀) | PASS |
| 컴플라이언스 모듈 회귀 | 라우팅 출력 모두 `assert_no_forbidden` 통과 | PASS |

본 PR 은 외부 I/O 변경이 없어 거래소 서버 다운·네트워크 지연·API 레이트리밋·뉴스 피드 장애 류 에지는 PRD 범위 외로 비적용.

---

## 4. 사용자 수동 체크리스트

자동 검증 9/9 통과. 사용자 환경에서 보조 회귀만 수행 권장.

- [ ] **데몬 기동 + ping/pong**:
  ```bash
  set -a && source .env && set +a
  python -m ai.coordinator.main
  ```
  Slack DM 으로 `ping` 발사 → `pong` 응답 확인. SIGINT 로 정상 종료(exit 0).

- [ ] **(선택) placeholder fail-fast 사용자 환경 재현**: `.env` 의 `SLACK_BOT_TOKEN` 을 `xoxb-여기에붙여넣기` 로 일시 변경 → 데몬 기동 시 stderr 한 줄 메시지 + non-zero exit 확인. 검증 후 원복.

- [ ] **(선택) `status` 명령 회귀**: DM 으로 `status` → 가동시간/호스트명/현재 시각(KST)/Python 버전 4종 모두 표시 확인.

---

## 5. 판정

- 자동 검증: 9/9 PASS
- 라벨 갱신: `impl-ready` → `qa-auto-passed`
- 실패 항목: 0건
- 사용자 수동: 1건(데몬 기동 + ping/pong 회귀, 보조)

---

## 6. 부록 — 실행 로그

### 6.1 회귀 테스트 (174 passed)

```
$ python -m pytest ai/tests/ -v
...
============================= 174 passed in 0.30s ==============================
```

### 6.2 dispatch + placeholder 단독 (20 passed)

```
$ python -m pytest ai/tests/test_coordinator_dispatch.py ai/tests/test_coordinator_config.py -v
...
============================== 20 passed in 0.22s ==============================
```

### 6.3 placeholder 데몬 fail-fast

```
$ SLACK_BOT_TOKEN="xoxb-여기에붙여넣기" SLACK_APP_TOKEN="xapp-여기에붙여넣기" \
    python -m ai.coordinator.main
[코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 가 placeholder 값입니다. .env 를 실제 토큰으로 채우세요.
$ echo "exit_code=$?"
exit_code=2
```

### 6.4 grep — `import sys` / `timedelta` 제거 확인

```
$ grep -n "^import sys" ai/coordinator/handlers.py
(no output — 0건)

$ grep -n "timedelta" ai/tests/test_coordinator_handlers.py
(no output — 0건)
```

### 6.5 컴플라이언스 grep — PRD/커밋/PR

```
PRD matches : ['signal', 'trading']    # 모두 docs/prd/coordinator-code-chore.md:5 의 GitHub URL 슬러그
Commit body : []
PR body     : []
```

### 6.6 PR 본문 `Closes` 라인

```
$ gh pr view 20 --json body --jq '.body' | grep -E "^Closes #"
Closes #6
Closes #10
Closes #7
```
