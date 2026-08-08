import json
import time
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave
import tempfile

from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk
from src.config import CONFIG


class LocalWhisperProvider(STTProvider):
    """Local Whisper transcription using faster-whisper or whisper.cpp."""
    
    name = "local"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = False
    
    def __init__(self, model: str = None, device: str = None, backend: str = None, **kwargs):
        super().__init__(api_key=None, **kwargs)
        self.model = model or CONFIG.whisper_model
        self.device = device or CONFIG.whisper_device
        self.backend = backend or CONFIG.whisper_backend
        self._engine = None
    
    def _get_engine(self):
        if self._engine is None:
            from src.transcription.engine import TranscriptionEngine
            self._engine = TranscriptionEngine()
        return self._engine
    
    async def transcribe_file(self, audio_path: Path, **kwargs) -> TranscriptResult:
        start = time.time()
        engine = self._get_engine()
        
        segments = engine.transcribe_file_with_timestamps(audio_path)
        full_text = " ".join([s["text"] for s in segments])
        
        # Get audio duration
        with wave.open(str(audio_path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
        
        elapsed = time.time() - start
        
        return TranscriptResult(
            provider=self.name,
            text=full_text,
            segments=[
                TranscriptSegment(
                    start=s["start"],
                    end=s["end"],
                    text=s["text"],
                )
                for s in segments
            ],
            duration_seconds=duration,
            processing_time_seconds=elapsed,
            cost_usd=0.0,
        )
    
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        engine = self._get_engine()
        chunk_start = 0.0
        
        async for audio_chunk in audio_generator:
            chunk_duration = len(audio_chunk) / CONFIG.sample_rate
            text = engine.transcribe_stream(audio_chunk)
            
            if text:
                yield StreamingChunk(
                    is_final=True,
                    text=text,
                    start=chunk_start,
                    end=chunk_start + chunk_duration,
                )
            
            chunk_start += chunk_duration
    
    def health_check(self) -> bool:
        try:
            self._get_engine()
            return True
        except Exception:
            return False
