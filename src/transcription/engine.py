import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
import subprocess
import json
import tempfile
import wave
from src.config import CONFIG


class TranscriptionEngine:
    """Local speech-to-text using faster-whisper or whisper.cpp.
    
    Supports both streaming (dictation) and batch (meeting) modes.
    """
    
    def __init__(self):
        self._whisper_model = None
        self._load_model()
    
    def _load_model(self):
        """Lazy-load the whisper model."""
        if self._whisper_model is not None:
            return
        
        if CONFIG.whisper_backend == "faster-whisper":
            try:
                from faster_whisper import WhisperModel
                self._whisper_model = WhisperModel(
                    CONFIG.whisper_model,
                    device=CONFIG.whisper_device,
                    compute_type="int8" if CONFIG.whisper_device == "cpu" else "float16"
                )
                print(f"[Transcription] Loaded faster-whisper model: {CONFIG.whisper_model}")
            except ImportError:
                print("faster-whisper not installed. Install with: pip install faster-whisper")
                raise
        elif CONFIG.whisper_backend == "mlx-whisper":
            try:
                import mlx_whisper
                self._whisper_model = mlx_whisper
                print(f"[Transcription] Loaded mlx-whisper backend")
            except ImportError:
                print("mlx-whisper not installed. Install with: pip install mlx-whisper")
                raise
        elif CONFIG.whisper_backend == "whisper.cpp":
            # whisper.cpp via subprocess - model should be pre-converted to ggml
            print(f"[Transcription] Using whisper.cpp backend (subprocess)")
            self._whisper_model = "whisper.cpp"
        else:
            raise ValueError(f"Unknown backend: {CONFIG.whisper_backend}")
    
    def transcribe_stream(self, audio_chunk: np.ndarray, *,
                         initial_prompt: str = "") -> str:
        """Transcribe a small audio chunk (for dictation streaming mode).
        
        Returns the transcribed text for this chunk.
        """
        if self._whisper_model is None:
            self._load_model()
        
        if CONFIG.whisper_backend == "faster-whisper":
            # Save to temp file for faster-whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
            
            self._write_wav(temp_path, audio_chunk, CONFIG.sample_rate)
            
            segments, _ = self._whisper_model.transcribe(
                temp_path,
                language=CONFIG.language,
                initial_prompt=initial_prompt or None,
                condition_on_previous_text=False,  # Don't condition on previous for streaming
                beam_size=1,
                best_of=1,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            text = " ".join([segment.text for segment in segments])
            Path(temp_path).unlink(missing_ok=True)
            return text.strip()
        
        elif CONFIG.whisper_backend == "mlx-whisper":
            return self._transcribe_mlx_array(audio_chunk, initial_prompt=initial_prompt)
        
        elif self._whisper_model == "whisper.cpp":
            # For whisper.cpp, use the stream tool
            return self._transcribe_whisper_cpp_stream(audio_chunk)
        
        return ""
    
    def transcribe_file(self, audio_path: Path) -> str:
        """Transcribe a full audio file (for meeting mode).
        
        Returns the complete transcript.
        """
        if self._whisper_model is None:
            self._load_model()
        
        if CONFIG.whisper_backend == "faster-whisper":
            segments, info = self._whisper_model.transcribe(
                str(audio_path),
                language=CONFIG.language,
                condition_on_previous_text=True,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            text = " ".join([segment.text for segment in segments])
            print(f"[Transcription] Detected language: {info.language}, probability: {info.language_probability:.2f}")
            return text.strip()
        
        elif CONFIG.whisper_backend == "mlx-whisper":
            return self._transcribe_mlx_file(audio_path)
        
        elif self._whisper_model == "whisper.cpp":
            return self._transcribe_whisper_cpp_file(audio_path)
        
        return ""
    
    def transcribe_file_with_timestamps(self, audio_path: Path) -> List[Dict[str, Any]]:
        """Transcribe with timestamps for meeting notes correlation.
        
        Returns list of dicts with 'start', 'end', 'text' keys.
        """
        if self._whisper_model is None:
            self._load_model()
        
        if CONFIG.whisper_backend == "faster-whisper":
            segments, info = self._whisper_model.transcribe(
                str(audio_path),
                language=CONFIG.language,
                condition_on_previous_text=True,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            return [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip()
                }
                for segment in segments
            ]
        
        elif CONFIG.whisper_backend == "mlx-whisper":
            result = self._whisper_model.transcribe(
                str(audio_path),
                path_or_hf_repo=CONFIG.whisper_model,
                language=CONFIG.language,
                verbose=False,
                temperature=0.0,
            )
            # mlx-whisper returns segments with start/end
            segments = result.get("segments", [])
            return [
                {
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", "").strip()
                }
                for seg in segments
            ]
        
        # For whisper.cpp, we'd need to parse output differently
        return []
    
    def _write_wav(self, path: str, audio: np.ndarray, sample_rate: int):
        """Write numpy array to WAV file."""
        # Convert float32 to int16
        audio_int16 = (audio * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_int16.tobytes())
    
    def _transcribe_mlx_array(self, audio: np.ndarray, *,
                              initial_prompt: str = "") -> str:
        """Transcribe a numpy audio array via mlx-whisper."""
        # mlx-whisper accepts numpy arrays directly or file paths
        result = self._whisper_model.transcribe(
            audio,
            path_or_hf_repo=CONFIG.whisper_model,
            language=CONFIG.language,
            initial_prompt=initial_prompt or None,
            verbose=False,
            temperature=0.0,
        )
        text = result.get("text", "")
        return text.strip()
    
    def _transcribe_mlx_file(self, audio_path: Path, *,
                             initial_prompt: str = "") -> str:
        """Transcribe an audio file via mlx-whisper."""
        result = self._whisper_model.transcribe(
            str(audio_path),
            path_or_hf_repo=CONFIG.whisper_model,
            language=CONFIG.language,
            initial_prompt=initial_prompt or None,
            verbose=False,
            temperature=0.0,
        )
        text = result.get("text", "")
        return text.strip()
    
    def _transcribe_whisper_cpp_stream(self, audio_chunk: np.ndarray) -> str:
        """Transcribe via whisper.cpp stream tool."""
        # Save to temp file and call whisper.cpp stream
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
        
        self._write_wav(temp_path, audio_chunk, CONFIG.sample_rate)
        
        try:
            result = subprocess.run(
                ["whisper-cli", "-m", f"~/.whisper/ggml-{CONFIG.whisper_model}.bin", 
                 "-f", temp_path, "-l", CONFIG.language, "-np", "-nt"],
                capture_output=True,
                text=True,
                timeout=30
            )
            Path(temp_path).unlink(missing_ok=True)
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            Path(temp_path).unlink(missing_ok=True)
            return ""
    
    def _transcribe_whisper_cpp_file(self, audio_path: Path) -> str:
        """Transcribe via whisper-cli for full files."""
        try:
            result = subprocess.run(
                ["whisper-cli", "-m", f"~/.whisper/ggml-{CONFIG.whisper_model}.bin",
                 "-f", str(audio_path), "-l", CONFIG.language, "-np", "-nt"],
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""


# Global engine instance
ENGINE = TranscriptionEngine()
