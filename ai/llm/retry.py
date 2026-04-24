"""
좁은 재시도 데코레이터 및 헬퍼.

재시도 대상 예외는 정확히 3종으로 제한:
- anthropic.APIConnectionError
- anthropic.RateLimitError
- anthropic.InternalServerError

지수 백오프: 초기 대기 1초, 배수 2, 지터 ±20%, 최대 5회 시도, 총 대기 상한 60초.
"""

import functools
import time
from typing import Callable, TypeVar, Any
from anthropic import (
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)


# 재시도 대상 예외 (allow-list)
RETRYABLE_EXCEPTIONS = (
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)

# 재시도 정책
MAX_RETRIES = 5
INITIAL_WAIT_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
JITTER_FRACTION = 0.2  # ±20%
MAX_TOTAL_WAIT_SECONDS = 60.0


F = TypeVar("F", bound=Callable[..., Any])


def narrow_retry(func: F) -> F:
    """좁은 재시도 데코레이터.

    재시도 가능한 예외(APIConnectionError, RateLimitError, InternalServerError)만
    지수 백오프로 재시도한다. 그 외 예외(AuthenticationError, BadRequestError 등)는
    재시도 없이 즉시 전파된다.

    설정:
    - 최대 5회 시도
    - 초기 대기: 1초
    - 지수 백오프: 2배씩 증가
    - 지터: ±20%
    - 총 대기 상한: 60초

    사용:
        @narrow_retry
        def call_llm():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        total_wait = 0.0
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except RETRYABLE_EXCEPTIONS as e:
                # 재시도 가능한 예외
                last_exception = e

                # 마지막 시도면 raise
                if attempt == MAX_RETRIES - 1:
                    raise

                # 대기 시간 계산 (지수 백오프 + 지터)
                base_wait = INITIAL_WAIT_SECONDS * (BACKOFF_MULTIPLIER ** attempt)
                jitter = base_wait * JITTER_FRACTION * (2 * __import__("random").random() - 1)
                wait_time = base_wait + jitter
                wait_time = max(0.0, wait_time)  # 음수 방지

                # 총 대기 상한 확인
                if total_wait + wait_time > MAX_TOTAL_WAIT_SECONDS:
                    # 상한을 넘으면 raise
                    raise

                total_wait += wait_time
                time.sleep(wait_time)

            except Exception:
                # 재시도 불가능한 예외는 즉시 propagate
                raise

        # 루프를 벗어나면 (통상적으로 도달하지 않음)
        if last_exception:
            raise last_exception

    return wrapper  # type: ignore


def _exponential_backoff_wait(
    attempt: int,
    initial_wait: float = INITIAL_WAIT_SECONDS,
    multiplier: float = BACKOFF_MULTIPLIER,
    jitter_fraction: float = JITTER_FRACTION,
) -> float:
    """지수 백오프 대기 시간 계산 (테스트용 헬퍼).

    매개변수:
        attempt: 시도 횟수 (0부터 시작).
        initial_wait: 초기 대기 시간 (초).
        multiplier: 지수 배수.
        jitter_fraction: 지터 비율.

    반환값:
        대기 시간 (초).
    """
    import random
    base_wait = initial_wait * (multiplier ** attempt)
    jitter = base_wait * jitter_fraction * (2 * random.random() - 1)
    return max(0.0, base_wait + jitter)
