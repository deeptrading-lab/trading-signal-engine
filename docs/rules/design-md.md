# DESIGN.md 포맷 가이드

이 저장소의 모든 디자인 가이드(`docs/design/<slug>.md`)는 **Google Labs `DESIGN.md` 포맷**을 따른다.
원본 스펙: <https://github.com/google-labs-code/design.md> (현재 버전 `alpha`).

## 왜 이 포맷인가
- **에이전트 간 일관성**: ux-designer가 정의한 토큰을 frontend-dev·reviewer가 동일한 키로 참조한다.
- **자동 검증**: `npx @google/design.md lint`가 깨진 토큰 참조·WCAG AA 대비비(4.5:1)·고립 토큰을 잡아준다.
- **상호운용성**: Tailwind theme / W3C DTCG `tokens.json`으로 export 가능 → frontend 구현 시 토큰을 코드에 직접 주입.

## 파일 구조

한 파일에 두 레이어가 들어간다.

1. **YAML front matter** — 머신 판독용 디자인 토큰 (정규값). `---` 펜스로 감싼다.
2. **Markdown 본문** — "왜 이 값인가"를 사람·에이전트가 읽는 근거.

```md
---
version: alpha
name: <디자인 시스템 이름>
description: <한 줄 요약, 선택>
colors:
  primary: "#1A1C1E"
  secondary: "#6C7278"
  tertiary: "#B8422E"
  neutral: "#F7F5F2"
typography:
  h1:
    fontFamily: Public Sans
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: -0.02em
  body-md:
    fontFamily: Public Sans
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.neutral}"
    rounded: "{rounded.sm}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.primary}"
---

# <slug> 디자인 가이드

## Overview
브랜드 톤·타겟 사용자·느낌의 방향 (예: "전문 트레이더용, 정보 밀도 우선, 차분한 톤").

## Colors
- **Primary (#1A1C1E)**: 핵심 텍스트·헤드라인. ...
- **Tertiary (#B8422E)**: 액션 트리거 전용. ...

## Typography
- **Headlines**: Public Sans Semi-Bold — 신뢰감.
- **Body**: Public Sans Regular 16px — 가독성.

## Layout
12-col grid, 8px 베이스라인. ...

## Components
- `button-primary`: CTA 한 화면에 1개 원칙. ...

## Do's and Don'ts
- ✅ 토큰 참조(`{colors.primary}`)로만 색을 사용한다.
- ❌ 원시 hex 값을 컴포넌트 영역에 직접 박지 않는다.
```

## 토큰 타입

| 타입 | 형식 | 예시 |
|:---|:---|:---|
| Color | `#` + sRGB 헥스 | `"#1A1C1E"` |
| Dimension | 숫자 + 단위(`px`, `em`, `rem`) | `48px`, `-0.02em` |
| Token Reference | `{path.to.token}` | `{colors.primary}` |
| Typography | `fontFamily`, `fontSize`, `fontWeight`, `lineHeight`, `letterSpacing`, `fontFeature`, `fontVariation` 객체 | 위 예시 참조 |

`components` 영역에서만 합성 토큰 참조(`{typography.label-md}`)가 허용된다. 그 외에는 원시 값으로 해석된다.

## 섹션 순서 (고정)

존재하는 섹션은 아래 순서를 지켜야 한다 (생략은 허용).

1. **Overview** (alias: "Brand & Style")
2. **Colors**
3. **Typography**
4. **Layout** (alias: "Layout & Spacing")
5. **Elevation & Depth** (alias: "Elevation")
6. **Shapes**
7. **Components**
8. **Do's and Don'ts**

## 컴포넌트 변형

hover/active/pressed 등 상태는 별도 컴포넌트 키로 표현한다.

```yaml
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
  button-primary-hover:
    backgroundColor: "{colors.primary}"
  button-primary-disabled:
    backgroundColor: "{colors.secondary}"
```

허용 속성: `backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`, `height`, `width`.

## 검증 (CLI)

작성·수정 후 lint를 통과해야 한다. ux-designer는 산출 직전, frontend-dev는 구현 시작 전 실행.

```bash
npx @google/design.md lint docs/design/<slug>.md
```

| 룰 | 심각도 | 검사 내용 |
|:---|:---|:---|
| `broken-ref` | error | `{colors.primary}` 참조가 정의된 토큰을 가리키지 않음 |
| `missing-primary` | warning | `colors`에 `primary` 누락 |
| `contrast-ratio` | warning | 컴포넌트 `backgroundColor`/`textColor` 쌍이 WCAG AA(4.5:1) 미달 |
| `orphaned-tokens` | warning | 정의됐지만 어떤 컴포넌트도 참조하지 않는 색 토큰 |
| `missing-typography` | warning | 색만 있고 타이포가 없음 (에이전트가 기본 폰트로 폴백) |
| `section-order` | warning | 섹션 순서가 표준에서 벗어남 |
| `token-summary` | info | 섹션별 토큰 개수 요약 |

PR 본문에 lint 결과(JSON 또는 요약)를 첨부한다.

### 두 버전 비교

기존 디자인을 수정할 때는 회귀 검사를 돌린다.

```bash
npx @google/design.md diff docs/design/<slug>.md docs/design/<slug>-v2.md
```

### 코드 동기화 (필요 시)

frontend가 Tailwind를 쓸 경우, 토큰을 직접 export 해서 테마에 주입한다.

```bash
npx @google/design.md export --format tailwind docs/design/<slug>.md > frontend/tailwind.theme.json
npx @google/design.md export --format dtcg docs/design/<slug>.md > frontend/tokens.json
```

## 에이전트별 책임

- **ux-designer**: `docs/design/<slug>.md`를 위 포맷으로 작성. 산출 직전 `lint` 통과 필수. 토큰 이름은 `primary`/`secondary`/`tertiary`/`neutral` 컨벤션 우선.
- **frontend-dev**: front matter의 토큰을 **그대로** 사용. 색·간격을 코드에 하드코딩하지 않는다. 토큰 부족 시 ux-designer에게 PRD·디자인 문서 갱신 요청.
- **reviewer**: 디자인 토큰 미준수(하드코딩된 hex/px) 발견 시 변경 요청.

## 참고

- 스펙 원문: <https://github.com/google-labs-code/design.md/blob/main/docs/spec.md>
- 영감을 받은 표준: [W3C Design Token Format Module](https://tr.designtokens.org/format/)
