import time
import logging
from typing import Callable, Any, TypeVar, ParamSpec
from functools import wraps

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')

class CircuitBreakerOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, max_failures: int = 5, reset_timeout: int = 60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker moved to HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError("Circuit is OPEN")
                
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
                logger.info("Circuit breaker moved to CLOSED state")
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.max_failures:
                self.state = "OPEN"
                logger.warning("Circuit breaker OPENED due to consecutive failures")
            raise e

def circuit_breaker(max_failures: int = 5, reset_timeout: int = 60) -> Callable:
    cb = CircuitBreaker(max_failures, reset_timeout)
    
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return cb.call(func, *args, **kwargs)
        return wrapper
    return decorator
