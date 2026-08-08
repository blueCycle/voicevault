import asyncio
import json
import time
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave

import httpx
from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk


class AssemblyAIProvider(STTProvider):
    """AssemblyAI Universal transcription with PII redaction and topic detection.
    
    Zero-retention, SOC 2, GDPR. Best feature set.
    Pricing: Universal = $0.37/hr = $0.00617/min
    """
    
    name = "assemblyai"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = True
    
    COST_PER_HOUR = 0.37  # Universal tier
    
    def __init__(self, api_key: str = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.base_url = "https://api.assemblyai.com/v2"
    
    def _headers(self):
        return {"authorization": self.api_key}
    
    async def transcribe_file(self, audio_path: Path, language: str = "en", diarize: bool = False, 
                              pii_redaction: bool = False, **kwargs) -> TranscriptResult:
        start = time.time()
        
        with wave.open(str(audio_path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
        
        async with httpx.AsyncClient() as client:
            # Upload
            with open(audio_path, 'rb') as f:
                upload_resp = await client.post(
                    f"{self.base_url}/upload",
                    headers=self._headers(),
                    content=f.read(),
                    timeout=300.0,
                )
                upload_resp.raise_for_status()
                upload_url = upload_resp.json()["upload_url"]
            
            # Submit
            payload = {
                "audio_url": upload_url,
                "language_code": language,
                "punctuate": True,
                "format_text": True,
            }
            if diarize:
                payload["speaker_labels"] = True
            if pii_redaction:
                payload["pii_redaction"] = True
            
            submit_resp = await client.post(
                f"{self.base_url}/transcript",
                headers={**self._headers(), "content-type": "application/json"},
                json=payload,
                timeout=30.0,
            )
            submit_resp.raise_for_status()
            transcript_id = submit_resp.json()["id"]
            
            # Poll for completion
            while True:
                poll_resp = await client.get(
                    f"{self.base_url}/transcript/{transcript_id}",
                    headers=self._headers(),
                    timeout=30.0,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                
                status = data.get("status")
                if status == "completed":
                    break
                elif status == "error":
                    raise RuntimeError(f"AssemblyAI transcription failed: {data.get('error')}")
                
                await asyncio.sleep(2.0)
        
        elapsed = time.time() - start
        
        segments = []
        full_text_parts = []
        
        if data.get("utterances"):
            for u in data["utterances"]:
                segments.append(TranscriptSegment(
                    start=u.get("start", 0) / 1000.0,
                    end=u.get("end", 0) / 1000.0,
                    text=u.get("text", ""),
                    speaker=u.get("speaker"),
                ))
                full_text_parts.append(u.get("text", ""))
        else:
            full_text_parts.append(data.get("text", ""))
        
        return TranscriptResult(
            provider=self.name,
            text=" ".join(full_text_parts),
            segments=segments,
            duration_seconds=duration,
            processing_time_seconds=elapsed,
            cost_usd=(duration / 3600.0) * self.COST_PER_HOUR,
            metadata={"language": language, "words": data.get("words", [])},
            raw_response=data,
        )
    
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], language: str = "en", **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        import websockets
        
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"{self.base_url}/realtime/token",
                headers=self._headers(),
                timeout=30.0,
            )
            token_resp.raise_for_status()
            token = token_resp.json()["token"]
        
        ws_url = f"wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000&token={token}"
        
        async with websockets.connect(ws_url) as ws:
            async def send_audio():
                async for chunk in audio_generator:
                    int16 = (chunk * 32767).astype(np.int16)
                    await ws.send(int16.tobytes())
                await ws.send(json.dumps({"terminate_session": True}))
            
            sender_task = asyncio.create_task(send_audio())
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    
                    if data.get("message_type") == "FinalTranscript":
                        text = data.get("text", "").strip()
                        if text:
                            yield StreamingChunk(
                                is_final=True,
                                text=text,
                                start=data.get("audio_start", 0) / 1000.0,
                                end=data.get("audio_end", 0) / 1000.0,
                                confidence=data.get("confidence"),
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
            resp = httpx.get(f"{self.base_url}/transcript", headers=self._headers(), timeout=10.0)
            return resp.status_code in (200, 400)  # 400 is OK (missing params), just checking auth
        except Exception:
            return False
