import json
import time
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave

import httpx
from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk


class SpeechmaticsProvider(STTProvider):
    """Speechmatics ASR with best-in-class multilingual support (50+ languages).
    
    Strong privacy posture. Enterprise on-prem available.
    Pricing: Custom enterprise, estimated ~$0.005/min for cloud.
    """
    
    name = "speechmatics"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = True
    
    COST_PER_MINUTE = 0.005  # Estimated cloud rate
    
    def __init__(self, api_key: str = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.base_url = "https://asr.api.speechmatics.com/v2"
    
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
                    f"{self.base_url}/jobs",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"data_file": (audio_path.name, f, "audio/wav")},
                    data={"config": json.dumps({
                        "type": "transcription",
                        "transcription_config": {
                            "language": language,
                            "diarization": "speaker" if diarize else "none",
                            "operating_point": "enhanced",
                        }
                    })},
                    timeout=300.0,
                )
                submit_resp.raise_for_status()
                job_id = submit_resp.json()["id"]
            
            # Poll for completion
            while True:
                poll_resp = await client.get(
                    f"{self.base_url}/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30.0,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                
                status = data.get("job", {}).get("status")
                if status == "done":
                    break
                elif status in ("expired", "rejected"):
                    raise RuntimeError(f"Speechmatics job failed: {status}")
                
                await asyncio.sleep(3.0)
            
            # Fetch transcript
            transcript_resp = await client.get(
                f"{self.base_url}/jobs/{job_id}/transcript",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
            transcript_resp.raise_for_status()
            transcript_data = transcript_resp.json()
        
        elapsed = time.time() - start
        
        segments = []
        full_text_parts = []
        for result in transcript_data.get("results", []):
            for alt in result.get("alternatives", []):
                text = alt.get("transcript", "").strip()
                if text:
                    segments.append(TranscriptSegment(
                        start=alt.get("start_time", 0),
                        end=alt.get("end_time", 0),
                        text=text,
                        speaker=alt.get("speaker"),
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
        
        config = json.dumps({
            "message": "StartRecognition",
            "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": 16000},
            "transcription_config": {"language": language, "operating_point": "enhanced"},
        })
        
        ws_url = f"wss://asr.api.speechmatics.com/v2?auth_token={self.api_key}"
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(config)
            
            async def send_audio():
                async for chunk in audio_generator:
                    int16 = (chunk * 32767).astype(np.int16)
                    await ws.send(int16.tobytes())
                await ws.send(json.dumps({"message": "EndOfStream", "last_seq_no": 1}))
            
            sender_task = asyncio.create_task(send_audio())
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    
                    if data.get("message") == "AddTranscript":
                        results = data.get("results", [])
                        if results:
                            text = " ".join([r.get("alternatives", [{}])[0].get("transcript", "") for r in results])
                            text = text.strip()
                            if text:
                                first = results[0]
                                last = results[-1]
                                yield StreamingChunk(
                                    is_final=data.get("is_final", True),
                                    text=text,
                                    start=first.get("start_time", 0),
                                    end=last.get("end_time", 0),
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
            resp = httpx.get(f"{self.base_url}/jobs", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False
