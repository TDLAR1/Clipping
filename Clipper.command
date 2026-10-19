#!/bin/bash
# Double-click this file on a Mac to make clips.
# First run sets everything up (a few minutes); later runs start right away.

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

pause() { echo; read -r -p "Press Enter to close this window." _; }

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>/dev/null; then
  echo "Python 3.10 or newer is needed. Opening the download page..."
  echo "Install it, then double-click Clipper.command again."
  open "https://www.python.org/downloads/"
  pause; exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing ffmpeg (one time only)..."
    brew install ffmpeg || { pause; exit 1; }
  else
    echo "ffmpeg is needed, and the easiest way to get it is Homebrew."
    echo "1. Copy the install line from the page that's opening and paste it into Terminal."
    echo "2. Then double-click Clipper.command again."
    open "https://brew.sh"
    pause; exit 1
  fi
fi

if [ ! -f .venv/.installed ]; then
  echo "Setting up the clipper (one time only, a few minutes)..."
  python3 -m venv .venv &&
    .venv/bin/pip install --upgrade pip -q &&
    .venv/bin/pip install -r requirements.txt -q &&
    touch .venv/.installed || { echo "Setup failed - see the message above."; pause; exit 1; }
fi

echo
echo "=========================================="
echo "  FREE AI CLIPPER"
echo "=========================================="
echo "Paste a video link, or drag a video file into this window, then press Enter:"
read -r SRC
SRC="${SRC//\\ / }"                          # dragged files escape spaces
SRC="${SRC#\'}"; SRC="${SRC%\'}"; SRC="${SRC#\"}"; SRC="${SRC%\"}"
SRC="$(echo "$SRC" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
[ -z "$SRC" ] && { echo "Nothing entered."; pause; exit 1; }

read -r -p "How many clips? (press Enter for 6): " COUNT
COUNT="${COUNT:-6}"

EXTRA=()
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found - using it to pick the best moments and write titles."
  EXTRA+=(--llm ollama)
fi

.venv/bin/python -m clipper "$SRC" -n "$COUNT" "${EXTRA[@]}"
STATUS=$?
if [ $STATUS -eq 0 ]; then
  open clips
  echo "Done! Your clips folder is open."
fi
pause
