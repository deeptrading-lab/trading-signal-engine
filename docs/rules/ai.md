# AI / Analysis 규칙 (Python)

- PRD·`AGENTS.md` 범위 밖 모델/엔드포인트/외부 연동 추가 금지
- LLM 호출/프롬프트/도구 호출 경로는 추적 가능하게 유지(로그/구조화 출력)
- MVP Slack 알림 흐름과 모순 없게 스키마·메시지 형식 유지

## 비용 가드레일

`docs/prd/cost-aware-llm-pipeline.md` 참고.

### 사용법

```python
from ai.llm import CostTracker, invoke_llm, Model

# 예산 정의
tracker = CostTracker(budget_usd=10.0)

# LLM 호출 (모델 라우팅·캐싱·재시도·비용 추적 자동)
response, tracker = invoke_llm(
    prompt="종목 분석해줘",
    items=[...],
    tracker=tracker,
    system_prompt="당신은 증권 분석가입니다.",
    force=None,  # 강제 모델 지정 가능
)

# 예산 초과 시 BudgetExceededError 발생
```

### 핵심 모듈

- **`ai.llm.router`**: `select_model(text_length, item_count, force)` — 모델 선택
  - text_length >= 10,000 또는 item_count >= 30 → SONNET
  - 그 외 → HAIKU
  - force 인자 우선
- **`ai.llm.cost_tracker`**: `CostTracker` — 불변 비용 추적기
  - `.add(input_tokens, output_tokens, model|usd)` → 새 인스턴스
  - 누적 비용 > budget_usd → `BudgetExceededError`
- **`ai.llm.retry`**: `@narrow_retry` — 좁은 재시도 데코레이터
  - 재시도 대상: `APIConnectionError`, `RateLimitError`, `InternalServerError` 만
  - 지수 백오프: 1초 → 2초 → 4초 → ... (지터 ±20%, 최대 60초)
  - 인증/검증 오류: 1회 시도 후 즉시 raise
- **`ai.llm.cache`**: `build_system_block(text)` — 프롬프트 캐싱
  - text 길이 >= 1,000자 → `cache_control: {type: "ephemeral"}` 자동 부착
- **`ai.llm.invoke`**: `invoke_llm(...)` — 통합 래퍼
  - 모델 선택 → 캐싱 → 재시도 → 비용 추적 순서 보장

### 주의사항

- `CostTracker`는 프로세스 수명 안에서만 유효 (영속화 안 함)
- 단가 테이블은 `ai.llm.pricing` 상수로 분리 (변동 시 해당 파일만 수정)
- LangGraph 노드는 `(state, tracker) -> (state, tracker)` 패턴 권장
- 예산 초과 여부는 호출자에게 전파 (파이프라인 즉시 중단)

