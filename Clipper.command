#!/bin/bash
# Double-click this file on a Mac to make clips.
# First run sets everything up (a few minutes); later runs start right away.

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

pause() { echo; read -r -p "Press Enter to close this window." _; }

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is needed to install the tools the clipper uses."
  echo "1. Copy the install line from the page that's opening and paste it into Terminal."
  echo "2. Then double-click Clipper.command again."
  open "https://brew.sh"
  pause; exit 1
fi

# The clipper's parts ship ready-made for Python 3.12, so it gets its own copy
# instead of whatever (possibly too new) Python is on the Mac.
NEED=()
command -v ffmpeg >/dev/null 2>&1 || NEED+=(ffmpeg)
[ -x "$(brew --prefix)/bin/python3.12" ] || NEED+=(python@3.12)
if [ ${#NEED[@]} -gt 0 ]; then
  echo "Installing ${NEED[*]} (one time only)..."
  HOMEBREW_NO_AUTO_UPDATE=1 brew install "${NEED[@]}" || { pause; exit 1; }
fi
PY="$(brew --prefix)/bin/python3.12"

if [ ! -f .venv/.installed ]; then
  echo "Setting up the clipper (one time only, a few minutes)..."
  rm -rf .venv
  "$PY" -m venv .venv &&
    .venv/bin/pip install --upgrade pip -q &&
    .venv/bin/pip install --only-binary=av,ctranslate2,numpy,opencv-python-headless \
      -r requirements.txt -q &&
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
