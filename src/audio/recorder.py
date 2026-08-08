import numpy as np
import sounddevice as sd
import wave
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
import time
from src.config import CONFIG


class AudioRecorder:
    """Full audio recording for meeting mode.
    
    Records microphone and optionally system audio (via loopback)
    to a WAV file. Supports start/stop with silence detection.
    """
    
    def __init__(self):
        self.is_recording = False
        self.frames: list[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        self.start_time: Optional[datetime] = None
        self.output_path: Optional[Path] = None
        self._silence_start: Optional[float] = None
        
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags):
        if status:
            print(f"Audio status: {status}")
        self.frames.append(indata.copy())
        
        # Silence detection
        if CONFIG.auto_detect_silence and self.is_recording:
            amplitude = np.abs(indata).mean()
            if amplitude < CONFIG.silence_threshold:
                if self._silence_start is None:
                    self._silence_start = time.time()
                elif time.time() - self._silence_start > CONFIG.silence_duration_ms / 1000.0:
                    print(f"[Meeting] Silence detected for {CONFIG.silence_duration_ms}ms, auto-stopping...")
                    self.stop()
            else:
                self._silence_start = None
    
    def start(self, title: Optional[str] = None) -> Path:
        """Start recording to a WAV file."""
        if self.is_recording:
            raise RuntimeError("Already recording")
        
        self.is_recording = True
        self.frames = []
        self.start_time = datetime.now()
        self._silence_start = None
        
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_{timestamp}.wav"
        if title:
            safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
            filename = f"meeting_{timestamp}_{safe_title}.wav"
        
        self.output_path = CONFIG.recordings_dir / filename
        
        self.stream = sd.InputStream(
            samplerate=CONFIG.sample_rate,
            channels=CONFIG.channels,
            dtype=np.int16,
            callback=self._audio_callback
        )
        self.stream.start()
        
        print(f"[Meeting] Recording started: {self.output_path}")
        return self.output_path
    
    def stop(self) -> Path:
        """Stop recording and save WAV file."""
        if not self.is_recording:
            raise RuntimeError("Not recording")
        
        self.is_recording = False
        
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        # Save WAV
        if self.frames and self.output_path:
            audio_data = np.concatenate(self.frames, axis=0)
            with wave.open(str(self.output_path), 'wb') as wav:
                wav.setnchannels(CONFIG.channels)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(CONFIG.sample_rate)
                wav.writeframes(audio_data.tobytes())
            
            duration = len(audio_data) / CONFIG.sample_rate
            print(f"[Meeting] Recording saved: {self.output_path} ({duration:.1f}s)")
            return self.output_path
        
        raise RuntimeError("No audio data recorded")
    
    @property
    def duration(self) -> float:
        """Current recording duration in seconds."""
        if not self.start_time:
            return 0.0
        if not self.is_recording:
            # Calculate from frames
            if self.frames:
                total_samples = sum(len(f) for f in self.frames)
                return total_samples / CONFIG.sample_rate
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.is_recording:
            self.stop()
        return False
