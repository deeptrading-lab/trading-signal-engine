# QA — session-notes-read-mandate

- 대상 PR: [#40 feature/session-notes-read-mandate](https://github.com/deeptrading-lab/trading-signal-engine/pull/40)
- 범위: docs-only (AGENTS.md, .claude/agents/manager.md, .claude/commands/status.md)
- 변경 규모: +24 / -5, 3 files
- 판정: **qa-passed**

## 수용 기준 표

| # | AC | 결과 | 검증 방법 / 근거 |
|---|----|----|------------------|
| 1 | AGENTS.md 진입 안내(line 6 근방)에 SESSION_NOTES + HANDOFF 둘 다 명시 + 읽는 순서(SESSION_NOTES 먼저) 명확 | PASS | `grep -n "SESSION_NOTES" AGENTS.md` → line 6 진입 callout에 "`docs/SESSION_NOTES.md`의 최신 1~2개 항목 + `docs/HANDOFF.md`의 최근 5개 항목을 먼저 읽는다" 로 SESSION_NOTES 가 앞에 배치됨. "둘은 보완 관계이며 어느 쪽도 건너뛰지 않는다" 명시. |
| 2 | AGENTS.md 문서 표(line 14 근방)에 `docs/SESSION_NOTES.md` 행 추가 + 책임 분담 | PASS | line 15 `docs/HANDOFF.md` 행이 "PR 단위 작업 인수인계 로그" 로 갱신, line 16 `docs/SESSION_NOTES.md` 신규 행 "세션 단위 자유서술 메모. 사용자 합의·우선순위·미결 결정 등 자동화로 못 잡는 맥락" 으로 책임 분담 명시. |
| 3 | AGENTS.md "작업 인수인계" 섹션에 두 파일 보완 관계 + 시작 전 읽는 순서 + 누락 시 사례 | PASS | line 240 섹션 제목이 "작업 인수인계 (HANDOFF + SESSION_NOTES)" 로 변경. line 244–245 두 파일의 책임 분담을 bullet 으로 정리. line 247–250 "시작 전" 절차에 1) SESSION_NOTES 최신 1~2개 → 2) HANDOFF 최근 5개 순서 명시. line 250 "둘 중 한쪽만 읽으면 사용자 합의를 무시한 권고를 하게 된다(2026-05-06 사례)" 로 누락 시 사례 인용. |
| 4 | `.claude/agents/manager.md` "작업 시작 전 필수 read" 절 신설 + 리포트 끝 read 사실 1줄 강제 | PASS | line 10–17 "## 작업 시작 전 필수 read (의무)" 섹션 신설. 두 파일을 "반드시" 읽도록 의무 부여. line 17 "리포트 본문 끝에 두 파일을 실제로 읽었음을 1줄로 명시한다" 강제 문구 포함. |
| 5 | `.claude/commands/status.md` manager 호출 프롬프트에 동일 의무 + 직전 세션 합의 반영 지시 | PASS | line 24 신규 라인 "**필수**: 리포트 작성 전 `docs/SESSION_NOTES.md` 최신 1~2개 항목과 `docs/HANDOFF.md` 최근 5개 항목을 먼저 읽고, 직전 세션의 사용자 합의·미결 결정(예: \"PRD 검토 후 PR 등록\", \"untracked 보류는 의도적\")을 권고에 반영하라. 리포트 끝에 두 파일을 실제로 읽었음을 1줄로 명시." — 의무 + 합의 반영 + 끝 1줄 명시 모두 충족. |
| 6 | 도메인 키워드 평문 노출 0건 | PASS | `git diff origin/main..origin/feature/session-notes-read-mandate \| grep -iE "^\+" \| grep -iE "signal\|trade\|desk\|ticker\|order book\|candle\|trading" \| grep -v "trading-signal-engine"` → 출력 없음. 신규 추가 라인 어디에도 트레이딩 도메인 키워드 평문 노출 없음. |
| 7 | 기존 자동화·다른 에이전트 정의에 영향 0건 (3개 파일로 한정) | PASS | `git diff --name-only` 결과 정확히 `.claude/agents/manager.md`, `.claude/commands/status.md`, `AGENTS.md` 3개. `.github/workflows/handoff-append.yml` diff 비어 있음. 다른 `.claude/agents/*.md` (coordinator-*, qa.md, dev.md 등) 무변경. |

## 재현 절차 — AC별 상세

### AC1: AGENTS.md 진입 안내
- 절차: `grep -n "SESSION_NOTES" AGENTS.md` 실행 후 line 6 확인.
- 기대: SESSION_NOTES 가 HANDOFF 보다 앞에 언급되고, "먼저 읽는다" 명시.
- 실제: line 6 callout 에서 "SESSION_NOTES.md의 최신 1~2개 항목 + HANDOFF.md의 최근 5개 항목을 먼저 읽는다" 순서로 정확히 배치됨. PASS.

### AC2: AGENTS.md 문서 표
- 절차: AGENTS.md line 11–18 문서 표 영역에서 SESSION_NOTES 행 존재 여부 확인.
- 기대: `docs/SESSION_NOTES.md` 행이 추가되고, HANDOFF 와 책임이 분리(자유서술 vs 자동 로그).
- 실제: line 15 (HANDOFF) "PR 단위 자동 append" / line 16 (SESSION_NOTES) "세션 단위 자유서술 메모" — 책임 분담 명료. PASS.

### AC3: AGENTS.md "작업 인수인계" 섹션
- 절차: AGENTS.md line 240 부근 섹션 본문 확인.
- 기대: 섹션 제목이 두 파일을 모두 포함, 시작 전 읽는 순서 단계화, 누락 사례 인용.
- 실제: 제목 "작업 인수인계 (HANDOFF + SESSION_NOTES)", bullet 으로 두 파일 분담, "시작 전" 절차가 1→2 번호로 순서화, "(2026-05-06 사례)" 누락 결과 명시. PASS.

### AC4: manager.md 의무 절
- 절차: `.claude/agents/manager.md` line 10–17 확인.
- 기대: "작업 시작 전 필수 read" 또는 동급 제목, 리포트 끝 read 1줄 강제.
- 실제: "## 작업 시작 전 필수 read (의무)" 섹션 신설. "리포트 본문 끝에 두 파일을 실제로 읽었음을 1줄로 명시한다" 강제 문구 포함. PASS.

### AC5: status.md 프롬프트 의무
- 절차: `.claude/commands/status.md` line 24 확인.
- 기대: manager 호출용 인라인 프롬프트에 두 파일 read 의무 + 합의 반영 + 끝 1줄 명시.
- 실제: 신규 라인이 세 요건 모두 포함, 예시까지 제공("PRD 검토 후 PR 등록", "untracked 보류는 의도적"). PASS.

### AC6: 컴플라이언스 (도메인 키워드 평문 노출)
- 절차: `git diff origin/main..origin/feature/session-notes-read-mandate | grep "^+" | grep -iE "signal|trade|desk|ticker|order book|candle"` 실행.
- 기대: 매치 0건 (기존 라인 `trading-signal-engine` 리포 이름 제외).
- 실제: 매치 0건. PASS.

### AC7: 회귀 (변경 파일 한정)
- 절차: `git diff --name-only origin/main..origin/feature/session-notes-read-mandate` 실행.
- 기대: 정확히 3개 파일 — `AGENTS.md`, `.claude/agents/manager.md`, `.claude/commands/status.md`.
- 실제: 정확히 3개 파일 일치. `.github/workflows/handoff-append.yml`, 다른 에이전트 정의 모두 무변경. PASS.

## 에지 케이스

| 시나리오 | 영향 | 결과 |
|----------|------|------|
| `docs/SESSION_NOTES.md` 파일이 아직 존재하지 않는 신규 클론 | 의무 read 가 read 실패로 끝날 수 있음 | 본 PR 범위 밖. SESSION_NOTES 파일 자체는 별도 PR 에서 도입됨(저장소 현재 상태에 파일 존재). 추후 fresh clone 환경에서 빈 SESSION_NOTES.md 도 허용되는지는 후속 점검 권장. |
| 두 파일이 모순되는 정보를 담을 때 | manager 가 어느 쪽을 우선할지 불명확 | manager.md/status.md 모두 "SESSION_NOTES = 사용자 합의 우선" 으로 안내(`status.md` 예시: "PRD 검토 후 PR 등록"). 우선순위 충돌 시 SESSION_NOTES 우위가 암묵적으로 명시됨. |
| Reviewer 가 PR 본문 `## 다음 작업` 섹션만 읽고 SESSION_NOTES 를 무시 | 자동 HANDOFF append 만 의존 시 합의 누락 가능 | AGENTS.md line 247–250 에서 "둘 중 한쪽만 읽으면 사용자 합의를 무시한 권고를 하게 된다" 로 명시 경고. 사람·AI 모두 적용. |
| `handoff-append.yml` 워크플로우가 SESSION_NOTES 도 자동 append 하려 시도 | 자유서술 본질 훼손 | 본 PR 은 워크플로우 무변경, SESSION_NOTES 는 수동 작성 영역으로 유지. AC7 검증으로 변경 없음 확인. |
| status 명령 캐시가 옛 프롬프트를 들고 있는 환경 | 새로운 의무가 적용 안 됨 | `.claude/commands/status.md` 는 호출 시점에 읽히는 인라인 프롬프트이므로 캐시 이슈 없음. |

## 자동화 / 수동 체크리스트

자동화 테스트 없음(docs-only). 다음 수동 검증 커맨드로 재현 가능:

```
git fetch origin feature/session-notes-read-mandate
git diff --stat origin/main..origin/feature/session-notes-read-mandate
git diff --name-only origin/main..origin/feature/session-notes-read-mandate
grep -n "SESSION_NOTES" AGENTS.md
grep -n "SESSION_NOTES\|HANDOFF" .claude/agents/manager.md
grep -n "SESSION_NOTES\|HANDOFF" .claude/commands/status.md
git diff origin/main..origin/feature/session-notes-read-mandate | grep "^+" | grep -iE "signal|trade|desk|ticker"
```

모든 커맨드 출력이 위 표의 "실제" 와 일치함을 확인.

## 종합

- AC 7건 전원 PASS, 실패 0건.
- 라벨 갱신: `qa-passed` 부여.

참고: SESSION_NOTES 최신 항목 + HANDOFF 최근 5개 항목 검토 (QA 자체에는 read 의무가 강제되진 않으나 본 PR 의 취지를 따라 확인).
