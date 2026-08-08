# VoiceVault - Privacy-First Voice Note Taking
# Voice-to-text dictation and meeting recording with AI summaries

import os
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

@dataclass
class Config:
    """Application configuration."""
    
    # Paths
    data_dir: Path = field(default_factory=lambda: Path.home() / "code" / "experiments" / "voicevault" / "data")
    recordings_dir: Path = field(default_factory=lambda: Path.home() / "code" / "experiments" / "voicevault" / "data" / "recordings")
    transcripts_dir: Path = field(default_factory=lambda: Path.home() / "code" / "experiments" / "voicevault" / "data" / "transcripts")
    notes_dir: Path = field(default_factory=lambda: Path.home() / "code" / "experiments" / "voicevault" / "data" / "notes")
    
    # Obsidian — updated by onboarding, fallback to default
    obsidian_vault: Optional[Path] = field(default_factory=lambda: Path.home() / "Obsidian" / "voicevault")
    
    # Audio
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 500
    
    # Whisper
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"  # model id or HF repo
    whisper_backend: str = "mlx-whisper"  # faster-whisper | mlx-whisper | whisper.cpp
    whisper_device: str = "mps"  # cpu, cuda, mps (mlx-whisper ignores this, uses Metal automatically)
    language: str = "en"

    # Hot-words / vocabulary passed as the Whisper `initial_prompt`
    # Use this to teach Whisper the names, brands, jargon, etc. that
    # appear in your dictations. Example:
    # initial_prompt = "Names: John Smith, Sarah Chen. Acronyms: HIPAA, KPI."
    initial_prompt: str = ""
    
    # Dictation mode
    dictate_hotkey: str = "ctrl"  # Hold this key to dictate: ctrl, cmd, alt, f13, or any letter
    dictate_buffer_ms: int = 1000
    
    # Meeting mode
    auto_detect_silence: bool = True
    silence_threshold: float = 0.01
    silence_duration_ms: int = 3000
    
    # LLM Summarization (Ollama)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    summarize_meetings: bool = True
    
    # Provider API Keys (all optional, used by provider registry)
    deepgram_api_key: Optional[str] = None
    assemblyai_api_key: Optional[str] = None
    speechmatics_api_key: Optional[str] = None
    revai_api_key: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_region: str = "us-east-1"
    aws_s3_bucket: Optional[str] = None
    
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    
    # Default providers (fallback chain)
    stt_provider: str = "local"  # local | deepgram | assemblyai | speechmatics | revai | aws
    llm_provider: str = "ollama"  # ollama | groq | anthropic | openrouter | mistral
    judge_provider: str = "anthropic"  # llm-as-judge provider
    
    def __post_init__(self):
        """Ensure directories exist."""
        for path in [self.data_dir, self.recordings_dir, self.transcripts_dir, 
                     self.notes_dir, self.obsidian_vault]:
            if path:
                path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def _user_json(cls) -> Dict[str, Any]:
        """Load user preferences from ~/.voicevault/user.json if present."""
        user_json = Path.home() / ".voicevault" / "user.json"
        if user_json.exists():
            with open(user_json) as f:
                data = json.load(f)
                # Convert vault_path string back to Path
                if "vault_path" in data:
                    data["obsidian_vault"] = Path(data.pop("vault_path"))
                return data
        return {}
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables, user.json, and class defaults."""
        # Get default field values from the class defaults
        defaults = {
            f.name: f.default_factory() if callable(f.default_factory) else f.default
            for f in cls.__dataclass_fields__.values()
        }
        # Merge user.json overrides (lowest precedence after class defaults)
        user_cfg = cls._user_json()
        # Environment variables override everything
        vault_path = user_cfg.get("obsidian_vault", defaults.get("obsidian_vault"))
        env_vault = os.getenv("VV_OBSIDIAN_VAULT")
        if env_vault:
            vault_path = Path(env_vault)
        return cls(
            data_dir=Path(os.getenv("VV_DATA_DIR", defaults.get("data_dir", "."))),
            obsidian_vault=vault_path,
            whisper_model=os.getenv("VV_WHISPER_MODEL", defaults.get("whisper_model", "mlx-community/whisper-large-v3-turbo")),
            whisper_backend=os.getenv("VV_WHISPER_BACKEND", defaults.get("whisper_backend", "mlx-whisper")),
            whisper_device=os.getenv("VV_WHISPER_DEVICE", defaults.get("whisper_device", "mps")),
            language=os.getenv("VV_LANGUAGE", defaults.get("language", "en")),
            initial_prompt=os.getenv("VV_INITIAL_PROMPT", defaults.get("initial_prompt", "")),
            dictate_hotkey=os.getenv("VV_DICTATE_HOTKEY", os.getenv("VV_WISPR_HOTKEY", defaults.get("dictate_hotkey", "ctrl"))),
            dictate_buffer_ms=int(os.getenv("VV_DICTATE_BUFFER_MS", defaults.get("dictate_buffer_ms", 1000))),
            ollama_url=os.getenv("VV_OLLAMA_URL", defaults.get("ollama_url", "http://localhost:11434")),
            ollama_model=os.getenv("VV_OLLAMA_MODEL", defaults.get("ollama_model", "llama3.1:8b")),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY"),
            assemblyai_api_key=os.getenv("ASSEMBLYAI_API_KEY"),
            speechmatics_api_key=os.getenv("SPEECHMATICS_API_KEY"),
            revai_api_key=os.getenv("REVAI_API_KEY"),
            aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region=os.getenv("AWS_REGION", defaults.get("aws_region", "us-east-1")),
            aws_s3_bucket=os.getenv("AWS_S3_BUCKET"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            mistral_api_key=os.getenv("MISTRAL_API_KEY"),
            stt_provider=os.getenv("VV_STT_PROVIDER", defaults.get("stt_provider", "local")),
            llm_provider=os.getenv("VV_LLM_PROVIDER", defaults.get("llm_provider", "ollama")),
            judge_provider=os.getenv("VV_JUDGE_PROVIDER", defaults.get("judge_provider", "anthropic")),
        )

# Global config instance
CONFIG = Config.from_env()
