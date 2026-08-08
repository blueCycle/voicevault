import json
import time
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave

import httpx
from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk


class RevAIProvider(STTProvider):
    """Rev.ai transcription - human-level accuracy at a premium.
    
    Zero-retention, HIPAA-eligible, SOC 2. Most accurate but expensive.
    Pricing: $0.035/min
    """
    
    name = "revai"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = True
    
    COST_PER_MINUTE = 0.035
    
    def __init__(self, api_key: str = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.base_url = "https://api.rev.ai"
    
    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
    
    async def transcribe_file(self, audio_path: Path, language: str = "en", diarize: bool = False, **kwargs) -> TranscriptResult:
        start = time.time()
        
        with wave.open(str(audio_path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
        
        async with httpx.AsyncClient() as client:
            # Submit job
            with open(audio_path, 'rb') as f:
                submit_resp = await client.post(
                    f"{self.base_url}/speechtotext/v1/jobs",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"media": (audio_path.name, f, "audio/wav")},
                    data={"options": json.dumps({
                        "transcriber": "machine",
                        "language": language,
                        "skip_diarization": not diarize,
                    })},
                    timeout=300.0,
                )
                submit_resp.raise_for_status()
                job_id = submit_resp.json()["id"]
            
            # Poll for completion
            while True:
                poll_resp = await client.get(
                    f"{self.base_url}/speechtotext/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30.0,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                
                status = data.get("status")
                if status in ("transcribed", "completed"):
                    break
                elif status in ("failed", ):
                    raise RuntimeError(f"Rev.ai job failed: {data.get('failure')}")
                
                await asyncio.sleep(5.0)
            
            # Fetch transcript
            transcript_resp = await client.get(
                f"{self.base_url}/speechtotext/v1/jobs/{job_id}/transcript",
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/vnd.rev.transcript.v1.0+json"},
                timeout=30.0,
            )
            transcript_resp.raise_for_status()
            transcript_data = transcript_resp.json()
        
        elapsed = time.time() - start
        
        segments = []
        full_text_parts = []
        for mono in transcript_data.get("monologues", []):
            for elem in mono.get("elements", []):
                if elem.get("type") == "text":
                    text = elem.get("value", "").strip()
                    if text:
                        segments.append(TranscriptSegment(
                            start=elem.get("ts", 0),
                            end=elem.get("end_ts", 0),
                            text=text,
                            speaker=mono.get("speaker", None),
                        ))
                        full_text_parts.append(text)
        
        return TranscriptResult(
            provider=self.name,
            text=" ".join(full_text_parts),
            segments=segments,
            duration_seconds=duration,
            processing_time_seconds=elapsed,
            cost_usd=(duration / 60.0) * self.COST_PER_MINUTE,
            metadata={"language": language},
            raw_response=transcript_data,
        )
    
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], language: str = "en", **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        import websockets
        
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"{self.base_url}/speechtotext/v1/stream",
                headers=self._headers(),
                json={"metadata": "voicevault"},
                timeout=30.0,
            )
            token_resp.raise_for_status()
            token = token_resp.json().get("access_token")
        
        ws_url = f"wss://api.rev.ai/speechtotext/v1/stream?access_token={token}&content_type=audio/x-raw;layout=interleaved;rate=16000;format=S16LE;channels=1"
        
        async with websockets.connect(ws_url) as ws:
            async def send_audio():
                async for chunk in audio_generator:
                    int16 = (chunk * 32767).astype(np.int16)
                    await ws.send(int16.tobytes())
            
            sender_task = asyncio.create_task(send_audio())
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    
                    if data.get("type") == "partial":
                        text = data.get("elements", [])
                        text = " ".join([e.get("value", "") for e in text if e.get("type") == "text"]).strip()
                        if text:
                            yield StreamingChunk(
                                is_final=False,
                                text=text,
                                start=data.get("element", {}).get("ts", 0),
                                end=data.get("element", {}).get("end_ts", 0),
                            )
                    elif data.get("type") == "final":
                        text = data.get("elements", [])
                        text = " ".join([e.get("value", "") for e in text if e.get("type") == "text"]).strip()
                        if text:
                            yield StreamingChunk(
                                is_final=True,
                                text=text,
                                start=data.get("element", {}).get("ts", 0),
                                end=data.get("element", {}).get("end_ts", 0),
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
            resp = httpx.get(f"{self.base_url}/account", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False
