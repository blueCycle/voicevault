from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from datetime import datetime


@dataclass
class TranscriptSegment:
    """A single segment of a transcript with timing."""
    start: float  # seconds
    end: float
    text: str
    confidence: Optional[float] = None
    speaker: Optional[str] = None  # for diarization
    word_timings: Optional[List[Dict[str, Any]]] = None


@dataclass
class TranscriptResult:
    """Result of a transcription operation."""
    provider: str
    text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: Optional[str] = None
    confidence: Optional[float] = None
    duration_seconds: float = 0.0
    processing_time_seconds: float = 0.0
    cost_usd: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_response: Optional[Any] = None  # provider-specific raw data for debugging


@dataclass
class StreamingChunk:
    """Real-time streaming transcription chunk."""
    is_final: bool  # True if this is a finalized (committed) transcript
    text: str
    start: float
    end: float
    speaker: Optional[str] = None
    confidence: Optional[float] = None


class STTProvider(ABC):
    """Abstract base class for Speech-to-Text providers."""
    
    name: str = "abstract"
    supports_streaming: bool = False
    supports_diarization: bool = False
    supports_batch: bool = True
    requires_api_key: bool = True
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.config = kwargs
    
    @abstractmethod
    async def transcribe_file(self, audio_path: Path, **kwargs) -> TranscriptResult:
        """Transcribe a full audio file (batch)."""
        pass
    
    @abstractmethod
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        """Real-time streaming transcription from audio chunks."""
        pass
    
    def normalize_audio(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Normalize audio to provider requirements. Override if needed."""
        return audio
    
    def health_check(self) -> bool:
        """Quick connectivity/auth check."""
        return True


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    provider: str
    text: str
    model: str
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    processing_time_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    name: str = "abstract"
    requires_api_key: bool = True
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.model = model
        self.config = kwargs
    
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        """Generate text from a prompt."""
        pass
    
    def health_check(self) -> bool:
        """Quick connectivity/auth check."""
        return True
    
    async def summarize_meeting(self, transcript: str, notes: Optional[str] = None, **kwargs) -> LLMResponse:
        """Default meeting summarization prompt."""
        system = """You are a meeting assistant. Generate a structured summary of the meeting transcript provided.

Format your response with:
1. Brief summary (2-3 sentences)
2. Key discussion points
3. Action items (with assignees if identifiable)
4. Decisions made

Be concise and factual. Do not hallucinate or invent information not present in the transcript."""
        
        user_prompt = f"TRANSCRIPT:\n{transcript}"
        if notes:
            user_prompt += f"\n\nUSER NOTES:\n{notes}"
        
        return await self.generate(user_prompt, system_prompt=system, **kwargs)


class ProviderRegistry:
    """Registry for STT and LLM providers."""
    
    _stt_providers: Dict[str, type] = {}
    _llm_providers: Dict[str, type] = {}
    
    @classmethod
    def register_stt(cls, name: str, provider_class: type):
        cls._stt_providers[name] = provider_class
    
    @classmethod
    def register_llm(cls, name: str, provider_class: type):
        cls._llm_providers[name] = provider_class
    
    @classmethod
    def get_stt(cls, name: str, **kwargs) -> STTProvider:
        if name not in cls._stt_providers:
            raise ValueError(f"Unknown STT provider: {name}. Available: {list(cls._stt_providers.keys())}")
        return cls._stt_providers[name](**kwargs)
    
    @classmethod
    def get_llm(cls, name: str, **kwargs) -> LLMProvider:
        if name not in cls._llm_providers:
            raise ValueError(f"Unknown LLM provider: {name}. Available: {list(cls._llm_providers.keys())}")
        return cls._llm_providers[name](**kwargs)
    
    @classmethod
    def list_stt(cls) -> List[str]:
        return list(cls._stt_providers.keys())
    
    @classmethod
    def list_llm(cls) -> List[str]:
        return list(cls._llm_providers.keys())
