# PRD: cost-aware-llm-pipeline

> 작성자: PM 에이전트  
> 작성일: 2026-04-25  
> 대상 디렉터리: `ai/` (Python / LangGraph)  
> UI: 없음

---

## 1. 배경 / 문제

- `ai/` 파이프라인은 뉴스 요약·티커 분류·복합 추론 등 서로 특성이 다른 LLM 호출을 **한 가지 모델(현재 Sonnet 가정)** 로 일괄 처리하고 있다. 저가(Haiku) 모델로 충분한 단순 태스크에도 Sonnet이 호출되어 **운영 비용이 불필요하게 3~4배** 누적된다.
- **예산 가드가 없다.** 외부 피드 버스트(뉴스 급증, 웹훅 루프) 또는 재시도 폭주 시 하루 예산을 수 분 만에 소진할 수 있지만, 이를 **코드 레벨에서 강제 차단하는 장치가 없다**.
- **재시도 전략이 지나치게 넓다.** 현재는 어떤 예외든 일괄 재시도하는 경향이 있어, 인증 오류(401)·검증 오류(400) 같은 **재시도해도 복구 불가능한 오류**까지 지수적으로 비용을 증폭시킨다.
- **긴 system prompt를 매 호출마다 재전송**하고 있어 입력 토큰 단가가 그대로 누적된다. Anthropic의 prompt caching(`cache_control: ephemeral`)을 쓰면 동일 prefix 재사용 시 입력 비용이 크게 감소하지만 아직 적용되어 있지 않다.
- 외부 오픈소스 Everything Claude Code(ECC)의 `cost-aware-llm-pipeline` 스킬이 위 4가지 축을 한 묶음 패턴으로 정리해 두었고, 레퍼런스 노트(`docs/references/everything-claude-code.md` §3)에도 **"거의 즉시 이식 가능"** 으로 분류되어 있다. 지금 이식하면 이후 `ai/`에 붙는 모든 신호 생성기·분석기가 처음부터 비용 가드 위에서 동작하게 된다.

**요약 문제**: `ai/` 파이프라인에 (a) 모델 라우팅, (b) 예산 한도 가드, (c) 좁은 재시도, (d) 프롬프트 캐싱 — 이 4가지가 동시에 부재하여 비용·안정성 리스크가 있다.

---

## 2. 목표

무엇이 달라지면 성공인가.

- **G1 (비용)**: 동일 워크로드 기준 LLM 호출 **입력 비용이 30% 이상 감소**한다(모델 라우팅 + 캐싱 복합 효과). 측정은 수용 기준 AC-R1/AC-C1의 벤치 스크립트로 한다.
- **G2 (안정성)**: 예산 초과 시 파이프라인이 **추가 호출 없이 즉시 중단**되며, 호출자에게 `BudgetExceededError` 가 전파된다.
- **G3 (정확성)**: 모델 라우팅 결정이 **결정적(deterministic)** 이며, 입력 텍스트 길이와 아이템 개수만 보고 동일한 모델을 고른다(테스트 가능).
- **G4 (재시도 효율)**: 복구 불가능한 오류(인증·검증)는 **1회 시도 후 즉시 실패**, 일시 오류(연결·레이트리밋·내부 오류)만 지수 백오프로 재시도한다.
- **G5 (재사용성)**: 위 4가지는 `ai/` 안의 **공통 모듈**로 제공되어, 이후 추가되는 LangGraph 노드가 같은 가드를 공유한다.

---

## 3. 범위 (In scope)

이번 PRD에서 반드시 포함한다.

1. **모델 라우팅 유틸**
   - `ai/llm/router.py` (경로는 구현자 재량 가능, 단 `ai/` 하위 Python 모듈이어야 함).
   - 시그니처: `select_model(text_length: int, item_count: int, force: Model | None = None) -> Model`.
   - 임계치: `text_length >= 10_000` 또는 `item_count >= 30` → `SONNET`, 그 외 → `HAIKU`.
   - `force` 인자 우선: `force`가 주어지면 임계치 무시하고 해당 모델 반환.
   - 모델 식별자는 enum/Literal로 타입 고정 (`HAIKU`, `SONNET` 최소 2종; `OPUS`는 선택적 확장 지점만 남긴다).

2. **불변 CostTracker**
   - `@dataclass(frozen=True, slots=True)` 기반.
   - 필드(최소): `input_tokens: int`, `output_tokens: int`, `usd_spent: float`, `budget_usd: float`.
   - `add(*, input_tokens, output_tokens, usd)` 는 **새 CostTracker 인스턴스를 반환**(원본 변경 금지).
   - `add` 결과가 `budget_usd` 를 초과하면 `BudgetExceededError` 를 raise.
   - 모델별 단가 테이블은 상수 모듈로 분리(`ai/llm/pricing.py` 등). 2026-04 기준 가격 표(아래 "가정·제약" 참조)를 초기값으로 넣는다.

3. **좁은 재시도 데코레이터/헬퍼**
   - 재시도 대상 예외 **정확히 3종만**: `anthropic.APIConnectionError`, `anthropic.RateLimitError`, `anthropic.InternalServerError`.
   - 그 외 예외(인증 `AuthenticationError`, 검증 `BadRequestError`, 타입 오류 등)는 **재시도 없이 즉시 propagate**.
   - 지수 백오프: 초기 대기 1초, 배수 2, 지터 ±20%, 최대 5회 시도, 총 대기 상한 60초.
   - `tenacity` 등 외부 라이브러리 사용 가능하되, 재시도 대상 예외는 **명시적 allow-list** 로만 구성.

4. **프롬프트 캐싱**
   - 1,000자 이상 system prompt에 Anthropic SDK 메시지 포맷의 `cache_control: {"type": "ephemeral"}` 를 자동 부착하는 헬퍼 제공.
   - 헬퍼 시그니처(예): `build_system_block(text: str) -> list[dict]`. 반환값은 Anthropic Messages API 에 그대로 투입 가능한 형식.
   - 임계 길이(1,000자)는 상수로 분리해 조정 가능.

5. **통합 진입점**
   - `ai/` 내 신호 생성/분석 노드가 위 4가지를 한 번에 쓰도록 **얇은 호출 래퍼**(예: `invoke_llm(prompt, items, tracker, force=None) -> (response, new_tracker)`) 를 제공한다.
   - 래퍼는 (a) `select_model` 호출 → (b) `cache_control` 부착 → (c) 재시도 데코레이터 적용된 SDK 호출 → (d) 응답의 usage를 `tracker.add(...)` 로 누적 → (e) 새 tracker 반환. 이 순서를 준수한다.

6. **단위 테스트**
   - 위 1~5 각각에 대해 pytest 단위 테스트. 외부 API 호출은 mock.
   - 수용 기준(AC)을 **테스트 케이스 1:1 이상** 으로 커버.

7. **규약 문서 갱신**
   - `docs/rules/ai.md` 가 있다면 "비용 가드레일" 섹션을 추가하거나 신설. 본 PRD를 링크한다.

---

## 4. 비범위 (Out of scope)

이번 PRD에서 **하지 않는다**.

- **UI / 대시보드**: 비용 사용량 시각화, Slack 알림 연동, 관리자 화면 — 전부 다음 PRD에서 다룬다. (UI: 없음)
- **Opus 라우팅 로직**: enum에 확장 포인트만 남기고, 실제 Opus로의 라우팅 임계치·호출 경로는 구현하지 않는다.
- **Kotlin `backend/` 측 비용 가드**: 본 PRD는 `ai/` Python 한정.
- **멀티 테넌트/조직별 예산 분리**: 단일 프로세스·단일 예산만 다룬다.
- **영속 저장(DB/파일)된 누적 사용량**: `CostTracker` 는 프로세스 수명 안에서만 유효. 영속화는 후속 과제.
- **LangGraph 그래프 재설계**: 기존 노드 구조 변경 없이 "호출 래퍼"만 갈아끼운다.
- **다른 LLM 벤더(OpenAI, Bedrock 등) 라우팅**: Anthropic SDK 단일.
- **프롬프트 내용 자체의 품질 개선**(리라이팅, few-shot 튜닝): 본 PRD는 **전달 경로 비용**만 다룬다.

---

## 5. 수용 기준 (Acceptance criteria)

QA가 그대로 테스트로 변환할 수 있는 검증 가능한 문장들.

### 모델 라우팅 (AC-R)
- **AC-R1**: `select_model(text_length=10_000, item_count=0)` 는 `SONNET` 을 반환한다.
- **AC-R2**: `select_model(text_length=9_999, item_count=29)` 는 `HAIKU` 를 반환한다.
- **AC-R3**: `select_model(text_length=0, item_count=30)` 는 `SONNET` 을 반환한다.
- **AC-R4**: `select_model(text_length=0, item_count=29)` 는 `HAIKU` 를 반환한다.
- **AC-R5**: `select_model(text_length=50_000, item_count=100, force=HAIKU)` 는 `HAIKU` 를 반환한다(강제 우선).
- **AC-R6**: `select_model` 은 동일 입력에 대해 항상 동일 출력을 낸다(결정적, 랜덤/시각 의존 없음).

### CostTracker (AC-C)
- **AC-C1**: `CostTracker(..., budget_usd=1.0).add(input_tokens=..., output_tokens=..., usd=0.4)` 호출 후, 원본 인스턴스의 `usd_spent` 는 변경되지 않고(불변), 반환된 새 인스턴스의 `usd_spent` 는 기존값 + 0.4 이다.
- **AC-C2**: 누적 `usd_spent` 가 `budget_usd` 를 **초과**하는 `add` 호출은 `BudgetExceededError` 를 raise한다.
- **AC-C3**: 누적 `usd_spent` 가 `budget_usd` 와 **정확히 같아지는** `add` 호출은 성공한다(경계 동작: "초과 시" 의 정의는 strict `>`).
- **AC-C4**: `CostTracker` 인스턴스에 직접 속성 대입을 시도하면(`tracker.usd_spent = 99`) `FrozenInstanceError` 가 발생한다.
- **AC-C5**: `CostTracker` 는 `__slots__` 을 사용하여 인스턴스에 새 속성 추가 시 `AttributeError` 가 발생한다.

### 좁은 재시도 (AC-T)
- **AC-T1**: `anthropic.APIConnectionError` 를 연속 3회 던지고 4회째 성공을 반환하도록 mock한 SDK 호출은 최종적으로 **성공 응답을 반환**하고, 호출 시도 횟수는 4이다.
- **AC-T2**: `anthropic.RateLimitError` 를 연속 던지는 mock은 최대 5회 재시도 후 예외를 전파한다(6회째 호출은 발생하지 않는다).
- **AC-T3**: `anthropic.InternalServerError` 는 AC-T1/T2와 동일한 재시도 정책을 따른다.
- **AC-T4**: `anthropic.AuthenticationError` 는 **재시도 없이 1회 시도 후 즉시 raise**된다(mock 호출 횟수 정확히 1).
- **AC-T5**: `anthropic.BadRequestError`(검증 오류)는 **재시도 없이 1회 시도 후 즉시 raise**된다(mock 호출 횟수 정확히 1).
- **AC-T6**: 재시도 간격은 지수적으로 증가한다(1회→2회 사이 대기 ≥ 0.8s, 2회→3회 사이 대기 ≥ 1.6s — 지터 -20% 감안 하한). 테스트는 `time.sleep` / tenacity의 `wait` 훅을 mock으로 측정한다.
- **AC-T7**: 총 재시도 누적 대기가 60초 상한을 넘지 않는다.

### 프롬프트 캐싱 (AC-P)
- **AC-P1**: 길이 1,200자의 system prompt를 `build_system_block` 에 넣으면, 반환 구조의 해당 블록에 `"cache_control": {"type": "ephemeral"}` 키가 포함된다.
- **AC-P2**: 길이 500자의 system prompt(임계 미만)는 `cache_control` 키가 포함되지 않는다.
- **AC-P3**: `build_system_block` 반환값을 Anthropic Messages API가 기대하는 형식(`[{"type": "text", "text": "...", "cache_control": {...}}]`)으로 검증한다.

### 통합 래퍼 (AC-I)
- **AC-I1**: `invoke_llm(prompt="..."(짧음), items=[], tracker=CostTracker(budget_usd=1.0, ...))` 는 내부적으로 `HAIKU` 를 선택해 SDK를 호출하고, 응답의 usage(mock: input 1000, output 500 토큰)를 단가 표에 곱해 누적한 **새 tracker** 를 반환한다. 원본 tracker 는 변경되지 않는다.
- **AC-I2**: `invoke_llm` 호출 중 누적 비용이 예산을 초과하면 `BudgetExceededError` 가 raise되고, 그 **이후 추가 SDK 호출은 발생하지 않는다**.
- **AC-I3**: `invoke_llm` 이 모델에 실제 전달한 요청 payload를 capture했을 때, system prompt 길이가 임계 이상이면 `cache_control: ephemeral` 이 포함되어 있다.
- **AC-I4**: `invoke_llm(..., force=SONNET)` 은 입력 크기와 무관하게 Sonnet SDK 엔드포인트로 호출된다(mock 검증).

### 문서 / 경로 (AC-D)
- **AC-D1**: 구현 모듈들은 모두 `ai/` 디렉터리 하위에 위치한다.
- **AC-D2**: 본 PRD가 `docs/rules/ai.md`(또는 신규 "비용 가드레일" 섹션)에서 링크된다.
- **AC-D3**: `BudgetExceededError` 클래스는 `ai/` 공개 경로에서 import 가능하며 `Exception` 의 하위 클래스다.

---

## 6. 가정 · 제약

- **언어/런타임**: Python 3.11+ (dataclass `slots=True` 지원 필수). 이외 버전은 지원 범위 밖.
- **SDK**: Anthropic 공식 Python SDK(`anthropic`) 최신 안정 버전. 예외 클래스 이름이 바뀌면 **재시도 allow-list를 동시에 갱신**해야 한다.
- **모델 단가(2026-04-25 기준, Anthropic 공식 가격)**:
  | Model | Input $/1M | Output $/1M | 특기사항 |
  |-------|----------:|------------:|---------|
  | Haiku 4.5 | $1.00 | $5.00 | — |
  | Sonnet 4.6 | $3.00 | $15.00 | — |
  | Opus 4.7 | $5.00 | $25.00 | 새 tokenizer (입력 토큰 35% 증가 가능) |
  | Opus 4.6 | $5.00 | $25.00 | — |
  이 표는 `ai/llm/pricing.py` 상수로 넣고, 변동 시 해당 파일만 수정한다(코드·테스트 분리). Opus 4.7 사용 시 실제 비용은 tokenizer 차이로 개인차가 클 수 있으니, 라우팅 임계치는 필요시 조정 권장.
- **프롬프트 캐싱 과금 규칙**: Anthropic cache write / cache read 단가는 본 PRD 범위에서는 **캐시 hit은 입력 비용 할인으로만 계산**(근사). 정확한 캐시 write/read 분리 회계는 후속 과제.
- **비결정성**: LLM 응답 자체는 비결정적이므로 라우팅/재시도/누적계산 테스트는 **응답 mock**으로 검증한다. 실제 응답 품질 eval은 별도 PRD(`eval-harness` 이식 시).
- **예산 값**: 기본값은 환경변수(`AI_DAILY_BUDGET_USD` 등)에서 읽는 것을 권장하되, 환경변수 설계 자체는 구현자 재량. 테스트에서는 직접 주입.
- **LangGraph 호환**: 기존 노드는 순수 함수적 시그니처가 되도록 `(state, tracker) -> (state, tracker)` 패턴을 권장. 단, **기존 그래프 구조는 변경하지 않는다**(비범위).
- **일정**: MVP 1스프린트 내 구현 + QA 통과를 가정. ECC 원본 코드는 MIT 라이선스이므로 참고·재작성 가능하되 파일 헤더에 출처 주석을 남긴다.

---

## 7. 참고

- `docs/references/everything-claude-code.md` §3 `cost-aware-llm-pipeline` — 4축(라우팅/트래커/재시도/캐싱) 패턴의 직접 출처.
- `AGENTS.md` §"PRD (PM 산출물)" — 본 PRD 양식 기준.
- `AGENTS.md` §"멀티 에이전트 역할" — Backend Dev(ai/ Python) 담당 범위 근거.
- 외부 원본: ECC 저장소 `skills/cost-aware-llm-pipeline/SKILL.md` (MIT).
- Anthropic 공식 문서: Prompt caching(`cache_control: ephemeral`), Messages API usage 필드.
- 관련 후속 PRD 후보: LLM 에이전트 보안 가드(보안), `eval-harness`(품질 회귀), `ai-regression-testing`(회귀 테스트 템플릿) — 본 PRD와 같은 ECC 레퍼런스 §1·2·4 참조.

---

**UI 포함 여부: 없음**  
**대상 에이전트: Backend Dev (Python, `ai/`) → QA → Code Reviewer → DevOps**
