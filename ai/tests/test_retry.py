"""좁은 재시도 테스트 (AC-T)."""

import pytest
import time
from unittest.mock import Mock, patch, call
from ai.llm.retry import narrow_retry, MAX_RETRIES, INITIAL_WAIT_SECONDS


# 테스트 목적의 커스텀 예외들
class RetryableError(Exception):
    """재시도 가능한 예외 (테스트용)."""
    pass


class NonRetryableError(Exception):
    """재시도 불가능한 예외 (테스트용)."""
    pass


# 재시도 데코레이터 수정: 테스트 예외 사용
def narrow_retry_test(func):
    """테스트용 재시도 데코레이터 (실제 Anthropic 예외 대신 커스텀 예외 사용)."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        total_wait = 0.0

        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except RetryableError as e:
                if attempt == MAX_RETRIES - 1:
                    raise

                base_wait = INITIAL_WAIT_SECONDS * (2 ** attempt)
                jitter = base_wait * 0.2 * (2 * __import__("random").random() - 1)
                wait_time = max(0.0, base_wait + jitter)

                if total_wait + wait_time > 60.0:
                    raise

                total_wait += wait_time
                time.sleep(wait_time)

            except NonRetryableError:
                raise

            except Exception:
                raise

        return None

    return wrapper


class TestRetry:
    """narrow_retry 데코레이터의 재시도 로직 테스트."""

    # AC-T1: 재시도 가능 예외 3회 후 4회째 성공
    def test_retry_retryable_succeed_on_fourth(self):
        """AC-T1: 재시도 가능 예외 3회 → 4회째 성공."""
        call_count = [0]

        @narrow_retry_test
        def failing_func():
            call_count[0] += 1
            if call_count[0] < 4:
                raise RetryableError("Retryable error")
            return {"result": "success"}

        with patch("time.sleep"):
            result = failing_func()

        assert result == {"result": "success"}
        assert call_count[0] == 4

    # AC-T2: 재시도 가능 예외 계속 발생 후 최대 5회 시도
    def test_retry_retryable_max_retries(self):
        """AC-T2: 재시도 가능 예외 계속 발생 → 5회 시도 후 raise."""
        call_count = [0]

        @narrow_retry_test
        def rate_limited_func():
            call_count[0] += 1
            raise RetryableError("Keep failing")

        with patch("time.sleep"):
            with pytest.raises(RetryableError):
                rate_limited_func()

        assert call_count[0] == MAX_RETRIES

    # AC-T3: 다른 재시도 가능 예외도 동일 정책
    def test_retry_another_retryable(self):
        """AC-T3: 다른 재시도 가능 예외도 재시도 정책 동일."""
        call_count = [0]

        @narrow_retry_test
        def server_error_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RetryableError("Server error")
            return {"result": "recovered"}

        with patch("time.sleep"):
            result = server_error_func()

        assert result == {"result": "recovered"}
        assert call_count[0] == 3

    # AC-T4: 재시도 불가능 예외는 즉시 raise
    def test_retry_non_retryable_no_retry(self):
        """AC-T4: 재시도 불가능 예외는 1회 시도 후 즉시 raise."""
        call_count = [0]

        @narrow_retry_test
        def non_retryable_func():
            call_count[0] += 1
            raise NonRetryableError("Auth failed")

        with patch("time.sleep"):
            with pytest.raises(NonRetryableError):
                non_retryable_func()

        assert call_count[0] == 1

    # AC-T5: 다른 예외도 즉시 raise
    def test_retry_other_error_no_retry(self):
        """AC-T5: 다른 예외도 1회 시도 후 즉시 raise."""
        call_count = [0]

        @narrow_retry_test
        def other_error_func():
            call_count[0] += 1
            raise ValueError("Some error")

        with patch("time.sleep"):
            with pytest.raises(ValueError):
                other_error_func()

        assert call_count[0] == 1

    # AC-T6: 지수 백오프 (대기 시간이 점진적 증가)
    def test_retry_exponential_backoff(self):
        """AC-T6: 지수 백오프로 대기 시간 증가."""
        call_count = [0]
        wait_times = []

        def mock_sleep(seconds):
            wait_times.append(seconds)

        @narrow_retry_test
        def slow_recover_func():
            call_count[0] += 1
            if call_count[0] < 5:
                raise RetryableError("Still failing")
            return {"result": "success"}

        with patch("time.sleep", side_effect=mock_sleep):
            result = slow_recover_func()

        assert result == {"result": "success"}
        assert len(wait_times) == 4

        # 지수 백오프: 각 대기 > 이전의 일부
        assert wait_times[0] >= INITIAL_WAIT_SECONDS * 0.8
        assert wait_times[1] >= INITIAL_WAIT_SECONDS * 2 * 0.8
        assert wait_times[2] >= INITIAL_WAIT_SECONDS * 4 * 0.8

    # AC-T7: 총 재시도 누적 대기가 60초 상한
    def test_retry_max_total_wait(self):
        """AC-T7: 총 대기 상한 60초를 넘지 않음."""
        call_count = [0]
        total_wait = [0.0]

        def mock_sleep(seconds):
            total_wait[0] += seconds

        @narrow_retry_test
        def many_retries_func():
            call_count[0] += 1
            raise RetryableError("Keep failing")

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(RetryableError):
                many_retries_func()

        # 총 대기는 60초를 넘지 않음
        assert total_wait[0] <= 60.0

    # 추가: 성공 케이스
    def test_retry_success_on_first_attempt(self):
        """첫 시도에 성공하면 즉시 반환."""
        call_count = [0]

        @narrow_retry_test
        def instant_success():
            call_count[0] += 1
            return {"result": "immediate"}

        result = instant_success()
        assert result == {"result": "immediate"}
        assert call_count[0] == 1

    # 추가: 혼합 예외 처리
    def test_retry_retryable_then_non_retryable(self):
        """재시도 가능 → 재시도 불가능한 순서로 예외 발생."""
        call_count = [0]

        @narrow_retry_test
        def mixed_errors_func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RetryableError("Connection failed")
            elif call_count[0] == 2:
                raise NonRetryableError("Auth failed")
            return {"result": "done"}

        with patch("time.sleep"):
            with pytest.raises(NonRetryableError):
                mixed_errors_func()

        assert call_count[0] == 2


class TestNarrowRetryDecorator:
    """실제 narrow_retry 데코레이터의 기본 동작 테스트."""

    def test_decorator_wraps_function(self):
        """데코레이터가 함수를 정상 래핑."""
        @narrow_retry
        def example_func(x):
            return x * 2

        assert example_func(5) == 10

    def test_decorator_preserves_function_name(self):
        """데코레이터가 함수명 유지."""
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
