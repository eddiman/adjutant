"""Token usage estimator for Claude Pro caps.

Logs a usage event to state/usage_log.jsonl and prints a session/weekly
summary with colour-coded warnings.

Replaces bash scripts/observability/usage_estimate.sh.

Session cap: 44 000 tokens / 5 hours (rolling)
Weekly cap:  350 000 tokens / 7 days  (rolling)

API cost equivalents (reference only — not actual billing):
  Sonnet: $3/1M input, $15/1M output
  Opus:   $5/1M input, $25/1M output
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ANSI colour codes
_GREEN = "\033[0;32m"
_YELLOW = "\033[1;33m"
_RED = "\033[0;31m"
_NC = "\033[0m"

# Default caps (can be overridden by adjutant.yaml via load_typed_config)
_DEFAULT_SESSION_CAP = 44_000
_DEFAULT_SESSION_WINDOW_HOURS = 5
_DEFAULT_WEEKLY_CAP = 350_000

# Pricing per 1M tokens (USD, for reference)
_PRICING = {
    "sonnet": {"input": 3.0, "output": 15.0},
    "opus": {"input": 5.0, "output": 25.0},
}


def _adj_dir() -> Path:
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set")
    return Path(raw)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Compute USD cost equivalent for the given token counts and model."""
    pricing = _PRICING.get(model, _PRICING["sonnet"])
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return cost


def _window_start(hours: int) -> str:
    """ISO-8601 timestamp N hours ago."""
    from adjutant.core.platform import date_subtract

    return date_subtract(hours, "hours")


def _sum_tokens_since(log_path: Path, since_iso: str) -> int:
    """Sum 'total' fields from usage_log.jsonl for entries after since_iso."""
    if not log_path.exists():
        return 0
    total = 0
    try:
        for line in log_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp", "")
            if ts >= since_iso:
                total += int(entry.get("total", 0))
    except OSError:
        pass
    return total


def log_usage(
    operation: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "sonnet",
    adj_dir: Optional[Path] = None,
) -> dict:
    """Log a usage event and return a summary dict.

    Args:
        operation:     Short description of the operation (e.g. "pulse check").
        input_tokens:  Number of input tokens used.
        output_tokens: Number of output tokens used.
        model:         "sonnet" (default) or "opus".
        adj_dir:       Path to Adjutant directory. Defaults to $ADJ_DIR.

    Returns:
        Dict with keys: operation, model, input, output, total, cost,
        session_total, session_cap, session_pct, week_total, week_cap, week_pct.
    """
    d = adj_dir or _adj_dir()

    total = input_tokens + output_tokens
    cost = _compute_cost(input_tokens, output_tokens, model)

    # Log to JSONL
    log_path = d / "state" / "usage_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = _iso_now()

    entry = {
        "timestamp": timestamp,
        "operation": operation,
        "model": model,
        "input": input_tokens,
        "output": output_tokens,
        "total": total,
        "cost_equiv": round(cost, 4),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Load caps from config
    try:
        from adjutant.core.config import load_typed_config

        cfg = load_typed_config(d / "adjutant.yaml")
        session_cap = cfg.llm.caps.session_tokens
        session_window_hours = cfg.llm.caps.session_window_hours
        week_cap = cfg.llm.caps.weekly_tokens
    except Exception:
        session_cap = _DEFAULT_SESSION_CAP
        session_window_hours = _DEFAULT_SESSION_WINDOW_HOURS
        week_cap = _DEFAULT_WEEKLY_CAP

    # Rolling window sums
    session_start = _window_start(session_window_hours)
    week_start = _window_start(24 * 7)

    session_total = _sum_tokens_since(log_path, session_start)
    week_total = _sum_tokens_since(log_path, week_start)

    session_pct = round(session_total * 100 / session_cap, 1) if session_cap else 0.0
    week_pct = round(week_total * 100 / week_cap, 1) if week_cap else 0.0

    return {
        "operation": operation,
        "model": model,
        "input": input_tokens,
        "output": output_tokens,
        "total": total,
        "cost": cost,
        "session_total": session_total,
        "session_cap": session_cap,
        "session_pct": session_pct,
        "week_total": week_total,
        "week_cap": week_cap,
        "week_pct": week_pct,
    }


def format_report(summary: dict, colour: bool = True) -> str:
    """Format a usage summary dict as a human-readable report string."""
    g = _GREEN if colour else ""
    y = _YELLOW if colour else ""
    r = _RED if colour else ""
    nc = _NC if colour else ""

    cost = summary["cost"]
    lines = [
        "",
        f"{g}Logged:{nc} {summary['operation']} — {summary['total']} tokens (${cost:.4f} equiv)",
        "",
        f"Session usage ({_DEFAULT_SESSION_WINDOW_HOURS}h rolling): "
        f"{summary['session_total']} / {summary['session_cap']} tokens "
        f"({summary['session_pct']}%)",
        f"Weekly usage (7d rolling):  "
        f"{summary['week_total']} / {summary['week_cap']} tokens "
        f"({summary['week_pct']}%)",
        "",
    ]

    pct = summary["session_pct"]
    if pct > 80:
        lines.append(f"{r}⚠ Session cap approaching — slow down{nc}")
    elif pct > 50:
        lines.append(f"{y}Session usage moderate{nc}")
    else:
        lines.append(f"{g}Session usage healthy{nc}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Usage: usage_estimate <operation> <input_tokens> <output_tokens> [model]
    """
    args = (argv or sys.argv)[1:]

    if len(args) < 3 or args[1] == "0":
        print("Usage: usage_estimate.sh <operation> <input_tokens> <output_tokens>")
        print("")
        print("Common estimates:")
        print("  Pulse check:       3000 input,  500 output")
        print("  Escalation:        5800 input,  600 output")
        print("  Daily review:     10000 input, 1000 output")
        print("  /reflect (Opus):  15000 input, 2000 output")
        print("  Conversation (5m): 8000 input, 1500 output")
        return 1

    operation = args[0]
    input_tokens = int(args[1])
    output_tokens = int(args[2])
    model = args[3] if len(args) > 3 else "sonnet"

    try:
        summary = log_usage(operation, input_tokens, output_tokens, model)
        print(format_report(summary))
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
