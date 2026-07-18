"""Retry helpers used across the pipeline (website fetches, API calls)."""
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from utils.logger import get_logger

logger = get_logger()


def with_retries(max_attempts: int = 3, base_seconds: float = 2.0, exceptions=(Exception,)):
    """Decorator factory: exponential backoff retry, logs each retry attempt."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_seconds, min=base_seconds, max=base_seconds * 8),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
