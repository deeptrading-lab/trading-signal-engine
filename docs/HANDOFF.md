# HANDOFF — 작업 인수인계 로그

> 새 작업을 시작할 때 **이 파일의 최근 5개 항목**을 먼저 읽고 컨텍스트를 잡는다.
> 본인이 다시 돌아왔을 때도 동일하게 확인한다 (어디까지 했는지 잊었을 때).
>
> - **자동 append (QA 통과 시점)**: PR에 `qa-passed` 라벨이 붙으면 [.github/workflows/handoff-append.yml](.github/workflows/handoff-append.yml) 가 **그 PR의 feature 브랜치 자체에** HANDOFF 항목을 commit한다. 별도 PR을 만들지 않고 같은 PR diff에 포함되어 Reviewer가 머지 직전 최종 점검할 때 함께 검토된다.
> - **다음 작업 후보 자동 추출**: PR 본문에 `## 다음 작업` (또는 `## Next steps`, `## Follow-up`, `## 후속`) 섹션이 있으면 그 내용이 자동으로 채워진다. **절대적 지시가 아니라 후보**이므로 다음 작업자는 참고만 하고 우선순위·문맥에 따라 자유롭게 결정한다.
> - **머지 전 최종 점검**: Reviewer 또는 작성자는 머지 직전 자동 생성된 HANDOFF 항목을 읽고 사실관계·다음 작업 후보가 적절한지 확인한다. 부적절하면 그 PR에서 직접 수정 후 머지.
> - **수동 append (선택)**: 세션을 끝낼 때 PR로 안 묶이는 메모(WIP, 디버깅 발견, 후속 TODO)는 이 파일 하단에 직접 추가해도 된다.

## 포맷

각 항목은 다음 구조를 따른다.

```markdown
### YYYY-MM-DD — 제목 (#PR / slug)

- **slug**: `slug-name` · **author**: @handle
- **PR**: https://github.com/.../pull/N
- **요약**: 한 줄 요약
- **현재 상태**: main 머지됨 / 후속 필요 / 운영 모니터링 중
- **PR 본문**: PR description 발췌 (자동 채워짐)
- **다음 작업 후보**: PR 본문의 `## 다음 작업` 섹션 발췌 (자동 채워짐, 후보일 뿐 강제 아님)
```

**PR 작성 팁**: PR 본문에 `## 다음 작업` 섹션을 넣어두면 HANDOFF에 자동 반영된다. 예시:

```markdown
## 다음 작업
- 운영 환경에서 N일 모니터링 후 알림 임계값 재조정
- 관련 slug `xyz` 의 후속 PR 진행
```

수동 메모(PR 없는 경우)는 `### YYYY-MM-DD — [WIP] 제목` 형태로 적는다.

---

## 로그

<!-- 새 항목은 이 줄 아래에 자동/수동으로 append된다. 위쪽이 최신이 아니라 아래쪽이 최신이다. -->

### 2026-05-02 — [BACKFILL] HANDOFF 도입 시점 누적 컨텍스트

이 항목은 HANDOFF 자동화 도입 전의 누적 상태를 1회 정리한 것이다. 이후 항목은 PR 단위로 자동 생성된다.

- **author**: @HY0118

**최근 머지된 작업 (최신순)**

- #26 — 코디네이터 봇 셋업 가이드 갱신 (owner 메타변수 + 후속 PR 결과 반영)
- #23 — 디자인 가이드 산출물 DESIGN.md 포맷 표준화
- #22 — references/rules 잔존 도메인 키워드 평문 정정
- #20 — 코디네이터 코드 정리 (dispatcher 추출 + placeholder 가드 + 미사용 import 제거)
- #19 — 코디네이터 PRD/QA 잔존 도메인 키워드 평문 정정
- #18 — feature 브랜치 산출물 commit 규칙 추가
- #16 — 코디네이터 docstring·가이드 잔존 노출 정정
- #14 — 코디네이터 컴플라이언스 가드 모듈 분리 + 응답 발사 가드 도입
- #13 — 코디네이터 진입점 `.env` 자동 로딩
- #12 — Slack 메시지 subtype 가드 추가
- #11 — 이슈 우선순위 정책 (P0/P1/P2) 추가
- #3 — 코디네이터 인바운드 데몬 도입 (Socket Mode)

**진행 중 (open)**

- **PR #25** `feature/slack-dev-relay` — 개발 협업 Slack 봇 MVP 구현. 라벨 `impl-ready`, **QA 대기 중**. 다음 단계: QA → `qa-passed` → Reviewer → 머지.
- **PR #27** `feature/handoff-system` — 본 HANDOFF 시스템. 라벨 미부여 (이 PR이 곧 자기 자신을 검증하게 됨).
- **Issue #24** `[slack-dev-relay]` PRD-ready, P1 — PR #25 가 그 구현체.

**TODO / 다음 작업 후보 (절대적 지시 아님, 후보)**

- PR #25 QA 진행 → `qa-passed` 라벨 부여 (본 워크플로우의 첫 자가 트리거 케이스가 됨)
- PR #27 (HANDOFF 시스템) `qa-passed` → Reviewer → 머지 → 동작 검증
- HANDOFF 자동화 동작 확인 후 1~2주 운영, 본문 발췌 길이/노이즈 점검
- 본 backfill 항목은 PR #27 머지 후 첫 자동 entry 가 추가되기 전까지 임시 기준점 역할
