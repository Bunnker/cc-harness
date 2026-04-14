#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/skills"
DEST="$HOME/.claude/skills"

if [ ! -d "$SRC" ]; then
  echo "ERROR: $SRC not found" >&2
  exit 1
fi

mkdir -p "$DEST"

count=0
for skill in "$SRC"/*/; do
  name="$(basename "$skill")"
  rm -rf "$DEST/$name"
  cp -r "$skill" "$DEST/$name"
  count=$((count + 1))
done

echo "Installed $count skills to $DEST"
