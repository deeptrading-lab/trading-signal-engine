"""좁은 재시도 테스트 (AC-T).

실제 `@narrow_retry` 데코레이터와 Anthropic SDK 예외를 직접 사용해 검증한다.
재시도 간격(T6), 총 대기 상한(T7)은 `time.sleep` mock 으로 측정한다.
"""

from unittest.mock import Mock, patch

import pytest
from anthropic import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from ai.llm.retry import (
    INITIAL_WAIT_SECONDS,
    MAX_RETRIES,
    MAX_TOTAL_WAIT_SECONDS,
    narrow_retry,
)


# ---------------------------------------------------------------------------
# Anthropic SDK 예외 팩토리
# SDK 예외 생성자는 `request=`/`response=` 키워드 인자를 요구하므로 Mock 으로 채운다.
# ---------------------------------------------------------------------------


def _make_api_connection_error(msg: str = "connection error") -> APIConnectionError:
    return APIConnectionError(message=msg, request=Mock())


def _make_rate_limit_error(msg: str = "rate limit") -> RateLimitError:
    return RateLimitError(msg, response=Mock(), body=None)


def _make_internal_server_error(msg: str = "internal") -> InternalServerError:
    return InternalServerError(msg, response=Mock(), body=None)


def _make_authentication_error(msg: str = "auth failed") -> AuthenticationError:
    return AuthenticationError(msg, response=Mock(), body=None)


def _make_bad_request_error(msg: str = "bad request") -> BadRequestError:
    return BadRequestError(msg, response=Mock(), body=None)


class TestRetry:
    """@narrow_retry 데코레이터의 재시도 로직 테스트 (실 Anthropic 예외)."""

    # AC-T1: APIConnectionError 3회 후 4회째 성공
    def test_retry_retryable_succeed_on_fourth(self):
        """AC-T1: APIConnectionError 3회 → 4회째 성공."""
        call_count = [0]

        @narrow_retry
        def failing_func():
            call_count[0] += 1
            if call_count[0] < 4:
                raise _make_api_connection_error()
            return {"result": "success"}

        with patch("time.sleep"):
            result = failing_func()

        assert result == {"result": "success"}
        assert call_count[0] == 4

    # AC-T2: RateLimitError 연속 발생 → 5회 시도 후 예외 전파
    def test_retry_retryable_max_retries(self):
        """AC-T2: RateLimitError 계속 발생 → 5회 시도 후 전파."""
        call_count = [0]

        @narrow_retry
        def rate_limited_func():
            call_count[0] += 1
            raise _make_rate_limit_error()

        with patch("time.sleep"):
            with pytest.raises(RateLimitError):
                rate_limited_func()

        assert call_count[0] == MAX_RETRIES

    # AC-T3: InternalServerError 동일 정책
    def test_retry_internal_server_error(self):
        """AC-T3: InternalServerError도 재시도 정책 동일."""
        call_count = [0]

        @narrow_retry
        def server_error_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise _make_internal_server_error()
            return {"result": "recovered"}

        with patch("time.sleep"):
            result = server_error_func()

        assert result == {"result": "recovered"}
        assert call_count[0] == 3

    # AC-T4: AuthenticationError → 재시도 없이 1회
    def test_retry_authentication_error_no_retry(self):
        """AC-T4: AuthenticationError는 1회 시도 후 즉시 raise."""
        call_count = [0]

        @narrow_retry
        def auth_error_func():
            call_count[0] += 1
            raise _make_authentication_error()

        with patch("time.sleep"):
            with pytest.raises(AuthenticationError):
                auth_error_func()

        assert call_count[0] == 1

    # AC-T5: BadRequestError → 재시도 없이 1회
    def test_retry_bad_request_error_no_retry(self):
        """AC-T5: BadRequestError는 1회 시도 후 즉시 raise."""
        call_count = [0]

        @narrow_retry
        def bad_request_func():
            call_count[0] += 1
            raise _make_bad_request_error()

        with patch("time.sleep"):
            with pytest.raises(BadRequestError):
                bad_request_func()

        assert call_count[0] == 1

    # 비(非)SDK 표준 예외(ValueError)도 즉시 전파
    def test_retry_non_sdk_error_no_retry(self):
        """ValueError 등 allow-list 외 예외는 1회 시도 후 즉시 raise."""
        call_count = [0]

        @narrow_retry
        def other_error_func():
            call_count[0] += 1
            raise ValueError("some error")

        with patch("time.sleep"):
            with pytest.raises(ValueError):
                other_error_func()

        assert call_count[0] == 1

    # AC-T6: 지수 백오프 (대기 시간 점진적 증가)
    def test_retry_exponential_backoff(self):
        """AC-T6: 지수 백오프로 대기 시간 점진적 증가.

        time.sleep 을 mock 으로 캡처해 각 시도 사이의 대기를 측정한다.
        지터 -20% 감안 하한: 1회→2회 ≥ 0.8s, 2회→3회 ≥ 1.6s, 3회→4회 ≥ 3.2s.
        """
        call_count = [0]
        wait_times: list[float] = []

        def mock_sleep(seconds: float) -> None:
            wait_times.append(seconds)

        @narrow_retry
        def slow_recover_func():
            call_count[0] += 1
            if call_count[0] < 5:
                raise _make_api_connection_error()
            return {"result": "success"}

        with patch("time.sleep", side_effect=mock_sleep):
            result = slow_recover_func()

        assert result == {"result": "success"}
        assert len(wait_times) == 4  # 4회 재시도 ⇒ 4회 sleep
        # 지수 백오프: 각 대기 ≥ (2^attempt * initial) * 0.8 (지터 -20%)
        assert wait_times[0] >= INITIAL_WAIT_SECONDS * 0.8
        assert wait_times[1] >= INITIAL_WAIT_SECONDS * 2 * 0.8
        assert wait_times[2] >= INITIAL_WAIT_SECONDS * 4 * 0.8
        assert wait_times[3] >= INITIAL_WAIT_SECONDS * 8 * 0.8

    # AC-T7: 총 재시도 누적 대기 ≤ 60초
    def test_retry_max_total_wait(self):
        """AC-T7: 누적 대기 합산이 60초 상한을 넘지 않음."""
        call_count = [0]
        total_wait = [0.0]

        def mock_sleep(seconds: float) -> None:
            total_wait[0] += seconds

        @narrow_retry
        def many_retries_func():
            call_count[0] += 1
            raise _make_rate_limit_error()

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(RateLimitError):
                many_retries_func()

        assert total_wait[0] <= MAX_TOTAL_WAIT_SECONDS

    # 성공 케이스: 첫 시도에서 즉시 반환
    def test_retry_success_on_first_attempt(self):
        """첫 시도에 성공하면 즉시 반환."""
        call_count = [0]

        @narrow_retry
        def instant_success():
            call_count[0] += 1
            return {"result": "immediate"}

        result = instant_success()
        assert result == {"result": "immediate"}
        assert call_count[0] == 1

    # 혼합 예외: 재시도 가능 → 재시도 불가능 순서
    def test_retry_retryable_then_non_retryable(self):
        """재시도 가능 예외 후 재시도 불가능 예외가 오면 즉시 전파."""
        call_count = [0]

        @narrow_retry
        def mixed_errors_func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise _make_api_connection_error()
            raise _make_authentication_error()

        with patch("time.sleep"):
            with pytest.raises(AuthenticationError):
                mixed_errors_func()

        assert call_count[0] == 2

    # exact-match: APIError 하위이더라도 allow-list 에 없는 타입은 재시도하지 않음
    def test_retry_exact_match_no_subclass_retry(self):
        """서브클래스 계열이더라도 RETRYABLE_EXCEPTIONS 에 없으면 재시도하지 않음.

        AuthenticationError 는 anthropic.APIStatusError 하위지만 allow-list 외이므로
        1회 시도 후 즉시 전파되어야 한다(PRD '정확히 3종' 요구사항).
        """
        call_count = [0]

        @narrow_retry
        def auth_error_func():
            call_count[0] += 1
            raise _make_authentication_error()

        with patch("time.sleep"):
            with pytest.raises(AuthenticationError):
                auth_error_func()

        assert call_count[0] == 1


class TestNarrowRetryDecorator:
    """@narrow_retry 데코레이터의 기본 동작 테스트."""

    def test_decorator_wraps_function(self):
        """데코레이터가 함수를 정상 래핑."""

        @narrow_retry
        def example_func(x):
            return x * 2

        assert example_func(5) == 10

    def test_decorator_preserves_function_name(self):
        """데코레이터가 함수명을 보존."""

        @narrow_retry
        def my_function():
            return 42

        assert my_function.__name__ == "my_function"

    def test_decorator_passes_args_and_kwargs(self):
        """데코레이터가 인자/키워드 정상 전달."""

        @narrow_retry
        def func_with_args(a, b, c=None):
            return (a, b, c)

        result = func_with_args(1, 2, c=3)
        assert result == (1, 2, 3)
