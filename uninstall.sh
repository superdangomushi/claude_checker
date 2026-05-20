#!/bin/bash
# Claude Battery uninstaller.
set -euo pipefail

LABEL="com.user.claudebattery"
INSTALL_DIR="$HOME/Library/Application Support/ClaudeBattery"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
CONFIG_FILE="$HOME/.claude_battery_config.json"
STATE_FILE="$HOME/.claude_battery_state.json"
SETTINGS="$HOME/.claude/settings.json"
WRAPPER_DIR="$HOME/.claude_battery"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✓\033[0m %s\n" "$*"; }

bold "Uninstalling Claude Battery"

if [[ -f "$PLIST_PATH" ]]; then
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  ok "Removed LaunchAgent"
fi

if [[ -d "$INSTALL_DIR" ]]; then
  rm -rf "$INSTALL_DIR"
  ok "Removed $INSTALL_DIR"
fi

if [[ -f "$CONFIG_FILE" ]]; then
  rm -f "$CONFIG_FILE"
  ok "Removed config"
fi

if [[ -f "$STATE_FILE" ]]; then
  rm -f "$STATE_FILE"
  ok "Removed state file"
fi

if [[ -d "$WRAPPER_DIR" ]]; then
  rm -rf "$WRAPPER_DIR"
  ok "Removed statusLine wrapper directory"
fi

if [[ -f "$SETTINGS" ]]; then
  python3 - "$SETTINGS" <<'PYEOF'
import json, sys
path = sys.argv[1]
try:
    with open(path) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
sl = data.get("statusLine")
cmd = (sl or {}).get("command") if isinstance(sl, dict) else None
if cmd and ("statusline_bridge.py" in cmd or "/.claude_battery/" in cmd):
    del data["statusLine"]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
PYEOF
  ok "Cleaned up statusLine entry in $SETTINGS"
fi

bold "Done."
