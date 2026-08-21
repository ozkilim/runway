#!/usr/bin/env bash
# runway installer: venv + deps + config scaffold + Claude Code skill.
# Idempotent — safe to re-run after `git pull` or moving the repo.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO/.venv"
PYBIN="$VENV/bin/python"
CONFIG_DIR="$HOME/.runway"
CONFIG="$CONFIG_DIR/config.yaml"
SKILL_DIR="$HOME/.claude/skills/runway"

say() { printf '\033[1m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- python venv
# Find a Python 3.10+; honour $PYTHON if the user set one.
version_ok() {
  command -v "$1" >/dev/null 2>&1 && "$1" -c \
    'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if version_ok "$candidate"; then PYTHON="$candidate"; break; fi
  done
fi
if [ -z "$PYTHON" ] || ! version_ok "$PYTHON"; then
  echo "error: Python 3.10+ not found (checked python3, python3.10-3.13)." >&2
  echo "Install it (e.g. 'brew install python@3.12' / 'apt install python3.12-venv')" >&2
  echo "or point me at one:  PYTHON=/path/to/python3.12 ./install.sh" >&2
  exit 1
fi

if [ ! -x "$PYBIN" ]; then
  say "Creating venv at $VENV"
  "$PYTHON" -m venv "$VENV"
fi

say "Installing dependencies"
"$PYBIN" -m pip install --quiet --upgrade pip
"$PYBIN" -m pip install --quiet -r "$REPO/requirements.txt"

# --------------------------------------------------------------------- config
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [ ! -f "$CONFIG" ]; then
  cp "$REPO/config.example.yaml" "$CONFIG"
  chmod 600 "$CONFIG"
  say "Created $CONFIG (all providers disabled until you fill it in)"
else
  say "Config already exists at $CONFIG — leaving it untouched"
fi

# ------------------------------------------------------- Claude Code skill
if [ -d "$HOME/.claude" ]; then
  mkdir -p "$SKILL_DIR"
  sed -e "s|{{RUNWAY_PYTHON}}|$PYBIN|g" \
      -e "s|{{RUNWAY_REPO}}|$REPO|g" \
      "$REPO/skill/SKILL.md" > "$SKILL_DIR/SKILL.md"
  say "Installed Claude Code skill -> $SKILL_DIR/SKILL.md"
else
  say "No ~/.claude found — skipped Claude Code skill install."
  echo "  Using another agent? See skill/AGENTS.md for a copy-paste snippet."
fi

# ----------------------------------------------------------------- next steps
cat <<EOF

Done. Next steps:

  1. Hook up a cloud (AWS takes ~5 minutes):
       docs/setup/aws.md      <- start here
       docs/setup/azure.md
       docs/setup/gcp.md

  2. Fill in $CONFIG
     (set enabled: true and paste the credentials the setup doc gave you)

  3. Verify credentials:
       $PYBIN $REPO/runway.py --check

  4. See your numbers:
       $PYBIN $REPO/runway.py

  5. Or just ask your agent: "what's my burn?"
     (Claude Code: the skill is installed. Other agents: paste skill/AGENTS.md
      into your agent's instructions, using the paths above.)
EOF
