# QA Report: coordinator-dotenv-autoload

> 작성자: QA 에이전트
> 작성일: 2026-05-01
> PRD: [`docs/prd/coordinator-dotenv-autoload.md`](../prd/coordinator-dotenv-autoload.md)
> PR: [#13](https://github.com/deeptrading-lab/trading-signal-engine/pull/13)
> 브랜치: `feature/coordinator-dotenv-autoload`
> 커밋: `1581a39`
> 관련 이슈: #9 (라벨: `enhancement`, `priority:P1`)

---

## 1. 판정 요약

- **자동 검증 결과**: PASS — 자동 검증 가능한 모든 항목 통과 (실패 0건).
- **수동 검증**: 사용자 몫. 본 리포트 §6 체크리스트 참조.
- **권장 라벨 변경**: `impl-ready` 제거 → `qa-auto-passed` 부여.
  - 사용자 수동 체크리스트 통과 확인 후 `qa-passed`로 승격 제안(머지 권한자 재량).
  - 어느 한 항목이라도 실패 시 `qa-failed`로 갱신 + PR 코멘트로 개발자에게 회송.

---

## 2. 변경 파일 요약 (PR diff)

```
ai/coordinator/main.py                         |  22 +++  (← _autoload_dotenv 추가, run() 첫 실행문에 호출)
ai/requirements.txt                            |   4 +    (← python-dotenv>=1.0)
ai/tests/test_coordinator_main_dotenv.py       | 182 +++  (← 신규 단위 테스트 7개)
docs/prd/coordinator-dotenv-autoload.md        | 147 +++  (← PRD 추적)
docs/references/slack-coordinator-bot-setup.md |  11 +-   (← §3-3 갱신 + 트러블슈팅 표 갱신 + §7 향후 확장 갱신)
```

- **`ai/coordinator/config.py`**: 변경 없음 (관심사 분리 유지 — PRD §"핵심 결정사항" 1번 준수).

---

## 3. 자동 검증 결과 (AUTO)

### 3-1. 단위 테스트 — 신규 추가분

```
$ python -m pytest ai/tests/test_coordinator_main_dotenv.py -v
============================== 7 passed in 0.17s ==============================

TestDotenvAutoload::test_loads_env_from_cwd                                PASSED
TestDotenvAutoload::test_loads_env_from_subdirectory                       PASSED
TestShellOverridesDotenv::test_shell_value_wins_over_dotenv                PASSED
TestShellOverridesDotenv::test_partial_shell_export_merges_with_dotenv     PASSED
TestDotenvAbsentFailsFast::test_autoload_is_silent_when_no_dotenv          PASSED
TestDotenvAbsentFailsFast::test_run_returns_nonzero_when_dotenv_absent_and_shell_empty  PASSED
TestDotenvAbsentFailsFast::test_load_config_raises_when_environment_empty  PASSED
```

### 3-2. AC별 PASS/FAIL/MANUAL 판정

| AC ID | 분류 | 판정 | 근거 |
|---|---|---|---|
| **AC-A1** | 자동 | **PASS** | `test_loads_env_from_cwd` — `.env` 만 있고 셸 환경변수 없을 때 `_autoload_dotenv()` 후 `os.environ` 적재 + `load_config()` 정상 동작 |
| **AC-A2** | 자동 | **PASS** | `test_autoload_is_silent_when_no_dotenv` — 빈 디렉토리에서 호출해도 예외 미발생, 환경변수도 새로 만들지 않음 |
| **AC-O1** | 자동 | **PASS** | `test_shell_value_wins_over_dotenv` — `monkeypatch.setenv` 로 셸 값 주입 후 `.env` 와 다른 값 검증 → 셸 값 유지 |
| **AC-O2** | 자동 | **PASS** | `test_loads_env_from_cwd`(reaffirm) + `test_partial_shell_export_merges_with_dotenv` (셸 일부만 export 시 나머지는 `.env` 적용) |
| **AC-F1** | 자동 | **PASS** | `test_run_returns_nonzero_when_dotenv_absent_and_shell_empty` — `run()` 호출 시 `exit_code != 0`, stderr 에 `[코디네이터] 시작 실패` + `SLACK_BOT_TOKEN` 포함 |
| **AC-F2** | 자동 | **PASS** | 동일 테스트의 `assert "Traceback" not in captured.err` — 트레이싱백 미노출 검증. fail-fast 한 줄 포맷 유지(`config.py` 변경 없음) |
| **AC-S1** | 자동(회귀) | **PASS** | `config.py` 미변경 + `test_coordinator_config.py::test_masked_repr_does_not_leak_token` 통과(전체 회귀 145 passed). `_mask()`/`with_masked_repr()` 무손상 |
| **AC-S2** | 자동(회귀) | **PASS** | `_autoload_dotenv()` 는 `find_dotenv()` 결과만 사용하고 stdout/stderr 출력 없음. 라이브러리 기본 동작은 silent |
| **AC-R1** | 자동 | **PASS** | `python -m pytest ai/tests/ -q` → **145 passed** (기존 138 + 신규 7) |
| **AC-R2** | 자동 | **PASS** | 신규 dotenv 테스트 **7개** (요구 최소 3개 초과). AC-A1/A2/O1/O2/F1/F2 모두 커버 |
| **AC-D1** | 자동(diff) | **PASS** | `slack-coordinator-bot-setup.md` §3-3 — 제목 "환경변수 로딩 + 데몬 실행" → "데몬 실행", `set -a && source .env && set +a` 라인 제거, "**자동 로딩**되므로 별도의 `source` 단계가 필요 없습니다" 명시 |
| **AC-D2** | 자동(diff) | **PASS** | 같은 §3-3 인용 블록 — "**셸 export 우선순위**: 셸에 이미 동일 이름의 환경변수가 export 되어 있으면 그 값이 우선 ... 컨테이너/CI 같은 운영 환경에서도 셸 환경변수 주입이 그대로 동작" 명시 |
| **AC-D3** | 자동(grep) | **PASS** | `git diff main...pr-13 -- docs/...slack-coordinator-bot-setup.md` 의 추가 라인에서 `signal`/`trade`/`desk`/`order`/`position`/`portfolio` 키워드 grep 결과 0건. PR 전체 변경 파일 통합 grep 도 0건 |
| **AC-Dep1** | 자동(파일 확인) | **PASS** | `ai/requirements.txt` 14행: `python-dotenv>=1.0` (PRD §3 의존성 §6 가정 준수) |
| **AC-Dep2** | 자동(설치 확인) | **PASS** | `pip show python-dotenv` → `Version: 1.2.2` (1.x 메이저 안). PR 본문에도 설치 성공 기재 |

### 3-3. 추가 점검 (사용자 지시 사항)

| 점검 항목 | 결과 |
|---|---|
| `_autoload_dotenv()` 호출 위치가 `run()` 진입 첫 실행문인지 | **OK** — `main.py:162` `_autoload_dotenv()` 가 `run()` 본문 첫 statement(docstring 직후 첫 실행문). `try: load_config()` 보다 먼저 호출됨 |
| `load_dotenv(override=False)` 명시되어 있는지 (override=True 금지) | **OK** — `main.py:157` `load_dotenv(dotenv_path, override=False)` |
| `find_dotenv(usecwd=True)` 사용해 cwd 부터 상위 탐색 | **OK** — `main.py:155` `find_dotenv(usecwd=True)`. `test_loads_env_from_subdirectory` 로 상위 탐색 동작 검증 |
| `config.py`는 변경 없는지 (관심사 분리 유지) | **OK** — `git diff main...pr-13 --name-only` 에 `ai/coordinator/config.py` 미포함 |
| 가이드 §3-3 에서 `set -a && source .env && set +a` 제거됐는지 | **OK** — `grep -n "set -a\|source .env" docs/references/slack-coordinator-bot-setup.md` 결과 NO_HITS |
| 토큰 마스킹 회귀 무결 | **OK** — `test_coordinator_config.py::test_masked_repr_does_not_leak_token` PASS. `_mask()` 무변경 |
| 트레이딩 도메인 키워드 신규 노출 0건 | **OK** — PR diff 추가 라인 통합 grep 결과 NO_HITS |

---

## 4. 회귀 / 외부 노출 텍스트 / 문서 변경 요약

### 회귀 (AC-R1)

```
$ python -m pytest ai/tests/ -q
.......................................................................  [ 49%]
.......................................................................  [ 99%]
.                                                                        [100%]
145 passed in 0.30s
```

- 기존 138개(또는 작성 시점 그 이상) + 신규 7개 = **145 passed**, 실패 0건.

### Grep — 트레이딩 도메인 키워드 (AC-D3)

```
$ git diff main...pr-13 -- ai/coordinator/main.py ai/tests/test_coordinator_main_dotenv.py \
    docs/references/slack-coordinator-bot-setup.md docs/prd/coordinator-dotenv-autoload.md \
    | grep "^+" | grep -v "^+++" | grep -iE "\b(signal|trade|desk|order|position|portfolio)\b"
NO_TRADING_KEYWORDS_ADDED
```

- 메모리 노트 `project_slack_bot_naming` 제약 — 회사 Slack 외부 가시성 텍스트에 트레이딩 도메인 키워드 노출 금지 — 위반 0건.

### 가이드 문서 변경 요약 (`docs/references/slack-coordinator-bot-setup.md`)

- §3-3 제목: "환경변수 로딩 + 데몬 실행" → "**데몬 실행**".
- `set -a && source .env && set +a` 라인 **제거**.
- "프로젝트 루트의 `.env` 는 데몬 시작 시 **자동 로딩**" 안내 추가.
- "셸 export 우선순위" 인용 블록 추가 — 임시 토큰 한 줄 실행 예시(`SLACK_BOT_TOKEN=... python -m ai.coordinator.main`) + 컨테이너/CI 환경 안전성.
- 트러블슈팅 표의 `SLACK_BOT_TOKEN 미설정` 행 — 원인을 "새 셸/창에서 `.env` 미로딩"에서 "프로젝트 루트가 아닌 곳에서 실행했거나 `.env` 가 없음"으로 갱신, 해결책도 자동 로딩 전제로 갱신.
- §7 향후 확장 표의 `python-dotenv 자동 로딩` 항목을 "구현됨 + PRD 링크"로 변경.

---

## 5. 에지 케이스 점검

| 시나리오 | 자동 테스트 / 수동 검증 | 판정 |
|---|---|---|
| 사용자가 프로젝트 루트가 아닌 하위 디렉토리에서 실행 | `test_loads_env_from_subdirectory` (자동) | **PASS** — `find_dotenv(usecwd=True)` 가 상위 디렉토리 탐색 |
| `.env` 가 아예 없는 디렉토리 | `test_autoload_is_silent_when_no_dotenv` (자동) | **PASS** — 예외 미발생, 다음 단계 fail-fast 위임 |
| 셸 export 와 `.env` 가 동시에 존재 | `test_shell_value_wins_over_dotenv` (자동) | **PASS** — 셸 값 우선(override=False) |
| 셸에 일부만 export, 나머지는 `.env` | `test_partial_shell_export_merges_with_dotenv` (자동) | **PASS** — 셸 export + `.env` 머지 동작 |
| 모든 환경변수 부재 | `test_run_returns_nonzero_when_dotenv_absent_and_shell_empty` (자동) | **PASS** — `run()` non-zero exit + 한 줄 메시지 + 트레이싱백 미노출 |
| 운영 환경(systemd / 컨테이너) 셸 환경변수 주입 | (수동) — PRD §6 가정 + AC-O1 자동 검증으로 안전 보장. 컨테이너 실배포는 본 PRD 비범위 | **MANUAL** — §6-3 |
| `.env` 에 다중 라인 / 변수 보간 등 비표준 포맷 | PRD §4 비범위 — `python-dotenv` 기본 파서 그대로 위임 | **OUT_OF_SCOPE** |
| Slack API 레이트리밋 / 서버 다운 / 네트워크 지연 | dotenv 자동 로딩과 무관. 본 PR 변경 영역 외(handler 영역) | **OUT_OF_SCOPE** (별 PRD: `slack-coordinator-inbound`) |

---

## 6. 사용자 수동 체크리스트 (MANUAL)

자동 검증으로 커버되지 않는, 실제 셸·환경에서 사용자가 직접 확인해야 하는 항목입니다. 모두 PASS 시 라벨을 `qa-passed`로 승격.

### 6-1. 단일 명령 기동 (AC-A1 실환경 재확인)

- [ ] 새 터미널 창을 연다 (셸에 `SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` 이 export 되어 있지 않음을 보장).
- [ ] 프로젝트 루트(`/Applications/하영/code_source/trading-signal-engine`)에 유효한 `.env` 가 존재함을 확인 (`ls .env`).
- [ ] **`source .env` 또는 `set -a && source .env && set +a` 를 실행하지 않은 채로** 다음을 실행:
  ```
  python -m ai.coordinator.main
  ```
- [ ] **기대**: `[INFO] ai.coordinator: 코디네이터를 시작합니다. CoordinatorConfig(bot_token=xoxb-***, app_token=xapp-***, ...)` 로그가 뜨고, Socket Mode 연결이 시도된다(에러 없이 기동).
- [ ] **확인**: 평문 토큰이 stdout/stderr 어디에도 출력되지 않는다(prefix + `***` 만 노출).

### 6-2. 셸 우선순위 (AC-O1 실환경 재확인)

- [ ] 같은 셸에서 임시 토큰을 export:
  ```
  export SLACK_BOT_TOKEN=xoxb-IMPORTED-FROM-SHELL
  ```
- [ ] `python -m ai.coordinator.main` 실행 시, `with_masked_repr()` 로그의 `bot_token` 마스킹은 동일하게 `xoxb-***` 로만 보이지만, 내부적으로 셸 값이 `.env` 보다 우선되는지 검증하려면 일시적으로 잘못된 prefix(예: `xoxb-INVALID`)를 export 해 동일 명령을 실행:
  ```
  export SLACK_BOT_TOKEN=invalid-prefix
  python -m ai.coordinator.main
  ```
- [ ] **기대**: `[코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 의 prefix 가 올바르지 않습니다 (기대: 'xoxb-').` (셸 값이 우선되어 prefix 검증에 걸린다 ⇒ override=False 확인).
- [ ] **정리**: `unset SLACK_BOT_TOKEN`.

### 6-3. 가이드 문서 따라하기 (신규 합류자 시뮬레이션)

- [ ] 가이드 [`docs/references/slack-coordinator-bot-setup.md`](../references/slack-coordinator-bot-setup.md) §3-3 만 보고 신규 합류자 입장에서 데몬을 띄울 수 있는지 따라가 본다.
- [ ] **기대**: §3-3 의 단일 명령(`python -m ai.coordinator.main`)만으로 데몬이 시작되며, `set -a`/`source .env` 같은 사전 단계가 더는 필요 없다.
- [ ] **기대**: §3-3 인용 블록에 "셸 export 우선" 안내가 보이고, 운영 환경 혼동 우려 없음.

### 6-4. fail-fast 실환경 재확인 (AC-F1/F2)

- [ ] 임시로 `.env` 를 다른 이름으로 옮긴다 (`mv .env .env.bak`).
- [ ] 셸에도 `SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` 이 없는 상태에서 실행:
  ```
  unset SLACK_BOT_TOKEN SLACK_APP_TOKEN
  python -m ai.coordinator.main
  echo "exit code: $?"
  ```
- [ ] **기대**: 한 줄 에러 `[코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 이 설정되지 않았습니다.` + `exit code: 2`.
- [ ] **기대**: 트레이싱백(`Traceback (most recent call last):` 등)이 출력되지 않는다.
- [ ] **정리**: `mv .env.bak .env`.

---

## 7. 실패 항목

- **없음.** 자동 검증 가능한 모든 AC 가 PASS.

---

## 8. 최종 산출물 / 라벨 권고

- **산출물 경로**: `/Applications/하영/code_source/trading-signal-engine/docs/qa/coordinator-dotenv-autoload.md`
- **자동 판정**: `qa-auto-passed` (실패 0건). 사용자 수동 체크리스트 §6 통과 시 `qa-passed`로 승격 권고.
- **권장 라벨 변경**: `impl-ready` 제거 → `qa-auto-passed` 추가.
- **PR 코멘트**: 본 리포트 §6 수동 체크리스트 링크 + "자동 PASS, 수동 검증 후 머지 권한자 재량으로 `qa-passed` 승격 요청".
