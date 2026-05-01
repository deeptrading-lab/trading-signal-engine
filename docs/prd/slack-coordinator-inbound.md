# PRD: Slack 코디네이터 봇 인바운드 처리 (로컬 데몬)

- **slug**: `slack-coordinator-inbound`
- **PM**: 이하영 (hayoung.lee2@musinsa.com, Slack `U0AE7A54NHL`)
- **작성일**: 2026-05-01
- **UI 포함 여부**: **No** (Slack 메시지 텍스트 응답만; 별도 웹/네이티브 UI 없음. Block Kit 같은 인터랙티브 컴포넌트는 Out of Scope)

---

## 1. 배경 / 문제

- 본 저장소는 사용자가 Claude Code 등에서 트리거한 결과를 Slack DM으로 **아웃바운드** 전송하는 흐름은 동작 중이다.
- 그러나 사용자가 Slack DM으로 **봇에게 보낸 메시지를 시스템이 수신해 처리하는 인바운드 흐름은 미구현**이다. 이로 인해 사용자가 슬랙에서 직접 시스템과 대화하거나 상태를 조회하는 운영 루프가 비어 있다.
- 프로젝트는 아직 서버에 배포되지 않은 상태이므로, **클라우드 인프라 없이 로컬 개발 머신에서 단독 실행되는 데몬**으로 인바운드 흐름을 먼저 검증한다(Slack Socket Mode 활용).
- 사용자는 이 워크스페이스에 코디네이터 역할의 봇 앱(`Hayoung AI Coordinator`, App ID는 Slack 콘솔에서 확인)을 이미 등록해 두었다.

### 컨텍스트 — 외부 노출 텍스트 네이밍 제약 (필수)

- 본 워크스페이스는 무신사/29CM 회사 Slack이며 **동료 가시성**이 있다.
- **봇 표시명, App 이름, 모든 사용자 노출 메시지 본문, 외부 문서·README 발췌**에 도메인 키워드 노출은 **절대 사용 금지**한다. 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조한다.
- 단, **코드 내부 변수명·파일명·디렉토리명·로그 키**는 내부용이므로 저장소 슬러그·기존 모듈명을 유지해도 된다. 사용자 응답 텍스트로 **출력되는** 문자열에만 제약이 적용된다.
- 본 PRD에서는 봇을 **"코디네이터 봇"** 으로 통칭한다.

---

## 2. 목표 (MVP)

사용자가 Slack DM으로 코디네이터 봇에 보낸 메시지를 **로컬 데몬**이 Socket Mode로 수신하여, **허용된 발신자**의 **간단한 명령**(`ping`, `status`, 그 외)에 응답하도록 한다.

성공 정의:

- 사용자가 Slack 클라이언트에서 봇 DM에 명령을 입력하면, 로컬에서 실행 중인 데몬이 5초 이내에 응답을 같은 DM 스레드에 회신한다.
- 화이트리스트 외 사용자는 응답을 받지 못한다(로그만 기록).
- 응답·로그·문서 어디에도 외부 노출 도메인 키워드가 새지 않는다.

---

## 3. 범위 (In scope)

### 3.1 기능

- **Slack Socket Mode 연결**: `slack-bolt` 기반 Python 데몬. App-Level Token으로 WebSocket 연결, 끊김 시 자동 재연결(slack-bolt 기본 동작에 위임).
- **이벤트 구독**: `message.im` 이벤트만 처리. 봇이 그룹/채널에 멘션되더라도 MVP에서는 **DM(IM) 채널의 사용자 메시지**만 응답한다.
- **명령 라우팅**(텍스트 정확 일치, 대소문자 무시, 앞뒤 공백 trim):
  - `ping` → `pong` 회신
  - `status` → 가동시간(uptime), 호스트명, 현재 시각(ISO-8601, KST), Python 버전을 포함한 진단 텍스트 회신
  - 그 외 임의 텍스트 → 사용 가능한 명령 목록 안내 회신
- **발신자 화이트리스트**: 환경변수 `SLACK_ALLOWED_USER_IDS`(콤마 구분, 기본값 `U0AE7A54NHL`)에 포함된 Slack User ID에서 온 메시지에만 응답. 그 외에는 **무시하고 INFO 로그만 남긴다**.
- **봇 자기 메시지 무시**: `bot_id` 또는 자기 자신의 user id로 들어온 이벤트는 처리하지 않는다(에코 루프 방지).

### 3.2 비기능

- **실행 형태**: 단일 프로세스 데몬. 실행 명령은 `python -m ai.coordinator.main` 형태(아래 §3.3 참고).
- **graceful shutdown**: SIGINT(Ctrl+C) / SIGTERM 수신 시 진행 중인 응답 처리를 마치고 깔끔하게 종료한다.
- **로깅**: 표준 `logging` 모듈. 기본 레벨 `INFO`. 환경변수 `LOG_LEVEL`로 override 가능. 토큰값은 절대 로그에 출력하지 않는다.
- **시작 시 환경변수 검증**: `SLACK_BOT_TOKEN`(prefix `xoxb-`), `SLACK_APP_TOKEN`(prefix `xapp-`)이 없거나 prefix가 틀리면 **명확한 한 줄 에러 메시지**를 출력하고 exit code != 0 으로 종료한다.
- **타임존**: `status` 응답의 시각은 KST(`Asia/Seoul`)로 출력한다.
- **동시성**: Socket Mode 단일 연결. 동시 다중 명령은 slack-bolt 기본 worker pool에 위임(추가 튜닝 없음).

### 3.3 코드 위치 / 의존성 (확정)

PM 결정사항:

- **디렉토리**: `ai/coordinator/`
  - `ai/coordinator/__init__.py`
  - `ai/coordinator/main.py` — 엔트리포인트 (Socket Mode 앱 시작)
  - `ai/coordinator/handlers.py` — `ping`/`status`/fallback 핸들러
  - `ai/coordinator/auth.py` — 발신자 화이트리스트 판정
  - `ai/coordinator/config.py` — 환경변수 로딩·검증
- **의존성 추가 위치**: `ai/requirements.txt` (현 저장소에는 `pyproject.toml`이 없고 `requirements.txt`만 존재함을 확인)
  - 추가: `slack-bolt>=1.18` (Socket Mode 클라이언트 의존성 포함)
- **테스트 위치**: `ai/tests/` 하위(기존 컨벤션 유지). 단, 실제 Slack 연결 테스트는 수동 검증으로 대체하고, 단위 테스트는 핸들러 입출력·환경변수 검증·화이트리스트 로직만 커버한다.

### 3.4 운영 / 문서

- 로컬 실행 절차를 **이 PRD의 부록 A**에 한 페이지 분량으로 명시한다(README 신규 생성 없이 PRD 부록으로 통일).
- `.env` 사용 시 `.gitignore`에 이미 포함된 `.venv`·`__pycache__` 외에 `.env`도 추가되어 있는지 DevOps가 확인(현 `.gitignore`에 `.env`가 없으면 추가 필요 — Out of Scope의 별도 작업이지만 본 PRD 적용 시 동시에 챙긴다).

---

## 4. 비범위 (Out of Scope)

- 명령 → `ai/` 분석 파이프라인 또는 `backend/` 주문·리스크 모듈 연동 (이번엔 단순 응답까지만)
- 멀티유저 권한 / 역할 기반 접근 제어
- Slash 커맨드(`/...`), Block Kit 인터랙티브 컴포넌트(버튼·모달 등)
- 채널 멘션(`app_mention`) 처리 — 이벤트는 받지 않거나 받아도 무시
- 클라우드 배포(Cloud Run, Lambda, ECS 등), 컨테이너화(Dockerfile)
- 지속적 메시지 저장(DB), 대화 히스토리 컨텍스트 유지
- 다국어 응답(한국어 단일)
- 메트릭/대시보드, Sentry 등 외부 APM 연동
- Slack 앱 매니페스트(`manifest.yaml`) 자동 생성 — 사용자가 콘솔에서 수동 설정한다는 전제

---

## 5. 수용 기준 (Acceptance Criteria)

QA가 그대로 체크리스트로 사용한다. **재현 절차 + 기대 결과** 형식.

### AC-1. 시작 시 연결 로그
- **재현**: 사전조건(§6.2) 충족 후 `python -m ai.coordinator.main` 실행.
- **기대**: 표준 출력/로그에 Socket Mode 연결 성공을 의미하는 메시지(예: `connected`, `socket mode established` 류)가 5초 이내 1회 이상 찍힌다. 토큰 값은 노출되지 않는다.

### AC-2. `ping` → `pong`
- **재현**: 본인(U0AE7A54NHL)이 `Hayoung AI Coordinator` DM에 `ping` 입력.
- **기대**: 5초 이내 같은 DM에 `pong` 텍스트 응답이 도착한다.

### AC-3. `status` 응답
- **재현**: 본인 DM에서 `status` 입력.
- **기대**: 5초 이내 응답이 도착하며, 응답 본문에 다음 4개 정보가 모두 포함된다:
  - 가동시간(uptime, 사람이 읽을 수 있는 형식 — 예: `0d 00:01:23`)
  - 호스트명
  - 현재 시각 (KST, ISO-8601)
  - Python 버전 (예: `3.11.x`)

### AC-4. 알 수 없는 명령
- **재현**: 본인 DM에서 `asdf`, 빈 공백 포함 `   ping ` (공백 trim 후 정상 처리), `PING`(대소문자 무시 후 정상 처리), `help` 등 명령 목록에 없는 임의 문자열 입력.
- **기대**:
  - 트림·대소문자 정규화 후 알려진 명령(`ping`/`status`)에 매칭되는 입력은 정상 응답.
  - 그 외 입력은 사용 가능한 명령 목록(`ping`, `status`)을 안내하는 응답이 도착한다.

### AC-5. 화이트리스트 외 발신자
- **재현**: `SLACK_ALLOWED_USER_IDS`에 포함되지 않은 다른 사용자가 같은 봇과의 DM(또는 봇이 포함된 그룹 DM)에서 `ping`을 보낸다.
- **기대**: 봇은 **응답하지 않는다**. 데몬 로그에는 INFO 레벨로 차단 사실(발신자 user id 일부 또는 전체, 이벤트 타입)이 기록된다.

### AC-6. graceful shutdown
- **재현**: 데몬 실행 중 터미널에서 Ctrl+C.
- **기대**: 스택 트레이스 없이 종료 메시지(예: `shutting down ...`)와 함께 프로세스가 0 또는 정상 시그널 종료 코드로 빠진다. 데몬이 행(hang)되지 않는다.

### AC-7. 환경변수 누락 시 명확한 실패
- **재현**: `SLACK_BOT_TOKEN` 또는 `SLACK_APP_TOKEN` 미설정 / 잘못된 prefix(예: `xoxb-` 아닌 값) 상태에서 데몬 실행.
- **기대**: 어떤 변수가 빠졌는지 또는 형식이 틀렸는지 **한 줄에 명확히 적힌 에러 메시지**가 출력되고, 비정상 종료 코드(exit != 0)로 빠진다. 토큰 값은 마스킹되거나 출력되지 않는다.

### AC-8. 외부 노출 텍스트 네이밍 컴플라이언스
- **재현**: AC-2 ~ AC-4의 모든 응답 메시지, 시작·종료 로그 중 **사용자에게 도달 가능한 모든 문자열**, 그리고 본 PRD §부록 A의 명령 예시를 검사.
- **기대**: 도메인 키워드가 단 한 곳도 등장하지 않는다(대소문자 무시) — 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조. 봇 응답에서 자기 자신을 지칭할 때는 "코디네이터" 같은 중립 표현을 쓴다.
- **참고**: 코드 내부 식별자(`ai.coordinator`, 모듈 변수명 등)는 검사 대상이 아니다.

### AC-9. 자기 자신 메시지 무시
- **재현**: 봇이 자기 응답으로 다시 트리거되어 무한 루프가 발생하는 상황을 강제하기 위해, 응답 텍스트에 `ping`을 포함한 메시지를 봇이 보내도록 임시 변경하지 않더라도, `bot_id` 필드가 채워진 이벤트가 들어왔을 때 핸들러가 조기 반환하는지를 단위 테스트 또는 로그로 확인.
- **기대**: 봇 자신의 메시지 이벤트에는 응답하지 않으며 INFO 로그도 과도하게 남기지 않는다.

---

## 6. 가정 · 제약

### 6.1 기술 / 비용

- Python 3.11+ (`ai/` 디렉토리 컨벤션 — `docs/prd/cost-aware-llm-pipeline.md` §6과 정렬).
- 추가 의존성: `slack-bolt` 1개 (Socket Mode 클라이언트 포함). 라이선스/비용 영향 없음(MIT, OSS).
- 무료 Socket Mode 사용. 회사 Slack 워크스페이스의 앱 설치/스코프 관리 권한이 사용자에게 있다고 가정.
- **로컬 머신이 켜져 있을 때만 동작**. 노트북 절전·네트워크 단절 시 메시지는 큐잉되지 않으며, 온라인 복귀 후 받지 못한 이벤트는 Slack의 Socket Mode 재전송 정책을 따른다(별도 보장 X).
- 토큰은 **환경변수 또는 git에 추적되지 않는 `.env` 파일**로만 관리한다. PRD·코드·커밋·로그 어디에도 토큰 값이 포함되지 않는다.

### 6.2 사전조건 — 사용자가 Slack 앱 콘솔에서 수동 설정 (개발 시작 전 완료 가정)

- App: `Hayoung AI Coordinator` (이미 등록됨)
- **Socket Mode** 활성화
- **App-Level Token** (`xapp-...`) 발급, scope: `connections:write`
- **Bot Token Scopes** (OAuth & Permissions): `app_mentions:read`, `im:history`, `im:read`, `im:write`, `chat:write`
- **Event Subscriptions** 활성화 → `Subscribe to bot events` 에 `message.im` 추가
- 워크스페이스에 봇 **재설치**(스코프 변경 시 필수)
- 로컬에 환경변수 설정:
  - `SLACK_BOT_TOKEN=xoxb-...`
  - `SLACK_APP_TOKEN=xapp-...`
  - `SLACK_ALLOWED_USER_IDS=U0AE7A54NHL` (생략 시 기본값 동일)
  - (선택) `LOG_LEVEL=INFO`

### 6.3 보안

- 토큰은 코드/PRD/커밋에 **하드코딩 금지**. `.env`는 `.gitignore`에 포함 확인(없으면 본 작업과 함께 추가).
- 화이트리스트 외 발신자에게는 응답을 보내지 않는다 — 외부 사용자 노이즈/오·발송 방지.
- `app_mentions:read` 스코프는 가지고 있더라도 **MVP에서는 채널 멘션에 응답하지 않는다**(스코프 회수는 필요 시 추후).

### 6.4 일정 / 운영

- 로컬 데몬이므로 배포·CI 변경 없음. DevOps의 push 게이트(§AGENTS.md)는 평소대로.
- 사용자 1인(이하영) 단독 사용을 가정. 멀티유저는 향후 PRD에서 다룸.

---

## 7. 참고

- 저장소 루트 `AGENTS.md` — PRD 양식, 라벨 플로우
- `docs/agents/pm.md` — PM 작성 원칙
- `docs/prd/cost-aware-llm-pipeline.md` — `ai/` 디렉토리 Python 3.11+ 컨벤션 선례
- `ai/requirements.txt` — 의존성 추가 대상 파일
- 기존 아웃바운드 흐름: `docs/agents/devops.md` 및 최근 커밋 `docs: Slack MCP 셋업 가이드 추가 및 .mcp.json gitignore 등록`
- 사용자 메모리 노트: 회사 Slack 동료 가시성, 봇 표시명에 트레이딩 도메인 노출 금지

---

## 부록 A. 로컬 실행 방법 (개발자/QA용)

> 사용자 노출 메시지가 아니므로 본 부록은 컴플라이언스 검사 대상이 아니지만, 그래도 외부 노출 키워드를 쓰지 않는다.

### A.1 1회성 셋업

1. Slack 앱 콘솔에서 §6.2 사전조건을 모두 완료한다.
2. 저장소 루트 `.env` (또는 셸 rc) 에 다음을 설정한다:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_ALLOWED_USER_IDS=U0AE7A54NHL
   ```
3. 가상환경 활성화 후 의존성 설치:
   ```
   pip install -r ai/requirements.txt
   ```

### A.2 실행

```
python -m ai.coordinator.main
```

연결 로그가 뜨면 Slack에서 `Hayoung AI Coordinator` DM에 `ping` 입력 → 5초 내 `pong` 회신을 확인한다.

### A.3 종료

`Ctrl+C` — 데몬이 graceful 하게 빠진다.

### A.4 트러블슈팅 요약

- 시작 즉시 토큰 형식 에러 → §6.2 환경변수 prefix 확인.
- 연결은 되는데 응답이 없다 → 발신자 user id가 `SLACK_ALLOWED_USER_IDS`에 포함됐는지, `message.im` 이벤트가 구독되어 있는지 확인.
- `not_allowed_token_type` 류 에러 → Socket Mode 토큰(`xapp-`)과 Bot Token(`xoxb-`)을 바꿔 넣었는지 확인.

---

## 부록 B. 향후 확장 (참고만; 본 PRD 범위 아님)

- 명령 → `ai/` 파이프라인(예: `select_model`/`invoke_llm` 호출) 또는 `backend/` 주문·리스크 모듈 연동
- 멀티유저 화이트리스트·권한 분리
- Slash 커맨드, Block Kit 인터랙티브(버튼·모달)
- 클라우드 배포(Cloud Run, Lambda, ECS) 및 컨테이너화
- 메시지 큐잉/재시도 보장, 메트릭 대시보드
