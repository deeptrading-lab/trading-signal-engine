# HANDOFF — 작업 인수인계 로그

> 새 작업을 시작할 때 **이 파일의 최근 5개 항목**을 먼저 읽고 컨텍스트를 잡는다.
> 본인이 다시 돌아왔을 때도 동일하게 확인한다 (어디까지 했는지 잊었을 때).
>
> - **자동 append (QA 통과 시점)**: PR에 `qa-passed` 라벨이 붙으면 [.github/workflows/handoff-append.yml](.github/workflows/handoff-append.yml) 가 **그 PR의 feature 브랜치 자체에** HANDOFF 항목을 commit한다. 별도 PR을 만들지 않고 같은 PR diff에 포함되어 Reviewer가 머지 직전 최종 점검할 때 함께 검토된다.
> - **다음 작업 후보 자동 추출**: PR 본문에 `## 다음 작업` (또는 `## Next steps`, `## Follow-up`, `## 후속`) 섹션이 있으면 그 내용이 자동으로 채워진다. **절대적 지시가 아니라 후보**이므로 다음 작업자는 참고만 하고 우선순위·문맥에 따라 자유롭게 결정한다.
> - **머지 전 최종 점검**: Reviewer 또는 작성자는 머지 직전 자동 생성된 HANDOFF 항목을 읽고 사실관계·다음 작업 후보가 적절한지 확인한다. 부적절하면 그 PR에서 직접 수정 후 머지.
> - **수동 append (선택)**: 세션을 끝낼 때 PR로 안 묶이는 메모(WIP, 디버깅 발견, 후속 TODO)는 이 파일 하단에 직접 추가해도 된다.

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
