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
