# PRD: coordinator-compliance-module

> 작성자: PM 에이전트
> 작성일: 2026-05-01
> 대상 디렉터리: `ai/coordinator/` (Python / Slack Bolt)
> UI: 없음
> Issue: [#8 컴플라이언스 가드 모듈화](https://github.com/deeptrading-lab/trading-signal-engine/issues/8)
> 라벨: `enhancement`, `priority:P1`
> 출처: PR #3 리뷰 발견 4 / QA §5.3

---

## 1. 배경 / 문제

회사 Slack 워크스페이스는 동료 가시성이 있는 환경이고, 코디네이터 봇 표시명·응답 텍스트·로그 등 외부 노출 텍스트에는 특정 도메인 키워드(영문 예: `signal`, `trade`, `trading`, `desk`, `quant`, `finance`, `market`, `ticker`, `pnl`)가 등장해서는 안 된다. 이는 봇 네이밍 제약과 동일한 정책이다.

현재 이 정책의 검사 책임은 **두 곳에 흩어져 있고, 한쪽은 비어 있다.**

1. **테스트 모듈 로컬에 묶인 헬퍼**
   - `ai/tests/test_coordinator_handlers.py` 안에 로컬 상수 `FORBIDDEN_KEYWORDS` 와 헬퍼 `assert_no_forbidden_keywords` 가 정의되어 있다.
   - 다른 테스트 파일이 같은 검사를 하려면 코드를 복사하거나 import 경로를 우회해야 한다 — 사실상 재사용 불가능한 상태.
   - 한 테스트 파일에서만 검사가 도는 동안 다른 코디네이터 진입점(예: `app_mention` 응답이 활성화될 경우)은 검증 사각지대로 남는다.

2. **runtime 보호 부재**
   - 응답 발사 경로(`say(...)`)나 `logger.info(...)` 메시지에 키워드가 섞여 들어가도 자동 감지되는 장치가 없다.
   - 미래에 새 명령(예: `/help`, `/status` 응답 추가)이나 LLM 생성 응답이 코디네이터에 붙을 때, **코드 변경 시점의 회귀로 키워드가 외부에 새어 나갈 위험**이 있다.

흩어진 책임을 **단일 모듈**로 모으고, **테스트 + runtime** 양쪽에서 같은 정의를 공유하면 회귀 위험을 구조적으로 줄일 수 있다.

**요약 문제**: 컴플라이언스 키워드 검사 책임이 (a) 테스트 모듈 로컬에 잠겨 있고, (b) runtime 응답 발사 경로에는 아예 없다.

---

## 2. 목표

무엇이 달라지면 성공인가.

- **G1 (단일 정의)**: 금지 키워드 목록과 검사 헬퍼는 `ai/coordinator/_compliance.py` **단 한 곳**에서 정의된다. 다른 파일은 import만 한다.
- **G2 (테스트 일관성)**: 모든 코디네이터 테스트가 같은 헬퍼를 import해 사용한다. 로컬 복제본은 0개.
- **G3 (runtime 보호)**: `say()` 로 외부에 발사되는 모든 응답 텍스트가 발사 직전에 자동으로 검사된다. 매치 발견 시 원본은 차단되고, 사용자에게는 도메인 정보 없는 fallback 응답이 발사되며, ERROR 로그가 남는다.
- **G4 (재사용성)**: 모듈은 외부에서 import 가능하지만 모듈명에 `_` prefix를 붙여 "내부 가드" 의도를 명시한다. 다른 패키지(예: `ai/llm/`)가 동일 검사가 필요해질 때 같은 헬퍼를 재사용할 수 있다.
- **G5 (회귀 0)**: 기존 145개 테스트가 모두 통과하며, 새 모듈 자체에 단위 테스트가 추가된다.

---

## 3. 범위 (In scope)

이번 PRD에서 반드시 포함한다.

### 3.1 신규 모듈 `ai/coordinator/_compliance.py`

다음 3가지 공개 심볼을 노출한다 (모듈명은 `_` prefix, 심볼명은 일반).

1. `FORBIDDEN_KEYWORDS: frozenset[str]`
   - 도메인 금지 키워드의 **단일 정의 지점**.
   - 초기값(영어, 소문자): `signal`, `trade`, `trading`, `desk`, `quant`, `finance`, `market`, `ticker`, `pnl`.
   - 추가/삭제 시 이 모듈만 수정한다.

2. `find_forbidden_keywords(text: str) -> list[str]`
   - 텍스트에서 발견된 금지 키워드를 **정렬·중복 제거된 리스트**로 반환한다.
   - 대소문자 무시(`re.IGNORECASE`).
   - **단어 경계** 기준(`\b`) — 영단어로 등장할 때만 매치. 식별자 부분 매치는 회피한다(예: `signature`는 `signal`로 매치되지 않음).
   - 매치 없으면 빈 리스트.

3. `assert_no_forbidden(text: str, *, context: str = "") -> None`
   - `find_forbidden_keywords(text)` 가 비어 있지 않으면 `AssertionError` 를 raise.
   - 에러 메시지에 `context` 값과 발견된 키워드 목록을 포함한다 — 테스트 실패 시 어느 응답 경로인지 즉시 식별 가능하도록.
   - 테스트에서 사용하기 위한 헬퍼이며, runtime 코드는 이 함수 대신 `find_forbidden_keywords` 를 직접 사용한다(아래 3.3 참조).

모듈 docstring은 영어/한국어 어떤 언어든 무방하나 **본 모듈 자체에도 금지 키워드가 등장해서는 안 된다.** docstring 예시·설명은 일반어("도메인 키워드", "외부 노출 텍스트") 수준으로만 표기한다.

### 3.2 기존 테스트 마이그레이션

- `ai/tests/test_coordinator_handlers.py`
  - 로컬 `FORBIDDEN_KEYWORDS` 상수 제거.
  - 로컬 `assert_no_forbidden_keywords` 헬퍼 제거.
  - 두 호출 지점을 `from ai.coordinator._compliance import assert_no_forbidden` 로 교체.
- `ai/tests/conftest.py` 는 **신규 작성하지 않는다.** 이번 범위에서는 fixture 자동 주입 불필요(테스트 파일이 직접 import하면 충분).
- 기존 테스트의 검사 의도(어떤 응답 경로에 어떤 키워드가 없어야 하는지)는 그대로 유지한다 — 헬퍼만 교체.

### 3.3 Runtime 보호 — `say()` 응답 텍스트 검사

`ai/coordinator/main.py` (또는 `handlers.py`) 에 다음 헬퍼를 추가한다.

- 헬퍼명: `safe_say(say, text: str, *, context: str = "") -> None`
  - 내부에서 `find_forbidden_keywords(text)` 호출.
  - **매치 없음 → 원본 텍스트 그대로 `say(text)` 호출.**
  - **매치 있음 →**
    1. 원본은 발사하지 **않는다**(차단 정책 A).
    2. fallback 메시지 발사: `say("응답 생성 중 문제가 발생했습니다. 다시 시도해 주세요.")` — fallback 자체에도 금지 키워드 없음을 단위 테스트로 보증한다.
    3. `logger.error("compliance: blocked response", extra={"context": context, "matched": <키워드 목록>})` — 실제 발견된 원문은 로그에 남기지 **않는다**(로그도 외부 노출 가능 영역). 매치된 키워드 목록만 남긴다.

기존 코디네이터 응답 경로(`/health`, `/whoami`, 기타 슬래시 명령 등) 중 사용자에게 텍스트를 발사하는 모든 지점은 직접 `say(...)` 대신 `safe_say(say, ...)` 를 호출하도록 교체한다.

**정책 결정 (PM 확정)**: 옵션 A(강제 차단 + fallback) 채택. 외부 노출 차단이 모니터링보다 우선이며, 회귀가 발견되면 ERROR 로그로 즉시 알 수 있다.

### 3.4 단위 테스트

- `ai/tests/test_coordinator_compliance.py` (신규)
  - `find_forbidden_keywords` 5종 케이스: (1) 매치 없음, (2) 단일 매치, (3) 다중 매치 + 정렬·중복 제거, (4) 대소문자 혼합, (5) 단어 경계 — 부분 문자열은 매치 안 함(`signature`로 검증).
  - `assert_no_forbidden` 2종: 매치 시 `AssertionError`, `context` 값이 메시지에 포함됨.
  - `safe_say` 2종: 매치 없는 텍스트는 원본 발사 / 매치 있는 텍스트는 차단 + fallback 발사 + ERROR 로그(mock `say`, mock `logger`).
- 기존 `test_coordinator_handlers.py` 는 마이그레이션 후 회귀 통과 확인.

### 3.5 가이드 문서 갱신

- `docs/references/slack-coordinator-bot-setup.md` §5 (보안/운영 체크리스트) 에 한 줄 추가:
  - "응답 발사 시 도메인 키워드 자동 검사 적용 — `ai/coordinator/_compliance.py`"

---

## 4. 비범위 (Out of scope)

이번 PRD에서 다루지 않는다.

1. **로그 메시지 자동 검사** — `logger.info/debug` 등 모든 로그 호출에 자동 필터를 거는 기능. 발사 횟수가 많아 false positive 부담이 크고, 핸들러·필터 설계가 별도 PRD 분량이다. 본 PRD의 runtime 보호는 **사용자 응답 텍스트(`say` 경로)에 한정**한다. 로그는 테스트 검증으로만 보호한다.
2. **다국어 키워드** — 한국어 트레이딩 용어 등. 현재 키워드 목록은 영어 한정.
3. **`backend/` Kotlin 코드의 컴플라이언스 가드** — 별도 PRD에서 다룬다.
4. **CI 파이프라인의 grep 검사** — 코드 레포지토리 전체 텍스트를 빌드 단계에서 grep하는 등의 정적 검사. 별도 작업.
5. **conftest 자동 주입 fixture** — 테스트 파일이 직접 import하면 충분하다고 판단. 추후 코디네이터 테스트 파일이 5개 이상으로 늘면 재검토.
6. **기존 키워드 목록 변경** — 본 PRD는 검사 구조의 모듈화이며, 키워드 추가·삭제는 다른 작업이다.

---

## 5. 수용 기준 (Acceptance criteria)

검증 가능한 문장으로 기술한다. QA는 각 항목당 최소 1개 이상의 테스트 항목을 만든다.

- **AC-1 (모듈 정의)**: `ai/coordinator/_compliance.py` 가 존재하고, 다음 3 심볼을 export 한다 — `FORBIDDEN_KEYWORDS`(`frozenset[str]`), `find_forbidden_keywords`, `assert_no_forbidden`.
- **AC-2 (단어 경계)**: `find_forbidden_keywords("signature analysis")` 는 빈 리스트를 반환한다(부분 매치 없음). `find_forbidden_keywords("Signal received")` 는 `["signal"]` 을 반환한다(대소문자 무시 + 단어 경계 매치).
- **AC-3 (정렬·중복 제거)**: 동일 키워드가 여러 번 등장하거나 여러 키워드가 섞여 있을 때, 반환 리스트는 **정렬되고 중복이 제거된** 형태다.
- **AC-4 (테스트 마이그레이션)**: `ai/tests/test_coordinator_handlers.py` 는 로컬 `FORBIDDEN_KEYWORDS` / `assert_no_forbidden_keywords` 정의를 더 이상 갖지 않는다(`grep` 으로 0건). 대신 `ai.coordinator._compliance` 를 import 한다.
- **AC-5 (runtime 차단)**: `safe_say(say, "test text contains signal here")` 호출 시 — (a) 원본 텍스트가 `say` 인자로 전달되지 않는다, (b) fallback 메시지("응답 생성 중 문제가 발생했습니다. 다시 시도해 주세요.")가 `say` 로 발사된다, (c) `logger.error` 가 정확히 1회 호출되며 `extra={"matched": ["signal"], ...}` 를 포함한다.
- **AC-6 (runtime 통과)**: `safe_say(say, "안녕하세요. 도움이 필요하신가요?")` 호출 시 — 원본 텍스트가 `say` 로 그대로 발사되고, ERROR 로그는 발생하지 않는다.
- **AC-7 (fallback 자체 검증)**: fallback 메시지 텍스트를 `find_forbidden_keywords` 에 넣었을 때 빈 리스트를 반환한다(자기 자신이 정책 위반이 되는 일이 없음을 보증).
- **AC-8 (회귀)**: 기존 145개 테스트 + 신규 테스트가 모두 통과한다 (`pytest ai/tests/`).
- **AC-9 (가이드 갱신)**: `docs/references/slack-coordinator-bot-setup.md` §5 에 새 모듈 경로가 한 줄 추가되어 있다.
- **AC-10 (정책 노출 0)**: 본 PRD 본문, 새 모듈 코드·docstring, 신규 테스트 파일, 가이드 갱신분, 커밋 메시지, PR 본문 어디에도 도메인 키워드(`signal`/`trade`/`trading`/`desk`/`quant`/`finance`/`market`/`ticker`/`pnl`) 의 영단어 노출이 없다 — **테스트 케이스 안의 입력 문자열은 예외**(검사 대상이므로 필연적으로 포함). 단, 테스트 파일은 외부에 직접 발사되지 않으므로 정책 위반이 아니다.

---

## 6. 가정·제약

- **Python**: 3.11+ 가정 (기존 `ai/` 와 동일). `frozenset[str]` 제네릭 표기 사용 가능.
- **의존성**: 표준 라이브러리만 사용. 신규 패키지 추가 없음.
- **검사 스코프**: "사용자 노출 텍스트" 한정. 코드 식별자, import 문(`from signal import ...` 같은 표준 라이브러리 모듈명 등)은 검사 대상이 아니다 — `_compliance.py` 자체는 텍스트만 받으며, AST/소스 파싱은 하지 않는다.
- **단어 경계 정의**: Python `re` 모듈의 `\b` 를 그대로 사용한다. 멀티바이트(한글) 경계는 정의되지 않으므로, 영문 단어 매칭 외 동작은 보장하지 않는다(다국어는 비범위).
- **로그 마스킹**: ERROR 로그에 원본 텍스트를 적지 않는다 — 매치된 키워드 목록만 적는다. 로그도 운영자에게 노출되는 채널이라는 가정.
- **fallback 메시지 텍스트**: "응답 생성 중 문제가 발생했습니다. 다시 시도해 주세요." 로 고정. 변경 시 PRD 갱신 필요.
- **정책 옵션 (확정)**: 옵션 A(차단 + fallback). 옵션 B(경고만)는 채택하지 않는다.
- **모듈명**: `_compliance` 의 underscore prefix는 "내부 가드" 의도 표시일 뿐 import를 막지는 않는다. 외부에서 `from ai.coordinator._compliance import ...` 가능.

---

## 7. 참고

- GitHub Issue: [#8 컴플라이언스 가드 모듈화](https://github.com/deeptrading-lab/trading-signal-engine/issues/8)
- 출처:
  - PR #3 리뷰 발견 4 (응답 발사 경로의 runtime 보호 부재)
  - QA §5.3 (테스트 헬퍼가 한 모듈에 잠겨 있어 다른 진입점 검증 사각지대)
- 관련 파일:
  - `ai/coordinator/main.py` — `say()` 호출 지점
  - `ai/coordinator/handlers.py` — 슬래시 명령 핸들러
  - `ai/tests/test_coordinator_handlers.py` — 마이그레이션 대상 테스트
  - `docs/references/slack-coordinator-bot-setup.md` §5 — 가이드 갱신 대상
- 정책 출처:
  - 봇 네이밍 제약(동료 가시성 회사 Slack에서 도메인 노출 금지) — 본 PRD가 텍스트 노출 영역으로 확장 적용
- 후속 작업(별도 Issue/PRD 후보):
  - 로그 메시지 자동 검사 (filter handler)
  - `backend/` Kotlin 컴플라이언스 가드
  - CI 단계 정적 grep 검사
  - 다국어 키워드 확장
