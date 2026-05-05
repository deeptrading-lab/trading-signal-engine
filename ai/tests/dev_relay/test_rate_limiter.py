"""`_RateLimiter` 단위 테스트 (AC-15 회귀 보호).

PRD `docs/prd/slack-dev-relay.md` §3.5 — 같은 user_id 가 5초 슬라이딩 윈도우
내에서 4번째 명령부터 차단된다. `time.monotonic` 의존을 회피하기 위해
`check(now=...)` 로 결정론적 시각을 주입한다.

추출은 의도적으로 하지 않는다 (이슈 #28 의 권고이지 요구사항 아님).
모듈 추출은 별도 PR 로 다룬다.
"""

from __future__ import annotations

from ai.dev_relay.main import _RateLimiter


class TestRateLimiterAllowAndBlock:
    """AC-15: 5초 윈도우 내 3회까지 통과, 4회째부터 차단."""

    def test_first_three_attempts_pass_then_fourth_blocked(self) -> None:
        limiter = _RateLimiter()
        # 5초 윈도우 내 (now 동일) 4번 시도.
        assert limiter.check("U1", now=0.0) is True
        assert limiter.check("U1", now=1.0) is True
        assert limiter.check("U1", now=2.0) is True
        # 4번째 시도는 차단.
        assert limiter.check("U1", now=3.0) is False


class TestRateLimiterWindowExpiry:
    """5초 윈도우 경과 후 카운터 리셋 — 다시 통과해야 한다."""

    def test_counter_resets_after_window(self) -> None:
        limiter = _RateLimiter()
        assert limiter.check("U1", now=0.0) is True
        assert limiter.check("U1", now=0.5) is True
        assert limiter.check("U1", now=1.0) is True
        # 4번째는 윈도우 내라서 차단.
        assert limiter.check("U1", now=1.5) is False
        # 첫 시도 (now=0.0) 대비 5초+α 경과 — 첫 두 슬롯은 만료, 다시 통과 가능.
        # 단, now=0.5 슬롯은 5.6 시점에 cutoff=0.6 보다 작아서 만료, now=1.0
        # 슬롯도 만료 → bucket 비어있는 상태.
        assert limiter.check("U1", now=5.6) is True


class TestRateLimiterPerUserIsolation:
    """다른 user_id 는 독립 카운터 — A 가 차단되어도 B 는 영향 없음."""

    def test_users_are_isolated(self) -> None:
        limiter = _RateLimiter()
        # U1 을 한도까지 채운다.
        assert limiter.check("U1", now=0.0) is True
        assert limiter.check("U1", now=0.1) is True
        assert limiter.check("U1", now=0.2) is True
        assert limiter.check("U1", now=0.3) is False
        # U2 는 같은 시각이지만 별도 버킷 — 한도 내에서 통과.
        assert limiter.check("U2", now=0.3) is True
        assert limiter.check("U2", now=0.4) is True
        assert limiter.check("U2", now=0.5) is True
        # U2 도 4번째는 차단.
        assert limiter.check("U2", now=0.6) is False
        # U1 은 여전히 차단 상태 (윈도우 내).
        assert limiter.check("U1", now=0.7) is False


class TestRateLimiterBoundary:
    """경계값: 정확히 윈도우 경계 시각에서의 동작 명세.

    구현은 `bucket[0] < cutoff` 로 만료 판정 — 정확히 5.0 초 차이는 아직
    만료되지 않는다 (`bucket[0] == cutoff` 이므로 `<` 가 False). 본 테스트는
    이 경계 동작을 못박아 향후 의도치 않은 변경을 잡는다.
    """

    def test_exactly_window_seconds_does_not_expire(self) -> None:
        limiter = _RateLimiter()
        # t=0 에 첫 슬롯 적재.
        assert limiter.check("U1", now=0.0) is True
        assert limiter.check("U1", now=0.0) is True
        assert limiter.check("U1", now=0.0) is True
        # t=5.0 — 윈도우 정확히 일치 (cutoff = 5.0 - 5.0 = 0.0). bucket[0]=0.0
        # 은 `< 0.0` 이 False → 만료 안 됨 → 4번째 시도는 차단.
        assert limiter.check("U1", now=5.0) is False
        # t=5.0 + epsilon — cutoff = 0.0 + epsilon, bucket[0]=0.0 < cutoff
        # → 만료 → 통과.
        assert limiter.check("U1", now=5.000_001) is True
