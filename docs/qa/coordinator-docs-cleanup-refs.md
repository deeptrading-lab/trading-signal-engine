# QA 리포트 — coordinator-docs-cleanup-refs

- PRD: [`docs/prd/coordinator-docs-cleanup-refs.md`](../prd/coordinator-docs-cleanup-refs.md)
- PR: [#22](https://github.com/deeptrading-lab/trading-signal-engine/pull/22) (`feature/coordinator-docs-cleanup-refs`)
- 커밋: `6a7b8e4` (구현), `88a190a` (PRD)
- Issue: #21 (P2)
- 검증일: 2026-05-01
- 검증 모드: 자동 grep 위주 (docs-only 정정, PR #19 동일 패턴)

---

## 0. 요약 판정

| AC | 항목 | 판정 |
|----|------|------|
| AC-1 | `docs/references/`·`docs/rules/` 단어 경계 grep — 평문 0건 (운영 예외 제외) | **PASS** |
| AC-2 | SSoT 참조 정확성 (`ai/coordinator/_compliance.py::FORBIDDEN_KEYWORDS`) | **PASS** |
| AC-3 | 회귀 sanity (`pytest ai/tests/`) | **PASS** (174 passed) |
| AC-4 | PR/커밋/PRD 본문 평문 0건 (예외 제외) | **PASS** |
| AC-5 | PR 본문에 `Closes #21` 포함 | **PASS** |

**최종 판정: qa-auto-passed (실패 0건)**

---

## 1. 검증 환경

- 브랜치: `feature/coordinator-docs-cleanup-refs` (HEAD `6a7b8e4`)
- 비교 베이스: `main`
- 변경 파일 4건 (PRD 1, references 2, rules 1)
- SSoT: `ai/coordinator/_compliance.py:32` `FORBIDDEN_KEYWORDS` 정의 확인

---

## 2. AC별 검증

### AC-1 — `docs/references/`·`docs/rules/` 평문 0건 (운영 예외 제외)

**재현 절차**

```
$ grep -rEn '\b(<도메인 키워드 alternation 정규식 — 자세한 정의는 SSoT 모듈 참조>)\b' \
    docs/references/ docs/rules/ -i
```

**기대 결과**: 운영 예외(GitHub URL 저장소 슬러그) 제외 매치 0건.

**실제 결과**

```
docs/references/everything-claude-code.md:241:## 🧠 trading-signal-engine 기준 이식 후보
```

- 전체 매치: **1건**
- 모두 `trading-signal-engine` 저장소 슬러그 — PRD §6 운영 예외(GitHub URL 저장소명).
- 평문 매치 (운영 예외 제외): **0건**.

→ **PASS**.

---

### AC-2 — SSoT 참조 정확성

**재현 절차**

```
$ grep -n 'ai/coordinator/_compliance.py' \
    docs/references/slack-mcp-setup.md \
    docs/references/everything-claude-code.md \
    docs/rules/backend.md
```

**기대 결과**: 정정된 4개 위치 모두 정확한 SSoT 경로(`ai/coordinator/_compliance.py`) + 심볼(`FORBIDDEN_KEYWORDS`)로 표기.

**실제 결과**

| 파일:라인 | SSoT 표기 |
|-----------|-----------|
| `docs/rules/backend.md:3` | `[\`ai/coordinator/_compliance.py\`](../../ai/coordinator/_compliance.py)` + `FORBIDDEN_KEYWORDS` |
| `docs/references/slack-mcp-setup.md:168` | 동일 패턴 |
| `docs/references/everything-claude-code.md:277` | 동일 패턴 |
| `docs/references/everything-claude-code.md:419` | 동일 패턴 |

- 모듈 sanity: `ai/coordinator/_compliance.py:32`에 `FORBIDDEN_KEYWORDS: frozenset[str]` 정의 확인.
- 상대 경로(`../../ai/coordinator/_compliance.py`) 모두 PR 변경 파일 위치 기준 정확.

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
........................................................................ [ 41%]
........................................................................ [ 82%]
..............................                                           [100%]
174 passed in 0.34s
```

→ 174 passed, 0 failed. **PASS**.

---

### AC-4 — PR/커밋/PRD 본문 평문 0건

**재현 절차**

```
$ gh pr view 22 --json body -q '.body' \
    | grep -nEi '\b(<도메인 키워드 alternation>)\b'
$ git log -1 --format=%B 6a7b8e4 \
    | grep -nEi '\b(<도메인 키워드 alternation>)\b'
$ git log -1 --format=%B 88a190a \
    | grep -nEi '\b(<도메인 키워드 alternation>)\b'
$ grep -nEi '\b(<도메인 키워드 alternation>)\b' \
    docs/prd/coordinator-docs-cleanup-refs.md
```

**기대 결과**

- 커밋 메시지: 운영 예외 외 매치 0건.
- PRD 본문: 운영 예외(`trading-signal-engine` 저장소 슬러그) 외 매치 0건.
- PR 본문: 매치 모두 운영 예외 또는 검사 정규식 메타 카테고리.

**실제 결과**

| 대상 | 매치 | 분류 |
|------|------|------|
| PR #22 본문 | 2건 (line 26, 33) | 검사 정규식 인용 1건 + `trading-signal-engine` 저장소 슬러그 1건. 평문 인용 0건. |
| 커밋 `6a7b8e4` 메시지 | 0건 | clean |
| 커밋 `88a190a` 메시지 | 0건 | clean |
| 본 PRD `coordinator-docs-cleanup-refs.md` | 3건 → 운영 예외 제외 시 0건 | line 3·36·41 모두 GitHub URL 저장소 슬러그 (`trading-signal-engine`) |

PR 본문 매치 일별:

```
26:$ grep -rEn '\b(...)\b' docs/references/ docs/rules/ -i   # 검사 정규식 메타
33:`everything-claude-code.md:241`의 `trading-signal-engine`  # 저장소 슬러그 운영 예외
```

→ 모두 운영 예외 카테고리. **PASS**.

---

### AC-5 — PR 본문 `Closes #21`

**재현 절차**

```
$ gh pr view 22 --json body -q '.body' | grep -n 'Closes #21'
```

**기대 결과**: 1건 이상 매치.

**실제 결과**

```
- [x] **AC-5**: 본 PR 본문에 `Closes #21` 포함
Closes #21
```

→ **PASS**.

---

## 3. 추가 점검 (PRD 비범위 영역)

### 3.1 정정 패턴 일관성

PR #16·#19 패턴(평문 → 메타 표현 + SSoT 참조 한 줄)을 4개 위치 모두 동일하게 적용.

| 위치 | 정정 방식 |
|------|-----------|
| `slack-mcp-setup.md:168` | Slack 채널 예시 평문(`#signal-engine`) → `#release-notes` + 정책 안내 인라인 |
| `everything-claude-code.md:275→277` | 외부 스킬 식별자 평문(섹션 헤딩) → 일반어 헤딩 + blockquote SSoT 참조 |
| `everything-claude-code.md:417→419` | Top 3 항목명 평문 → 메타 표현 + 인라인 §1 참조 + SSoT 참조 |
| `backend.md:1,3` | 헤딩 부제(`Trading Core`) 일반어(`도메인 코어`)로 변경 + blockquote SSoT 참조 추가 |

산문 흐름에 어색함 없음, 의미 손실 없음.

### 3.2 SSoT 모듈 import sanity

```
$ python -m pytest ai/tests/ -q   # 174 passed
```

SSoT 모듈 import 부수효과 없음.

### 3.3 PRD §6 예외 카테고리 검증

PRD §6은 두 가지 운영 예외만 인정:
1. 검사 정규식 메타 (alternation 패턴 인용)
2. GitHub URL `trading-signal-engine` 저장소명

본 PR 잔존 매치 1건(`everything-claude-code.md:241`)은 카테고리 2에 정확히 부합 — 헤딩 본문이 GitHub 저장소명을 직접 가리키는 산문 인용.

---

## 4. 에지 케이스

docs-only 정정 PR로 런타임·외부 의존성·네트워크 영향 없음.

| 시나리오 | 위험도 | 확인 |
|---------|--------|------|
| 거래소 서버 다운 | 영향 없음 | 코드 무변경 |
| 네트워크 지연 | 영향 없음 | 코드 무변경 |
| API 레이트리밋 | 영향 없음 | 코드 무변경 |
| 뉴스 피드 장애 | 영향 없음 | 코드 무변경 |
| 회귀(코드 import 부수효과) | PASS | `pytest ai/tests/` 174 passed |
| SSoT 상대 경로 깨짐 | PASS | `../../ai/coordinator/_compliance.py` 4건 모두 유효 |
| 후속 PRD에서 잔존 평문 재유입 | 본 PR 범위 외 | `docs/agents/` 등은 PRD §4 비범위 — 후속 이슈로 분리 |

---

## 5. 자동화 명령 로그

```
$ git rev-parse HEAD
6a7b8e44121e997fdfdca86fe24329b7a965ec56

$ git diff main..feature/coordinator-docs-cleanup-refs --stat
 docs/prd/coordinator-docs-cleanup-refs.md  | 44 ++++++++++++++++++++
 docs/references/everything-claude-code.md  |  6 +-
 docs/references/slack-mcp-setup.md         |  2 +-
 docs/rules/backend.md                      |  4 +-
 4 files changed, 51 insertions(+), 5 deletions(-)

$ grep -rEn '\b(<도메인 키워드>)\b' docs/references/ docs/rules/ -i
docs/references/everything-claude-code.md:241:## 🧠 trading-signal-engine 기준 이식 후보
# (운영 예외만 잔존, 평문 0건)

$ python -m pytest ai/tests/ -q
174 passed in 0.34s
```

---

## 6. 최종 판정

- AC-1 ~ AC-5 모두 **PASS**.
- 실패 0건, 블로킹 0건.
- 라벨 갱신 권고: `impl-ready` → **`qa-auto-passed`**.
