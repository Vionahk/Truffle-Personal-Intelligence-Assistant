#!/usr/bin/env bash
set -euo pipefail

# Simple helper to guide users through running the AI Care Assistant demo.
# Intended for Unix-like shells (WSL, Git Bash, macOS, Linux). On native
# Windows PowerShell, follow the PowerShell instructions instead.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "== AI Care Assistant Demo Helper =="

# 1) Ensure running as root/sudo per request
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "This script requires sudo/root privileges to run some checks."
  echo "Please re-run with sudo: sudo $0"
  exit 1
fi

# 2) Check Python >= 3.9
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.9+ and re-run." >&2
  exit 1
fi
python3 - <<'PY' || { echo "ERROR: Python must be 3.9 or newer." >&2; exit 1; }
import sys
if sys.version_info < (3,9):
    raise SystemExit(1)
print('python-ok')
PY

echo "Python check: OK"

# 3) Check pip availability
if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "ERROR: pip not available for python3. Install pip and re-run." >&2
  exit 1
fi

echo "pip: OK"

# 4) Create / activate virtual environment
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment .venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Virtual environment activated"

# 5) Upgrade pip and install requirements
python -m pip install --upgrade pip
if [ -f requirements.txt ]; then
  echo "Installing/updating required Python packages..."
  pip install --upgrade -r requirements.txt || true
fi

# Install commonly-required extras for camera/microphone checks if missing
pip install --upgrade opencv-python numpy SpeechRecognition >/dev/null 2>&1 || true

echo "Dependencies installed/updated (best effort)"

# 6) Webcam check (attempt to open device 0)
echo "Checking webcam..."
python - <<'PY' || { echo "WARNING: Webcam test failed or OpenCV not installed." >&2; }
import cv2, sys
try:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit(1)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise SystemExit(1)
    print('webcam-ok')
except Exception:
    sys.exit(1)
PY

echo "Webcam check: If you saw 'webcam-ok', camera is accessible."

# 7) Microphone check (try SpeechRecognition)
echo "Checking microphone..."
python - <<'PY' || { echo "WARNING: Microphone test failed or microphone library not installed." >&2; }
import sys
try:
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as src:
        print('microphone-open')
except Exception:
    sys.exit(1)
PY

echo "Microphone check: If you saw 'microphone-open', microphone is accessible."

# 8) Final instructions and run demo
echo ""
echo "Starting demo: the assistant will run with mock hardware by default."
echo "To stop at any time press Ctrl+C."
echo "Launching now..."

python scripts/run_demo.py

echo "Demo finished." 
