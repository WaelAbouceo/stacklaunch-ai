"""LLM telemetry — token usage, cost estimate, and latency.

Wraps each model call so the platform can answer "how much are we spending and how
fast is it?" — a baseline observability requirement. Records are kept in-memory
(process-lifetime) and summarised via `snapshot()`; cost is estimated from the
per-1K-token prices in config. Deliberately dependency-free; swap for OpenTelemetry
+ a persistent backend in production.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from core import config

_lock = threading.Lock()


@dataclass
class _Stats:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    cost_usd: float = 0.0
    by_model: dict = field(default_factory=dict)


_stats = _Stats()


def _cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1000 * config.PRICE_PER_1K_PROMPT
        + completion_tokens / 1000 * config.PRICE_PER_1K_COMPLETION
    )


def record(model: str, prompt_tokens: int, completion_tokens: int,
           latency_ms: float, error: bool = False) -> None:
    cost = _cost(prompt_tokens, completion_tokens)
    with _lock:
        _stats.calls += 1
        _stats.prompt_tokens += prompt_tokens
        _stats.completion_tokens += completion_tokens
        _stats.total_latency_ms += latency_ms
        _stats.cost_usd += cost
        if error:
            _stats.errors += 1
        m = _stats.by_model.setdefault(
            model, {"calls": 0, "promptTokens": 0, "completionTokens": 0, "costUsd": 0.0}
        )
        m["calls"] += 1
        m["promptTokens"] += prompt_tokens
        m["completionTokens"] += completion_tokens
        m["costUsd"] = round(m["costUsd"] + cost, 6)


def snapshot() -> dict:
    with _lock:
        avg_latency = (_stats.total_latency_ms / _stats.calls) if _stats.calls else 0.0
        return {
            "calls": _stats.calls,
            "errors": _stats.errors,
            "promptTokens": _stats.prompt_tokens,
            "completionTokens": _stats.completion_tokens,
            "totalTokens": _stats.prompt_tokens + _stats.completion_tokens,
            "estimatedCostUsd": round(_stats.cost_usd, 6),
            "avgLatencyMs": round(avg_latency, 1),
            "byModel": _stats.by_model,
        }


def reset() -> None:
    global _stats
    with _lock:
        _stats = _Stats()


class timer:
    """Context manager returning elapsed ms via `.ms`."""

    def __enter__(self) -> "timer":
        self._t0 = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._t0) * 1000
