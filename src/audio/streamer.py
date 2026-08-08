import numpy as np
import sounddevice as sd
import threading
import queue
from typing import Callable, Optional
import time
from src.config import CONFIG


class AudioStreamer:
    """Real-time audio streaming for dictation mode.
    
    Captures microphone audio in chunks and passes to a callback
    for immediate transcription at the cursor.
    """
    
    def __init__(self, callback: Callable[[np.ndarray], None]):
        self.callback = callback
        self.is_streaming = False
        self.audio_queue = queue.Queue()
        self.stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags):
        """SoundDevice callback - called for every audio chunk."""
        if status:
            print(f"Audio status: {status}")
        # Convert to mono float32
        audio = indata[:, 0].astype(np.float32)
        self.audio_queue.put(audio)
        
    def _process_loop(self):
        """Background thread: consumes audio chunks and calls transcription."""
        buffer = []
        buffer_duration = 0.0
        target_duration = CONFIG.dictate_buffer_ms / 1000.0
        
        while self.is_streaming:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                buffer.append(chunk)
                buffer_duration += len(chunk) / CONFIG.sample_rate
                
                # Process when buffer reaches target duration
                if buffer_duration >= target_duration:
                    audio_chunk = np.concatenate(buffer)
                    self.callback(audio_chunk)
                    buffer = []
                    buffer_duration = 0.0
            except queue.Empty:
                continue
        
        # Flush remaining buffer
        if buffer:
            audio_chunk = np.concatenate(buffer)
            self.callback(audio_chunk)
    
    def start(self):
        """Start streaming audio from microphone."""
        if self.is_streaming:
            return
            
        self.is_streaming = True
        self.audio_queue = queue.Queue()
        
        self.stream = sd.InputStream(
            samplerate=CONFIG.sample_rate,
            channels=CONFIG.channels,
            dtype=np.float32,
            callback=self._audio_callback
        )
        self.stream.start()
        
        self._thread = threading.Thread(target=self._process_loop)
        self._thread.start()
        
        print("[Dictate] Audio streaming started")
    
    def stop(self):
        """Stop streaming audio."""
        self.is_streaming = False
        
        if self._thread:
            self._thread.join(timeout=2.0)
        
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        print("[Dictate] Audio streaming stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
