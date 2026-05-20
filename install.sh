#!/bin/bash
# Claude Battery installer.
#
# Installs:
#   - A menu bar app showing remaining Claude Code usage (5-hour window)
#   - A statusLine hook in ~/.claude/settings.json that captures the real
#     `rate_limits` payload from Claude Code's API responses
#
# Re-run is safe: existing settings are backed up and only the statusLine
# key is touched.

set -euo pipefail

LABEL="com.user.claudebattery"
INSTALL_DIR="$HOME/Library/Application Support/ClaudeBattery"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
SETTINGS="$HOME/.claude/settings.json"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✓\033[0m %s\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "\033[33m⚠\033[0m %s\n" "$*"; }
err()  { printf "\033[31m✗\033[0m %s\n" "$*" >&2; }

bold "Claude Battery installer"

# 1) macOS check
if [[ "$(uname -s)" != "Darwin" ]]; then
  err "This installer only supports macOS."
  exit 1
fi

# 2) Locate python3
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found. Install Python 3 (https://www.python.org/downloads/) and re-run."
  exit 1
fi
PY="$(command -v python3)"
info "Using Python at $PY ($("$PY" --version))"

# 3) Stop any existing instance
if [[ -f "$PLIST_PATH" ]]; then
  info "Stopping existing instance…"
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# 4) Copy app files
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/claude_battery.py"      "$INSTALL_DIR/"
cp "$SRC_DIR/statusline_bridge.py"   "$INSTALL_DIR/"
cp "$SRC_DIR/requirements.txt"       "$INSTALL_DIR/"
ok "Copied app files to $INSTALL_DIR"

# 5) Create venv & install dependencies
if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  info "Creating virtual environment…"
  "$PY" -m venv "$INSTALL_DIR/venv"
fi
info "Installing dependencies (rumps, pyobjc)…"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "Dependencies installed"

# 6) Wire statusLine hook into ~/.claude/settings.json.
#    Claude Code runs the statusLine command via a shell, so we install a
#    wrapper at a path with no spaces (the install dir contains a space)
#    to avoid shell-parsing breakage.
WRAPPER_DIR="$HOME/.claude_battery"
WRAPPER="$WRAPPER_DIR/bridge.sh"
mkdir -p "$WRAPPER_DIR"
cat > "$WRAPPER" <<EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/statusline_bridge.py"
EOF
chmod +x "$WRAPPER"
ok "Wrote statusLine wrapper at $WRAPPER"

mkdir -p "$HOME/.claude"
STATUSLINE_CMD="$WRAPPER"

if [[ -f "$SETTINGS" ]]; then
  cp "$SETTINGS" "$SETTINGS.claudebattery.bak.$(date +%Y%m%d%H%M%S)"
fi

python3 - "$SETTINGS" "$STATUSLINE_CMD" <<'PYEOF'
import json, os, sys
path, cmd = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

existing = data.get("statusLine")
if isinstance(existing, dict) and existing.get("command") and "claude_battery" not in existing.get("command", "") and "statusline_bridge.py" not in existing.get("command", ""):
    print(f"NOTE: existing statusLine command will be replaced: {existing.get('command')!r}", file=sys.stderr)

data["statusLine"] = {"type": "command", "command": cmd, "padding": 0}

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
ok "Wired statusLine hook in $SETTINGS"

# 7) Write LaunchAgent plist
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/venv/bin/python</string>
        <string>${INSTALL_DIR}/claude_battery.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/stderr.log</string>
</dict>
</plist>
EOF
ok "Wrote LaunchAgent at $PLIST_PATH"

# 8) Load it
launchctl load "$PLIST_PATH"
ok "Started Claude Battery"

echo
bold "Done!"
info "Look for a 🟢/🟡/🟠/🔴 icon with a % in your menu bar."
info "The real 5h / 7d limits appear after Claude Code makes its next API call."
info "Until then, a JSONL-based estimate is shown."
info "Logs:        $INSTALL_DIR/stdout.log / stderr.log"
info "Uninstall:   ./uninstall.sh"
