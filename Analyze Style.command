#!/bin/bash
# Double-click to turn a Short you like into pictures + a report to send to Claude.
# Run Clipper.command once first so everything is installed.

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
pause() { echo; read -r -p "Press Enter to close this window." _; }

if [ ! -f .venv/.installed ]; then
  echo "Run Clipper.command once first - it installs everything this needs."
  pause; exit 1
fi
.venv/bin/pip install -q -U --pre "yt-dlp[default]" >/dev/null 2>&1 || true

echo "Paste the link of a Short whose style you like (or drag the video file here):"
read -r SRC
SRC="${SRC//\\ / }"
SRC="${SRC#\'}"; SRC="${SRC%\'}"; SRC="${SRC#\"}"; SRC="${SRC%\"}"
SRC="$(echo "$SRC" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -z "$SRC" ] && { echo "Nothing entered."; pause; exit 1; }

if .venv/bin/python -m clipper.analyze "$SRC"; then
  open style
  echo "Send Claude the two pictures and paste the report text."
fi
pause
