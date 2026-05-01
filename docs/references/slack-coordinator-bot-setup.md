# 코디네이터 봇 셋업 가이드 (인바운드 + 아웃바운드)

사용자 Slack DM ↔ 로컬 코디네이터 데몬 사이의 양방향 메시지 처리 환경을 구축하는 가이드입니다.

> **이 가이드의 목적**
> - 본인 계정에 별도 Slack App(`Hayoung AI Coordinator`)을 만들어 DM으로 명령을 받고 응답한다.
> - Socket Mode를 사용해 외부 공개 URL 없이 로컬 머신에서 이벤트를 수신한다.
> - 토큰은 `.env`로 분리해 시크릿 노출을 막는다.
>
> **`slack-mcp-setup.md`와의 차이**
> | 구분 | slack-mcp-setup.md | 본 가이드 |
> |---|---|---|
> | 대상 | Claude Code → Slack (read/write) | 사용자 DM → 로컬 데몬 → 응답 |
> | 토큰 | Bot Token(xoxb)만 | Bot Token(xoxb) + App-Level Token(xapp) |
> | 실행 주체 | Claude Code 세션 내부 MCP | 로컬 Python 데몬 (`python -m ai.coordinator.main`) |
> | 전송 채널 | HTTP API | WebSocket (Socket Mode) |

---

## 0. 외부 노출 텍스트 네이밍 제약 (필독)

회사 Slack은 동료 가시성이 있으므로 봇의 **표시명/설명/응답 메시지/로그**에 트레이딩 도메인이 드러나면 안 됩니다.

**금지 키워드**: `signal`, `trade`, `trading`, `desk`, `quant`, `finance`, `market`, `ticker`, `pnl`

- ✅ 허용: 코드 내부 변수명·디렉토리명·패키지명 (`ai/coordinator/`, `route_command` 등)
- ❌ 금지: App Name, Display Name, Description, 응답 메시지 본문, 로그 출력, 커밋/PR 제목

본 가이드의 모든 예시 이름(`Hayoung AI Coordinator`, `coordinator-socket` 등)은 이 원칙을 따른 결과입니다.

---

## 1. 사전 준비

- macOS + zsh
- Python 3.11+ (`.venv` 있는 프로젝트 루트)
- Slack workspace 접근 권한 (musinsa.slack.com 등)
- `slack-mcp-setup.md`와 별개로 새 Slack App 생성 권한

---

## 2. Slack App 생성

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. App 이름: `Hayoung AI Coordinator` (소유자 식별 + 트레이딩 키워드 회피 + 코디네이터 톤)
3. workspace 선택 → **Create App**

### 2-1. Basic Information

좌측 메뉴 **Basic Information** → **Display Information**:
- **App Name**: `Hayoung AI Coordinator`
- **Short description**: `개인 워크플로우 코디네이터` (또는 비슷한 중립 표현)
- **App icon**: 차트·금융 연상 이미지 회피, 추상 도형/이니셜/일러스트 권장
- **Save Changes**

### 2-2. App Home (DM 표시 + 답장 허용)

좌측 메뉴 **App Home**:
- **Your App's Presence in Slack** → **App Display Name**, **Default username** 위 이름으로 통일
- **Show Tabs** 섹션:
  - **Messages Tab**: ON
  - **Allow users to send Slash commands and messages from the messages tab**: ✅
- **Save Changes**

> 이 토글이 OFF면 봇 DM 입력창에 "이 앱으로 메시지를 보내는 기능이 꺼져 있습니다"가 떠서 인바운드가 막힙니다.

### 2-3. Bot Token Scopes

좌측 메뉴 **OAuth & Permissions** → **Scopes** → **Bot Token Scopes**:

| Scope | 용도 |
|---|---|
| `app_mentions:read` | 채널 멘션 이벤트 수신 (현재는 무시 처리) |
| `im:history` | DM 히스토리 읽기 |
| `im:read` | DM 채널 목록 |
| `im:write` | 봇이 DM 채널 생성/접근 |
| `chat:write` | 봇 메시지 작성 (응답 송신) |

### 2-4. Event Subscriptions

좌측 메뉴 **Event Subscriptions** → **Enable Events**: ON
- **Subscribe to bot events** → **Add Bot User Event** → `message.im`
- **Save Changes** (페이지 하단)

### 2-5. Socket Mode + App-Level Token

좌측 메뉴 **Socket Mode** → **Enable Socket Mode**: ON
- 자동으로 모달이 뜸 → **Generate an app-level token**:
  - **Token Name**: `coordinator-socket`
  - **Scopes**: `connections:write` (자동 추가됨, 그대로 둠)
  - **Generate**
- 생성된 `xapp-1-...` 토큰 **즉시 복사** (모달 닫으면 다시 못 봄)

### 2-6. Workspace에 (재)설치

좌측 메뉴 **Install App** → **Reinstall to Workspace** (스코프 추가 시 필수)
- 설치 완료 후 **Bot User OAuth Token**(`xoxb-...`) 복사

> 토큰 취급은 `slack-mcp-setup.md` §2-3 주의사항 그대로 적용 — 코드/채팅/스크린샷 노출 금지, 의심 시 즉시 **Revoke & Reinstall**.

---

## 3. 로컬 데몬 실행

### 3-1. 의존성 설치

프로젝트 루트에서:

```bash
source .venv/bin/activate
python -m pip install -r ai/requirements.txt
```

> **`pip not found`가 뜨는 경우**: venv에 pip 스크립트가 누락된 케이스. 위처럼 `python -m pip` 형태로 호출하면 모듈로 직접 실행되어 동작합니다. 영구 해결은 `python -m ensurepip --upgrade`.

### 3-2. `.env` 작성

프로젝트 루트의 `.env.example`을 복사:

```bash
cp .env.example .env
```

`.env`를 편집해 실제 토큰으로 채움:

```dotenv
SLACK_BOT_TOKEN=xoxb-실제값          # OAuth & Permissions → Bot User OAuth Token
SLACK_APP_TOKEN=xapp-실제값          # Basic Information → App-Level Tokens 또는 Socket Mode 모달
SLACK_ALLOWED_USER_IDS=U0XXXXXXXXX   # 본인 user id (콤마로 다중 지정 가능)
LOG_LEVEL=INFO
```

> `.env`는 `.gitignore`에 등록되어 있어 커밋되지 않습니다. `.env.example`만 추적됩니다.
>
> **본인 user id 확인**: Slack 프로필 → 더보기(⋯) → **Copy member ID**. 또는 Claude Code 세션에서 `mcp__slack__users_search`로 조회.

### 3-3. 데몬 실행

프로젝트 루트의 `.env` 는 데몬 시작 시 **자동 로딩**되므로 별도의 `source` 단계가 필요 없습니다.

```bash
python -m ai.coordinator.main
```

> **셸 export 우선순위**: 셸에 이미 동일 이름의 환경변수가 export 되어 있으면 그 값이 우선이고, `.env` 값은 덮어쓰지 않습니다(`load_dotenv(override=False)`). 임시로 다른 토큰을 쓰고 싶으면 `SLACK_BOT_TOKEN=xoxb-... python -m ai.coordinator.main` 처럼 한 줄에 묶어 실행하면 됩니다. 컨테이너/CI 같은 운영 환경에서도 셸 환경변수 주입이 그대로 동작합니다.

연결 성공 시 다음과 같은 로그가 뜹니다:

```
[INFO] ai.coordinator: 코디네이터를 시작합니다. CoordinatorConfig(bot_token=xoxb-***, app_token=xapp-***, ...)
[INFO] ai.coordinator: ⚡️ Bolt app is running!
[INFO] ai.coordinator: Starting to receive messages from a new connection (session id: ...)
```

토큰은 `xoxb-***` / `xapp-***` 형태로만 노출되며 평문 토큰은 절대 로그에 흐르지 않습니다.

### 3-4. DM 테스트

Slack에서 `Hayoung AI Coordinator` DM 채널 열고 입력:

| 입력 | 기대 응답 |
|---|---|
| `ping` | `pong` |
| `status` | 가동시간 / 호스트명 / 현재 시각(KST) / Python 버전 4종 |
| 알 수 없는 명령 (예: `asdf`) | 사용 가능한 명령 목록 안내 |

대소문자·앞뒤 공백은 정규화됩니다 (`PING`, `  ping  ` 모두 동일).

### 3-5. 종료

터미널에서 `Ctrl+C` 한 번 → 다음 로그 후 정상 종료:

```
[INFO] ai.coordinator: 종료 시그널 수신(2) — 코디네이터를 정리 중입니다.
[INFO] ai.coordinator: 키보드 인터럽트로 종료합니다.
[INFO] ai.coordinator: 코디네이터를 정리했습니다.
```

빠르게 두 번 눌러도 첫 시그널 이후 핸들러는 OS 기본으로 되돌아가 traceback이 새지 않습니다.

---

## 4. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 봇 DM 입력창에 "이 앱으로 메시지를 보내는 기능이 꺼져 있습니다" | App Home → Messages Tab 토글 OFF | §2-2 토글 ON + 답장 허용 체크 |
| 봇 메시지가 알림으로만 뜨고 사이드바에 DM 채널 안 보임 | 사용자가 봇 DM을 한 번도 안 연 상태 | Slack에서 봇 검색 → 프로필 → **Message** 한 번 보내면 정상 채널로 표시 |
| `[코디네이터] 시작 실패: 환경변수 SLACK_BOT_TOKEN 이 설정되지 않았습니다.` | 프로젝트 루트가 아닌 곳에서 실행했거나 `.env` 가 없음 | 프로젝트 루트(또는 그 하위)에서 실행 + `.env` 파일 존재 확인. `.env` 는 자동 로딩됨 |
| `pip: command not found` | venv에 pip 스크립트 누락 | `python -m pip ...` 형태로 호출, 또는 `python -m ensurepip --upgrade` |
| `not_authed` / `invalid_auth` | 토큰 오타·만료·Reinstall 후 토큰 갱신 미반영 | OAuth & Permissions 페이지에서 최신 `xoxb` 다시 복사 |
| `missing_scope` | Bot Token Scopes 부족 | §2-3 표 확인 후 추가 → **Reinstall to Workspace** |
| Socket Mode 연결 안 됨 | App-Level Token 누락 또는 Socket Mode OFF | §2-5 재확인, `xapp-1-` 토큰이 `.env`에 있는지 체크 |
| Ctrl+C 후 종료 안 됨 (옛 버그) | 시그널 핸들러가 메인 wait를 못 깨움 | 본 PR에서 fix 완료. 코드 최신인지 확인 |

---

## 5. 보안 체크리스트

- [ ] `.env`가 `.gitignore`에 등록되어 있고, `git status`에서 보이지 않는다
- [ ] 토큰을 README/스크린샷/채팅에 노출한 적 없다 (의심 시 **Revoke & Reinstall**)
- [ ] `SLACK_ALLOWED_USER_IDS`에 본인 ID만 있다 (그 외에는 응답하지 않음)
- [ ] 봇 응답·로그·문서 어디에도 트레이딩 도메인 키워드가 없다 (자동 검증: `ai/tests/test_coordinator_handlers.py::assert_no_forbidden_keywords`)
- [ ] 응답 발사 시 도메인 키워드 자동 검사 적용 — `ai/coordinator/_compliance.py`
- [ ] App icon/Description/Display Name이 회사 동료 시점에서 의심스럽지 않다

---

## 6. 코드 구조 (구현 참고용)

```
ai/coordinator/
├── __init__.py
├── config.py     # 환경변수 로딩·검증, 토큰 마스킹 repr
├── auth.py       # 화이트리스트 판정, 자기 메시지 무시, user id 마스킹
├── handlers.py   # ping/status/fallback 응답 렌더링, 의존성 주입 가능한 라우터
└── main.py       # Socket Mode 엔트리포인트, 시그널 핸들러
```

테스트는 `ai/tests/test_coordinator_*.py`. 네트워크 의존부(slack-bolt)는 `main.build_app` 내부 지역 import라 단위 테스트는 slack-bolt 미설치 환경에서도 동작합니다.

---

## 7. 향후 확장 (Out of Scope, 별도 PRD)

- 명령 → ai/ 파이프라인 또는 backend/ 모듈 호출 연동
- 슬래시 커맨드, Block Kit 인터랙티브 컴포넌트
- 클라우드 배포 (Cloud Run / Lambda 등 — Socket Mode 대신 HTTP webhook으로 전환)
- `.env` 자동 로딩 — 구현됨 (PRD: [`coordinator-dotenv-autoload`](../prd/coordinator-dotenv-autoload.md))
- 메시지 subtype 가드 — 구현됨 (PRD: [`slack-message-subtype-guard`](../prd/slack-message-subtype-guard.md))

---

## 8. 참고

- [Slack: Socket Mode](https://api.slack.com/apis/connections/socket)
- [slack-bolt Python](https://slack.dev/bolt-python/)
- 본 프로젝트 PRD: [docs/prd/slack-coordinator-inbound.md](../prd/slack-coordinator-inbound.md)
- 본 프로젝트 QA: [docs/qa/slack-coordinator-inbound.md](../qa/slack-coordinator-inbound.md)
