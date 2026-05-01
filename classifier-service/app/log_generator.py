"""Synthetic log-chunk generator (see Appendix A of the implementation guide).

The generator picks lines from per-profile pools and interleaves timestamps.
Profiles correspond to the four severity classes the classifier outputs.

Public API:
    generate_log_chunk(profile, num_lines=30, seed=None) -> (chunk_text, severity)

Designed for ~30-line chunks (~2 minutes of activity) but accepts any size.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Callable

# A LineGen takes (timestamp_str, random.Random) and returns one log line.
LineGen = Callable[[str, random.Random], str]


# ---------- line pools ----------

NORMAL_LINES: list[LineGen] = [
    lambda t, r: f"{t} INFO  HTTP 200 GET /api/health ({r.randint(8, 40)}ms)",
    lambda t, r: f"{t} INFO  Processing scheduled job #{r.randint(1000, 9999)}: daily-rollup",
    lambda t, r: f"{t} INFO  Cache hit ratio: {r.uniform(85, 99):.1f}%",
    lambda t, r: f"{t} DEBUG Connection pool: {r.randint(5, 40)}/50 active",
    lambda t, r: f"{t} INFO  Backup completed in {r.uniform(3, 12):.1f}s",
    lambda t, r: f"{t} INFO  HTTP 200 POST /api/orders/{r.randint(1000, 99999)} ({r.randint(40, 180)}ms)",
    lambda t, r: f"{t} INFO  User '{r.choice(['alice', 'bob', 'carol', 'dave'])}' authenticated",
    lambda t, r: f"{t} DEBUG GC pause: {r.randint(2, 15)}ms (young gen)",
    lambda t, r: f"{t} INFO  Healthcheck OK on node-{r.randint(1, 12):02d}",
    lambda t, r: f"{t} INFO  Metrics flushed to statsd ({r.randint(40, 200)} datapoints)",
]

WARNING_LINES: list[LineGen] = [
    lambda t, r: f"{t} WARN  Request latency elevated: p99={r.randint(550, 2200)}ms (threshold 500ms)",
    lambda t, r: f"{t} WARN  Deprecated endpoint /v1/users used by client {r.randint(1, 99)}.x.x.x — migrate to /v2/users",
    lambda t, r: f"{t} WARN  Queue depth: {r.randint(8000, 9999)} (capacity 10000)",
    lambda t, r: f"{t} WARN  Retry attempt {r.randint(1, 3)}/3 for upstream service 'payments'",
    lambda t, r: f"{t} WARN  Certificate expires in {r.randint(7, 60)} days",
    lambda t, r: f"{t} WARN  Slow query: SELECT * FROM users took {r.randint(800, 3500)}ms",
    lambda t, r: f"{t} WARN  Memory usage at {r.randint(75, 89)}% on node-{r.randint(1, 12):02d}",
    lambda t, r: f"{t} WARN  Connection pool nearing capacity: {r.randint(45, 49)}/50",
    lambda t, r: f"{t} WARN  Throttled by external API '{r.choice(['stripe', 'twilio', 'sendgrid'])}': retry-after={r.randint(1, 10)}s",
    lambda t, r: f"{t} WARN  Healthcheck degraded on shard-{r.randint(0, 7)}: {r.randint(2, 5)} consecutive slow responses",
]

ERROR_LINES: list[LineGen] = [
    lambda t, r: f"{t} ERROR HTTP 500 POST /api/orders — IntegrityError: duplicate key value violates unique constraint",
    lambda t, r: f"{t} ERROR Failed to connect to Redis at 10.0.{r.randint(1, 5)}.{r.randint(100, 199)}:6379 - Connection refused",
    lambda t, r: f"{t} ERROR Upstream 'inventory' timed out after 30s",
    lambda t, r: f"{t} ERROR Exception in thread 'worker-{r.randint(1, 16)}': NullPointerException at OrderService.process(OrderService.java:142)",
    lambda t, r: f"{t} ERROR Queue consumer lag: {r.randint(60, 600)}s — SLO breached",
    lambda t, r: f"{t} ERROR Database query failed: SQLSTATE[40P01]: Deadlock detected",
    lambda t, r: f"{t} ERROR HTTPS handshake failed: certificate verify failed (expired)",
    lambda t, r: f"{t} ERROR Authentication failure for user '{r.choice(['admin', 'svc-acct', 'jenkins'])}': invalid token",
    lambda t, r: f"{t} ERROR Batch job #{r.randint(4000, 9000)} failed: Cache unavailable",
    lambda t, r: f"{t} ERROR Circuit breaker tripped on '{r.choice(['payments', 'shipping', 'pricing'])}': {r.randint(15, 50)} consecutive failures",
]

FATAL_LINES: list[LineGen] = [
    lambda t, r: f"{t} FATAL Out of memory: Java heap space — Cannot allocate {r.choice([256, 512, 1024])}MB",
    lambda t, r: f"{t} FATAL JVM terminated. Core dump written to /var/crash/core.{r.randint(1000, 9999)}",
    lambda t, r: f"{t} FATAL Service '{r.choice(['order-processor', 'payments', 'inventory', 'auth'])}' crashed. PID {r.randint(1000, 9999)} exited with signal 9",
    lambda t, r: f"{t} FATAL Unrecoverable database corruption detected in tablespace 'prod_orders'",
    lambda t, r: f"{t} FATAL Disk full on /var/log: 0 bytes available",
    lambda t, r: f"{t} FATAL Kernel panic - not syncing: Fatal exception in interrupt",
    lambda t, r: f"{t} FATAL Cluster lost quorum: {r.randint(2, 4)} of 5 nodes unreachable",
    lambda t, r: f"{t} FATAL Cascading failure: {r.randint(3, 12)} dependent services unreachable",
    lambda t, r: f"{t} ERROR Pod OOMKilled: order-processor-{r.randint(0, 999):03d} exceeded memory limit",
    lambda t, r: f"{t} FATAL TLS root cert distrusted; all outbound HTTPS calls failing",
]


_PROFILES: dict[str, dict] = {
    "normal": {
        "primary": NORMAL_LINES,
        "secondary": [],
        "primary_ratio": 1.0,
        "severity": "NORMAL",
    },
    "warning": {
        "primary": WARNING_LINES,
        "secondary": NORMAL_LINES,
        "primary_ratio": 0.35,
        "severity": "WARNING",
    },
    "error": {
        "primary": ERROR_LINES,
        "secondary": NORMAL_LINES,
        "primary_ratio": 0.45,
        "severity": "ERROR",
    },
    "fatal": {
        "primary": FATAL_LINES,
        "secondary": ERROR_LINES + NORMAL_LINES,
        "primary_ratio": 0.35,
        "severity": "FATAL_OR_CRITICAL",
    },
}

# Roughly mirrors real production traffic so the automation demo isn't
# a wall of FATAL chunks.
_MIXED_WEIGHTS: list[tuple[str, int]] = [
    ("normal", 70),
    ("warning", 15),
    ("error", 12),
    ("fatal", 3),
]


def generate_log_chunk(
    profile: str,
    num_lines: int = 30,
    seed: int | None = None,
) -> tuple[str, str]:
    """Generate a synthetic log chunk.

    Args:
        profile: One of {"normal", "warning", "error", "fatal", "mixed"}.
        num_lines: How many log lines to emit (clamped 1..200 by the schema).
        seed: Optional seed for reproducible output.

    Returns:
        (log_chunk_text, intended_severity)
    """
    if profile not in _PROFILES and profile != "mixed":
        raise ValueError(f"Unknown profile: {profile!r}")

    r = random.Random(seed)

    if profile == "mixed":
        names = [p for p, _ in _MIXED_WEIGHTS]
        weights = [w for _, w in _MIXED_WEIGHTS]
        profile = r.choices(names, weights=weights, k=1)[0]

    cfg = _PROFILES[profile]

    t = datetime.now(timezone.utc).replace(tzinfo=None)
    lines: list[str] = []
    for _ in range(num_lines):
        t += timedelta(seconds=r.randint(1, 4))
        ts = t.strftime("%Y-%m-%d %H:%M:%S")
        if cfg["secondary"] and r.random() >= cfg["primary_ratio"]:
            pool = cfg["secondary"]
        else:
            pool = cfg["primary"]
        lines.append(r.choice(pool)(ts, r))

    return "\n".join(lines), cfg["severity"]
