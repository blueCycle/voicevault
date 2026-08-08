#!/bin/bash
# Quick run script for VoiceVault

cd "$(dirname "$0")/.."
source venv/bin/activate

# Auto-generate the menubar icon if missing (one-time per fresh clone)
if [ ! -f "data/voicevault_icon.png" ]; then
    echo "[run.sh] Generating menu-bar icon..."
    python scripts/build-icon.py || echo "[run.sh] Icon generation failed (non-fatal)"
fi

python src/app.py
