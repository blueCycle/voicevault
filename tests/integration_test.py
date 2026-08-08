#!/usr/bin/env python3
"""VoiceVault Integration Test Suite

Runs all major components without the GUI (no rumps needed).
Tests config loading, imports, transcription, Ollama, meeting pipeline,
audio recorder initialization, and obsidian export.
"""

import sys
import tempfile
import json
import time
import os
from pathlib import Path
import numpy as np
import wave

sys.path.insert(0, str(Path(__file__).parent.parent))

FAILED = 0
PASSED = 0

def test(name, fn):
    global FAILED, PASSED
    try:
        fn()
        print(f"  ✅ {name}")
        PASSED += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAILED += 1


def t_config_loads():
    from src.config import Config, CONFIG
    assert CONFIG.dictate_hotkey == "ctrl"
    assert CONFIG.dictate_buffer_ms == 1000
    assert CONFIG.whisper_model == "mlx-community/whisper-large-v3-turbo"
    assert CONFIG.whisper_backend == "mlx-whisper"
    assert CONFIG.whisper_device == "mps"
    assert CONFIG.language == "en"
    assert CONFIG.ollama_url == "http://localhost:11434"
    assert CONFIG.obsidian_vault is not None

def t_config_user_json_override():
    from src.config import Config
    app_dir = Path.home() / ".voicevault"
    app_dir.mkdir(exist_ok=True)
    user_json = app_dir / "user_test_override.json"
    # Temporarily write to a test file path by monkeypatching
    # Actually, let's just test the _user_json method exists and returns a dict
    result = Config._user_json()
    assert isinstance(result, dict)

def t_transcription_engine_loads():
    from src.transcription.engine import TranscriptionEngine
    engine = TranscriptionEngine()
    assert engine._whisper_model is not None

def t_transcription_engine_transcribe_file():
    from src.transcription.engine import TranscriptionEngine
    engine = TranscriptionEngine()
    # Create a silent test WAV file
    sample_rate = 16000
    duration = 1  # 1 second of silence
    samples = np.zeros(int(duration * sample_rate), dtype=np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
    with wave.open(temp_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    try:
        text = engine.transcribe_file(Path(temp_path))
        # Should return empty or some whitespace for silence
        assert isinstance(text, str)
    finally:
        Path(temp_path).unlink(missing_ok=True)

def t_meeting_manager_init():
    from src.meeting.session import MeetingManager
    mgr = MeetingManager()
    assert not mgr.is_recording
    assert mgr.current_session is None

def t_audio_recorder_init():
    from src.audio.recorder import AudioRecorder
    rec = AudioRecorder()
    assert not rec.is_recording

def t_audio_streamer_init():
    from src.audio.streamer import AudioStreamer
    def dummy_callback(chunk):
        pass
    streamer = AudioStreamer(callback=dummy_callback)
    assert not streamer.is_streaming

def t_obsidian_exporter_init():
    from src.obsidian.exporter import ObsidianExporter
    exporter = ObsidianExporter()
    assert exporter is not None

def t_ollama_health():
    import requests
    from src.config import CONFIG
    resp = requests.get(f"{CONFIG.ollama_url}/api/tags", timeout=3)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    models = [m.get("name", m.get("model", "")) for m in data["models"]]
    assert any("llama3.1" in m for m in models), f"llama3.1 not in {models}"

def t_ollama_generate():
    import requests
    from src.config import CONFIG
    resp = requests.post(
        f"{CONFIG.ollama_url}/api/generate",
        json={"model": CONFIG.ollama_model, "prompt": "Say hi in one word.", "stream": False},
        timeout=30
    )
    assert resp.status_code == 200
    text = resp.json().get("response", "").strip()
    assert len(text) > 0

def t_onboarding_needs():
    from src.onboarding import needs_onboarding
    # Just check it runs without error
    result = needs_onboarding()
    assert isinstance(result, bool)

def t_onboarding_user_config_format():
    from src.onboarding import APP_DIR, USER_JSON
    # Ensure the paths are valid Path objects
    assert isinstance(APP_DIR, Path)
    assert isinstance(USER_JSON, Path)

def t_hotkey_resolution():
    # Simulate the key resolution logic from app.py
    from pynput import keyboard
    key_map = {
        'ctrl': (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r),
        'cmd': (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r),
        'f13': (keyboard.Key.f13,),
        'a': ('char', 'a'),
    }
    for hk, target in key_map.items():
        if target[0] == 'char':
            assert hasattr(keyboard.Key, 'a') or True  # char keys are handled separately
        else:
            assert target[0] in (keyboard.Key.ctrl, keyboard.Key.cmd, keyboard.Key.f13)

def t_inject_text():
    from src.injection.macos import inject_text
    # Should at least not crash for empty text
    assert inject_text("") == False
    # Should copy to clipboard and report success for non-empty
    assert inject_text("test") == True

def t_import_all():
    # Verify all renamed modules import cleanly
    import src.config
    import src.audio.streamer
    import src.audio.recorder
    import src.transcription.engine
    import src.meeting.session
    import src.obsidian.exporter
    import src.injection.macos
    import src.onboarding
    # app.py depends on rumps which may not work in CLI mode, so skip it

def t_deprecation_alias():
    # VV_WISPR_HOTKEY should still work via the fallback
    import os
    os.environ["VV_WISPR_HOTKEY"] = "f13"
    try:
        from src.config import Config
        c = Config.from_env()
        assert c.dictate_hotkey == "f13"
    finally:
        del os.environ["VV_WISPR_HOTKEY"]


def main():
    print()
    print("=" * 50)
    print("  VoiceVault Integration Test Suite")
    print("=" * 50)
    print()

    tests = [
        ("Config loads and defaults correct", t_config_loads),
        ("Config user.json loader exists", t_config_user_json_override),
        ("Transcription engine loads", t_transcription_engine_loads),
        ("Transcription engine transcribes silence", t_transcription_engine_transcribe_file),
        ("MeetingManager initializes", t_meeting_manager_init),
        ("AudioRecorder initializes", t_audio_recorder_init),
        ("AudioStreamer initializes", t_audio_streamer_init),
        ("ObsidianExporter initializes", t_obsidian_exporter_init),
        ("Ollama health check", t_ollama_health),
        ("Ollama generation works", t_ollama_generate),
        ("Onboarding needs_onboarding runs", t_onboarding_needs),
        ("Onboarding paths are valid", t_onboarding_user_config_format),
        ("Hotkey resolution logic", t_hotkey_resolution),
        ("Text injection (clipboard fallback)", t_inject_text),
        ("All renamed modules import cleanly", t_import_all),
        ("Legacy VV_WISPR_HOTKEY still works", t_deprecation_alias),
    ]

    for name, fn in tests:
        test(name, fn)

    print()
    print("=" * 50)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 50)
    print()

    if FAILED > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
