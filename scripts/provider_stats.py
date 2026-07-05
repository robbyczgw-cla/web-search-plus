"""Rolling provider performance memory for adaptive routing.

Port of the plugin/hermes v2.5 provider-stats module. Routing scores are
benchmarked but static: a provider that has been slow or returning empty
results for days keeps its full score. This module records the real outcome of
every provider call (latency, result count, errors) in a small rolling window
and turns it into a bounded score adjustment, so routing gently prefers
providers that are currently fast and productive — without ever overriding
strong query-class signals.

Unlike the in-process plugin, this skill runs as a fresh CLI process per call,
so the window is persisted to ``provider_stats.json`` in the cache directory
(same location, permissions, and atomic-write discipline as
``provider_health.json``). When caching is disabled (``WSP_DISABLE_CACHE=1``)
the samples stay process-local only and adjustments are effectively off.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DISABLE_CACHE_ENV = "WSP_DISABLE_CACHE"


def _cache_dir() -> Path:
    """Resolved per call so tests and callers can repoint WSP_CACHE_DIR."""
    return Path(os.environ.get("WSP_CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")))


def _stats_file() -> Path:
    return _cache_dir() / "provider_stats.json"

# Rolling window: keep this many most-recent samples per provider.
MAX_SAMPLES_PER_PROVIDER = 50
# Ignore samples older than this; stale history should not steer routing.
SAMPLE_MAX_AGE_SECONDS = 7 * 24 * 3600
# Providers need this many fresh samples before stats influence routing.
MIN_SAMPLES_FOR_ADJUSTMENT = 5
# Hard bound on routing-score influence. Query-class signals weigh 1.0-4.0
# per match, so performance can break ties and nudge close calls but never
# overrule a clear content-based winner.
MAX_SCORE_ADJUSTMENT = 1.0
# Median latency at or above this counts as fully slow (speed factor 0).
LATENCY_CEILING_SECONDS = 8.0
# Neutral point: providers performing at this combined level get adjustment 0.
PERFORMANCE_BASELINE = 0.75

_STATS_LOCK = threading.Lock()
_memory_samples: Dict[str, List[Dict[str, Any]]] = {}


def _persistence_disabled() -> bool:
    return os.environ.get(DISABLE_CACHE_ENV, "").strip() == "1"


def _load_samples() -> Dict[str, List[Dict[str, Any]]]:
    if _persistence_disabled():
        # Copy so read-modify-write in record_provider_outcome cannot clobber
        # the backing store when _save_samples clears it first.
        return dict(_memory_samples)
    stats_file = _stats_file()
    if not stats_file.exists():
        return {}
    try:
        with open(stats_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _save_samples(samples: Dict[str, List[Dict[str, Any]]]) -> None:
    if _persistence_disabled():
        _memory_samples.clear()
        _memory_samples.update(samples)
        return
    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(cache_dir, 0o700)
        fd, tmp_path = tempfile.mkstemp(dir=str(cache_dir), prefix=".stats-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(samples, f, ensure_ascii=False, separators=(",", ":"))
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, _stats_file())
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError:
        # Stats are best-effort telemetry; never fail a search over them.
        pass


def record_provider_outcome(provider: str, latency_seconds: float, result_count: int, error: bool, now: Optional[float] = None) -> None:
    sample = {
        "t": int(now if now is not None else time.time()),
        "lat": round(max(0.0, float(latency_seconds or 0.0)), 3),
        "n": max(0, int(result_count or 0)),
        "err": bool(error),
    }
    with _STATS_LOCK:
        samples = _load_samples()
        provider_samples = list(samples.get(provider) or [])
        provider_samples.append(sample)
        samples[provider] = provider_samples[-MAX_SAMPLES_PER_PROVIDER:]
        _save_samples(samples)


def _fresh_samples(provider: str, now: float) -> List[Dict[str, Any]]:
    cutoff = now - SAMPLE_MAX_AGE_SECONDS
    return [s for s in (_load_samples().get(provider) or []) if isinstance(s, dict) and int(s.get("t", 0)) >= cutoff]


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def get_provider_performance(provider: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    now_ts = now if now is not None else time.time()
    samples = _fresh_samples(provider, now_ts)
    if not samples:
        return None
    successes = [s for s in samples if not s.get("err")]
    empty = [s for s in successes if int(s.get("n", 0)) == 0]
    latencies = [float(s.get("lat", 0.0)) for s in successes]
    return {
        "samples": len(samples),
        "success_rate": round(len(successes) / len(samples), 3),
        "empty_rate": round(len(empty) / len(successes), 3) if successes else 0,
        "median_latency_seconds": round(_median(latencies), 3) if latencies else None,
    }


def performance_adjustment(provider: str, now: Optional[float] = None) -> float:
    """Bounded routing-score adjustment from recent real-world performance.

    Combines reliability (success rate, discounted by empty-result rate) and
    speed (median latency vs. LATENCY_CEILING_SECONDS) into
    [-MAX_SCORE_ADJUSTMENT, +MAX_SCORE_ADJUSTMENT]. Returns 0 until
    MIN_SAMPLES_FOR_ADJUSTMENT fresh samples exist.
    """
    perf = get_provider_performance(provider, now)
    if not perf or perf["samples"] < MIN_SAMPLES_FOR_ADJUSTMENT:
        return 0.0
    reliability = perf["success_rate"] * (1 - 0.5 * perf["empty_rate"])
    if perf["median_latency_seconds"] is None:
        speed = 0.0
    else:
        speed = max(0.0, min(1.0, 1 - perf["median_latency_seconds"] / LATENCY_CEILING_SECONDS))
    combined = 0.6 * reliability + 0.4 * speed
    adjustment = (combined - PERFORMANCE_BASELINE) * 2 * MAX_SCORE_ADJUSTMENT
    return round(max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, adjustment)), 3)


def performance_adjustments(providers: List[str], now: Optional[float] = None) -> Dict[str, float]:
    """Adjustments for several providers; providers without impact are omitted."""
    adjustments = {}
    for provider in providers:
        value = performance_adjustment(provider, now)
        if value != 0:
            adjustments[provider] = value
    return adjustments


def _reset_provider_stats_for_tests() -> None:
    with _STATS_LOCK:
        _memory_samples.clear()
        try:
            if _stats_file().exists():
                _stats_file().unlink()
        except OSError:
            pass
