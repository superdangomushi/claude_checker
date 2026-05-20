#!/usr/bin/env python3
"""Statusline bridge — receives Claude Code's statusLine stdin JSON,
extracts the official `rate_limits` (5h / 7d) and writes them to a
state file the menu bar app reads. Prints nothing to stdout so the
statusline stays empty (the menu bar already shows the percentage).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path.home() / ".claude_battery_state.json"


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return
    if not raw.strip():
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    rate_limits = data.get("rate_limits")
    if not rate_limits:
        # No rate_limits in payload (e.g. API key user, no subscription) — leave state alone.
        return

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rate_limits": rate_limits,
        "model": (data.get("model") or {}).get("display_name")
        if isinstance(data.get("model"), dict)
        else data.get("model"),
    }
    try:
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(out, indent=2))
        tmp.replace(STATE_FILE)
    except OSError:
        pass

    # Print nothing — the menu bar app displays the value.


if __name__ == "__main__":
    main()
