import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter (spec Section 16's principles,
    applied here to webhook delivery rather than Kafka consumption —
    same reasoning as notification-service's identically-shaped
    RetryPolicy: jitter stops a burst of deliveries that fail at the
    same moment, e.g. a merchant's endpoint going down, from all
    retrying in lockstep and hitting it again simultaneously.
    """

    max_attempts: int = 6
    base_delay_seconds: float = 5.0
    backoff_factor: float = 2.0
    jitter_ratio: float = 0.2

    def delay_seconds(self, attempt: int) -> float:
        """`attempt` is 1-indexed: the delay before retry number
        `attempt`. Never negative even at the largest jitter draw.
        """
        base = self.base_delay_seconds * (self.backoff_factor ** (attempt - 1))
        jitter = base * self.jitter_ratio
        return max(0.0, base + random.uniform(-jitter, jitter))
