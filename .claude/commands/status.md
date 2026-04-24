---
description: 모든 slug의 진행 현황·블록·우선순위를 보고한다. read-only. 실행·라벨 변경 없음.
argument-hint: [<slug>] [--write] [--for <user>]
---

사용자가 `/status $ARGUMENTS` 를 호출했다. **manager 서브에이전트**(read-only)를 Agent 툴로 호출해 현황 리포트를 받아온다.

## 인자 파싱
- 위치 인자 1개가 있으면 → `mode=slug-detail`, `slug=<name>`
- 없으면 → `mode=summary`
- `--write` 포함 → `write=true` (manager가 `docs/STATUS.md`에 리포트 저장)
- `--for <user>` → 해당 사용자 기준으로 우선순위 추천

## 실행
```
Agent(subagent_type="manager", prompt="""
mode: <summary|slug-detail>
slug: <없으면 생략>
for: <github-user, 기본은 `git config user.name` 또는 현재 사용자>
write: <true|false>

AGENTS.md의 핸드오프 표와 GitHub 라벨 플로우를 기준으로 모든 slug의 현재 단계를 판정하고, 블록·경고·추천 액션을 리포트하라. read-only 원칙을 엄격히 지켜라.
""")
```

## 출력 처리
- manager가 반환한 리포트를 **그대로 사용자에게 표시**.
- `--write`를 지정했는데 `docs/STATUS.md` 갱신이 안 됐으면 manager에게 재시도 요청.
- 사용자가 추천 액션을 따르겠다고 하면 **별도로 `/pipeline`을 실행**하도록 안내 (manager는 절대 실행 트리거하지 않음).

## 중단 조건
- manager가 read-only 원칙을 위반하려 하면(예: 라벨 변경 시도) 즉시 중단하고 사용자에게 경고.
- `gh` 인증 실패 시 설치·인증 안내를 보여주고 중단.
