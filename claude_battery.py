#!/usr/bin/env python3
"""Claude Battery — menu bar indicator for Claude Code usage limits.

Prefers real data from Claude Code's statusLine hook (the official
`rate_limits.five_hour` / `rate_limits.seven_day` payload). Falls back
to a JSONL-based 5-hour rolling estimate when no real data is available.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rumps

try:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
except Exception:
    pass


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
STATE_FILE      = Path.home() / ".claude_battery_state.json"
CONFIG_FILE     = Path.home() / ".claude_battery_config.json"
WINDOW_HOURS    = 5

# Fallback estimate budget (weighted = input + output + cache_creation + cache_read/10).
# Only used when no real rate_limits data is available from Claude Code yet.
PLAN_LIMITS = {
    "pro":   700_000,
    "max5":  3_500_000,
    "max20": 14_000_000,
}
PLAN_LABELS = {"pro": "Pro", "max5": "Max 5x", "max20": "Max 20x"}

# Real rate_limits older than this are considered stale (5h window already elapsed).
STATE_MAX_AGE = timedelta(hours=5, minutes=30)


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {"plan": "max5"}


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def parse_iso(s):
    """Parse ISO 8601 string. Returns None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_timestamp(v):
    """Accept either an ISO string or a Unix epoch (seconds). Returns aware datetime or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str):
        return parse_iso(v)
    return None


def read_real_state():
    """Read the statusline-bridge-written state. Returns dict or None."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        return None
    updated = parse_timestamp(data.get("updated_at"))
    if not updated:
        return None
    if datetime.now(timezone.utc) - updated > STATE_MAX_AGE:
        return None  # Stale — the 5h window has fully rolled past.
    return data


def weighted_tokens(usage):
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0) // 10
    )


def estimate_usage_from_jsonl():
    """Fallback: weighted token sum in the last 5 hours from JSONL logs."""
    if not CLAUDE_PROJECTS.exists():
        return 0, None
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    entries = []
    for jsonl_file in CLAUDE_PROJECTS.rglob("*.jsonl"):
        try:
            with open(jsonl_file, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = parse_iso(entry.get("timestamp"))
                    usage = (entry.get("message") or {}).get("usage") or {}
                    if not ts or not usage or ts < cutoff:
                        continue
                    tokens = weighted_tokens(usage)
                    if tokens > 0:
                        entries.append((ts, tokens))
        except (IOError, OSError):
            continue
    if not entries:
        return 0, None
    return sum(t for _, t in entries), min(ts for ts, _ in entries)


def battery_icon(pct):
    if pct >= 75: return "🟢"
    if pct >= 50: return "🟡"
    if pct >= 25: return "🟠"
    return "🔴"


def format_eta(reset_at):
    if not reset_at:
        return "—"
    delta = reset_at - datetime.now(timezone.utc)
    secs = max(0, int(delta.total_seconds()))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    return f"{h}h {m}m"


class ClaudeBatteryApp(rumps.App):
    def __init__(self):
        super().__init__("ClaudeBattery", title="🤖 --%", quit_button=None)
        self.config = load_config()

        self.status_item  = rumps.MenuItem("Loading…")
        self.source_item  = rumps.MenuItem("Source: —")
        self.five_item    = rumps.MenuItem("5h: —")
        self.week_item    = rumps.MenuItem("7d: —")
        self.reset_item   = rumps.MenuItem("Reset in: —")
        self.plan_item    = rumps.MenuItem(f"Fallback plan: {PLAN_LABELS[self.config['plan']]}")

        plan_menu = rumps.MenuItem("Change Fallback Plan")
        plan_menu.add(rumps.MenuItem("Pro",     callback=lambda _: self.set_plan("pro")))
        plan_menu.add(rumps.MenuItem("Max 5x",  callback=lambda _: self.set_plan("max5")))
        plan_menu.add(rumps.MenuItem("Max 20x", callback=lambda _: self.set_plan("max20")))

        self.menu = [
            self.status_item,
            None,
            self.five_item,
            self.week_item,
            self.reset_item,
            None,
            self.source_item,
            self.plan_item,
            plan_menu,
            None,
            rumps.MenuItem("Refresh", callback=lambda _: self.update_status()),
            rumps.MenuItem("Quit",    callback=rumps.quit_application),
        ]

        self.timer = rumps.Timer(lambda _: self.update_status(), 30)
        self.timer.start()
        self.update_status()

    def set_plan(self, plan):
        self.config["plan"] = plan
        save_config(self.config)
        self.plan_item.title = f"Fallback plan: {PLAN_LABELS[plan]}"
        self.update_status()

    def update_status(self):
        real = read_real_state()
        if real:
            self._render_real(real)
        else:
            self._render_estimate()

    def _render_real(self, state):
        rl = state.get("rate_limits") or {}
        five = rl.get("five_hour") or {}
        week = rl.get("seven_day") or {}

        five_used = five.get("used_percentage")
        week_used = week.get("used_percentage")

        remaining_5h = max(0, 100 - int(round(five_used))) if isinstance(five_used, (int, float)) else None
        if remaining_5h is None:
            # No 5h field — use weekly as the primary battery.
            remaining_5h = max(0, 100 - int(round(week_used))) if isinstance(week_used, (int, float)) else 0
            primary_label = "7d"
        else:
            primary_label = "5h"

        self.title = f"{battery_icon(remaining_5h)} {remaining_5h}%"
        self.status_item.title = f"Remaining ({primary_label}): {remaining_5h}%"

        self.five_item.title = (
            f"5h:  {round(five_used)}% used"
            if isinstance(five_used, (int, float)) else "5h:  (not provided)"
        )
        self.week_item.title = (
            f"7d:  {round(week_used)}% used"
            if isinstance(week_used, (int, float)) else "7d:  (not provided)"
        )

        reset_at = parse_timestamp(five.get("resets_at")) or parse_timestamp(week.get("resets_at"))
        self.reset_item.title = f"Reset in: {format_eta(reset_at)}"
        self.source_item.title = "Source: Claude Code (live)"

    def _render_estimate(self):
        used, oldest = estimate_usage_from_jsonl()
        limit = PLAN_LIMITS[self.config["plan"]]
        used_pct = min(100, int((used / limit) * 100)) if limit else 0
        remaining_pct = max(0, 100 - used_pct)

        self.title = f"{battery_icon(remaining_pct)} {remaining_pct}%"
        self.status_item.title = f"Remaining (est.): {remaining_pct}%"
        self.five_item.title = f"5h est.: {used:,} / {limit:,} tok"
        self.week_item.title = "7d:  —  (waiting for Claude Code data)"

        reset_at = oldest + timedelta(hours=WINDOW_HOURS) if oldest else None
        self.reset_item.title = f"Reset in: {format_eta(reset_at)}"
        self.source_item.title = "Source: JSONL estimate (run Claude Code once for real data)"


if __name__ == "__main__":
    ClaudeBatteryApp().run()
