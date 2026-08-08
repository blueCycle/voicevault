import json
import time
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave
import tempfile

import httpx
from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk


class DeepgramProvider(STTProvider):
    """Deepgram Nova-2 streaming and batch transcription.
    
    Zero-retention, SOC 2. Best real-time streaming API.
    Pricing: Nova-2 = $0.0043/min, on-prem container available.
    """
    
    name = "deepgram"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = True
    
    COST_PER_MINUTE = 0.0043  # Nova-2
    
    def __init__(self, api_key: str = None, model: str = "nova-2", **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.model = model
        self.base_url = "https://api.deepgram.com/v1"
    
    def _headers(self):
        return {"Authorization": f"Token {self.api_key}"}
    
    async def transcribe_file(self, audio_path: Path, language: str = "en", diarize: bool = False, **kwargs) -> TranscriptResult:
        start = time.time()
        
        with wave.open(str(audio_path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
        
        params = {
            "model": self.model,
            "language": language,
            "punctuate": "true",
            "paragraphs": "true",
            "utterances": "true",
        }
        if diarize:
            params["diarize"] = "true"
        
        async with httpx.AsyncClient() as client:
            with open(audio_path, 'rb') as f:
                resp = await client.post(
                    f"{self.base_url}/listen",
                    headers=self._headers(),
                    params=params,
                    content=f.read(),
                    timeout=300.0,
                )
                resp.raise_for_status()
                data = resp.json()
        
        elapsed = time.time() - start
        
        segments = []
        full_text_parts = []
        if "results" in data and "channels" in data["results"]:
            for alt in data["results"]["channels"][0].get("alternatives", []):
                for para in alt.get("paragraphs", {}).get("paragraphs", []):
                    for sent in para.get("sentences", []):
                        segments.append(TranscriptSegment(
                            start=sent.get("start", 0),
                            end=sent.get("end", 0),
                            text=sent.get("text", ""),
                        ))
                        full_text_parts.append(sent.get("text", ""))
        
        return TranscriptResult(
            provider=self.name,
            text=" ".join(full_text_parts),
            segments=segments,
            duration_seconds=duration,
            processing_time_seconds=elapsed,
            cost_usd=(duration / 60.0) * self.COST_PER_MINUTE,
            metadata={"model": self.model, "language": language},
            raw_response=data,
        )
    
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], language: str = "en", **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        import websockets
        
        ws_url = (
            f"wss://api.deepgram.com/v1/listen?"
            f"model={self.model}&language={language}&punctuate=true&interim_results=true&encoding=linear16&sample_rate=16000&channels=1"
        )
        
        async with websockets.connect(ws_url, extra_headers={"Authorization": f"Token {self.api_key}"}) as ws:
            # Start sender task
            async def send_audio():
                async for chunk in audio_generator:
                    # Convert float32 to int16 bytes
                    int16 = (chunk * 32767).astype(np.int16)
                    await ws.send(int16.tobytes())
                await ws.send(json.dumps({"type": "CloseStream"}))
            
            sender_task = asyncio.create_task(send_audio())
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    
                    if data.get("type") == "Results":
                        channel = data.get("channel", {})
                        alt = channel.get("alternatives", [{}])[0]
                        text = alt.get("transcript", "").strip()
                        if text:
                            yield StreamingChunk(
                                is_final=not data.get("is_final", True),
                                text=text,
                                start=alt.get("words", [{}])[0].get("start", 0) if alt.get("words") else 0,
                                end=alt.get("words", [{}])[-1].get("end", 0) if alt.get("words") else 0,
                                confidence=alt.get("confidence"),
                            )
            except asyncio.TimeoutError:
                pass
            finally:
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
    
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/projects", headers=self._headers(), timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False
