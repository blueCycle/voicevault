#!/bin/bash
# VoiceVault Setup Script for macOS

set -e

echo "🎙 VoiceVault Setup"
echo "=================="

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️  This setup script is designed for macOS. Continuing anyway..."
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# pysqlite3: the notes-search index (sqlite-vec) needs loadable-extension
# support that most prebuilt Python interpreters ship without. Build it
# against Homebrew's sqlite3, which has it enabled.
if ! python3 -c "import pysqlite3" 2>/dev/null; then
    if command -v brew &> /dev/null && brew --prefix sqlite &> /dev/null; then
        echo "Building pysqlite3 against Homebrew's sqlite3 (for notes search)..."
        CFLAGS="-I$(brew --prefix sqlite)/include" LDFLAGS="-L$(brew --prefix sqlite)/lib" \
            pip install pysqlite3 --no-binary pysqlite3
    else
        echo "⚠️  Homebrew's sqlite3 not found — skipping pysqlite3."
        echo "   Notes search (Electron dashboard) needs it: brew install sqlite"
        echo "   then re-run this script."
    fi
fi

# Check for Ollama
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found. Install from https://ollama.com"
    echo "   Then run: ollama pull llama3.1:8b"
else
    echo "✅ Ollama found"
    
    # Check if Ollama daemon is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "🚀 Starting Ollama daemon..."
        ollama serve &
        sleep 3
    fi
    
    # Check if model is pulled
    if ! ollama list | grep -q "llama3.1"; then
        echo "Pulling llama3.1:8b model..."
        ollama pull llama3.1:8b
    else
        echo "✅ llama3.1:8b model available"
    fi
fi

# Setup .env
if [ ! -f ".env" ]; then
    echo "Creating .env from example..."
    cp .env.example .env
fi

# mlx-whisper (the default backend in .env.example) only has wheels for
# Apple Silicon. On Intel Macs, switch the .env to faster-whisper/cpu so
# the app actually starts instead of failing to import mlx on first run.
if [ "$(uname -m)" != "arm64" ]; then
    echo "⚠️  Intel Mac detected — mlx-whisper isn't available here."
    echo "   Switching .env to the faster-whisper/cpu backend."
    sed -i '' \
        -e 's/^VV_WHISPER_BACKEND=mlx-whisper/VV_WHISPER_BACKEND=faster-whisper/' \
        -e 's/^VV_WHISPER_MODEL=mlx-community\/whisper-large-v3-turbo/VV_WHISPER_MODEL=base/' \
        -e 's/^VV_WHISPER_DEVICE=mps/VV_WHISPER_DEVICE=cpu/' \
        .env
fi

# Check BlackHole (for system audio capture in meetings)
if [ ! -d "/Library/Audio/Plug-Ins/HAL/BlackHole.driver" ]; then
    echo "⚠️  BlackHole not found. For meeting audio capture:"
    echo "   brew install blackhole-2ch"
    echo "   Then create Multi-Output Device in Audio MIDI Setup"
fi

echo ""
echo "✅ Dependencies installed!"
echo ""

# Run onboarding wizard if first time
if [ ! -f "$HOME/.voicevault/first_run_complete" ]; then
    echo "🚀 Running first-time onboarding..."
    source venv/bin/activate
    python src/onboarding.py
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run VoiceVault:"
echo "   ./scripts/run.sh"
echo ""
echo "First time setup:"
echo "   - Grant Accessibility permission when prompted (for text injection)"
echo "   - Grant Microphone permission when prompted"
echo ""
echo "For meeting recording with system audio:"
echo "   1. Install BlackHole: brew install blackhole-2ch"
echo "   2. Open Audio MIDI Setup, create Multi-Output Device"
echo "   3. Set System Output to Multi-Output Device before recording"
