# PRD: 개발 협업 Slack 봇 — Dev Manager (로컬 데몬)

- **slug**: `slack-dev-relay` (코드·브랜치·Issue 식별자는 기존 슬러그 유지 — 내부용이므로 변경 비용 회피)
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-01 (봇 표시명 변경: 2026-05-02)
- **UI 포함 여부**: **No** (별도 웹/네이티브 UI 없음. Slack 메시지·Block Kit 버튼만 사용 — Block Kit은 Slack 워크스페이스 네이티브 UX이므로 본 저장소의 UX/UI 디자이너 합류 트리거에는 해당하지 않는다.)
- **봇 표시명 (PM 결정)**: **`Hayoung Dev Manager`**
  - App 이름·Display Name·App Home·Bot User Name 모두 동일.
  - 기존 `Hayoung AI Coordinator` 와는 **별도 Slack App**, **별도 토큰**, **별도 데몬 프로세스**로 분리한다.
  - 내부 식별자(슬러그 `slack-dev-relay`, 디렉토리 `ai/dev_relay/`, 환경변수 `SLACK_DEV_RELAY_*`, audit 경로 `~/.local/state/dev_relay/`)는 사용자 노출 채널이 아니므로 그대로 유지한다.

---

## 1. 배경 / 문제

- 사용자(이하영)는 본 저장소의 트레이딩 코어 개발을 가속하고 싶다. 현재는 PC 앞에 앉아 Claude Code 세션을 직접 띄울 때만 작업이 진행되며, **이동 중·외근 중·저녁 시간 등 PC 앞을 떠난 시간이 모두 데드타임**이다.
- 해결 방향: **Slack 메신저에서 명령**을 보내면 로컬 PC의 Claude Agent SDK 세션이 자동 트리거되어 작업하고, 결과를 다시 Slack DM으로 보고하는 봇을 만든다. 모바일(iOS/Android Slack 앱)에서도 PR 리뷰 의뢰·머지 승인·진행 상황 확인이 가능해진다.
- 이미 워크스페이스에는 트레이딩 코어 명령용 봇(`Hayoung AI Coordinator`, slug `slack-coordinator-inbound`) 이 별도 App으로 존재한다. 본 PRD가 만들 봇은 **개발 워크플로 협업 전용**이며, 트레이딩 코어와는 책임을 분리한다.

### 컨텍스트 — 외부 노출 텍스트 네이밍 제약 (필수, 재확인)

- 본 워크스페이스(무신사/29CM 회사 Slack)는 **동료 가시성**이 있다.
- **봇 표시명, App 이름, App 설명, App Home, 모든 사용자 노출 메시지 본문, Block Kit 버튼 라벨, 외부 문서·README 발췌, 커밋 메시지·PR 본문**에 도메인 키워드 평문 노출은 **절대 사용 금지**한다.
- 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) 의 `FORBIDDEN_KEYWORDS` **단일 정의 지점**을 참조한다. 본 봇도 같은 모듈을 그대로 재사용한다 (별도 키워드 셋을 만들지 않는다 — 정책 단일화).
- **코드 내부 식별자**(디렉토리 `ai/dev_relay/`, 모듈 변수명, 로그 키 등) 는 내부용이므로 저장소 슬러그·기존 모듈명을 유지해도 된다. 사용자에게 **출력되는** 문자열에만 제약이 적용된다.
- 본 PRD 본문에서 봇을 통칭할 때는 **"Dev Manager 봇"** 으로 부른다.

---

## 2. 목표 (MVP)

사용자가 Slack DM(혹은 App Home Messages Tab)에 슬래시 형식 명령을 보내면, 로컬 데몬이 작업 큐에 적재 → Claude Agent SDK 세션을 띄워 처리 → 진행 상황·결과를 같은 Slack 스레드로 단계별 보고 → **위험 작업(머지·push 등)은 Block Kit 버튼으로 2단계 승인**을 받은 뒤 실행한다.

### 성공 정의 (MVP 기준)

- 사용자가 모바일 Slack 앱에서 명령 1건을 보내면, 로컬 데몬이 5초 이내에 첫 응답(접수 확인)을 같은 DM에 회신한다.
- `review pr <N>` 명령이 reviewer 에이전트를 호출해 PR을 분석하고, 결과 요약 + 발견 사항(최대 3건) + Block Kit 버튼(`[머지 검토]`, `[상세 보기]`)을 동일 스레드에 보낸다.
- 사용자가 `[머지 검토]` → `[승인]` 두 단계 confirm을 모두 누르면 devops 에이전트가 머지를 수행하고 결과를 같은 스레드에 보고한다.
- 모든 명령·결과·승인 액션이 audit log에 기록된다.
- 응답·로그·문서 어디에도 외부 노출 도메인 키워드가 평문으로 새지 않는다.

---

## 3. 범위 (In Scope)

### 3.1 Slack App (신규)

사용자가 Slack 앱 콘솔에서 **새 App을 직접 생성**한다 (부록 A 참고). 본 PRD는 데몬 코드만 책임지며, Slack App 생성 자체는 사용자 수동 작업이다.

- App 이름 / Display Name: **`Hayoung Dev Manager`** (소문자 변형 포함, 컴플라이언스 준수)
- 표시 설명(App Description): "Personal workflow manager for hayoung. Bridges Slack DMs to a local automation agent." (도메인 키워드 미포함)
- **Bot Token Scopes** (OAuth & Permissions):
  - 필수: `app_mentions:read`, `im:history`, `im:read`, `im:write`, `chat:write`, `chat:write.public`
  - 선택: `reactions:write` (작업 시작/완료 시 메시지에 이모지 리액션 표시 — UX 보강용, 미구현이어도 AC에는 영향 없음)
- **App-Level Token** (`xapp-...`): scope `connections:write` (Socket Mode)
- **Socket Mode**: ON
- **Event Subscriptions**: ON
  - Subscribe to bot events: `message.im`
- **Interactivity & Shortcuts**: ON
  - Interactivity Request URL: 사용 안 함 (Socket Mode 페이로드로 수신)
  - Block Kit 액션 페이로드(`block_actions`)는 Socket Mode를 통해 데몬이 수신
- **App Home**:
  - Messages Tab: ON
  - "Allow users to send Slash commands and messages from the messages tab": **ON**
- 워크스페이스 설치는 사용자가 콘솔에서 1회 수행한다.

### 3.2 코드 위치 / 의존성 (확정)

PM 결정사항:

- **신규 패키지**: `ai/dev_relay/` (기존 `ai/coordinator/` 와 형제 디렉토리, 동일 컨벤션)
  - `ai/dev_relay/__init__.py`
  - `ai/dev_relay/main.py` — 엔트리포인트 (`python -m ai.dev_relay.main`)
  - `ai/dev_relay/config.py` — 환경변수 검증 (`SLACK_DEV_RELAY_BOT_TOKEN`, `SLACK_DEV_RELAY_APP_TOKEN`, `DEV_RELAY_ALLOWED_USER_IDS`, `ANTHROPIC_API_KEY`)
  - `ai/dev_relay/auth.py` — 화이트리스트 판정 (코디네이터 `auth.py` 와 같은 패턴, 별도 모듈로 둔다 — 정책이 봇별로 갈릴 수 있음)
  - `ai/dev_relay/queue.py` — 작업 큐 (SQLite 단일 파일)
  - `ai/dev_relay/dispatcher.py` — 명령 파싱 + 라우팅
  - `ai/dev_relay/agent_runner.py` — Claude Agent SDK 호출 래퍼
  - `ai/dev_relay/slack_renderer.py` — Block Kit 메시지 빌드 (텍스트 컴플라이언스 가드 자동 적용)
- **기존 자산 재사용** (신규 모듈 만들지 않는다):
  - `ai/coordinator/_compliance.py` — `FORBIDDEN_KEYWORDS`, `find_forbidden_keywords`, `assert_no_forbidden` 그대로 import
  - `python-dotenv` 자동 로딩 패턴 — 코디네이터 진입점과 동일한 한 줄 (`load_dotenv(override=False)`)
  - `logging` 토큰 마스킹 패턴 — 코디네이터의 헬퍼 재사용 (필요 시 `ai/coordinator/` 에서 공용 위치로 이동, 단 그 작업은 본 PRD에서 강제하지 않음 — 우선 import 해서 쓰고 중복이 보이면 별도 PRD로 추출)
- **의존성 추가** (`ai/requirements.txt`):
  - `slack-bolt>=1.18` — 이미 추가됨 (코디네이터에서 사용 중, 그대로 공유)
  - `claude-agent-sdk>=0.1` — **신규 추가**. 정확한 패키지명/버전은 Backend Dev가 PyPI에서 최신 안정 버전을 확인해 확정한다 (PRD에서는 의존성 의도만 고정).
  - SQLite는 표준 라이브러리(`sqlite3`)로 충분 — 추가 의존성 없음.
- **테스트 위치**: `ai/tests/dev_relay/` 하위. 단위 테스트는 dispatcher 명령 파싱·queue 멱등성·slack_renderer 컴플라이언스 검증·auth 화이트리스트 로직만 커버. 실제 Slack 연결과 Claude Agent SDK 호출은 수동 검증으로 대체.

### 3.3 MVP 명령 (정확히 3개)

DM 메시지 본문에 다음 텍스트를 정확히 일치(앞뒤 공백 trim, 대소문자 무시)로 매칭한다.

| 명령 | 입력 예 | 동작 |
|------|---------|------|
| **status** | `status` | 작업 큐 현황(처리 중 N건 / 대기 N건) + Manager 서브에이전트 호출 결과 짧은 요약을 5초 이내에 응답 |
| **review pr `<N>`** | `review pr 22` | 큐에 적재 → 즉시 첫 응답(접수 확인) → reviewer 에이전트 호출 → 단계별 진행을 같은 스레드에 보고 → 완료 시 결과 요약 + 발견 사항(최대 3건) + Block Kit 버튼 (`[머지 검토]`, `[상세 보기]`) |
| **merge pr `<N>`** | `merge pr 22` | 큐에 적재 → 첫 응답에 **2단계 confirm 다이얼로그** 즉시 표시 (`[승인]`, `[취소]`). `[승인]` 클릭 시에만 devops 에이전트가 머지 수행. 단독 명령으로도 호출 가능하지만, 일반 흐름은 `review pr` 결과의 `[머지 검토]` 버튼에서 진입 |

**정확히 위 3개 명령만** MVP 범위. 그 외 입력은 사용 가능한 명령 목록을 안내하는 fallback 응답을 보낸다 (코디네이터의 fallback 패턴과 동일).

명령 추가(`implement <slug>`, `qa <slug>` 등)는 **별도 후속 PRD**로 분리한다.

### 3.4 작업 큐

- **백엔드**: **SQLite 단일 파일** (PM 결정 — JSON 대비 멱등성·동시성·조회 모두 우월하며 표준 라이브러리로 의존성 추가 없음)
- **위치**: `${XDG_STATE_HOME:-~/.local/state}/dev_relay/queue.db` (macOS에서 디렉토리 없으면 자동 생성, 권한 0700)
- **스키마** (MVP 최소 컬럼):
  ```sql
  CREATE TABLE IF NOT EXISTS jobs (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      idempotency_key TEXT NOT NULL UNIQUE,   -- Slack client_msg_id (없으면 event_id)
      user_id         TEXT NOT NULL,           -- 마스킹 전 원문 (DB는 로컬 파일이므로 OK)
      command         TEXT NOT NULL,           -- 정규화된 명령 (예: "review pr 22")
      status          TEXT NOT NULL,           -- pending|running|done|failed|cancelled
      created_at      TEXT NOT NULL,           -- ISO-8601 KST
      started_at      TEXT,
      finished_at     TEXT,
      result_summary  TEXT                     -- 사용자 노출 요약(컴플라이언스 통과한 텍스트)
  );
  ```
- **멱등성**: Slack 이벤트의 `client_msg_id` (없으면 `event_id`) 를 `idempotency_key` 로 사용. 같은 키 재수신 시 새 job을 만들지 않고 기존 job 상태만 회신.
- **동시 실행 제한**: **1건** (PM 결정 — MVP에서는 단순성·트레이싱 용이성을 우선. 두 번째 명령은 `pending` 으로 대기, 첫 응답에 "현재 1건 처리 중, 큐에 적재됨" 안내).
- **재시작 복구**: 데몬 재시작 시 `running` 상태로 남아 있는 job은 `failed` 로 마킹하고 사용자에게 "이전 세션이 끊겨 작업이 중단됐습니다. 다시 명령해 주세요." 안내. 자동 재시도는 하지 않는다 (Claude Agent SDK 비용·부작용 회피).

### 3.5 인터랙티브 승인 (Block Kit, 2단계 confirm)

- **위험 작업**(머지·push·destructive git op)은 반드시 버튼 confirm을 거친다. MVP에서는 `merge pr <N>` 만 해당.
- 흐름:
  1. `review pr 22` 결과 메시지에 `[머지 검토]` `[상세 보기]` 버튼 노출.
  2. 사용자가 `[머지 검토]` 클릭 → 봇이 같은 스레드에 **confirm 다이얼로그**: "PR #22 머지를 진행할까요? `[승인]` `[취소]`".
  3. `[승인]` 클릭 → devops 에이전트 호출 → 머지 수행 → 결과 보고.
  4. `[취소]` 클릭 → 작업 중단 + 봇이 "이유를 알려주시면 다음에 반영하겠습니다." 한 번만 묻고 종료.
- **버튼 액션 페이로드 검증** (필수):
  - `user.id` 가 화이트리스트(`DEV_RELAY_ALLOWED_USER_IDS`) 에 포함되는지.
  - `action_id` 와 `value` 가 사전에 봇이 발사한 메시지의 페이로드와 정확히 매칭되는지 (replay 방지 — `value` 에 `idempotency_key:job_id` 를 묶어 검증).
  - 같은 액션 재클릭(`block_actions` 중복 수신)은 첫 클릭만 처리하고 이후는 무시 + INFO 로그.
- 버튼 라벨·confirm 메시지 본문은 모두 컴플라이언스 가드(`assert_no_forbidden`) 통과 — 빌드 시점 검증.

### 3.6 Audit Log

- **위치**: `${XDG_STATE_HOME:-~/.local/state}/dev_relay/audit.jsonl` (JSON Lines, append-only)
- **형식** (1 라인 1 이벤트, 모두 ISO-8601 KST):
  ```json
  {"ts":"2026-05-01T14:23:01+09:00","kind":"command_received","user":"U0AE...***","cmd":"review pr 22","key":"abcd-1234","job_id":17}
  {"ts":"2026-05-01T14:23:01+09:00","kind":"job_started","job_id":17}
  {"ts":"2026-05-01T14:24:30+09:00","kind":"job_done","job_id":17,"duration_s":89,"result_brief":"리뷰 완료, 발견 2건"}
  {"ts":"2026-05-01T14:25:10+09:00","kind":"button_action","user":"U0AE...***","action":"merge_review","job_id":17}
  {"ts":"2026-05-01T14:25:14+09:00","kind":"button_action","user":"U0AE...***","action":"approve","job_id":17}
  {"ts":"2026-05-01T14:25:42+09:00","kind":"merge_done","job_id":17,"pr":22}
  ```
- 모든 user_id 는 **앞 6자만 보존하고 뒤는 `***` 로 마스킹**. 토큰·평문 비밀은 절대 기록되지 않는다.
- audit.jsonl 은 `.gitignore` 의 영향을 받지 않는 외부 경로(`~/.local/state/...`)이므로 저장소 commit 위험 없음.

### 3.7 비기능

- **실행 형태**: 단일 프로세스 데몬 (`python -m ai.dev_relay.main`).
- **graceful shutdown**: SIGINT/SIGTERM 수신 시 처리 중인 job 1건은 끝까지 마치고(또는 일정 timeout 내 미완 시 `failed` 마킹) 종료. 코디네이터의 시그널 핸들러 패턴과 동일.
- **로깅**: 표준 `logging`. 기본 `INFO`, 환경변수 `LOG_LEVEL` override. 토큰 평문 절대 미출력 — 코디네이터의 마스킹 헬퍼 재사용.
- **시작 시 환경변수 검증**: `SLACK_DEV_RELAY_BOT_TOKEN`(prefix `xoxb-`), `SLACK_DEV_RELAY_APP_TOKEN`(prefix `xapp-`), `ANTHROPIC_API_KEY`(prefix `sk-ant-`), `DEV_RELAY_ALLOWED_USER_IDS` 가 없거나 형식이 틀리면 한 줄 에러 + exit != 0.
- **dotenv 자동 로딩**: 진입점에서 `load_dotenv(override=False)` (코디네이터 패턴 그대로).
- **컴플라이언스 가드**: `slack_renderer` 가 외부 발사 직전 모든 텍스트(메시지 본문·버튼 라벨·앱 표시 텍스트)에 `find_forbidden_keywords` 를 적용. 매치 시 발사 차단 + ERROR 로그 + 사용자에게 "응답 생성 중 오류가 발생했어요. 다시 시도해 주세요." 라는 중립 fallback 회신.
- **rate limit**: 같은 `user_id` 가 5초 내 4번째 명령을 보내면 무시 + "잠시 후 다시 시도해 주세요" 안내 + INFO 로그.

### 3.8 보안

- **화이트리스트**: 본인 user_id만 (`DEV_RELAY_ALLOWED_USER_IDS=U0AE7A54NHL`). 그 외 user_id 는 메시지·버튼 클릭 모두 무시 + INFO 로그.
- **머지·push 2단계 confirm**: §3.5 참조.
- **destructive op 자체 차단**: PRD에 명시되지 않은 destructive 명령(`git reset --hard`, `git push --force`, `branch -D`, `clean -f` 등)은 **봇이 자체적으로 거부**하고 사용자에게 "이 작업은 PC에 직접 들어가서 수행해 주세요." 안내. 이 거부는 명령 라우터(dispatcher) 와 agent_runner 두 층 모두에서 검증한다.
- **토큰 마스킹**: 로그·에러·audit log 모두 적용.
- **로컬 파일 권한**: `queue.db` 와 `audit.jsonl` 디렉토리는 0700, 파일은 0600 으로 생성.

---

## 4. 비범위 (Out of Scope)

- 트레이딩 코어 명령 처리 (`Hayoung AI Coordinator` slug `slack-coordinator-inbound` 영역)
- 클라우드 배포 / 컨테이너화 (로컬 PC 한정)
- 멀티유저 협업 — 본인 user_id 화이트리스트 추가만으로 단일 큐를 공유하는 형태는 가능하지만, **동시성·격리·권한 분리는 보장하지 않는다**
- Slash 커맨드(`/dev review pr 5` 형태) — DM 메시지로만. (회사 워크스페이스 슬래시 커맨드 충돌 회피)
- LLM 호출 비용 가드 통합 — 본 PRD는 컴플라이언스 가드(`_compliance`) 만 적용. 토큰·비용 모니터링은 `cost-aware-llm-pipeline` 의 가드를 향후 별도 PRD로 통합
- PR 작성·구현 명령 (`implement <slug>`, `qa <slug>` 등) — Phase 2 별도 PRD
- 외부 알림(이메일·SMS·푸시) — Slack DM만
- 채널 멘션(`app_mention`) 응답 — DM(IM) 만
- App 매니페스트(`manifest.yaml`) 자동 생성 — 사용자가 콘솔에서 수동 설정
- 데몬 자동 시작(launchd plist 자동 설치) — 부록 B에 가이드만 제공, 강제 X
- 토큰 회전 자동화·외부 비밀관리 시스템 연동
- 대화 컨텍스트 유지 (각 명령은 독립적인 Claude Agent SDK 세션)

---

## 5. 수용 기준 (Acceptance Criteria)

QA가 그대로 체크리스트로 사용한다. **재현 절차 + 기대 결과** 형식.

### AC-1. 시작 시 연결 로그
- **재현**: 사전조건(§6.2) 충족 후 `python -m ai.dev_relay.main` 실행.
- **기대**: 표준 출력/로그에 Socket Mode 연결 성공을 의미하는 메시지(`connected` 또는 `socket mode established` 류)가 5초 이내 1회 이상 찍힌다. 토큰 값은 노출되지 않는다.

### AC-2. `status` 응답
- **재현**: 본인(U0AE7A54NHL)이 `Hayoung Dev Manager` DM에 `status` 입력.
- **기대**: 5초 이내 같은 DM에 응답이 도착하며, 응답 본문에 다음이 포함된다:
  - 처리 중 작업 수
  - 대기(pending) 작업 수
  - 최근 완료된 PR 번호 1건 이상 (없으면 "최근 처리 이력 없음")

### AC-3. `review pr <N>` 큐 적재 + 즉시 첫 응답
- **재현**: 본인 DM에 `review pr 22` 입력 (PR #22 는 머지 또는 open 상태 어느 것이든 가능).
- **기대**:
  - 5초 이내 같은 DM에 첫 응답: "PR #22 리뷰 시작합니다. 진행 상황은 이 스레드에 보고할게요." (정확한 문구 미준수, 의미만 매칭).
  - SQLite `jobs` 테이블에 status=`running` 인 행이 1개 추가됐다.
  - audit.jsonl 에 `command_received` + `job_started` 두 라인이 기록됐다.

### AC-4. `review pr <N>` 결과 + Block Kit 버튼
- **재현**: AC-3 의 reviewer 에이전트 처리가 끝날 때까지 대기 (수 분 소요 가능).
- **기대**:
  - 같은 스레드에 결과 메시지가 도착한다.
  - 메시지에는 결과 요약(2~3 문장) + 발견 사항(있으면 최대 3건, 없으면 "특이사항 없음") 이 포함된다.
  - 메시지 하단에 Block Kit 버튼 두 개 (`머지 검토`, `상세 보기`) 가 노출된다.
  - audit.jsonl 에 `job_done` 라인이 기록됐다.

### AC-5. `[머지 검토]` → `[승인]` 2단계 confirm 머지
- **재현**: AC-4 결과 메시지에서 `[머지 검토]` 버튼 클릭 → 같은 스레드에 confirm 다이얼로그 등장 → `[승인]` 클릭.
- **기대**:
  - 1단계: confirm 메시지에 PR 번호와 `[승인]` `[취소]` 두 버튼이 노출된다.
  - 2단계: `[승인]` 클릭 후 devops 에이전트가 머지를 수행하고, 같은 스레드에 머지 결과(성공/실패, 머지 SHA 또는 실패 사유) 가 보고된다.
  - audit.jsonl 에 `button_action(merge_review)`, `button_action(approve)`, `merge_done` 세 라인이 순서대로 기록됐다.

### AC-6. `[취소]` 시 작업 중단
- **재현**: AC-5 의 1단계 confirm 메시지에서 `[취소]` 클릭.
- **기대**:
  - 봇이 작업을 중단하고 "취소했습니다. 이유를 알려주시면 다음에 반영할게요." 안내.
  - devops 에이전트가 호출되지 않았다 (audit.jsonl 에 `merge_done` 부재).

### AC-7. 화이트리스트 외 발신자 / 버튼 클릭 무시
- **재현**:
  - 다른 user_id 가 봇 DM에 `status` 보냄.
  - 다른 user_id 가 본인 스레드의 `[머지 검토]` 버튼을 (가능한 시나리오로) 클릭.
- **기대**: 두 경우 모두 봇은 응답하지 않는다. 데몬 로그에 INFO 레벨로 차단 사실(마스킹된 user_id, 이벤트/액션 종류)이 기록된다. devops 에이전트는 호출되지 않는다.

### AC-8. graceful shutdown
- **재현**: 데몬 실행 중 Ctrl+C (SIGINT). 또는 `kill <pid>` (SIGTERM).
- **기대**:
  - 처리 중인 job 1건이 있으면 종료 timeout(예: 30초) 까지 대기 후 미완 시 `failed` 마킹.
  - 스택 트레이스 없이 종료 메시지(`shutting down ...`) 와 함께 정상 종료 코드로 빠진다.

### AC-9. 환경변수 누락 시 fail-fast
- **재현**: `SLACK_DEV_RELAY_BOT_TOKEN`, `SLACK_DEV_RELAY_APP_TOKEN`, `ANTHROPIC_API_KEY` 중 하나 미설정 또는 잘못된 prefix 상태에서 데몬 실행.
- **기대**: 어떤 변수가 빠졌는지/형식이 틀렸는지 한 줄 에러 메시지가 출력되고 exit != 0. 토큰 값은 출력되지 않는다.

### AC-10. 토큰·user_id 마스킹
- **재현**: AC-1 ~ AC-9 의 모든 로그 출력과 audit.jsonl 내용을 grep.
- **기대**: 토큰 평문(`xoxb-...`, `xapp-...`, `sk-ant-...`) 이 단 한 곳도 출력되지 않는다. user_id 는 audit.jsonl 에서 앞 6자만 노출되고 뒤는 `***`.

### AC-11. 멱등성 (같은 client_msg_id 재수신)
- **재현**: 같은 `client_msg_id` 를 가진 `message.im` 이벤트를 강제로 두 번 주입 (Slack이 재전송하는 시나리오 시뮬레이션 — 단위 테스트로 검증 가능).
- **기대**: `jobs` 테이블에 새 row가 추가되지 않고, Claude Agent SDK 도 한 번만 호출된다. 두 번째 이벤트는 INFO 로그(`duplicate event ignored`) 만 남긴다.

### AC-12. audit log 기록 완전성
- **재현**: AC-2 ~ AC-6 시나리오 1회 완주.
- **기대**: audit.jsonl 에 다음 이벤트들이 빠짐없이 기록된다 (각 1라인):
  - `command_received` (status, review pr, merge pr 각각)
  - `job_started` / `job_done` 또는 `job_failed`
  - `button_action` (merge_review, approve 또는 cancel)
  - `merge_done` (승인 흐름에 한해)

### AC-13. destructive op 자체 차단
- **재현**: 본인 DM에 `git reset --hard HEAD~5` 또는 `force push main` 등 PRD 비범위 명령 입력. (또는 명령 라우터가 인식 못 하더라도 reviewer 에이전트가 destructive op를 제안하는 경우.)
- **기대**:
  - 라우터는 unknown command fallback 으로 처리하고 사용 가능한 명령 목록을 안내한다.
  - 어떤 경로로도 봇이 destructive git 명령을 실행하지 않는다 (agent_runner 화이트리스트 가드 통과).

### AC-14. 동시성 — 두 번째 명령 큐 적재
- **재현**: AC-3 의 `review pr 22` 처리 중에 본인 DM에 `review pr 23` 추가 입력.
- **기대**:
  - 두 번째 명령에 대해 즉시 첫 응답: "현재 1건 처리 중입니다. 큐에 적재됐어요 (대기 1건)."
  - 첫 번째 작업 완료 후 두 번째 작업이 자동으로 시작된다.
  - audit.jsonl 에 두 작업 모두 정상 기록.

### AC-15. rate limit
- **재현**: 본인 DM에 5초 내 4건 이상의 명령(예: `status` 4번 연속) 을 빠르게 입력.
- **기대**: 4번째 이후 명령은 큐에 적재되지 않고, 봇이 "잠시 후 다시 시도해 주세요" 한 번만 안내. INFO 로그 기록.

### AC-16. 외부 노출 텍스트 컴플라이언스
- **재현**: AC-2 ~ AC-15 의 모든 봇 응답 메시지, Block Kit 버튼 라벨, App 표시명, App 설명, 시작·종료 로그 중 사용자에게 도달 가능한 모든 문자열, 부록 A·B 의 명령 예시, 본 PRD 본문, 새 디렉토리 docstring, 본 PRD 구현 PR 본문, 커밋 메시지를 검사.
- **기대**: 도메인 키워드(대소문자 무시) 가 단 한 곳도 등장하지 않는다. 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py) `FORBIDDEN_KEYWORDS` 참조.
- **자동화**: `slack_renderer` 의 발사 직전 가드, 그리고 `ai/tests/dev_relay/test_compliance.py` 에서 PRD·디자인·구현 산출물 텍스트 정적 검사.

### AC-17. 자기 자신 메시지 무시
- **재현**: 봇이 자기 응답으로 다시 트리거되어 무한 루프가 발생하는 상황 강제 (`bot_id` 채워진 이벤트 단위 테스트로 검증).
- **기대**: 핸들러가 조기 반환하며 응답하지 않는다.

---

## 6. 가정 · 제약

### 6.1 기술 / 비용

- Python 3.11+ (`ai/` 디렉토리 컨벤션 — `cost-aware-llm-pipeline` §6, `slack-coordinator-inbound` §6.1 과 정렬).
- 추가 의존성: `claude-agent-sdk` 1개 신규. `slack-bolt` 는 코디네이터에서 이미 사용 중. 라이선스는 모두 OSS.
- **비용**: Claude Agent SDK 호출은 Anthropic API 토큰 비용을 발생시킨다. MVP에서는 동시 1건 + 본인 단독 사용이라 일일 호출 수가 제한적이지만, 비용 모니터링 가드 통합은 별도 PRD로 분리.
- **로컬 머신이 켜져 있을 때만 동작**. 노트북 절전·네트워크 단절 시 메시지는 큐잉되지 않으며, 온라인 복귀 후 받지 못한 이벤트는 Slack Socket Mode 재전송 정책을 따른다(별도 보장 X).
- 토큰은 환경변수 또는 git-untracked `.env` 로만 관리. PRD·코드·커밋·로그·audit.jsonl 어디에도 토큰 값이 포함되지 않는다.

### 6.2 사전조건 — 사용자가 Slack 앱 콘솔에서 수동 설정 (개발 시작 전 완료 가정)

- **신규 App 생성**: `Hayoung Dev Manager` (부록 A 단계별 가이드)
  - Socket Mode ON
  - App-Level Token (`xapp-...`), scope `connections:write`
  - Bot Token Scopes: §3.1
  - Event Subscriptions: `message.im`
  - Interactivity ON
  - App Home Messages Tab ON + 사용자 메시지 허용
- 워크스페이스에 봇 설치
- 로컬 환경변수 (`.env` 또는 셸 rc):
  - `SLACK_DEV_RELAY_BOT_TOKEN=xoxb-...`
  - `SLACK_DEV_RELAY_APP_TOKEN=xapp-...`
  - `ANTHROPIC_API_KEY=sk-ant-...`
  - `DEV_RELAY_ALLOWED_USER_IDS=U0AE7A54NHL`
  - (선택) `LOG_LEVEL=INFO`

### 6.3 보안

- 토큰 하드코딩 금지. `.env` 는 `.gitignore` 포함 확인.
- 화이트리스트 외 발신자/버튼 클릭 모두 무시 — 외부 사용자 노이즈/오·발송 방지.
- destructive git op 자체 차단 (§3.8).
- audit.jsonl 은 외부 경로(`~/.local/state/...`) — 저장소 commit 위험 없음.
- 본 봇은 `Hayoung AI Coordinator` 와 **별도 토큰**을 쓰므로, 한 봇의 토큰 유출이 다른 봇의 권한으로 이어지지 않는다.

### 6.4 일정 / 운영

- 로컬 데몬이므로 배포·CI 변경 없음. DevOps의 push 게이트(AGENTS.md)는 평소대로.
- 사용자 1인(이하영) 단독 사용 가정. 멀티유저는 향후 PRD.
- 본 봇과 `Hayoung AI Coordinator` 는 동시 실행 가능 (서로 다른 프로세스, 서로 다른 토큰, 서로 다른 SQLite 파일).

---

## 7. 참고

- 저장소 루트 `AGENTS.md` — PRD 양식, 라벨 플로우, 봇 명세 컴플라이언스 원칙
- `docs/agents/pm.md` — PM 작성 원칙
- `docs/prd/slack-coordinator-inbound.md` — 자매 봇 PRD (Socket Mode 데몬 패턴 선례)
- `docs/prd/coordinator-compliance-module.md` — `_compliance` 모듈 단일 정의 원칙
- `docs/prd/coordinator-dotenv-autoload.md` — dotenv 자동 로딩 패턴
- `docs/prd/cost-aware-llm-pipeline.md` — `ai/` 디렉토리 Python 3.11+ 컨벤션
- `ai/coordinator/_compliance.py` — `FORBIDDEN_KEYWORDS` 단일 정의 지점 (재사용 대상)
- `ai/coordinator/auth.py`, `ai/coordinator/config.py`, `ai/coordinator/main.py` — 패키지 구조 선례
- `ai/requirements.txt` — 의존성 추가 대상 파일
- 사용자 메모리 노트: 회사 Slack 동료 가시성, 봇 표시명에 트레이딩 도메인 노출 금지
- Claude Agent SDK 공식 문서: 정확한 패키지명·버전은 Backend Dev가 PyPI 최신 안정판 기준 확정 (PRD에서는 `claude-agent-sdk` 의도만 고정)

---

## 8. PM 결정사항 요약 (구현·QA가 한눈에 보도록)

| 항목 | 결정 |
|------|------|
| 봇 표시명 / App 이름 | **`Hayoung Dev Manager`** (내부 슬러그·디렉토리·환경변수는 `slack-dev-relay`/`dev_relay`/`SLACK_DEV_RELAY_*` 그대로) |
| 코드 위치 | `ai/dev_relay/` (코디네이터와 형제 디렉토리) |
| 작업 큐 백엔드 | **SQLite** (단일 파일, `~/.local/state/dev_relay/queue.db`) |
| 동시 실행 제한 | **1건** (MVP) — 두 번째 명령은 pending 으로 적재 |
| Claude Agent SDK 호출 패턴 | **동기(sync) 호출 + worker thread** — slack-bolt 이벤트 루프와 분리. async 전환은 후속 PRD |
| Audit log 위치 / 형식 | `~/.local/state/dev_relay/audit.jsonl` (JSONL append-only, ISO-8601 KST, user_id 6자 + `***` 마스킹) |
| MVP 명령 수 | **3개** (`status`, `review pr <N>`, `merge pr <N>`) |
| 2단계 confirm 적용 명령 | `merge pr <N>` (단독 호출 또는 `[머지 검토]` 버튼 진입 모두) |
| 컴플라이언스 정책 단일 정의 | `ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS` 재사용 (별도 셋 만들지 않음) |
| 환경변수 prefix | `SLACK_DEV_RELAY_BOT_TOKEN`, `SLACK_DEV_RELAY_APP_TOKEN`, `ANTHROPIC_API_KEY`, `DEV_RELAY_ALLOWED_USER_IDS` |

---

## 부록 A. Slack App 생성 단계별 가이드 (사용자 1회성 셋업)

> 사용자 노출 텍스트가 아니지만 본 부록도 도메인 키워드를 쓰지 않는다.

A.1 https://api.slack.com/apps → **Create New App** → From scratch.
- App Name: `Hayoung Dev Manager`
- Workspace: 회사 Slack 워크스페이스 선택.

A.2 좌측 **App Home** → Messages Tab ON, "Allow users to send Slash commands and messages from the messages tab" 체크.

A.3 좌측 **Socket Mode** → Enable Socket Mode → ON. App-Level Token 발급(`connections:write` 스코프, 토큰 형식 `xapp-...`) → 안전한 곳에 복사.

A.4 좌측 **OAuth & Permissions** → Bot Token Scopes 추가:
- `app_mentions:read`
- `im:history`
- `im:read`
- `im:write`
- `chat:write`
- `chat:write.public`
- (선택) `reactions:write`

A.5 좌측 **Event Subscriptions** → Enable Events ON → "Subscribe to bot events" 에 `message.im` 추가 → Save.

A.6 좌측 **Interactivity & Shortcuts** → Interactivity ON. Request URL 비워둠 (Socket Mode 사용).

A.7 좌측 **Basic Information** → 기본 설명/표시명 컴플라이언스 검토:
- Short description: "Personal workflow manager for hayoung."
- Long description: "Bridges Slack DMs to a local automation agent for personal productivity."
- App icon: 중립 아이콘.

A.8 **Install to Workspace** (또는 스코프 변경 후 재설치) → Bot User OAuth Token (`xoxb-...`) 복사.

A.9 로컬 `.env` 에 토큰 등록:
```
SLACK_DEV_RELAY_BOT_TOKEN=xoxb-...
SLACK_DEV_RELAY_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-...
DEV_RELAY_ALLOWED_USER_IDS=U0AE7A54NHL
```

A.10 의존성 설치 후 데몬 실행:
```
pip install -r ai/requirements.txt
python -m ai.dev_relay.main
```

연결 로그 확인 후 Slack 모바일/데스크톱에서 `Hayoung Dev Manager` DM에 `status` 입력 → 5초 내 응답 확인.

---

## 부록 B. 로컬 데몬 자동 시작 가이드 (옵션, 강제 X)

macOS 에서 PC 부팅 시 자동 기동을 원하면 launchd 를 사용한다. 본 PRD는 가이드만 제공하고, 자동 설치는 강제하지 않는다.

B.1 plist 작성 (`~/Library/LaunchAgents/com.hayoung.dev-relay.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hayoung.dev-relay</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/hayoung/.virtualenvs/&lt;repo-venv&gt;/bin/python</string>
    <string>-m</string>
    <string>ai.dev_relay.main</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/hayoung/path/to/&lt;repo-root&gt;</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key>
  <string>/Users/hayoung/.local/state/dev_relay/stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/hayoung/.local/state/dev_relay/stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
```

B.2 로드/언로드:
```
launchctl load  ~/Library/LaunchAgents/com.hayoung.dev-relay.plist
launchctl unload ~/Library/LaunchAgents/com.hayoung.dev-relay.plist
```

B.3 환경변수는 plist 의 `EnvironmentVariables` 또는 `~/.zshenv` 에 secrets 를 export 하는 방식 중 사용자 선호에 따라 선택. 토큰을 plist 에 평문으로 적지 말 것 (plist 도 백업 대상이 될 수 있음).

---

## 부록 C. 향후 확장 (참고만; 본 PRD 범위 아님)

- 명령 추가: `implement <slug>`, `qa <slug>`, `pipeline <slug>` (사용자가 모바일에서 전체 파이프라인 트리거)
- 비용 가드 통합: `cost-aware-llm-pipeline` 의 가드를 `agent_runner` 에 wrap
- 멀티유저 협업 / 동시 실행 N건 / job 우선순위
- Slash 커맨드 (`/dev <subcommand>`)
- Web UI 대시보드 (큐 현황·audit log 시각화)
- 외부 비밀관리 (1Password CLI, AWS Secrets Manager)
- 클라우드 배포 (작은 VM 또는 컨테이너)
