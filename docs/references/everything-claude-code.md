# Everything Claude Code (ECC) 레퍼런스

> 출처: https://github.com/affaan-m/everything-claude-code
> 조사 일자: 2026-04-25
> 목적: 필요 시 선별적으로 훅·에이전트·스킬·보안 도구를 이식하기 위한 참고 노트

## 📦 레포 개요

| 항목 | 값 |
|------|----|
| 이름 | affaan-m/everything-claude-code (ECC) |
| 생성 | 2026-01-18 |
| 최근 푸시 | 2026-04-23 |
| Stars | 166,019 |
| Forks | 25,771 |
| License | MIT |
| 주 언어 | JavaScript |
| 설명 | Agent harness performance optimization system. Skills, instincts, memory, security, research-first development for Claude Code, Codex, OpenCode, Cursor and beyond. |

---

## 🧩 디렉터리 구조 (실측)

```
everything-claude-code/
├── agents/              # 48개 특화 에이전트
├── skills/              # 183개 워크플로우 스킬 (주 인터페이스)
├── commands/            # 79개 레거시 슬래시 커맨드
├── rules/               # 언어별/공통 가이드
│   ├── common/
│   ├── typescript/
│   ├── python/
│   ├── golang/
│   ├── swift/
│   └── php/
├── hooks/               # 8개 이벤트 훅 자동화
├── mcp-configs/         # 14개 MCP 서버 설정
├── scripts/             # Node.js 크로스플랫폼 스크립트
├── manifests/           # 플러그인 매니페스트
├── plugins/
├── research/
├── schemas/
├── src/
├── tests/
├── examples/
├── contexts/
├── docs/
├── ecc2/                # Rust 컨트롤 플레인 (알파)
├── ecc_dashboard.py     # Tkinter 데스크톱 GUI
├── .claude-plugin/
├── .claude/
├── .cursor/             # Cursor IDE 어댑터
├── .codex/              # Codex CLI 어댑터
├── .codex-plugin/
├── .opencode/           # OpenCode 플러그인 (31개 커맨드)
├── .gemini/
├── .trae/
├── .kiro/
├── .codebuddy/
├── .agents/
├── .mcp.json
├── agent.yaml
├── install.sh / install.ps1
├── README.md / README.zh-CN.md
├── CLAUDE.md / AGENTS.md / RULES.md
├── SECURITY.md / EVALUATION.md
├── the-shortform-guide.md
├── the-longform-guide.md
├── the-security-guide.md
├── COMMANDS-QUICK-REF.md
├── WORKING-CONTEXT.md
├── REPO-ASSESSMENT.md
└── SOUL.md
```

---

## 🎮 주요 에이전트 (48개 중 발췌)

| 에이전트 | 용도 |
|---------|------|
| planner | 기능 계획 (`/ecc:plan "OAuth 추가"`) |
| architect | 시스템 설계 |
| code-reviewer | 코드 품질/보안 검토 |
| security-reviewer | OWASP 취약점 분석 |
| tdd-guide | 테스트 주도 개발 |
| build-error-resolver | 빌드 에러 수정 |
| e2e-runner | Playwright E2E 테스트 |
| python-reviewer | Python 코드 검토 |
| typescript-reviewer | TS/JS 코드 검토 |
| java-reviewer | Java/Spring Boot 검토 |
| rust-reviewer | Rust 코드 검토 |
| pytorch-build-resolver | PyTorch/CUDA 에러 해결 |

---

## ⚡ 주요 슬래시 커맨드 (79개 중 발췌)

| 커맨드 | 설명 |
|--------|------|
| `/ecc:plan` | 구현 계획 수립 |
| `/tdd` | 테스트 주도 개발 |
| `/code-review` | 코드 검토 |
| `/build-fix` | 빌드 에러 수정 |
| `/e2e` | E2E 테스트 생성 |
| `/security-scan` | AgentShield 보안 감시 |
| `/refactor-clean` | 데드 코드 제거 |
| `/learn-eval` | 패턴 추출 및 평가 |
| `/multi-plan` | 다중 에이전트 계획 |
| `/pm2` | PM2 서비스 관리 |
| `/sessions` | 세션 히스토리 |
| `/skill-create` | Git 히스토리에서 스킬 생성 |

---

## 🔗 훅(Hook) 시스템

8개 이벤트 유형을 지원:

- `SessionStart` — 세션 시작 시 컨텍스트 로드
- `SessionEnd` — 세션 종료 시 상태 저장 / 패턴 추출
- `PreToolUse` — 도구 실행 전 검증·차단
- `PostToolUse` — 파일 수정 후 자동 포맷팅, 타입체크
- `Stop` — 세션 중단 시 훅

예시 (console.log 경고 훅):
```json
{
  "matcher": "tool == \"Edit\" && tool_input.file_path matches \"\\.(ts|tsx|js|jsx)$\"",
  "hooks": [{
    "type": "command",
    "command": "grep -n 'console\\.log' \"$file_path\" && echo '[Hook] console.log 제거' >&2"
  }]
}
```

---

## 📡 MCP 서버 (14개)

| 서버 | 기능 |
|------|------|
| GitHub | 코드 리포·이슈·PR 접근 |
| Supabase | PostgreSQL, 인증 |
| Vercel | 배포·환경 변수 |
| Playwright | E2E 브라우저 자동화 |
| Context7 | 소스 코드 검색 |
| Exa | 웹/회사 뉴럴 검색 |
| Sequential Thinking | 깊은 추론 (Opus 전용) |
| Memory | 세션 메모리 저장 |

---

## 🔒 AgentShield — 보안 스캐너

```bash
npx ecc-agentshield scan          # 기본 검사
npx ecc-agentshield scan --opus   # Opus 3중 분석
npx ecc-agentshield scan --fix    # 자동 수정
```

검사 항목:
- 비밀키 패턴 (sk-, ghp_, AKIA …) 탐지
- 권한 감시
- MCP 서버 위험 평가
- 훅 인젝션 분석

---

## 💰 토큰 최적화 규약

```json
{
  "model": "sonnet",
  "env": {
    "MAX_THINKING_TOKENS": "10000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"
  }
}
```

효과(레포 주장치):
- Sonnet 사용 → ~60% 비용 감소
- 생각 토큰 제한 → ~70% 숨겨진 비용 감소
- 선택적 `/compact` 커맨드로 컨텍스트 관리

---

## 🚀 설치

### 플러그인(권장)
```bash
/plugin marketplace add https://github.com/affaan-m/everything-claude-code
/plugin install everything-claude-code@everything-claude-code

# rules/는 플러그인으로 배포 불가 → 수동 복사
mkdir -p ~/.claude/rules
cp -R rules/common ~/.claude/rules/
cp -R rules/typescript ~/.claude/rules/
```

### 수동
```bash
git clone https://github.com/affaan-m/everything-claude-code.git
cd everything-claude-code
cp agents/*.md ~/.claude/agents/
cp -r rules/common ~/.claude/rules/
bash ./install.sh --target claude --modules hooks-runtime
```

### 대시보드
```bash
npm run dashboard
# 또는
python3 ./ecc_dashboard.py
```

---

## 🌐 지원 하네스

| 플랫폼 | 상태 | 핵심 파일 |
|--------|------|----------|
| Claude Code | 기본 | `.claude-plugin/plugin.json` |
| Cursor IDE | 완전 지원 | `.cursor/hooks/adapter.js` |
| Codex (macOS+CLI) | 완전 지원 | `.codex/config.toml` |
| OpenCode | 31개 커맨드 | `.opencode/opencode.json` |
| Gemini / Trae / Kiro / CodeBuddy | 각 어댑터 존재 | `.gemini/`, `.trae/`, `.kiro/`, `.codebuddy/` |
| Antigravity | 실험 | `.agents/` |

---

## 📚 공식 가이드

- the-shortform-guide.md — 설정·기초 (필독)
- the-longform-guide.md — 토큰 최적화·메모리·평가·병렬화
- the-security-guide.md — 공격 벡터·샌드박싱·CVE

---

## 🧠 trading-signal-engine 기준 이식 후보

현재 우리 레포는 이미 PM→UX→Dev→QA→Reviewer→DevOps 파이프라인 + 라벨 기반 상태 머신이 잡혀 있어서 ECC를 통째로 얹을 필요는 없다. 선별 도입 후보만 정리.

### 우선도 높음
- **hooks 모듈** — PostToolUse 자동 포맷/타입체크, SessionEnd 패턴 추출. 우리 라벨 업데이트 자동화와 궁합이 좋음
- **AgentShield** (`npx ecc-agentshield scan`) — 비밀키·MCP·훅 인젝션 스캐너. reviewer / security 단계에 보강 가능
- **토큰 최적화 규약** — `MAX_THINKING_TOKENS`, autocompact 설정. 장기 세션 비용 절감

### 우선도 중간
- **language별 reviewer 에이전트** — 우리 `reviewer`를 Python(ai/) / Kotlin(backend/) 전문으로 쪼갤 때 참고
- **skill-create 패턴** — git 히스토리에서 재사용 가능한 스킬을 추출하는 아이디어

### 우선도 낮음 / 비도입
- 멀티 하네스 어댑터(.cursor / .codex / .opencode …) — 현재 Claude Code 단일 하네스로 충분
- ecc2 Rust 컨트롤 플레인 — 알파 단계
- Tkinter 대시보드 — 우리 워크플로와 무관

---

## ⚠️ 주의할 점

- 디렉터리 수가 방대하고 멀티 하네스 어댑터가 엉켜 있어, 통째 복사 시 현재 에이전트 규약과 충돌 위험
- 훅·MCP 설정은 임의 커맨드 실행 권한을 전제로 하므로 보안 리뷰 후 선별 적용 권장
- stars·skill 개수 등 수치는 레포 README 기준이며 빠르게 변동 가능 — 이식 전 최신 상태 재확인 필요

---

## 🔬 우선 검토 스킬 상세 요약

아래는 실제로 내용을 받아 확인한 6개 스킬의 요약. 원문은 `skills/<name>/SKILL.md`.

---

### 1. 자율 에이전트 보안 스킬 ⭐ (reviewer / backend-dev)

> 외부 스킬 식별자(도메인 키워드 포함)는 ECC 레포(`hesreallyhim/awesome-claude-code-agents`)에서 직접 확인. 사내 문서에 평문 인용은 회피한다 — 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조.

**톤**: 지갑·트랜잭션 권한을 가진 자율 에이전트의 보안 패턴. 표본은 Web3/on-chain(지갑 키, MEV, 슬리피지)이지만 **패턴은 CEX·선물 API에도 전용 가능**.

**핵심 레이어(다 중첩해야 함)**:
1. **Prompt injection을 금융 공격으로 취급** — 외부 텍스트(뉴스, 티커, 웹훅)가 실행 프롬프트에 들어가기 전 정규식 필터. 패턴 예: `ignore previous instructions`, `transfer ... to`, `approve ... for`.
2. **Hard spend limits** — 모델 출력과 **독립된** 단건/일일 금액 가드 (`SpendLimitGuard.check_and_record`).
3. **Simulate before send** — 전송 전 `eth_call` 시뮬레이션 + `min_amount_out` 필수.
4. **Circuit breaker** — 연속 손실 N회 / 시간당 낙폭 초과 시 자동 halt.
5. **Wallet isolation** — 세션 자금만 담긴 전용 핫월렛. 키는 env·시크릿 매니저에서만.
6. **MEV/deadline 보호** — private RPC(Flashbots), per-strategy 슬리피지 bps, 트랜잭션 deadline.

**Pre-deploy 체크리스트**(레포 발췌):
- 외부 데이터는 LLM 컨텍스트 진입 전 sanitize
- 스펜드 리미트는 모델 출력과 독립 실행
- 모든 트랜잭션은 시뮬레이션 후 전송, `min_amount_out` 의무
- Circuit breaker는 drawdown·비정상 상태에서 정지
- 키는 env/시크릿 매니저에서만
- 성공·실패 모든 에이전트 결정은 audit log

**우리 레포 이식 포인트**:
- `backend/`(Kotlin 주문 실행기)의 **SpendLimitGuard**·**CircuitBreaker** 패턴 이식 → `docs/rules/backend.md`에 규약으로
- `ai/`(LangGraph 신호 생성)의 **injection 필터** — 뉴스·SNS 피드 파이프라인 앞단
- `reviewer` 에이전트 체크리스트에 6개 레이어를 항목으로 추가

---

### 2. `ai-regression-testing` ⭐ (qa)

**톤**: "같은 모델이 코드도 쓰고 리뷰도 하면 같은 블라인드스팟을 공유한다"는 문제 정의. 해결책 = 자동 테스트.

**AI가 반복하는 회귀 패턴 4종**:
1. **Sandbox/production 경로 불일치** — 한쪽만 수정해서 응답 shape이 깨짐 (가장 빈번)
2. **SELECT 절 누락** — 응답 필드 추가했는데 DB select에 빠짐
3. **Error state leakage** — 에러 set하면서 이전 데이터 clear 누락
4. **낙관적 업데이트 롤백 누락** — API 실패 시 UI 복원 안 됨

**운영 원칙**:
- "발견된 버그에 대해서만" 테스트 작성 (커버리지 목표 금지)
- 버그 발견 즉시 테스트 작성(가능하면 수정 전에)
- 테스트는 구현이 아닌 **응답 shape**을 검증
- 빠르게 유지(샌드박스 모드로 DB 없이 < 1s)

**bug-check 워크플로**:
```
Step 1: 자동 테스트 실행 (npm test / build)  ← 실패 = 최상위 버그
Step 2: AI 코드 리뷰 (알려진 블라인드스팟 기준)
Step 3: 수정한 각 버그에 회귀 테스트 작성
```

**우리 레포 이식 포인트**:
- `qa` 에이전트 체크리스트에 **"에지 케이스 + 경로 parity 검사"** 섹션 추가
- `docs/qa/<slug>.md` 템플릿에 "회귀 테스트 명(BUG-Rn)" 필드
- `ai/` 신호 생성기는 mock/live 모드 parity가 생명 — 가장 직접적인 적용처
- 샌드박스 모드 테스트 헬퍼(`createTestRequest`) 패턴을 Python pytest로 포팅 가치 있음

---

### 3. `cost-aware-llm-pipeline` ⭐ (backend-dev / ai)

**4가지 축을 합성한 파이프라인**:

1. **모델 라우팅** — 텍스트 길이·아이템 개수 임계치로 Haiku↔Sonnet 자동 선택
   ```python
   if text_length >= 10_000 or item_count >= 30: return SONNET
   else: return HAIKU  # 3-4x 저렴
   ```
2. **불변 CostTracker** — `@dataclass(frozen=True, slots=True)`, `add()`는 새 tracker 반환
3. **좁은 재시도** — `APIConnectionError`, `RateLimitError`, `InternalServerError`만 재시도(지수 백오프). 인증·검증 오류는 즉시 실패.
4. **Prompt caching** — 긴 system prompt에 `cache_control: {"type": "ephemeral"}`

**2025-2026 가격표**(레포 기재):
| Model | Input $/1M | Output $/1M | Rel |
|-------|-----------|------------|-----|
| Haiku 4.5 | $0.80 | $4.00 | 1x |
| Sonnet 4.6 | $3.00 | $15.00 | ~4x |
| Opus 4.5 | $15.00 | $75.00 | ~19x |

**우리 레포 이식 포인트**:
- `ai/` 시그널 파이프라인에 거의 **즉시 이식 가능** — 뉴스 요약/분류는 Haiku, 복합 추론은 Sonnet
- 배치 작업 앞단에 `BudgetExceededError` 가드 배치
- `docs/rules/ai.md`에 "비용 가드레일" 규약으로 명문화

---

### 4. `eval-harness` ⭐ (qa)

**EDD(Eval-Driven Development)** — 평가를 AI 개발의 단위 테스트로 취급.

**평가 유형**:
- **Capability eval** — 새로 할 수 있는 것 정의 (pass/fail 기준 체크박스)
- **Regression eval** — 기존 기능 깨지지 않는지

**Grader 3종**:
- Code-based (결정적): `grep -q`, `npm test`, build
- Model-based (LLM-as-judge): 1-5점 + 이유
- Human: 보안·민감 영역

**메트릭**:
- `pass@1`, `pass@3` (k번 중 1번 이상 성공)
- `pass^3` (3번 연속 성공, 릴리스 게이트용)
- 권장치: capability `pass@3 >= 0.90`, regression `pass^3 = 1.00`

**워크플로**: Define → Implement → Evaluate → Report. `.claude/evals/<feature>.md`에 정의, `.log`에 실행 이력.

**Anti-patterns**: 알려진 eval 예시에 프롬프트 과적합, happy-path만 측정, 비용/지연 드리프트 무시, 플래키 grader 릴리스 게이트 통과.

**우리 레포 이식 포인트**:
- `qa` 에이전트가 `docs/qa/<slug>.md` 작성할 때 **pass@k/pass^k** 개념으로 강화
- 신호 생성기처럼 비결정적 컴포넌트는 `pass^3` 릴리스 게이트 필수
- `.claude/evals/` 디렉터리를 추가해 eval 정의 버전 관리

---

### 5. `agent-eval` (도구 비교용 — 우선도 낮음)

YAML + git worktree로 여러 코딩 에이전트(Claude Code, Aider, Codex …)를 동일 작업에 돌려 pass rate/cost/time/consistency 비교. **별도 도구 설치 필요**(외부 레포).

**우리 레포 이식 포인트**:
- 현재는 Claude Code 단일이라 **당장 불필요**.
- 나중에 Codex/다른 에이전트 도입 검토 시 재방문.

---

### 6. `safety-guard` (devops / 운영)

**PreToolUse 훅**으로 파괴 명령(`rm -rf`, `git push --force`, `git reset --hard`, `DROP TABLE`, `kubectl delete`, `chmod 777`, `--no-verify` …) 차단. 3가지 모드:

- **Careful** — 파괴 명령 경고 + 확인
- **Freeze** — 지정 디렉터리 밖 Write/Edit 차단
- **Guard** — Careful + Freeze 동시

**우리 레포 이식 포인트**:
- `devops` 에이전트가 이미 "사용자 명시 승인 없이 push 금지" 규약을 가지고 있음 → **훅으로 기계적 강제**가 가능해짐
- 자율 실행 모드(`--dangerously-skip-permissions` 등) 쓸 때 안전망
- 우리 `.claude/settings.json`에 PreToolUse hook으로 붙이면 좋음

---

## 📌 즉시 이식 추천 Top 3

1. **cost-aware-llm-pipeline** → `ai/` 파이프라인 (비용 즉시 절감)
2. **자율 에이전트 보안 스킬 체크리스트** (위 §1 참조 — 도메인 키워드 평문 회피, 정확한 정책 목록은 [`ai/coordinator/_compliance.py`](../../ai/coordinator/_compliance.py)의 `FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조) → `reviewer` 에이전트 + `docs/rules/backend.md`
3. **ai-regression-testing 패턴 4종** → `qa` 에이전트 템플릿 + `docs/qa/` 섹션 추가

