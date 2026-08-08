#!/usr/bin/env python3
"""VoiceVault Onboarding Wizard

A TUI-based first-run experience that:
1. Welcomes the user
2. Asks for their name
3. Asks for vault location (with sensible default)
4. Checks dependencies (Ollama, Whisper model)
5. Records a test sentence and transcribes it live
6. Creates a demo meeting note in the vault

Design: 2 user inputs, 90 seconds to first value.
"""

import json
import sys
import time
import subprocess
import wave
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
import sounddevice as sd

from src.config import CONFIG


# ── Paths ──────────────────────────────────────────────────────────

APP_DIR = Path.home() / ".voicevault"
USER_JSON = APP_DIR / "user.json"
FIRST_RUN_FLAG = APP_DIR / "first_run_complete"


# ── Public API ───────────────────────────────────────────────────────

def needs_onboarding() -> bool:
    """Return True if the user has not completed onboarding."""
    return not FIRST_RUN_FLAG.exists()


def run_onboarding() -> Dict[str, Any]:
    """Run the full onboarding wizard. Returns user config dict."""
    _print_banner()
    
    name = _ask_name()
    vault_path = _ask_vault(name)
    _check_dependencies()
    _test_transcription()
    _create_demo_note(vault_path, name)
    
    user_config = {
        "name": name,
        "vault_path": str(vault_path),
        "onboarded_at": _iso_now(),
        "first_run_complete": True,
    }
    
    _save_user_config(user_config)
    FIRST_RUN_FLAG.touch()
    
    _print_done(vault_path)
    return user_config


# ── Internal steps ───────────────────────────────────────────────────

def _print_banner():
    """Print welcome banner."""
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  VoiceVault                                                  ║")
    print("║  Your voice → structured notes. Entirely offline.           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print("Welcome! Let's get you set up in under 2 minutes.")
    print()


def _ask_name() -> str:
    """Ask for the user's name."""
    default = Path.home().name  # e.g. "kumar"
    name = input(f"What should we call you? [{default}]: ").strip()
    if not name:
        name = default
    print(f"  → Hello, {name}!\n")
    return name


def _ask_vault(name: str) -> Path:
    """Ask for the Obsidian vault location."""
    # Default: ~/Obsidian/{name}-voicevault
    obsidian_dir = Path.home() / "Obsidian"
    if not obsidian_dir.exists():
        obsidian_dir = Path.home()
    
    default = obsidian_dir / f"{name}-voicevault"
    
    path_str = input(
        f"Where should VoiceVault store your notes?\n"
        f"[{default}]: ".strip()
    ).strip()
    
    if path_str:
        vault = Path(path_str).expanduser().resolve()
    else:
        vault = default
    
    # Create vault + subfolders
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "Meetings").mkdir(exist_ok=True)
    (vault / "Dictations").mkdir(exist_ok=True)
    (vault / "Templates").mkdir(exist_ok=True)
    
    print(f"  → Vault created: {vault}\n")
    return vault


def _check_dependencies():
    """Check Ollama and Whisper dependencies."""
    print("Checking dependencies...")
    
    # Check Ollama
    ollama_ok = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            has_llama = any("llama3.1" in (m.get("name") or m.get("model", "")) for m in models)
            if has_llama:
                print("  ✓ Ollama is running (llama3.1:8b available)")
                ollama_ok = True
            else:
                print("  ⚠ Ollama is running but llama3.1:8b not found")
    except Exception:
        pass
    
    if not ollama_ok:
        print("  ⚠ Ollama is not running or llama3.1:8b is missing.")
        print()
        print("  To start Ollama, run this in another terminal:")
        print("    ollama run llama3.1:8b")
        print()
        input("  Press Enter once Ollama is running, or to skip for now...")
    
    # Check Whisper model (faster-whisper downloads on first use)
    print("  ✓ Whisper model will download on first use if needed")
    print()


def _test_transcription():
    """Record a test sentence and transcribe it."""
    print("Let's test your microphone. Say this out loud:")
    print()
    print('  "VoiceVault is ready for my first meeting."')
    print()
    
    input("  Press Enter when you're ready...")
    
    # Record 3 seconds
    duration = 3.0
    sample_rate = 16000
    print(f"  [Listening for {int(duration)} seconds...]", end="", flush=True)
    
    try:
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype=np.float32)
        for i in range(int(duration)):
            time.sleep(1)
            print(".", end="", flush=True)
        sd.wait()
        print(" done]")
    except Exception as e:
        print(f"\n  ⚠ Could not record audio: {e}")
        print("  Make sure your microphone is accessible.")
        return
    
    # Save to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
    
    _write_wav(temp_path, recording.squeeze(), sample_rate)
    
    # Transcribe
    print("  Transcribing...", end="", flush=True)
    try:
        # Import here to avoid heavy import during setup if whisper not installed
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.transcription.engine import TranscriptionEngine
        
        engine = TranscriptionEngine()
        text = engine.transcribe_file(Path(temp_path))
        print(" done]")
        
        if text.strip():
            print(f"\n  Heard: \"{text.strip()}\"\n")
            print("  ✓ Transcription looks good!\n")
        else:
            print("\n  ⚠ We didn't hear anything clearly.")
            print("  Try adjusting your microphone volume in System Settings.")
            print()
    except Exception as e:
        print(f"\n  ⚠ Transcription failed: {e}")
        print("  This is OK — you can try again after the app starts.\n")
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _create_demo_note(vault: Path, name: str):
    """Create a sample meeting note so the user sees the output format."""
    print("Creating a demo meeting note in your vault...")
    
    demo_path = vault / "Meetings" / "demo-voicevault-onboarding.md"
    
    content = f"""---
id: demo-onboarding
title: VoiceVault Demo Meeting
date: 2026-07-03
time: 09:00
duration: 15min
type: meeting
recording: none
---

# VoiceVault Demo Meeting

*Date: 2026-07-03 at 09:00 | Duration: 15 minutes*

## Summary

This is a sample meeting note to show you what VoiceVault output looks like. When you record a real meeting, the AI will generate a summary like this one based on the transcript and your notes.

## Key Discussion Points

- VoiceVault runs entirely on your machine — no cloud required
- You can dictate anywhere by holding the **{CONFIG.dictate_hotkey.upper()}** key (dictation mode)
- You can record meetings and get AI-enhanced summaries (meeting mode)
- All notes are stored in Markdown format in your Obsidian vault

## Action Items

- [ ] Record your first real meeting with VoiceVault
- [ ] Try dictating a quick note by holding {CONFIG.dictate_hotkey.upper()} and speaking
- [ ] Explore the vault folder in Obsidian

## My Notes

| Time | Tag | Note |
|------|-----|------|
| 0:00 | note | This is where your inline notes will appear during a meeting |
| 2:30 | action | You can tag notes as action, decision, or question |

## Transcript

**[0:00]** Welcome to the VoiceVault demo. This is what a transcribed meeting looks like.

**[1:30]** You can see the transcript is broken into timestamps so you can easily find specific moments.

**[5:00]** After the meeting ends, the AI reads the transcript and your notes to generate the summary above.

---

#meeting #voicevault #demo
"""
    
    demo_path.write_text(content, encoding="utf-8")
    print(f"  → Created: {demo_path}\n")


def _save_user_config(config: Dict[str, Any]):
    """Save user config to ~/.voicevault/user.json."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_JSON, "w") as f:
        json.dump(config, f, indent=2)


def _print_done(vault: Path):
    """Print final success message."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  You're ready! 🚀                                          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"Your notes will live in: {vault}")
    print()
    print("Quick start:")
    print(f"  • Hold {CONFIG.dictate_hotkey.upper()} key → speak → release → text appears at cursor")
    print("  • Click the menu bar icon → Start Meeting → speak → Stop")
    print()
    print("VoiceVault is now running in your menu bar. Enjoy!")
    print()


def _write_wav(path: str, audio: np.ndarray, sample_rate: int):
    """Write numpy array to WAV file."""
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_int16.tobytes())


def _iso_now() -> str:
    """Return ISO-formatted UTC timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Main entry point for standalone use ─────────────────────────────

if __name__ == "__main__":
    run_onboarding()
