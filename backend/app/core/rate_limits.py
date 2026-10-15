"""Small process-local limits for the single-instance portfolio deployment."""

from collections import OrderedDict, deque
from math import ceil
from threading import Lock
from time import monotonic


class ProcessRateLimiter:
    """Token-bucket question limits and rolling-window upload limits.

    Render Free runs one backend instance. State is intentionally process-local;
    restarts reset these protective limits, while durable work remains in PostgreSQL.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._questions: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._uploads: OrderedDict[str, deque[tuple[float, int]]] = OrderedDict()

    def consume_question(
        self,
        user_key: str,
        *,
        per_minute: int,
        burst: int,
        now: float | None = None,
    ) -> int | None:
        timestamp = monotonic() if now is None else now
        refill_per_second = per_minute / 60
        with self._lock:
            tokens, last_updated = self._questions.get(user_key, (float(burst), timestamp))
            replenished = tokens + max(0, timestamp - last_updated) * refill_per_second
            tokens = min(float(burst), replenished)
            if tokens < 1:
                retry_after = max(1, ceil((1 - tokens) / refill_per_second))
                self._questions[user_key] = (tokens, timestamp)
                self._questions.move_to_end(user_key)
                self._bound_users(self._questions)
                return retry_after
            self._questions[user_key] = (tokens - 1, timestamp)
            self._questions.move_to_end(user_key)
            self._bound_users(self._questions)
            return None

    def consume_upload(
        self,
        user_key: str,
        byte_size: int,
        *,
        uploads_per_hour: int,
        bytes_per_hour: int,
        now: float | None = None,
    ) -> int | None:
        timestamp = monotonic() if now is None else now
        cutoff = timestamp - 3_600
        with self._lock:
            uploads = self._uploads.setdefault(user_key, deque())
            self._uploads.move_to_end(user_key)
            self._bound_users(self._uploads)
            while uploads and uploads[0][0] <= cutoff:
                uploads.popleft()
            current_bytes = sum(size for _, size in uploads)
            if len(uploads) >= uploads_per_hour or current_bytes + byte_size > bytes_per_hour:
                retry_after = max(1, ceil(uploads[0][0] + 3_600 - timestamp)) if uploads else 3_600
                return retry_after
            uploads.append((timestamp, byte_size))
            return None

    @staticmethod
    def _bound_users(collection: OrderedDict) -> None:
        while len(collection) > 2_048:
            collection.popitem(last=False)


process_rate_limiter = ProcessRateLimiter()
