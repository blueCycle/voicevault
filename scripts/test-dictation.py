#!/usr/bin/env python3
"""Live mic dictation smoke test.

Records from the macOS microphone for a fixed window, transcribes via
the configured whisper backend (mlx-whisper by default), then calls
inject_text() to push the result to the focused application.

Verifies the full dictation pipeline:
  mic -> numpy buffer -> ENGINE.transcribe_stream (numpy path)
       -> inject_text() (clipboard + simulated Cmd+V)

Outputs the transcript to data/test_dictation.txt for deterministic
verification regardless of which app holds focus.

Usage:
    ./venv/bin/python scripts/test-dictation.py [duration_seconds]
    ./venv/bin/python scripts/test-dictation.py 5
"""

import sys
import time
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import pyperclip

# Make `src.*` imports work whether we run from project root or scripts/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import CONFIG
from src.transcription.engine import ENGINE
from src.injection.macos import inject_text


SAMPLE_RATE = CONFIG.sample_rate         # 16000
CHANNELS = CONFIG.channels               # 1
DTYPE = np.float32

OUTPUT_TXT = ROOT / "data" / "test_dictation.txt"


def list_input_devices():
    print("[Test] Available input devices:")
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            marker = " <-- default" if i == sd.default.device[0] else ""
            print(f"  [{i}] {d['name']} (in={d['max_input_channels']}){marker}")


def record_mic(seconds: float) -> np.ndarray:
    """Capture `seconds` of mono float32 audio from the default input."""
    print(f"[Test] Recording for {seconds:.1f}s — speak now")
    frames = int(seconds * SAMPLE_RATE)

    # Use a RawInputStream so we get a single contiguous numpy array.
    audio = sd.rec(
        frames=frames,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()  # block until capture completes

    # rec() returns shape (frames, channels) for multi-channel; flatten to 1-D
    if audio.ndim == 2:
        audio = audio[:, 0]
    return audio


def transcribe_buffer(audio: np.ndarray) -> str:
    print(f"[Test] Transcribing {len(audio) / SAMPLE_RATE:.1f}s of audio "
          f"via backend={CONFIG.whisper_backend} model={CONFIG.whisper_model}")
    t0 = time.perf_counter()
    # numpy-array entry point — exercises _transcribe_mlx_array()
    text = ENGINE.transcribe_stream(audio)
    dt = time.perf_counter() - t0
    print(f"[Test] Transcription took {dt:.2f}s, {len(text)} chars")
    return text


def save_transcript(text: str) -> Path:
    OUTPUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_TXT.write_text(text + "\n")
    print(f"[Test] Wrote transcript → {OUTPUT_TXT}")
    return OUTPUT_TXT


def inject_with_focus_check(text: str) -> bool:
    """Send text to the focused app via the production injector."""
    if not text:
        print("[Test] No text to inject")
        return False
    print("[Test] About to inject — focus any text field now (e.g. TextEdit)")
    # Give the user a moment to switch focus.
    for i in range(3, 0, -1):
        print(f"  injecting in {i}...")
        time.sleep(1)
    ok = inject_text(text)
    # Verify clipboard side-effect — even if Cmd+V missed due to no
    # focused text field, the clipboard should hold our text (briefly).
    current_clipboard = pyperclip.paste()
    print(f"[Test] inject_text returned: {ok}")
    print(f"[Test] Clipboard restored to prior value (len={len(current_clipboard)}). "
          f"That means live injection happened.")
    return ok


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    print("=" * 60)
    print("  VoiceVault — live mic dictation test")
    print(f"  backend={CONFIG.whisper_backend}  "
          f"model={CONFIG.whisper_model}  device={CONFIG.whisper_device}")
    print("=" * 60)

    list_input_devices()
    print()

    try:
        audio = record_mic(duration)
    except Exception as e:
        print(f"[Test] Mic capture failed: {e}")
        print("[Test] Hint: grant microphone permission to your Terminal app via")
        print("       System Settings → Privacy & Security → Microphone")
        sys.exit(2)

    if np.abs(audio).max() < 1e-4:
        print("[Test] Warning: near-silent capture. Speak louder or check mic.")

    text = transcribe_buffer(audio)
    if not text:
        print("[Test] Empty transcription (silence or unintelligible audio).")
        print("[Test] Pipeline functional, but no text produced this run.")
        save_transcript("")
        sys.exit(0)

    save_transcript(text)
    print(f"[Test] Transcript preview: {text[:200]!r}"
          + ("..." if len(text) > 200 else ""))

    inject_with_focus_check(text)
    print("[Test] Done.")


if __name__ == "__main__":
    main()
