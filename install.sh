#!/usr/bin/env bash
# install.sh -- vibe-coding-tools setup for Linux/Mac (incl. cloud-session VM)
# Usage:
#   git clone https://github.com/choipeanut/vibe-coding-tools.git ~/vibe-coding-tools
#   bash ~/vibe-coding-tools/install.sh
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "=== vibe-coding-tools installer (Linux/Mac) ==="
echo ""

# 1. Python check
echo "[1/4] Checking Python..."
if command -v python3 >/dev/null 2>&1; then
    echo "      OK: $(python3 --version)"
    PY=python3
elif command -v python >/dev/null 2>&1; then
    echo "      OK: $(python --version)"
    PY=python
else
    echo "      ERROR: python3 not found."
    exit 1
fi

# 2. Install /blog command
echo "[2/4] Installing /blog command..."
mkdir -p "$HOME/.claude/commands"
cp "$REPO_ROOT/claude/commands/blog.md" "$HOME/.claude/commands/blog.md"
echo "      OK: $HOME/.claude/commands/blog.md"

# 3. Install SessionEnd hook
echo "[3/4] Installing SessionEnd hook..."
mkdir -p "$HOME/.claude/hooks"
cp "$REPO_ROOT/claude/hooks/archive_session.py" "$HOME/.claude/hooks/archive_session.py"
echo "      OK: $HOME/.claude/hooks/archive_session.py"

# 4. Register hook in settings.json
echo "[4/4] Registering hook in settings.json..."
SETTINGS="$HOME/.claude/settings.json"
HOOK_CMD="$PY \"\$HOME/.claude/hooks/archive_session.py\""
"$PY" - "$SETTINGS" "$HOOK_CMD" <<'PYEOF'
import json, os, sys
settings_path, hook_cmd = sys.argv[1], sys.argv[2]
data = {}
if os.path.isfile(settings_path):
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
hooks = data.setdefault("hooks", {})
se = hooks.setdefault("SessionEnd", [])
already = any(
    "archive_session.py" in h.get("command", "")
    for g in se for h in g.get("hooks", [])
)
if not already:
    se.append({"matcher": "", "hooks": [{"type": "command", "command": hook_cmd}]})
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("      OK: settings.json updated.")
else:
    print("      OK: already registered.")
PYEOF

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next:"
echo "  1. Restart the session / reload commands"
echo "  2. Connect Notion MCP"
echo "  3. Run /blog"
echo ""
