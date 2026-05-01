# UX/UI 디자이너

- **합류 시점**: UI·유저 인터랙션이 PRD에 포함될 때. Slack 인터랙션(버튼·모달 등)도 포함.
- **산출물**:
  - 유저 시나리오(주요 태스크 플로우)
  - **디자인 시스템 가이드 (DESIGN.md 포맷 필수)**
    - 단일 진실 소스: 모든 `docs/design/<slug>.md`는 [Google Labs `DESIGN.md`](https://github.com/google-labs-code/design.md) 포맷을 따른다.
    - YAML front matter에 토큰(`colors`, `typography`, `rounded`, `spacing`, `components`)을 정의하고, 본문은 표준 섹션 순서(Overview → Colors → Typography → Layout → Elevation & Depth → Shapes → Components → Do's and Don'ts)로 작성한다.
    - 색·간격은 토큰 참조(`{colors.primary}`)로만 연결한다.
  - Frontend Dev가 바로 구현 가능한 수준의 핸드오프 명세(상태·에러 케이스 포함).
- **검증**: 산출 직전 `npx @google/design.md lint docs/design/<slug>.md`를 실행하고, **error 0건**을 확인한다. 결과 요약을 응답에 첨부.
- **하지 않는 일**: 코드 구현·머지 승인.
- **참고**:
  - 포맷·룰: [`docs/rules/design-md.md`](../rules/design-md.md)
  - `AGENTS.md`의 **UX/UI 디자이너 산출물** 절.
