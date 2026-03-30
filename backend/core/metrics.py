from dataclasses import dataclass
from threading import Lock
from time import perf_counter


@dataclass
class MetricsSnapshot:
    request_count: int
    error_count: int
    total_latency_ms: float


class MetricsStore:
    def __init__(self) -> None:
        self._request_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0
        self._lock = Lock()

    def observe_request(self, latency_ms: float, is_error: bool) -> None:
        with self._lock:
            self._request_count += 1
            if is_error:
                self._error_count += 1
            self._total_latency_ms += latency_ms

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                request_count=self._request_count,
                error_count=self._error_count,
                total_latency_ms=self._total_latency_ms,
            )


def now_ms() -> float:
    return perf_counter() * 1000


metrics_store = MetricsStore()
