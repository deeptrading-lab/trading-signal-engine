# HANDOFF — 작업 인수인계 로그

> 새 작업을 시작할 때 **이 파일의 최근 5개 항목 + [SESSION_NOTES.md](SESSION_NOTES.md) 최신 1~2개** 를 먼저 읽고 컨텍스트를 잡는다.
> 본인이 다시 돌아왔을 때도 동일하게 확인한다 (어디까지 했는지 잊었을 때).
>
> - **자동 append (QA 통과 시점)**: PR에 `qa-passed` 라벨이 붙으면 [.github/workflows/handoff-append.yml](.github/workflows/handoff-append.yml) 가 **그 PR의 feature 브랜치 자체에** HANDOFF 항목을 commit한다. 별도 PR을 만들지 않고 같은 PR diff에 포함되어 Reviewer가 머지 직전 최종 점검할 때 함께 검토된다.
> - **다음 작업 후보 자동 추출**: PR 본문에 `## 다음 작업` (또는 `## Next steps`, `## Follow-up`, `## 후속`) 섹션이 있으면 그 내용이 자동으로 채워진다. **절대적 지시가 아니라 후보**이므로 다음 작업자는 참고만 하고 우선순위·문맥에 따라 자유롭게 결정한다.
> - **머지 전 최종 점검**: Reviewer 또는 작성자는 머지 직전 자동 생성된 HANDOFF 항목을 읽고 사실관계·다음 작업 후보가 적절한지 확인한다. 부적절하면 그 PR에서 직접 수정 후 머지.
> - **수동 append (선택)**: PR 단위 메모(WIP, 디버깅 발견, 후속 TODO)는 이 파일 하단에 직접 추가해도 된다.
> - **세션 단위 메모는 [SESSION_NOTES.md](SESSION_NOTES.md) 에**: 여러 PR + 사용자 합의 + follow-up 표가 섞인 세션 마무리 정리는 본 파일 자동화로 못 잡으므로 별도 파일에 자유서술로 남긴다.

## 포맷

각 항목은 다음 구조를 따른다.

```markdown
### YYYY-MM-DD — 제목 (#PR / slug)

- **slug**: `slug-name` · **author**: @handle
- **PR**: https://github.com/.../pull/N
- **요약**: 한 줄 요약
- **현재 상태**: main 머지됨 / 후속 필요 / 운영 모니터링 중
- **PR 본문**: PR description 발췌 (자동 채워짐)
- **다음 작업 후보**: PR 본문의 `## 다음 작업` 섹션 발췌 (자동 채워짐, 후보일 뿐 강제 아님)
```

**PR 작성 팁**: PR 본문에 `## 다음 작업` 섹션을 넣어두면 HANDOFF에 자동 반영된다. 예시:

```markdown
## 다음 작업
- 운영 환경에서 N일 모니터링 후 알림 임계값 재조정
- 관련 slug `xyz` 의 후속 PR 진행
```

수동 메모(PR 없는 경우)는 `### YYYY-MM-DD — [WIP] 제목` 형태로 적는다.

---

## 로그

<!-- 새 항목은 이 줄 아래에 자동/수동으로 append된다. 위쪽이 최신이 아니라 아래쪽이 최신이다. -->

### 2026-05-02 — [BACKFILL] HANDOFF 도입 시점 누적 컨텍스트

이 항목은 HANDOFF 자동화 도입 전의 누적 상태를 1회 정리한 것이다. 이후 항목은 PR 단위로 자동 생성된다.

- **author**: @HY0118

**최근 머지된 작업 (최신순)**

- #26 — 코디네이터 봇 셋업 가이드 갱신 (owner 메타변수 + 후속 PR 결과 반영)
- #23 — 디자인 가이드 산출물 DESIGN.md 포맷 표준화
- #22 — references/rules 잔존 도메인 키워드 평문 정정
- #20 — 코디네이터 코드 정리 (dispatcher 추출 + placeholder 가드 + 미사용 import 제거)
- #19 — 코디네이터 PRD/QA 잔존 도메인 키워드 평문 정정
- #18 — feature 브랜치 산출물 commit 규칙 추가
- #16 — 코디네이터 docstring·가이드 잔존 노출 정정
- #14 — 코디네이터 컴플라이언스 가드 모듈 분리 + 응답 발사 가드 도입
- #13 — 코디네이터 진입점 `.env` 자동 로딩
- #12 — Slack 메시지 subtype 가드 추가
- #11 — 이슈 우선순위 정책 (P0/P1/P2) 추가
- #3 — 코디네이터 인바운드 데몬 도입 (Socket Mode)

> **NOTE (2026-05-05)**: 아래 "진행 중 (open)" / "TODO" 두 소섹션은 backfill 시점 (2026-05-02) 의 스냅샷으로, **이미 모두 처리되어 stale 상태**다. 자연어 봇이 정보원으로 인용해 사실관계 오답을 낸 사례가 있어 strikethrough 처리했다. **현재 진행 중인 작업은 본 파일 최하단 항목 + GitHub PR/이슈 라벨로 확인** 한다.
>
> ~~PR #25 / PR #27 / Issue #24 모두 머지·종료 완료. 자세한 entry 는 본 파일 하단 자동 생성 항목 참조.~~

~~**진행 중 (open)** *(stale, 위 NOTE 참조)*~~

- ~~**PR #25** `feature/slack-dev-relay` — QA 통과 후 머지됨 (`8063b68`). 본 파일 하단 자동 entry 참조.~~
- ~~**PR #27** `feature/handoff-system` — 머지됨 (자기 자신 자가 트리거 케이스 검증 통과).~~
- ~~**Issue #24** `[slack-dev-relay]` — PR #25 머지로 close.~~

~~**TODO / 다음 작업 후보** *(stale, 위 NOTE 참조)*~~

- ~~PR #25 QA 진행 → `qa-passed` 라벨 부여 — 완료~~
- ~~PR #27 (HANDOFF 시스템) `qa-passed` → Reviewer → 머지 — 완료~~
- ~~HANDOFF 자동화 동작 확인 후 1~2주 운영 — 진행 중 (정상 동작 확인됨, PR #27/#25 entry 가 자동 추가된 것이 그 증거)~~
- ~~본 backfill 항목은 PR #27 머지 후 첫 자동 entry 가 추가되기 전까지 임시 기준점 역할 — 역할 종료~~

### 2026-05-01 — HANDOFF 인수인계 로그 + qa-passed 시점 자동 append 워크플로우 (#27)

- **slug**: `handoff-system` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/27
- **요약**: HANDOFF 인수인계 로그 + qa-passed 시점 자동 append 워크플로우
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > 두 사람이 비동기로 작업할 때 **직전에 무엇이 머지되었고 무엇이 남았는지**를 빠르게 따라잡기 위한 시스템.
  > 
  > - [docs/HANDOFF.md](docs/HANDOFF.md): 작업 시작 전 최근 5개 항목을 읽는 단일 진입점
  > - [.github/workflows/handoff-append.yml](.github/workflows/handoff-append.yml): `qa-passed` 라벨이 붙은 시점에 **해당 PR의 feature 브랜치 자체**에 HANDOFF 항목을 자동 commit
  > - [AGENTS.md](AGENTS.md): 작업 시작 전 HANDOFF 확인 + 운영 섹션 + Reviewer 게이트에 HANDOFF 점검 항목 추가
  > 
  > ## 동작 방식
  > 
  > 1. PR이 QA를 통과하여 `qa-passed` 라벨이 붙음
  > 2. 워크플로우가 그 PR의 head 브랜치를 checkout
  > 3. PR 번호·제목·작성자·slug·본문 발췌·"다음 작업 후보"를 `docs/HANDOFF.md` 에 append
  > 4. **같은 feature 브랜치에 commit + push** (별도 chore PR 만들지 않음)
  > 5. Reviewer가 코드 + HANDOFF 항목을 한 번에 최종 점검 후 머지
  > 
  > PR 본문에 `## 다음 작업` 섹션이 있으면 자동으로 추출되어 HANDOFF에 후보로 기재됩니다 (강제 아님).
  > 
  > 멱등성: 같은 PR에 라벨이 재부착되어도 `(#PR번호)` 가 이미 있으면 skip.
  > 
  > ## Test plan
  > 
  > - [ ] 이 PR을 QA 통과 처리하여 `qa-passed` 라벨을 부여 → 워크플로우가 동일 브랜치(`feature/handoff-system`)에 HANDOFF 항목을 commit하는지 확인
  > - [ ] 자동 추가된 HANDOFF 항목이 사실관계대로인지 검토
  > - [ ] 라벨을 떼었다가 재부착해도 중복 entry가 생기지 않는지 확인 (멱등성)
  > - [ ] PR 본문의 `## 다음 작업` 섹션이 HANDOFF "다음 작업 후보" 로 잘 추출되는지 확인
  > 
  > ## 다음 작업
  > 
  > - 머지 후 다음 PR부터는 본문에 `## 다음 작업` 섹션을 의식적으로 작성하여 HANDOFF 추적 품질 확인
- **다음 작업 후보** (PR 본문 기반, 절대적 지시 아님):
  - 머지 후 다음 PR부터는 본문에 `## 다음 작업` 섹션을 의식적으로 작성하여 HANDOFF 추적 품질 확인
  - 1~2주 운영 후 본문 발췌 길이(현재 30줄)가 너무 길면 축소 검토
  - main 브랜치 보호 규칙이 있다면 `github-actions[bot]` 의 feature 브랜치 push 가 막히지 않는지 첫 트리거 시 확인

### 2026-05-05 — feat(slack-dev-relay): MVP 데몬 구현 (#25)

- **slug**: `slack-dev-relay` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/25
- **요약**: feat(slack-dev-relay): MVP 데몬 구현 — Slack DM 명령으로 로컬 Claude Agent SDK 세션을 트리거하는 단일 프로세스 봇. PR amend 로 구독 모드 인증(claude CLI 승계) 추가, `.env.local` 분리.
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (사용자 PC + Slack 워크스페이스에서 수동 검증 완료, audit log/취소 흐름/구독 모드 시작 로그까지 확인)
- **PR 본문 발췌**:
  > ## 요약
  > 
  > `docs/prd/slack-dev-relay.md` 의 MVP 데몬을 구현합니다. Slack DM 명령을 받아 로컬 큐에 적재하고 Block Kit 버튼으로 2단계 승인을 받아 Claude Agent SDK 세션을 트리거하는 단일 프로세스 봇입니다.
  > 
  > Closes #24
  > 
  > ## 변경 범위
  > 
  > ### 신규 패키지: `ai/dev_relay/`
  > - `__init__.py` / `main.py` — Socket Mode 진입점, audit log, rate limit, graceful shutdown
  > - `config.py` — 환경변수 검증 (xoxb / xapp / sk-ant prefix + placeholder 차단)
  > - `auth.py` — 화이트리스트 + user_id 마스킹 (앞 6자)
  > - `queue.py` — SQLite 단일 파일 (`~/.local/state/dev_relay/queue.db`), 멱등성·동시 1건·재시작 복구
  > - `dispatcher.py` — 3개 명령 (`status` / `review pr <N>` / `merge pr <N>`) 파싱 + destructive op 1차 차단
  > - `agent_runner.py` — SDK 호출 worker thread + destructive op 2차 차단
  > - `slack_renderer.py` — Block Kit 빌더 + 발사 직전 컴플라이언스 가드 + 정적 템플릿 import 시점 검증
  > 
  > ### 신규 테스트: `ai/tests/dev_relay/`
  > - `test_dispatcher.py` — 36 케이스 (명령 파싱·정규화·destructive 검출)
  > - `test_queue.py` — 13 케이스 (멱등성·상태 전이·재시작 시뮬레이션)
  > - `test_auth.py` — 17 케이스 (화이트리스트·마스킹·액션 페이로드)
  > - `test_compliance.py` — 39 케이스 (runtime 가드·Block Kit 빌더·PRD/소스 정적 검사)
  > - `test_config.py` — 추가 (필수/선택 토큰, auth_mode, 마스킹·placeholder·prefix 검증)
  > 
  > ### 의존성
  > - `ai/requirements.txt` 에 `claude-agent-sdk>=0.1.72,<0.2` 추가
  > 
  > ### amend (구독 모드 + .env.local)
  > - `ANTHROPIC_API_KEY` 를 선택으로 강등 — 미설정 시 구독 모드 (`claude` CLI 인증 승계)
  > - 시작 로그에 `auth_mode=api_key|subscription` 1라인
  > - dotenv 로딩 `.env` → `.env.local` (override=True). 공유 저장소이므로 개인 토큰은 `.env.local` 격리
- **다음 작업 후보** (절대적 지시 아님):
  - 실 reviewer agent 통합 PR (AC-4 / AC-5 2단계 / AC-14 의 deferred 항목을 살리는 후속 PRD/PR)
  - launchd plist 자동 설치 (PRD 부록 B) 가 필요해질 시점에 별도 PRD
  - 구독 quota 사용량 모니터링 (Max 20x 한도 진단) — 일상 운영 데이터가 쌓이면 cost-aware-llm-pipeline 가드 통합 검토

### 2026-05-05 — chore: Makefile — daemon/test/install 명령 정리 (#33) / pip → python -m pip 후속 fix (#34)

- **slug**: `makefile` · **author**: @HY0118 (수동 entry — chore 라벨이라 qa-passed 자동 append 미적용)
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/33 + https://github.com/deeptrading-lab/trading-signal-engine/pull/34
- **요약**: 데몬 실행·테스트 등 평문으로 PRD 부록에만 적혀 있던 명령을 루트 `Makefile` 한 장으로 모음. 두 봇 (coordinator / dev_relay) 데몬 타겟 분리. 이후 `pip` shim 없는 venv (uv-managed 등) 회귀를 `python -m pip` 으로 일반화 fix.
- **현재 상태**: 둘 다 main 머지 완료 (`bf45789`, `84532a6`).
- **다음 작업 후보**:
  - HANDOFF.md / README.md 에 "make help 부터 보세요" 한 줄 추가 검토 (별도 docs PR)
  - 명령이 더 늘면 그때 pyproject.toml + 콘솔 entry point 마이그레이션 검토

### 2026-05-05 — [WIP] feat(dev-relay): Phase 1 자연어 분기 — A.2 수동 검증 중 (#32)

- **slug**: `dev-relay-natural-language` · **author**: @HY0118 (수동 WIP entry — qa-passed 라벨 부여 시점에 정식 자동 entry 가 위에 append 됨)
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/32 — 라벨 `impl-ready`, QA 대기 중.
- **요약**: PRD `dev-relay-natural-language` Phase 1 (read-only 자연어 에이전트 루프) 구현. SDK 0.1.73 / Haiku 분류 + Sonnet 응답 / PreToolUse hook / 30분 만료 세션 / B-2 URL placeholder escape.
- **현재 상태**:
  - 자동 테스트 484건 통과 (회귀 0건)
  - 수동 검증 진행 중: A.1 (PASS, 추정), A.2 (부분 PASS — 응답 도착·Block Kit 분할·다중 정보원 종합 OK / 단 사실관계 오류 발견 — 본 backfill stale 인용이 원인 → 본 PR 로 수정), A.3~A.8 미진행
  - 수동 검증 중 SDK 버그 1건 발견·수정: `HookJSONOutput()` 호출 → `'types.UnionType' object is not callable` 에러. fix 커밋 `c8e69ce`. PR #32 에 통합.
- **다음 작업 후보**:
  - A.3~A.8 마저 진행해 전체 부록 A QA 완료
  - QA 보고서 (`docs/qa/dev-relay-natural-language.md`) 작성 후 `qa-passed` 라벨
  - **shell metachar 정책 완화 후속 PR** (`feat/dev-relay-shell-pipe-allow`) — `| head` / `2>/dev/null` 같은 read-only 패턴 한정 허용. A.2 검증 중 LLM 이 `gh pr view ... 2>/dev/null || ...` 시도하다 차단된 사례 다수.

### 2026-05-05 — chore(dev-relay): audit.jsonl 0600 권한 + _RateLimiter 단위 테스트 (#36)

- **slug**: `slack-dev-relay-audit-perm-ratelimit-test` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/36
- **요약**: chore(dev-relay): audit.jsonl 0600 권한 + _RateLimiter 단위 테스트
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## 요약
  > 
  > 이슈 #28 follow-up 의 1번 항목 (audit 0600 + RateLimiter 테스트) 만 처리하는 mini-PR. shutdown watchdog (#28 의 다른 항목) 은 별도 PR 로 다룬다.
  > 
  > ## 변경 사항
  > 
  > 1. **`audit.jsonl` 0600 권한 적용** — `ai/dev_relay/main.py::_append_audit` 가 신규 파일 생성 시 `os.chmod(path, 0o600)` 호출. 이미 존재하는 파일은 사용자가 명시적으로 권한을 풀어둔 경우를 존중해 건드리지 않음. PRD `docs/prd/slack-dev-relay.md` §3.8 "로컬 파일 권한 — 파일 0600" 준수.
  > 2. **`_RateLimiter` 단위 테스트 추가** — `ai/tests/dev_relay/test_rate_limiter.py`. AC-15 회귀 보호 4 케이스:
  >    - 같은 user_id 5초 내 3회 통과 / 4회째 차단
  >    - 윈도우 경과 후 카운터 리셋
  >    - 다른 user_id 독립 카운터
  >    - 정확히 윈도우 경계 시각 (5.0초) 동작 명세 (`bucket[0] < cutoff` 동작 못박기)
  > 
  > `time.monotonic` 의존 회피를 위해 `now=` 인자를 주입해 결정론적 테스트.
  > 
  > ## 의도적으로 하지 않은 것
  > 
  > - `_RateLimiter` 모듈 추출 — 이슈 #28 본문의 권고이지 요구사항이 아님. blast radius 최소화를 위해 별도 PR 로 다룬다.
  > - shutdown watchdog (#28 의 별도 항목) — 다음 PR.
  > 
  > ## 수용 기준 체크리스트
  > 
  > - [x] 신규 audit.jsonl 파일이 0600 권한으로 생성된다
  > - [x] 기존 파일은 chmod 호출 없이 그대로 둔다
  > - [x] `_RateLimiter` 4 케이스 테스트 통과
  > - [x] 전체 회귀: `pytest ai/tests/ -q` 509 passed
  > - [x] 빠른 재현: `pytest ai/tests/dev_relay/test_rate_limiter.py -v`
  > 
  > ## 참고
  > 
- **다음 작업 후보**: _PR 본문에 별도 섹션 없음. 본문 참고하여 판단._

### 2026-05-05 — fix(dev-relay): AgentRunner.shutdown(timeout) watchdog 보강 (#37)

- **slug**: `slack-dev-relay-shutdown-watchdog` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/37
- **요약**: fix(dev-relay): AgentRunner.shutdown(timeout) watchdog 보강
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## 범위
  > Issue #28 항목 2 (shutdown watchdog) + PR #36 nit 이월 1건.
  > 
  > ## 배경
  > `AgentRunner.shutdown(timeout=...)` 은 timeout 인자를 받지만 `ThreadPoolExecutor.shutdown` 이 timeout 을 지원하지 않아 무시되고 있었다. 호출 측 `ai/dev_relay/main.py:809` 에서 30초 timeout 을 넘기지만 실제로는 무한 대기. PRD `docs/prd/slack-dev-relay.md` §3.7 (graceful shutdown 30초 timeout) 의 의도를 코드로 보장한다.
  > 
  > ## 변경
  > ### 1) `AgentRunner.shutdown` watchdog (`ai/dev_relay/agent_runner.py`)
  > - `wait=True` + `timeout` 지정: 별도 daemon thread (`dev-relay-agent-shutdown`) 에서 `executor.shutdown(wait=True)` 를 수행하고 `thread.join(timeout)` 로 대기. timeout 만료 시 `executor.shutdown(wait=False)` 로 신규 task 만 차단하고 WARNING 로그 (`shutdown timeout exceeded (%.1fs) — forcing`).
  > - `wait=True` + `timeout=None`: 기존 동작 (무한 대기) 유지.
  > - `wait=False`: 기존 동작 (즉시 반환) 유지.
  > - docstring 의 "호출자가 별도 watchdog thread 로 강제 종료를 구현한다" 문구 제거.
  > - 호출 측 `main.py:809` 는 손대지 않음 (회귀 보호).
  > 
  > ### 2) PR #36 nit 이월 (`ai/dev_relay/main.py::_append_audit`)
  > - docstring 한 줄: `"부모 디렉터리는 default_db_path() 호출 측에서 0700 으로 보장된다"` → `"부모 디렉터리(0700) 는 JobQueue::_ensure_dir_secure 가 보장한다."`. 코드 동작 변경 없음.
  > 
  > ## 테스트 (`ai/tests/dev_relay/test_agent_runner_shutdown.py`, 신규)
  > - 빠른 task → timeout 안 걸림, watchdog WARNING 0건.
  > - 느린 task (2s sleep) → `timeout=0.2` 만료 후 ~0.3초 이내 반환 + WARNING 1건.
  > - `timeout=None` → watchdog 미등록, 정상 종료.
  > - `wait=False` → watchdog 미등록, 즉시 반환.
  > 
  > 전체 회귀: `pytest -q` → 513 passed, 0 failures.
  > 
  > ## 수용 기준
  > - [x] `AgentRunner.shutdown(wait=True, timeout=T)` 가 T 초 안에 반환된다 (worker task 가 더 오래 걸려도).
  > - [x] timeout 만료 시 WARNING 로그 (`shutdown timeout exceeded`) 가 한 번 남는다.
  > - [x] `wait=True, timeout=None` / `wait=False` 기존 호출은 회귀 없음.
  > - [x] 호출 측 `main.py:809` 무수정.
- **다음 작업 후보**: _PR 본문에 별도 섹션 없음. 본문 참고하여 판단._

### 2026-05-05 — docs: SESSION_NOTES.md 신설 + 직전·당일 세션 backfill (#38)

- **slug**: `handoff-session-notes` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/38
- **요약**: docs: SESSION_NOTES.md 신설 + 직전·당일 세션 backfill
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > - 세션 단위 자유서술 메모 파일 [docs/SESSION_NOTES.md](docs/SESSION_NOTES.md) 신설.
  > - HANDOFF 자동화는 PR 본문 `## 다음 작업` 섹션만 추출 → **여러 PR + 사용자 합의 + follow-up 표가 섞인 세션 마무리 정리는 누락**. 직전 세션의 P1/P2/P3 follow-up 5건이 어떤 파일에도 안 남아 이번 세션 시작 시 사용자가 직접 이미지로 공유해야 했음.
  > - 직전 세션(2026-05-05) + 당일 세션(2026-05-06) backfill, HANDOFF.md 안내에 SESSION_NOTES 참조 한 줄 추가.
  > - 누락 QA 리포트 2건(PR #36/#37 머지 시점에 포함됐어야 함) 동봉.
  > 
  > ## 변경 요약
  > 
  > - `docs/SESSION_NOTES.md` 신설 — 형식 가이드, 작성 시점, 정책, 2026-05-05/06 두 항목.
  > - `docs/HANDOFF.md` 상단 안내 보강 — "세션 단위 메모는 SESSION_NOTES.md 에" 한 줄.
  > - `docs/qa/slack-dev-relay-audit-perm-ratelimit-test.md` (PR #36 누락분 동봉).
  > - `docs/qa/slack-dev-relay-shutdown-watchdog.md` (PR #37 누락분 동봉).
  > 
  > ## 설계 결정 (3개 옵션 중)
  > 
  > | 옵션 | 채택 | 이유 |
  > |---|---|---|
  > | 1. Stop hook 자동화 | X | 마찰 ↑, 사용자가 안 쓸 가능성 |
  > | 2. PR 템플릿에 `## 다음 작업` 강제 | X | 세션 단위(여러 PR 묶음)는 여전히 못 잡음 |
  > | **3. 별도 SESSION_NOTES.md** | **O** | HANDOFF 자동화 단순성 유지 + 자유서술로 사각 보완 |
  > 
  > ## Test plan
  > 
  > - [x] `docs/SESSION_NOTES.md` 형식 가이드와 두 backfill 항목이 일관 (위 과거, 아래 최신).
  > - [x] `docs/HANDOFF.md` 안내가 SESSION_NOTES 와 모순 없음 (PR 단위 vs 세션 단위 책임 분리 명확).
  > - [x] QA 리포트 2건 내용 자체는 이미 검증된 것 (PR #36/#37 QA 통과 시점에 작성).
  > - [ ] reviewer/QA 가 본 PR 자체를 검토.
  > 
  > ## 다음 작업
- **다음 작업 후보** (PR 본문 기반, 절대적 지시 아님):
  - (선택) 다음 세션 시작 시 본 PR 의 SESSION_NOTES 최신 항목을 컨텍스트로 사용. 동작이 의도대로면 정책 정착, 아니면 옵션 1/2 추가 검토.
  - `dev-relay-agent-integration` PRD 초안 [별도 PR](docs/prd/dev-relay-agent-integration.md) 로 처리 (사용자 검토 후).
  - shell metachar 정책 완화 (`feat/dev-relay-shell-pipe-allow`) — 직전 세션 P1, 추천 다음 트랙 1순위.

### 2026-05-05 — docs(qa): handoff-session-notes 리포트 backfill (#39)

- **slug**: `qa-handoff-session-notes-backfill` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/39
- **요약**: docs(qa): handoff-session-notes 리포트 backfill
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > - PR #38 머지 후 사후 작성된 QA 리포트(`docs/qa/handoff-session-notes.md`)를 단독 chore PR 로 backfill.
  > - 리포트 자체는 PR #38 QA 통과 시점에 검증된 것 (5/5 AC PASS, 회귀 513 passed). 본 PR 에서 다시 검증 불필요.
  > 
  > ## 배경
  > 
  > PR #38 자체에 QA 리포트를 동봉하지 못한 이유 — QA 에이전트가 PR #38 머지 직후 리포트를 작성했고 (자동 hook 없음), main 으로 commit 되지 않은 채 워킹 디렉토리에만 남아 있었다. 새 세션에서 untracked 상태로 발견되어 분리 PR 로 처리.
  > 
  > ## Test plan
  > 
  > - [x] 파일 내용은 PR #38 QA 통과 시점에 이미 검증됨.
  > - [ ] reviewer 가 본 PR 자체를 검토 (docs-only chore).
  > 
  > ## 다음 작업
  > 
  > - (구조 보강 후순위) QA 에이전트가 PR 머지 직후 리포트를 자동 동봉하도록 자동화 검토 — 본 PR 처럼 backfill 필요 사례가 반복되면 진행.
  > 
  > ## Refs
  > 
  > - PR #38 (SESSION_NOTES 도입, merged `3dbb3ca`)
- **다음 작업 후보** (PR 본문 기반, 절대적 지시 아님):
  - (구조 보강 후순위) QA 에이전트가 PR 머지 직후 리포트를 자동 동봉하도록 자동화 검토 — 본 PR 처럼 backfill 필요 사례가 반복되면 진행.

### 2026-05-05 — docs(handoff): SESSION_NOTES.md read 의무화 (manager·status·AGENTS) (#40)

- **slug**: `session-notes-read-mandate` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/40
- **요약**: docs(handoff): SESSION_NOTES.md read 의무화 (manager·status·AGENTS)
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > 직전 세션에서 SESSION_NOTES.md 가 도입됐지만(#38), 그 read 의무를 manager 서브에이전트·status 스킬·AGENTS.md 진입 안내 어디에도 명시 안 했다. 결과: 다음 세션 Claude 가 `/status` 호출 시 SESSION_NOTES 를 무시하고 HANDOFF/`gh`/AGENTS.md 만 참고해 **사용자 합의(\"PRD 검토 후 PR 등록\")를 무시한 권고**를 함. 본 PR 로 read 의무를 명시한다.
  > 
  > ## 변경
  > 
  > - `AGENTS.md`
  >   - 상단 진입 안내(line 6): "HANDOFF 최근 5개" → "**SESSION_NOTES 최신 1~2개 + HANDOFF 최근 5개**" 로 보강.
  >   - 문서 표(line 15-): `docs/SESSION_NOTES.md` 행 추가, 두 파일의 책임 분담 명시.
  >   - §"작업 인수인계" 섹션 보강: 두 파일이 보완 관계임 + 시작 전 읽는 순서(SESSION_NOTES → HANDOFF) + 누락 시 사례.
  > - `.claude/agents/manager.md`: "작업 시작 전 필수 read" 절 신설. 리포트 끝에 두 파일 read 사실을 1줄로 명시 강제.
  > - `.claude/commands/status.md`: manager 호출 프롬프트에 동일 의무 + 직전 세션 합의 반영 지시 추가.
  > 
  > ## Test plan
  > 
  > - [ ] 본 PR 머지 후 새 Claude 세션에서 `/status` 호출 시 manager 가 SESSION_NOTES 최신 항목을 실제로 읽고, 리포트 끝에 read 사실을 1줄로 명시하는지 확인.
  > - [ ] PRD `dev-relay-agent-integration` 가 untracked 상태로 남아 있어도 manager 가 \"의도된 보류\"(SESSION_NOTES 미결·블록 절 명시) 임을 인지해 즉시 PR 화 권고를 안 하는지 확인.
  > 
  > ## 다음 작업
  > 
  > - 다른 서브에이전트(pm/qa/reviewer/devops/backend-dev/frontend-dev/ux-designer)도 SESSION_NOTES read 가 필요한지 검토. 본 PR 은 manager 만 다룬다 — pipeline 흐름 외 직접 호출은 manager 가 진입점이므로.
  > - (운영 1~2주 후) SESSION_NOTES read 의무가 실제로 새 세션 권고 품질을 끌어올렸는지 평가. 안 됐으면 hook 자동화 검토.
  > 
  > ## Refs
  > 
  > - 누락 사례: 2026-05-06 세션 마무리 직후 새 세션 `/status` 결과.
  > - PR #38 (SESSION_NOTES.md 도입, merged \`3dbb3ca\`).
- **다음 작업 후보** (PR 본문 기반, 절대적 지시 아님):
  - 다른 서브에이전트(pm/qa/reviewer/devops/backend-dev/frontend-dev/ux-designer)도 SESSION_NOTES read 가 필요한지 검토. 본 PR 은 manager 만 다룬다 — pipeline 흐름 외 직접 호출은 manager 가 진입점이므로.
  - (운영 1~2주 후) SESSION_NOTES read 의무가 실제로 새 세션 권고 품질을 끌어올렸는지 평가. 안 됐으면 hook 자동화 검토.

### 2026-05-05 — docs(session-notes): 2026-05-06 오후 세션 정리 append (#41)

- **slug**: `session-notes-2026-05-06-late` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/41
- **요약**: docs(session-notes): 2026-05-06 오후 세션 정리 append
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > 오늘 오후 세션 마무리 정리 + SESSION_NOTES 작성 정책 갱신.
  > 
  > - SESSION_NOTES.md 에 2026-05-06 오후 항목 append (PR #39/#40 흐름 + 다음 세션 시작 포인트 7건)
  > - **정책 갱신**: SESSION_NOTES 단독 PR 금지 — HANDOFF 자동화 컨벤션과 통일해 **세션 마지막 작업 PR 의 같은 브랜치에 append** 하고 함께 머지. 본 PR 자체는 정책 도입 메타 작업 케이스.
  > - AGENTS.md §"작업 인수인계" 섹션에 동일 정책 명시.
  > 
  > ## 변경
  > 
  > - `docs/SESSION_NOTES.md` — 2026-05-06 오후 항목 append + 형식 가이드에 "별도 PR 금지" 절 추가
  > - `AGENTS.md` — §"작업 인수인계" 에 SESSION_NOTES 작성 방식 정책 추가
  > 
  > ## Test plan
  > 
  > - [x] SESSION_NOTES.md 형식 가이드와 신규 항목 일관 (위 과거 / 아래 최신)
  > - [x] AGENTS.md 정책이 SESSION_NOTES 본문 정책과 모순 없음
  > - [ ] reviewer/QA 검증
  > 
  > ## 다음 작업
  > 
  > - 내일부터는 본 정책 적용. 세션 마지막 PR 이 정해질 때까지 SESSION_NOTES 항목 작성 보류.
  > - PRD `dev-relay-agent-integration` 사용자 검토 후 별도 PR (다음 세션 첫 트랙).
  > - Issue #28 본문 strikethrough (사용자 동의 후, 외부 가시 액션).
  > - shell metachar 정책 완화 — 다음 세션 추천 1순위.
  > 
  > ## Refs
  > 
  > - 이전 세션 마무리(#38)에서 SESSION_NOTES 도입, read 의무화(#40), QA backfill(#39) 흐름.
- **다음 작업 후보** (PR 본문 기반, 절대적 지시 아님):
  - 내일부터는 본 정책 적용. 세션 마지막 PR 이 정해질 때까지 SESSION_NOTES 항목 작성 보류.
  - PRD `dev-relay-agent-integration` 사용자 검토 후 별도 PR (다음 세션 첫 트랙).
  - Issue #28 본문 strikethrough (사용자 동의 후, 외부 가시 액션).
  - shell metachar 정책 완화 — 다음 세션 추천 1순위.

### 2026-05-06 — feat(dev-relay): 에이전트 통합 — reviewer 결과·실 머지·동시성 큐 적재 (#43)

- **slug**: `dev-relay-agent-integration` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/43
- **요약**: feat(dev-relay): 에이전트 통합 — reviewer 결과·실 머지·동시성 큐 적재
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > 상위 PRD `slack-dev-relay.md` deferred 3건(AC-4 reviewer 결과 + Block Kit 버튼, AC-5 2단계 실 머지, AC-14 동시성 큐 적재) 을 reproducible 하게 통합한다. 본 PRD: docs/prd/dev-relay-agent-integration.md (#42).
  > 
  > ### 트리거 / 참고
  > - 트리거 Issue: #28
  > - 상위 PRD: docs/prd/slack-dev-relay.md
  > - 본 PRD: docs/prd/dev-relay-agent-integration.md
  > - 선행 PR: #25 (slack-dev-relay), #37 (AgentRunner shutdown)
  > 
  > ### 구현 결정 (PRD §10 표 그대로)
  > - **Worker 루프**: 데몬 시작 시 백그라운드 thread 1개 (`JobPicker`). `JobQueue.pending` 을 1초 폴링 (`DEFAULT_POLL_INTERVAL_S`). oldest-first 1건 dequeue → `pending → running` atomic 전이 (`claim_next_pending`).
  > - **reviewer 호출**: `AgentRunner.run_callable` 경유. `nl_sdk_runtime` 와 별도 진입점 (`_build_reviewer`). 결과는 `ReviewResult(summary, findings, detail)` — `[머지 검토]` `[상세 보기]` 버튼 발사 + `ReviewDetailCache(LRU)` 에 본문 저장. `[상세 보기]` 캐시 유실 시 `TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED` 안내 + audit `reviewer_detail_lookup_failed`.
  > - **머지 호출**: `_perform_merge` (merger 모듈) — `AgentRunner` 우회. `gh pr merge <N> --squash --delete-branch` 고정 (PRD §10). `validate_approval` 이 화이트리스트 user_id + action_id + payload 의 idempotency_key·job_id 일치를 통과한 경우에만 호출.
  > - **Block Kit 페이로드 v2**: `pr=<N>;key=<idempotency_key>;job=<job_id>` 신규 포맷. `[머지 검토]` `[승인]` `[취소]` `[상세 보기]` 모두 본 포맷. legacy `build_action_value`/`parse_action_value` 는 호환성 유지용으로 남김.
  > - **destructive 가드 회귀**: `is_destructive` 가 \`gh pr merge\` 를 차단하지 않음을 회귀 테스트로 명시 (`test_merger.py::TestDispatcherDoesNotBlockGhMerge`). 기존 `git reset --hard`, `force push`, `branch -d`, `clean -fd` 차단은 그대로.
  > - **실패 분류 5개** (`failures.py`): `destructive_blocked` / `sdk_timeout` / `github_unauthorized` / `github_unprocessable` / `compliance_blocked` + `unknown_error` fallback. 각 분류별 사용자 노출 메시지는 PRD §3.5 표 그대로 정적 템플릿 (`TEMPLATE_FAIL_*`).
  > - **신규 audit kind 7개**: `reviewer_started`, `reviewer_done`, `reviewer_failed`, `reviewer_detail_lookup_failed`, `merge_started`, `merge_done`, `merge_failed`. 기존 `command_received`/`job_started`/`job_done` 라이프사이클과 협업.
  > - **재시작 머지 carve-out**: `audit_recovery.find_merge_in_flight_job_ids` 가 `merge_started` 후 종결 라인 없는 job_id 를 식별. `JobQueue.recover_running_as_failed(merge_in_flight_job_ids=...)` 가 carve-out job 은 `unknown` 으로 남기고 사용자 안내 (`TEMPLATE_MERGE_CARVE_OUT_NOTICE`).
  > - **컴플라이언스**: 신규 메시지·버튼 라벨·audit kind 명·신규 PRD 본문·신규 모듈 모두 `ai/coordinator/_compliance.py` `FORBIDDEN_KEYWORDS` 통과. `test_compliance.py` 정적 검사가 본 PRD 산출물도 커버.
  > 
  > ### 신규 모듈 (재사용 인프라 재구현 금지 원칙 준수)
  > - `ai/dev_relay/worker.py` — `JobPicker`, `JobHandler` 시그니처. `AgentRunner` 그대로 사용.
  > - `ai/dev_relay/reviewer.py` — `ReviewResult`, `ReviewDetailCache`, `truncate_findings`. SDK 호출 자체는 caller-injected.
  > - `ai/dev_relay/merger.py` — `validate_approval`, `perform_merge`, `classify_merge_stderr`, `extract_sha`. 외부 프로세스 호출도 caller-injected.
  > - `ai/dev_relay/failures.py` — `FailureClassification`, `classify_exception`, `classify_github_status`, `user_message_for`.
  > - `ai/dev_relay/audit_recovery.py` — `find_merge_in_flight_job_ids`.
  > - `ai/dev_relay/queue.py` 추가: `claim_next_pending`, `mark_unknown`, `recover_running_as_failed` 시그니처 확장 (failed/unknown 분리).
  > - `ai/dev_relay/slack_renderer.py` 추가: `build_action_value_v2`/`parse_action_value_v2`/`ActionPayloadV2`, 7개 신규 정적 템플릿.
  > 
- **다음 작업 후보**: _PR 본문에 별도 섹션 없음. 본문 참고하여 판단._

### 2026-05-06 — feat(dev-relay): Bash 가드 pipe(|) 부분 허용 — segment 분리 + 재귀 검증 (#45)

- **slug**: `dev-relay-shell-pipe-allow` · **author**: @HY0118
- **PR**: https://github.com/deeptrading-lab/trading-signal-engine/pull/45
- **요약**: feat(dev-relay): Bash 가드 pipe(|) 부분 허용 — segment 분리 + 재귀 검증
- **현재 상태**: QA 통과 · 리뷰·머지 대기 (이 항목은 QA 통과 시점에 자동 기록됨)
- **PR 본문 발췌**:
  > ## Summary
  > 
  > NL 세션 read-only 가드(`ai/dev_relay/tool_policy.py`)에 **`|` (pipe) 부분 허용** 로직을 추가했습니다. 양쪽 segment 가 모두 read-only 화이트리스트에 들어맞을 때만 통과시키고, 다른 metachar 6종(`>`, `>>`, `<`, `&`, `;`, `` ` ``, `\$()`)은 거부 유지.
  > 
  > - 트리거 PRD: [docs/prd/dev-relay-shell-pipe-allow.md](docs/prd/dev-relay-shell-pipe-allow.md) (#44 머지됨)
  > - 변경 대상: `ai/dev_relay/tool_policy.py` 단일 파일 (호출 측 변경 없음)
  > - 신규 reason / audit kind / 외부 인터페이스 변경 **0건**
  > 
  > ## 수용 기준 체크리스트
  > 
  > - [x] **AC-PIPE-1** 양쪽 RO pipe 허용 (12건 parametrize, `TestBashPipeAllowed`)
  > - [x] **AC-PIPE-2** 우회 시도 13종 거부 (PRD §3.5 매트릭스, `TestBashPipeBypassDenied`)
  > - [x] **AC-PIPE-3** 기존 단일 명령 회귀 0건 (88 → 125 case 모두 pass)
  > - [x] **AC-PIPE-4** segment 수 상한 5 — 6 segment `parse_error`, 5 segment 통과
  > - [x] **AC-PIPE-5** 빈 segment / 토큰화 오류 (`||`, leading/trailing pipe, unclosed quote)
  > - [x] **AC-PIPE-6** destructive 1차 차단 우선순위 (`TestBashDestructiveDenied` 보강 2건)
  > - [x] **AC-PIPE-7** 다른 metachar 잔존 거부 (3건)
  > - [x] **AC-PIPE-8** 컴플라이언스 정적 검사 — PRD 본문 0 hit, `test_dev_relay_source_clean` 자동 커버
  > - [x] **AC-PIPE-9** NL hook 통합 회귀 (`TestNLPipeHookIntegration` 3건 — SDK PreToolUse 시나리오)
  > 
  > ## 구현 핵심
  > 
  > 1. `_evaluate_bash(command, *, depth=0)` — internal depth parameter 추가 (max 1, fail-fast)
  > 2. destructive 1차 차단 → 토큰화 → `|` 검출 시 `_evaluate_pipe_segments` 분기
  > 3. `_evaluate_pipe_segments` — 토큰 기준 분할, 빈 segment / 상한 검사, 잔존 metachar 검사, 각 segment `_evaluate_bash(depth=1)` 재귀
  > 4. 한 segment 라도 거부되면 그 segment 의 reason 그대로 전파 (audit 가독성)
  > 5. 모듈 상수 `_MAX_PIPE_SEGMENTS = 5` 노출
  > 
  > ## 우회 매트릭스 13건 통과 확인 (AC-PIPE-2)
  > 
- **다음 작업 후보**: _PR 본문에 별도 섹션 없음. 본문 참고하여 판단._
