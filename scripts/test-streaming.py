#!/usr/bin/env python3
"""Headless test for the rolling-window streaming dictation loop.

Mimics the production dictation flow from `src/app.py` but without
rumps — captures the mic in chunks, re-transcribes the cumulative
buffer on a rolling interval, computes the diff against already
"injected" text, and emits each delta as it appears.

Output:
  - Each delta is printed as it lands.
  - Deltas are appended to `data/test_streaming.txt`.
  - Each delta is also copied to the system clipboard (mirrors what
    `inject_text` does — minus the simulated Cmd+V paste).

Usage:
    ./venv/bin/python scripts/test-streaming.py

Speak into the mic, then press <Enter> to stop and run the final flush.
"""

import sys
import time
import threading
import difflib
from pathlib import Path

import numpy as np
import sounddevice as sd
import pyperclip

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import CONFIG
from src.transcription.engine import ENGINE
# Re-use the exact same delta algorithm the GUI uses
from src.app import VoiceVaultApp


SAMPLE_RATE = CONFIG.sample_rate         # 16000
CHANNELS = CONFIG.channels
CHUNK_S = CONFIG.chunk_duration_ms / 1000.0     # 0.5s
INTERVAL_S = max(CONFIG.dictate_buffer_ms / 1000.0, 0.5)  # 1s

OUTPUT_TXT = ROOT / "data" / "test_streaming.txt"

audio_chunks: list = []
audio_lock = threading.Lock()
injected_text = ""
stop_event = threading.Event()


def _capture_loop():
    chunk_frames = int(CHUNK_S * SAMPLE_RATE)
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
        blocksize=chunk_frames,
    )
    stream.start()
    try:
        while not stop_event.is_set():
            audio, _ = stream.read(chunk_frames)
            mono = audio[:, 0].copy() if audio.ndim == 2 else audio.copy()
            with audio_lock:
                audio_chunks.append(mono)
    finally:
        stream.stop()
        stream.close()


def _streaming_worker():
    global injected_text
    last_size = 0
    while not stop_event.is_set():
        target = time.monotonic() + INTERVAL_S
        while time.monotonic() < target and not stop_event.is_set():
            time.sleep(0.05)
        if stop_event.is_set():
            break

        with audio_lock:
            buf_len = len(audio_chunks)
            if buf_len <= last_size:
                continue
            snapshot = list(audio_chunks)
            last_size = buf_len

        audio_seconds = sum(len(c) / SAMPLE_RATE for c in snapshot)
        print(f"\n[Test] -> cumulative transcribe ({len(snapshot)} chunks, "
              f"{audio_seconds:.1f}s of audio)")
        t0 = time.perf_counter()
        text = ENGINE.transcribe_stream(np.concatenate(snapshot)) or ""
        print(f"[Test]    {time.perf_counter() - t0:.2f}s inference -> "
              f"{len(text)} chars: {text!r}")
        if not text:
            continue

        delta = VoiceVaultApp._compute_dictation_delta(text, injected_text)
        if delta:
            injected_text += delta
            print(f"[Test]    +DELTA  ({len(delta):3d} chars): {delta!r}")
            pyperclip.copy(delta)
            OUTPUT_TXT.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_TXT, "a") as f:
                f.write(delta)


def _final_flush():
    global injected_text
    with audio_lock:
        if not audio_chunks:
            print("[Test] No audio captured.")
            return
        snap = list(audio_chunks)
    audio_seconds = sum(len(c) / SAMPLE_RATE for c in snap)
    total_seconds = audio_seconds
    # Trim to the last 30s for the final inference (large buffer is overkill
    # for capturing whatever Whisper missed in incremental passes)
    if audio_seconds > 30:
        keep_chunks = []
        accum = 0.0
        target = 30.0
        for c in reversed(snap):
            keep_chunks.insert(0, c)
            accum += len(c) / SAMPLE_RATE
            if accum >= target:
                break
        snap = keep_chunks
        print(f"[Test] FINAL flush (tail 30s of {total_seconds:.1f}s)")
    else:
        print(f"[Test] FINAL flush on full {audio_seconds:.1f}s buffer")

    t0 = time.perf_counter()
    text = ENGINE.transcribe_stream(np.concatenate(snap)) or ""
    print(f"[Test]    {time.perf_counter() - t0:.2f}s -> "
          f"{len(text)} chars: {text!r}")

    delta = VoiceVaultApp._compute_dictation_delta(text, injected_text)
    if delta:
        injected_text += delta
        print(f"[Test]    FINAL +DELTA ({len(delta)} chars): {delta!r}")
        with open(OUTPUT_TXT, "a") as f:
            f.write(delta)
    print(f"[Test] Total transcript length: {len(injected_text)} chars")
    print(f"[Test] Appended each delta -> {OUTPUT_TXT}")


def main():
    print("=" * 64)
    print("  VoiceVault — headless streaming incremental dictation test")
    print(f"  chunk={CHUNK_S}s  interval={INTERVAL_S}s  "
          f"backend={CONFIG.whisper_backend}  model={CONFIG.whisper_model}")
    print("=" * 64)
    print()
    print("Speak into the mic. Press <Enter> to stop and run the final flush.")
    print("Each incremental delta will print as Whisper emits it.")
    print()

    cap = threading.Thread(target=_capture_loop, daemon=True)
    cap.start()
    worker = threading.Thread(target=_streaming_worker, daemon=True)
    worker.start()

    try:
        input()
    except EOFError:
        pass

    print("\n[Test] Stopping capture + worker...")
    stop_event.set()
    cap.join(timeout=2.0)
    worker.join(timeout=3.0)
    _final_flush()
    print("\n[Test] Done.")


if __name__ == "__main__":
    main()
