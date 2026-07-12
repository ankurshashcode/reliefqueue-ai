"""Small in-memory safety budget for public live-AMD judge requests."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

LIVE_AMD_ROUTES = {"/api/ai/live-verification", "/api/ai/burst-verification"}
LIVE_AMD_DEFAULT_WINDOW_SECONDS = 3600
LIVE_AMD_DEFAULT_IP_BUDGET = 40
LIVE_AMD_DEFAULT_GLOBAL_BUDGET = 160
LIVE_AMD_DEFAULT_MAX_BODY_BYTES = 262_144
LIVE_AMD_MAX_CASES = 24
_RATE_LOCK = threading.Lock()
_RATE_EVENTS: dict[str, list[tuple[float, int]]] = {}


def positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(0, value)


def estimated_live_amd_cost(route: str, body: dict[str, Any]) -> int:
    if route == "/api/ai/burst-verification":
        reports = body.get("reports")
        count = len(reports) if isinstance(reports, list) else 1
        # Per-case calls plus one synthesis and one bounded repair allowance.
        return max(1, min(LIVE_AMD_MAX_CASES, count)) + 2
    mode = str(body.get("workload_mode") or body.get("mode") or "single")
    # Complex dossiers can use an initial call plus bounded semantic repairs.
    return 3 if mode in {"complex", "dossier", "complex_dossier"} else 2


def consume_live_amd_budget(
    client_key: str,
    route: str,
    body: dict[str, Any],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    window = positive_env_int("RELIEFQUEUE_AMD_DEMO_RATE_WINDOW_SECONDS", LIVE_AMD_DEFAULT_WINDOW_SECONDS)
    ip_budget = positive_env_int("RELIEFQUEUE_AMD_DEMO_IP_BUDGET", LIVE_AMD_DEFAULT_IP_BUDGET)
    global_budget = positive_env_int("RELIEFQUEUE_AMD_DEMO_GLOBAL_BUDGET", LIVE_AMD_DEFAULT_GLOBAL_BUDGET)
    cost = estimated_live_amd_cost(route, body)
    if window == 0 or (ip_budget == 0 and global_budget == 0):
        return {"allowed": True, "cost": cost, "retry_after_seconds": 0}

    cutoff = timestamp - window
    keys = (f"ip:{client_key}", "global")
    limits = (ip_budget, global_budget)
    with _RATE_LOCK:
        for key in keys:
            _RATE_EVENTS[key] = [event for event in _RATE_EVENTS.get(key, []) if event[0] > cutoff]
        for key, limit in zip(keys, limits):
            if limit <= 0:
                continue
            events = _RATE_EVENTS[key]
            used = sum(event_cost for _, event_cost in events)
            if used + cost > limit:
                oldest = min((event_time for event_time, _ in events), default=timestamp)
                retry_after = max(1, int(window - (timestamp - oldest)))
                return {
                    "allowed": False,
                    "cost": cost,
                    "scope": key.split(":", 1)[0],
                    "used": used,
                    "limit": limit,
                    "retry_after_seconds": retry_after,
                }
        for key in keys:
            _RATE_EVENTS.setdefault(key, []).append((timestamp, cost))
    return {"allowed": True, "cost": cost, "retry_after_seconds": 0}


def reset_live_amd_budgets_for_test() -> None:
    with _RATE_LOCK:
        _RATE_EVENTS.clear()
