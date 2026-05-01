# PRD: coordinator-dotenv-autoload

> 작성자: PM 에이전트  
> 작성일: 2026-05-01  
> 대상 디렉터리: `ai/coordinator/` (Python)  
> UI: 없음  
> 관련 이슈: [#9](https://github.com/deeptrading-lab/trading-signal-engine/issues/9) (라벨: `enhancement`, `priority:P1`)  
> 출처: PR #3 가이드 §7 + 사용자 UX 피드백

---

## 1. 배경 / 문제

- 현재 `python -m ai.coordinator.main` 으로 코디네이터 데몬을 띄우려면, 사용자는 매번 셸에서 다음 한 줄을 선행 실행해야 한다.
  ```bash
  set -a && source .env && set +a
  ```
- 이는 **매일 데몬을 띄우는 사용자 워크플로**(아침 시작 시, 새 터미널 창, tmux 분할 패널 등)에서 다음과 같은 마찰을 만든다.
  - 새 셸·새 창마다 동일 명령을 반복해야 한다.
  - `source` 직후 `python ...` 까지 한 줄에 묶지 않으면 export 누락이 발생하기 쉽다.
  - 가이드(`docs/references/slack-coordinator-bot-setup.md` §3-3)도 이 두 단계를 사용자에게 외우게 만들고 있어, 신규 합류자의 첫 실행 실패율이 높다.
- 파이썬 진영의 표준 해법인 `python-dotenv` 는 진입점에서 `load_dotenv()` 한 줄로 `.env` 를 자동 탐색·로딩한다. 이미 `.env.example` 가 PR #3에서 도입되어 있으므로, **로딩 메커니즘만 코드 쪽으로 옮기면** 사용자는 한 줄(`python -m ai.coordinator.main`)로 데몬을 시작할 수 있다.
- `python-dotenv` 는 **기본적으로 셸에 export 된 값을 덮어쓰지 않는다**(`override=False`). 따라서 운영 환경(systemd / 컨테이너)에서 명시적으로 환경변수를 주입하는 워크플로와 충돌하지 않는다.

**요약 문제**: `.env` 로딩이 **셸 단계**에 있어 매일 사용자 UX가 나쁘고 실수가 잦다. 진입점 코드 한 곳에서 자동 처리해야 한다.

---

## 2. 목표

무엇이 달라지면 성공인가.

- **G1 (UX)**: 사용자가 프로젝트 루트에서 `python -m ai.coordinator.main` **단일 명령**만 실행해도 `.env` 의 토큰이 적재되어 데몬이 정상 시작된다.
- **G2 (안전)**: 셸에 이미 export 된 환경변수가 있으면 **셸 값이 우선**된다(운영 환경에서 의도치 않은 오버라이드 금지).
- **G3 (회귀 무결)**: `.env` 와 셸 환경변수가 모두 부재하면 기존 `ConfigError` fail-fast 동작이 그대로 유지된다(조용한 실패 금지).
- **G4 (문서 일치)**: 가이드 문서가 새 사용법을 정확히 반영하고, 외부 노출 텍스트 제약(트레이딩 도메인 키워드 금지)을 위반하지 않는다.

---

## 3. 범위 (In scope)

이번 PRD에서 반드시 포함한다.

1. **의존성 추가**
   - `ai/requirements.txt` 에 `python-dotenv >= 1.0` (정확한 마이너 버전 핀은 구현자 재량, 단 `>= 1.0` 메이저).
   - 현재 사용 중인 `pip-tools`/락 파일이 있다면 동일하게 갱신.

2. **자동 로딩 진입점**
   - `ai/coordinator/main.py` 의 진입점, 또는 `ai/coordinator/config.py` 의 모듈 로딩 시점 중 **단 한 곳**에서 `load_dotenv()` 를 호출한다.
   - 구현 결정사항(둘 중 어느 곳을 선택했는지·이유)은 Backend Dev 가 PR 본문에 한 줄로 기록한다.
   - `.env` 파일은 **프로젝트 루트** 에서 자동 탐색한다(`python-dotenv` 의 `find_dotenv()` 기본 동작 또는 명시적 경로 계산 모두 허용).
   - `load_dotenv(override=False)` 또는 동등한 명시적 인자로 **셸 환경변수 우선** 을 보장한다.

3. **가이드 문서 갱신**
   - `docs/references/slack-coordinator-bot-setup.md` §3-3 (또는 해당 절):
     - `set -a && source .env && set +a` 단계를 **제거** 하거나, "자동 로딩되므로 별도 export 불필요" 안내로 대체한다.
     - `.env` 파일이 프로젝트 루트에 존재하면 자동 인식됨을 명시.
     - 운영 환경에서 셸 export 가 우선됨을 한 줄로 명시(혼동 방지).
   - 도메인 키워드 노출 금지 원칙은 그대로 유지 — 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조.

4. **테스트 (pytest, 단위)**
   - `.env` 가 있고 셸 환경변수가 없을 때 자동 로딩되는지 검증 (tempfile 로 가짜 `.env` + 모킹된 cwd / `find_dotenv` 경로).
   - 셸 환경변수가 export 되어 있고 `.env` 에 다른 값이 있을 때, **셸 값이 우선** 됨을 검증 (monkeypatch 로 `os.environ` 주입).
   - `.env` 부재 + 셸 환경변수 부재 시 기존 `ConfigError` fail-fast 가 그대로 작동함을 검증.
   - 외부 API 호출(Slack 등)은 mock 으로 차단.

---

## 4. 비범위 (Out of scope)

이번 PRD에서 **하지 않는다**.

- **`.env` 파일 위치 커스터마이징**: `--env-file` 같은 CLI 플래그, `DOTENV_PATH` 같은 별도 환경변수로 경로 지정하는 기능은 본 PRD 범위 밖. 프로젝트 루트 1곳만 본다.
- **다중 환경 파일**: `.env.local`, `.env.production`, `.env.test` 같은 머지·우선순위 정책은 다루지 않는다.
- **`ai/coordinator/` 외 디렉터리**: `backend/`(Kotlin), `ai/` 의 다른 진입점에서의 dotenv 도입은 본 PRD 범위 밖. 코디네이터 데몬에 한정.
- **시크릿 매니저 연동**: AWS Secrets Manager / Vault 등의 외부 소스에서 시크릿을 끌어오는 기능은 후속 과제.
- **`.env` 포맷 확장**: 다중 라인 값, 변수 보간(`${VAR}`) 등의 고급 기능은 `python-dotenv` 기본값을 그대로 따른다(별도 설계 없음).
- **로깅 변경**: dotenv 로딩 자체에 대한 별도 INFO/DEBUG 로그 포맷 정의는 하지 않는다(라이브러리 기본 동작 그대로).

---

## 5. 수용 기준 (Acceptance criteria)

QA 가 그대로 테스트로 변환할 수 있도록 검증 가능한 문장으로 기술한다.

### 자동 로딩 (AC-A)
- **AC-A1**: 프로젝트 루트에 `SLACK_BOT_TOKEN=xoxb-FROM-DOTENV` 등을 담은 `.env` 가 존재하고, 셸에 해당 환경변수가 export 되어 있지 **않을 때**, `python -m ai.coordinator.main` 단일 명령만 실행하면 코디네이터가 토큰을 정상 적재해 데몬을 시작한다(에러 없이 기동, 또는 mock 환경에서 시작 직전까지 진행).
- **AC-A2**: `.env` 가 없는 디렉터리에서 시작해도, 라이브러리 호출 자체는 예외를 던지지 않는다(다음 단계의 `ConfigError` 가 자연스럽게 작동해야 한다).

### 우선순위 (AC-O)
- **AC-O1**: 셸에 `SLACK_BOT_TOKEN=xoxb-FROM-SHELL` 가 export 되어 있고, `.env` 에는 `SLACK_BOT_TOKEN=xoxb-FROM-DOTENV` 가 들어 있을 때, **실제 사용되는 값은 `xoxb-FROM-SHELL`** 이다(즉, dotenv 가 셸 값을 덮어쓰지 않는다).
- **AC-O2**: 셸에 환경변수가 없고 `.env` 에만 값이 있을 때는 `.env` 값이 적용된다(AC-A1 의 reaffirm).

### Fail-fast 회귀 (AC-F)
- **AC-F1**: `.env` 부재 + 셸 환경변수 부재 + 필수 토큰 누락 상태로 `python -m ai.coordinator.main` 을 실행하면, **기존과 동일한 `ConfigError`** 가 발생하고, 프로세스는 **non-zero exit code** 로 종료한다.
- **AC-F2**: 위 실패 메시지는 한 줄(또는 기존 가이드와 동일한 길이)이며, 트레이싱백이 길게 노출되지 않는다(기존 fail-fast 포맷 유지).

### 보안 (AC-S)
- **AC-S1**: 토큰이 자동 로딩되더라도, 로그·에러 메시지 어디에도 평문 토큰이 출력되지 않는다(기존 마스킹 동작 그대로).
- **AC-S2**: `.env` 의 키 이름·값 어느 쪽도 stdout/stderr 에 그대로 dump 되지 않는다.

### 회귀 (AC-R)
- **AC-R1**: 기존 단위 테스트 138 개 + 통합 회귀 모두 통과한다(현재 테스트 카운트는 작성 시점 기준이며, 구현 시점에 늘었다면 그 수치 기준으로 전부 통과).
- **AC-R2**: 새로 추가된 dotenv 관련 단위 테스트가 최소 3 개(AC-A1, AC-O1, AC-F1) 이상 추가되어 통과한다.

### 문서 (AC-D)
- **AC-D1**: `docs/references/slack-coordinator-bot-setup.md` §3-3 가 새 사용법(자동 로딩, 한 줄 실행)을 반영한다.
- **AC-D2**: 같은 문서에 "셸 export 가 우선됨" 한 줄이 명시된다(운영 혼동 방지).
- **AC-D3**: 위 문서 변경분에 도메인 키워드가 새로 추가되지 않는다 — 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조.

### 의존성 (AC-Dep)
- **AC-Dep1**: `ai/requirements.txt` 에 `python-dotenv >= 1.0` 이 명시되어 있다(버전 핀 형식은 기존 파일의 컨벤션 따름).
- **AC-Dep2**: `pip install -r ai/requirements.txt` 가 추가 옵션 없이 성공한다.

---

## 6. 가정 · 제약

- **런타임**: Python 3.11+.
- **라이브러리**: `python-dotenv >= 1.0`. 1.x 메이저 안에서는 `load_dotenv` / `find_dotenv` API가 안정적이라고 가정.
- **`.env` 형식**: 표준 `KEY=VALUE` 라인. 따옴표·주석 등은 `python-dotenv` 기본 파서 규칙을 그대로 따른다. PR #3 의 `.env.example` 와 호환된다.
- **탐색 경로**: 프로젝트 루트 1곳. 사용자는 `python -m ai.coordinator.main` 을 **프로젝트 루트에서** 실행한다고 가정한다(다른 경로에서의 실행은 본 PRD 범위 밖이며, `find_dotenv` 의 상위 디렉터리 탐색 동작에 위임).
- **운영 환경**: 컨테이너/CI 등에서는 셸 환경변수가 항상 우선이라는 정책이 유지된다(`override=False`).
- **외부 노출 텍스트 제약**: 응답·로그·문서·커밋·PR 본문에서 트레이딩 도메인 키워드를 노출하지 않는다(회사 Slack 가시성 제약, 메모리 노트 `project_slack_bot_naming` 참조).
- **일정**: 단일 PR로 완료 가능한 소규모 변경(코드 1~2 파일 + 문서 1 파일 + 테스트 1 파일).

---

## 7. 참고

- GitHub Issue #9: `https://github.com/deeptrading-lab/trading-signal-engine/issues/9`
- 출처: PR #3 가이드 §7 + 사용자 UX 피드백
- `docs/references/slack-coordinator-bot-setup.md` §3-3 — 갱신 대상 문서
- `python-dotenv` 공식 문서: `load_dotenv`, `find_dotenv`, `override` 옵션
- `AGENTS.md` §"PRD (PM 산출물)" — 본 PRD 양식 기준
- 메모리 노트: `project_slack_bot_naming` (Slack 봇 표시명/외부 텍스트 제약)

---

**UI 포함 여부: 없음**  
**대상 에이전트: Backend Dev (Python, `ai/coordinator/`) → QA → Code Reviewer → DevOps**

### 보고 (PR/QA 작성 시 필수 기재)
- 산출물 경로: 변경된 코드 파일·테스트 파일·문서 파일 경로 명시.
- 핵심 결정사항:
  1. `load_dotenv()` 호출 위치 — `config.py` 모듈 로드 시점 vs `main.py` 진입점 — 어디로 결정했고 그 이유.
  2. `.env` 탐색 경로 정책 — `find_dotenv()` 기본 동작 사용 여부, 또는 명시적 경로 계산 사용 여부와 이유.
