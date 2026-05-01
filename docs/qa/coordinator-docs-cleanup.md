# QA 리포트 — coordinator-docs-cleanup

- PRD: [`docs/prd/coordinator-docs-cleanup.md`](../prd/coordinator-docs-cleanup.md)
- PR: [#19](https://github.com/deeptrading-lab/trading-signal-engine/pull/19) (`feature/coordinator-docs-cleanup`)
- 커밋: `28a42fd` (구현), `dd23ec8` (PRD)
- Issue: #17 (P2)
- 검증일: 2026-05-01
- 검증 모드: 자동 grep 위주 (docs-only 정정)

---

## 0. 요약 판정

| AC | 항목 | 판정 |
|----|------|------|
| AC-1 | `docs/prd/`·`docs/qa/` 단어 경계 grep — 평문 0건 (운영 예외 제외) | **PASS** |
| AC-2 | SSoT 참조 정확성 (`ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`) | **PASS** |
| AC-3 | 회귀 sanity (`pytest ai/tests/`) | **PASS** (166 passed) |
| AC-4 | PR/커밋/PRD 본문 평문 0건 (예외 제외) | **PASS** |
| AC-5 | PR 본문에 `Closes #17` 포함 | **PASS** |

**최종 판정: qa-auto-passed (실패 0건)**

---

## 1. 검증 환경

- 브랜치: `feature/coordinator-docs-cleanup` (HEAD `28a42fd`)
- 비교 베이스: `main`
- 변경 파일 11건 (PRD 6, QA 5)
- SSoT 키워드 9개 — `ai/coordinator/_compliance.py:32-44` `FORBIDDEN_KEYWORDS`

---

## 2. AC별 검증

### AC-1 — `docs/prd/`·`docs/qa/` 평문 0건 (운영 예외 제외)

**재현 절차**

```
$ grep -rEn '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b' docs/prd/ docs/qa/ -i | wc -l
$ grep -rEn '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b' docs/prd/ docs/qa/ -i | grep -v 'trading-signal-engine'
```

**기대 결과**: 운영 예외(GitHub URL 저장소 슬러그 `trading-signal-engine`, 검사 정규식 메타) 제외 매치 0건.

**실제 결과**

- 전체 매치: **36건**
- `trading-signal-engine` 저장소 슬러그 제외: **2건**
- 그 2건 모두 `docs/qa/coordinator-code-chore.md:229,349` — 본 PR 비변경 파일이며 같은 줄에 "GitHub 저장소 URL 슬러그" 주석으로 운영 예외 명시 (선례: PR #14 QA §3.3, PRD §6).

**본 PR이 수정한 파일 11건만 한정 grep**

```
$ git diff main..feature/coordinator-docs-cleanup --name-only -- docs/prd/ docs/qa/ \
    | xargs grep -EHn '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b' -i \
    | grep -v 'trading-signal-engine'
(no output)
```

→ 본 PR 변경 파일에서 운영 예외 외 평문 매치 **0건**. **PASS**.

---

### AC-2 — SSoT 참조 정확성

**재현 절차**

```
$ grep -rEHn 'FORBIDDEN_KEYWORDS' docs/prd/ docs/qa/
```

**기대 결과**: 정정 문서에 `ai/coordinator/_compliance.py`의 `FORBIDDEN_KEYWORDS` SSoT 참조 표기가 일관되게 사용된다.

**실제 결과**

- 정정 패턴 핵심 문구: `정확한 정책 목록은 [\`ai/coordinator/_compliance.py\`](../../ai/coordinator/_compliance.py)의 \`FORBIDDEN_KEYWORDS\` 단일 정의 지점을 참조` — 9건 이상에서 동일 패턴.
- 변형 표기 (`ai.coordinator._compliance.FORBIDDEN_KEYWORDS`, `ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`)도 산문 흐름에 맞게 사용되며 모두 SSoT 모듈·심볼 정확.
- 실제 SSoT 위치 검증: `ai/coordinator/_compliance.py:32-44`에 `FORBIDDEN_KEYWORDS: frozenset[str]` 정의 확인.

→ **PASS**.

---

### AC-3 — 회귀 sanity check

**재현 절차**

```
$ python -m pytest ai/tests/ -q
```

**기대 결과**: 코드 변경 없음 → 기존 테스트 모두 통과.

**실제 결과**

```
........................................................................ [ 43%]
........................................................................ [ 86%]
......................                                                   [100%]
166 passed in 0.29s
```

→ 166 passed, 0 failed. **PASS**.

---

### AC-4 — PR/커밋/PRD 본문 평문 0건

**재현 절차**

```
$ gh pr view 19 --json body -q '.body' | grep -nEi '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b'
$ git log -1 --format=%B 28a42fd | grep -nEi '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b'
$ git log -1 --format=%B dd23ec8 | grep -nEi '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b'
$ grep -nEi '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b' docs/prd/coordinator-docs-cleanup.md | grep -v 'trading-signal-engine'
```

**기대 결과**

- 커밋 메시지·PRD 본문: 운영 예외 외 매치 0건.
- PR 본문: 매치 모두 운영 예외 카테고리.

**실제 결과**

| 대상 | 매치 | 분류 |
|------|------|------|
| PR #19 본문 | `signal` x6, `trading` x6 (총 12건) | 모두 `trading-signal-engine` 저장소 슬러그 또는 운영 예외 설명 라인. 평문 인용 0건. |
| 커밋 `28a42fd` 메시지 | 0건 | clean |
| 커밋 `dd23ec8` 메시지 | 0건 | clean |
| 본 PRD `coordinator-docs-cleanup.md` (운영 예외 제외) | 0건 | clean |

PR 본문 매치 라인 일별:

```
43:# 운영 예외 제외(저장소 슬러그 trading-signal-engine 카테고리)
45:$ grep ... | grep -v 'trading-signal-engine' | wc -l
49:$ grep ... | grep -v 'trading-signal-engine' | wc -l
54:- GitHub URL 내 저장소명 `trading-signal-engine`
55:- 절대 경로(`/Applications/.../trading-signal-engine`) 내 저장소 슬러그
75:본 PR 본문·커밋 메시지·본 PRD ... 등장하지 않음(저장소 URL `trading-signal-engine` 운영 예외 제외).
```

→ 모두 운영 예외 카테고리. **PASS**.

---

### AC-5 — PR 본문 `Closes #17`

**재현 절차**

```
$ gh pr view 19 --json body -q '.body' | grep -n 'Closes #17'
```

**기대 결과**: 1건 이상 매치.

**실제 결과**

```
7:Closes #17
23:- [x] **AC-5**: 본 PR 본문에 `Closes #17` 포함.
```

→ **PASS**.

---

## 3. 추가 점검 (PRD 비범위 영역)

### 3.1 다른 docs 영역 잔존 평문 grep

**재현 절차**

```
$ grep -rEn '\b(signal|trade|trading|desk|quant|finance|market|ticker|pnl)\b' \
    docs/references/ docs/agents/ docs/rules/ docs/design/ -i \
    | grep -v 'trading-signal-engine'
```

**결과 (참고용)**

```
docs/references/everything-claude-code.md:275: ### 1. `llm-trading-agent-security` ⭐ ...
docs/references/everything-claude-code.md:417: 2. **llm-trading-agent-security 체크리스트** → ...
docs/references/slack-mcp-setup.md:168: - "내 #signal-engine 채널 최근 메시지 10개 보여줘"
docs/rules/backend.md:1: # Backend 규칙 (Trading Core)
```

- `docs/agents/`·`docs/design/` 0건.
- `docs/references/`·`docs/rules/` 4건 잔존.

**판정**: 본 PRD §4(비범위)에서 "PRD 외 영역(`README`, `references/` 등) 정정 — 잔존 발견 시 후속 이슈로 분리"로 명시되어 본 PR 스코프 외. **블로킹 아님 — 후속 이슈 분리 권고**.

### 3.2 메타 표현 산문 가독성

샘플 점검 대상: `docs/qa/slack-coordinator-inbound.md`, `docs/qa/coordinator-compliance-module.md`, `docs/prd/slack-message-subtype-guard.md`.

- 평문 나열을 `도메인 키워드` 메타 표현 + SSoT 참조 한 줄로 우회한 패턴 일관.
- 검사 정규식 인용은 `<도메인 키워드 alternation 정규식 — 자세한 정의는 SSoT 모듈 참조>` 메타 표기로 대체 (PR #16 선례 동일).
- 표준 라이브러리 시그널 처리 코드 블록은 의사코드(`<표준 시그널 모듈로 ...>`)로 메타화 — 의미 손실 없음.
- 산문 흐름에 어색함 없음, 추가 정정 사유 없음.

### 3.3 SSoT 모듈 sanity

```
$ python -c "from ai.coordinator._compliance import FORBIDDEN_KEYWORDS; print(len(FORBIDDEN_KEYWORDS))"
```

→ 9 (PRD에 명시된 SSoT 9개 키워드와 일치). 모듈 import 성공.

---

## 4. 에지 케이스

docs-only 정정 PR로 런타임/외부 의존성·네트워크 영향 없음.

| 시나리오 | 위험도 | 확인 |
|---------|--------|------|
| 거래소 서버 다운 | 영향 없음 | 코드 무변경 |
| 네트워크 지연 | 영향 없음 | 코드 무변경 |
| API 레이트리밋 | 영향 없음 | 코드 무변경 |
| 뉴스 피드 장애 | 영향 없음 | 코드 무변경 |
| 회귀(코드 import 부수효과) | PASS | `pytest ai/tests/` 166 passed |
| SSoT 링크 깨짐 | PASS | `ai/coordinator/_compliance.py` 존재, 라인 번호(`32-44`) 정확 |
| 후속 PRD에서 잔존 평문 재유입 | 외부 영역 4건 잔존 (PRD 비범위) | 후속 이슈 권고 |

---

## 5. 자동화 명령 로그

```
$ git rev-parse HEAD
28a42fd...

$ git diff main..feature/coordinator-docs-cleanup --stat
 docs/prd/coordinator-compliance-module.md | 14 ++++----
 docs/prd/coordinator-docs-cleanup.md      | 46 ++++++++++++++++++++++
 docs/prd/coordinator-dotenv-autoload.md   |  4 +--
 docs/prd/cost-aware-llm-pipeline.md       |  2 +-
 docs/prd/slack-coordinator-inbound.md     |  8 ++---
 docs/prd/slack-message-subtype-guard.md   |  5 ++-
 docs/qa/coordinator-compliance-cleanup.md | 28 ++++++++--------
 docs/qa/coordinator-compliance-module.md  | 36 ++++++++++----------
 docs/qa/coordinator-dotenv-autoload.md    |  4 +--
 docs/qa/slack-coordinator-inbound.md      | 56 ++++++++++++-----------------
 docs/qa/slack-message-subtype-guard.md    | 16 ++++-----
 11 files changed, 129 insertions(+), 90 deletions(-)

$ python -m pytest ai/tests/ -q
166 passed in 0.29s
```

---

## 6. 권고 (비블로킹)

- **후속 이슈 분리 권고**: `docs/references/everything-claude-code.md`, `docs/references/slack-mcp-setup.md`, `docs/rules/backend.md`에 잔존 평문 4건. 본 PRD §4 비범위 — 신규 P3 이슈로 분리 검토.

---

## 7. 최종 판정

- AC-1 ~ AC-5 모두 **PASS**.
- 실패 0건, 블로킹 0건.
- 라벨 갱신 권고: `impl-ready` → **`qa-auto-passed`**.
