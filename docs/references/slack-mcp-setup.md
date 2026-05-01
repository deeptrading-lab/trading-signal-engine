# Slack MCP 셋업 가이드

Claude Code에서 Slack workspace를 읽고 쓸 수 있게 해주는 MCP(Model Context Protocol) 서버 설정 가이드입니다.

> **이 가이드의 목적**
> - 본인 PC에서 Claude Code가 Slack의 채널/메시지를 읽고 쓸 수 있게 한다.
> - 토큰은 환경변수로 분리해 안전하게 관리한다.
> - `.mcp.json`은 `.gitignore`에 등록되어 있어 개인 설정으로만 동작한다 (팀 공유 X).

---

## 1. 사전 준비

- macOS + zsh
- Node.js 18+ (npx 사용)
- Claude Code CLI 설치
- Slack workspace 접근 권한 (예: `musinsa.slack.com`)

---

## 2. Slack App 생성 및 토큰 발급

본인 계정으로 Slack App을 만들고, Bot Token을 발급합니다. **이 단계는 본인이 직접 수행**하셔야 합니다 (토큰은 절대 채팅·코드에 노출 금지).

### 2-1. App 생성

1. https://api.slack.com/apps 접속 → **Create New App** → **From scratch**
2. App 이름 입력 (예: `claudecodebot-<본인이름>`), workspace 선택
3. **Create App** 클릭

### 2-2. Bot Token Scopes 추가

좌측 메뉴 **OAuth & Permissions** → **Scopes** 섹션 → **Bot Token Scopes** 에 아래 권한 추가:

| Scope | 용도 |
|---|---|
| `channels:history` | public 채널 메시지 읽기 |
| `channels:read` | public 채널 목록 조회 |
| `groups:history` | private 채널 메시지 읽기 (초대된 채널만) |
| `groups:read` | private 채널 목록 조회 |
| `im:history` | DM 메시지 읽기 |
| `im:read` | DM 목록 조회 |
| `mpim:history` | 그룹 DM 메시지 읽기 |
| `mpim:read` | 그룹 DM 목록 조회 |
| `chat:write` | 메시지 작성 |
| `users:read` | 유저 목록·이름 조회 |
| `reactions:write` | 이모지 반응 추가 |

> **권한 최소화 원칙**: 위 목록은 표준 셋업이며, 메시지 작성이 필요 없으면 `chat:write` 빼는 등 필요에 따라 줄여도 됩니다.

### 2-3. Workspace에 설치

1. **OAuth & Permissions** 페이지 상단 **Install to Workspace** 클릭
2. workspace admin 승인이 필요할 수 있음 (musinsa는 사내 정책 확인)
3. 설치 완료 후 **Bot User OAuth Token** (`xoxb-...` 형식) 복사

> **⚠️ 토큰 취급 주의**
> - 절대 코드·README·채팅·스크린샷·git에 노출 금지
> - 노출됐다면 즉시 **Revoke Token** → **Reinstall to Workspace** 로 재발급
> - 1Password / macOS Keychain 등 시크릿 매니저 사용 권장 (이 가이드는 단순화를 위해 zshrc 사용)

---

## 3. 환경변수 등록

토큰을 `~/.zshrc`에 영구 등록합니다.

```bash
nano ~/.zshrc
```

파일 맨 아래에 다음 줄 추가 (실제 토큰으로 치환):

```bash
export SLACK_MCP_XOXB_TOKEN="xoxb-여기에-실제-토큰"
```

저장: `Ctrl+X` → `Y` → `Enter`

> **macOS nano 주의**: `Ctrl+O` 는 macOS 시스템이 가로채서 파일 열기 다이얼로그가 뜰 수 있음. `Ctrl+X` 로 종료 시 저장 프롬프트가 나오니 그쪽이 안전.

적용 및 확인:

```bash
source ~/.zshrc
echo "${SLACK_MCP_XOXB_TOKEN:0:10}..."   # xoxb-12345... 같이 앞부분만 보이면 OK
```

> **VSCode/Claude Code에 반영하려면 완전 재시작 필수** (`Cmd+Q` 후 다시 열기). 단순 reload나 새 터미널 열기는 부족 — env 상속은 프로세스 시작 시점에만 일어남.

---

## 4. 프로젝트에 MCP 서버 등록

프로젝트 루트의 `.mcp.json` 파일을 생성합니다 (이미 `.gitignore`에 등록되어 있음).

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "slack-mcp-server@latest", "--transport", "stdio"],
      "env": {
        "SLACK_MCP_XOXB_TOKEN": "${SLACK_MCP_XOXB_TOKEN}",
        "SLACK_MCP_ADD_MESSAGE_TOOL": "true"
      }
    }
  }
}
```

**필드 설명:**
- `command` + `args`: npx로 [korotovsky/slack-mcp-server](https://github.com/korotovsky/slack-mcp-server) 실행 (stdio 방식)
- `SLACK_MCP_XOXB_TOKEN`: shell env 에서 주입 (`${...}` 문법). 토큰을 파일에 직접 박지 않음
- `SLACK_MCP_ADD_MESSAGE_TOOL`: `chat:write` 권한 활성화. 메시지 발송이 필요 없으면 `false`

---

## 5. 연결 검증

```bash
claude mcp list
```

다음과 같이 나오면 성공:

```
slack: npx -y slack-mcp-server@latest --transport stdio - ✓ Connected
```

### 첫 실행시 주의: 캐싱 시간

대형 workspace (수천 채널·수만 유저)는 첫 실행시 캐싱에 1~2분 걸립니다. 이때 `claude mcp list` 가 `✗ Failed to connect` 로 보일 수 있는데, 다음과 같이 직접 실행해 진행 상황 확인:

```bash
{ npx -y slack-mcp-server@latest --transport stdio < /dev/null & PID=$!; sleep 5; kill $PID; } 2>&1 | head -20
```

다음 로그가 나오면 정상 (캐시 빌드 중):

```
Authenticated to Slack ... team:MUSINSA
Caching users collection...
Loaded users from cache count:22550
Caching channels collection...
```

캐시 위치: `~/Library/Caches/slack-mcp-server/` — 한 번 만들어지면 다음부터는 빠르게 시작합니다.

### Rate limit 경고

초기 캐싱시 `slack rate limit exceeded, retry after 30s` 가 뜰 수 있는데, 라이브러리가 자동 재시도하니 무시해도 됩니다.

---

## 6. 첫 사용

1. **Claude Code 새 세션 시작** (이전 세션은 .mcp.json 인식 못 함)
2. 처음 Slack 툴 호출시 **"Trust this MCP server?"** 프롬프트 → Approve
3. **봇을 채널에 초대**해야 그 채널 읽기/쓰기 가능:
   ```
   /invite @claudecodebot-<본인이름>
   ```
   DM은 초대 없이 바로 가능.

### 사용 예시 (Claude Code 프롬프트)

- "내 #signal-engine 채널 최근 메시지 10개 보여줘"
- "@hayoung 한테 DM으로 '배포 끝났습니다' 보내줘"
- "alpha-cost-guard PR 머지됐다고 #release-notes 채널에 알려줘"

---

## 7. 보안 체크리스트

- [ ] 토큰은 `~/.zshrc` 외 다른 곳에 평문 저장 안 함
- [ ] `.mcp.json` 이 `.gitignore` 에 있음 → `git status` 로 확인
- [ ] 봇 권한은 필요 최소한만 (위 표 참고)
- [ ] 봇은 필요한 채널에만 초대 (전체 channels 자동 join 금지)
- [ ] 토큰 노출 의심시 즉시 **Revoke & Reinstall**
- [ ] 사내 정책상 외부 MCP 서버 실행이 허용되는지 확인 (`npx`로 외부 패키지 다운로드)

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `✗ Failed to connect` | 환경변수 미상속 | VSCode 완전 재시작 (Cmd+Q 후 재실행) |
| `✗ Failed to connect` (env 정상) | 첫 실행 캐싱 타임아웃 | 위 5번 직접 실행으로 캐시 빌드 후 재시도 |
| `not_in_channel` 에러 | 봇이 채널에 없음 | Slack에서 `/invite @<봇이름>` |
| `missing_scope` 에러 | OAuth scope 부족 | 2-2 표 참고해 scope 추가 후 **Reinstall to Workspace** |
| `invalid_auth` | 토큰 오타·만료·재발급 후 미반영 | `echo $SLACK_MCP_XOXB_TOKEN` 으로 값 확인 → zshrc 수정 → VSCode 재시작 |
| `quote>` 가 터미널에 뜸 | shell이 따옴표 매칭 대기중 | `Ctrl+C` 로 빠져나오고 `nano` 로 다시 시도 |

---

## 9. 참고 링크

- [korotovsky/slack-mcp-server](https://github.com/korotovsky/slack-mcp-server) — 사용 중인 MCP 서버
- [Slack API: OAuth Scopes](https://api.slack.com/scopes)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Code: MCP 설정](https://docs.claude.com/en/docs/claude-code/mcp)
