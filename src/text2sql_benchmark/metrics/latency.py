from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator


@contextmanager
def measure_latency() -> Generator[list[float], None, None]:
    """Uso: with measure_latency() as ms: ...; latency = ms[0]"""
    result: list[float] = [0.0]
    start = time.perf_counter()
    yield result
    result[0] = (time.perf_counter() - start) * 1000
