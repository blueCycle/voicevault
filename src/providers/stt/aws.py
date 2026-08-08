import json
import time
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import wave

import boto3
from src.providers.base import STTProvider, TranscriptResult, TranscriptSegment, StreamingChunk


class AWSProvider(STTProvider):
    """AWS Transcribe batch and streaming transcription.
    
    HIPAA-eligible, BAA available, no retention by default. GovCloud option.
    Pricing: $0.024/min (standard), $0.006/min (medical)
    """
    
    name = "aws"
    supports_streaming = True
    supports_diarization = True
    supports_batch = True
    requires_api_key = True
    
    COST_PER_MINUTE = 0.024  # Standard tier
    
    def __init__(self, api_key: str = None, aws_access_key: str = None, aws_secret_key: str = None, 
                 region: str = "us-east-1", **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.aws_access_key = aws_access_key or kwargs.get("aws_access_key")
        self.aws_secret_key = aws_secret_key or kwargs.get("aws_secret_key")
        self.region = region
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                'transcribe',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.region,
            )
        return self._client
    
    async def transcribe_file(self, audio_path: Path, language: str = "en-US", diarize: bool = False, **kwargs) -> TranscriptResult:
        start = time.time()
        
        with wave.open(str(audio_path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
        
        import uuid
        job_name = f"voicevault-{uuid.uuid4()}"
        s3_uri = kwargs.get("s3_uri")
        
        if not s3_uri:
            # Upload to S3 first
            import boto3
            s3 = boto3.client('s3', aws_access_key_id=self.aws_access_key, 
                              aws_secret_access_key=self.aws_secret_key, region_name=self.region)
            bucket = kwargs.get("s3_bucket")
            if not bucket:
                raise ValueError("AWS batch transcription requires s3_uri or s3_bucket parameter")
            
            key = f"voicevault/{audio_path.name}"
            s3.upload_file(str(audio_path), bucket, key)
            s3_uri = f"s3://{bucket}/{key}"
        
        client = self._get_client()
        
        job_args = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": s3_uri},
            "MediaFormat": "wav",
            "LanguageCode": language,
            "Settings": {
                "ShowSpeakerLabels": diarize,
                "MaxSpeakerLabels": 10 if diarize else 2,
            },
        }
        
        client.start_transcription_job(**job_args)
        
        # Poll
        while True:
            await asyncio.sleep(5.0)
            job = client.get_transcription_job(TranscriptionJobName=job_name)
            status = job["TranscriptionJob"]["TranscriptionJobStatus"]
            
            if status == "COMPLETED":
                break
            elif status == "FAILED":
                raise RuntimeError(f"AWS Transcribe failed: {job['TranscriptionJob'].get('FailureReason')}")
        
        # Fetch transcript from result URL
        transcript_uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
        import httpx
        async with httpx.AsyncClient() as client_http:
            resp = await client_http.get(transcript_uri, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        segments = []
        full_text_parts = []
        results = data.get("results", {})
        
        if diarize and "speaker_labels" in results:
            for item in results["speaker_labels"].get("segments", []):
                for word in item.get("items", []):
                    text = word.get("alternatives", [{}])[0].get("content", "")
                    if text:
                        segments.append(TranscriptSegment(
                            start=float(word.get("start_time", 0)),
                            end=float(word.get("end_time", 0)),
                            text=text,
                            speaker=item.get("speaker_label"),
                        ))
                        full_text_parts.append(text)
        else:
            for item in results.get("items", []):
                if item.get("type") == "pronunciation":
                    text = item.get("alternatives", [{}])[0].get("content", "")
                    if text:
                        segments.append(TranscriptSegment(
                            start=float(item.get("start_time", 0)),
                            end=float(item.get("end_time", 0)),
                            text=text,
                        ))
                        full_text_parts.append(text)
        
        return TranscriptResult(
            provider=self.name,
            text=" ".join(full_text_parts),
            segments=segments,
            duration_seconds=duration,
            processing_time_seconds=elapsed,
            cost_usd=(duration / 60.0) * self.COST_PER_MINUTE,
            metadata={"language": language, "job_name": job_name},
            raw_response=data,
        )
    
    async def transcribe_stream(self, audio_generator: AsyncGenerator[np.ndarray, None], language: str = "en-US", **kwargs) -> AsyncGenerator[StreamingChunk, None]:
        import amazon_transcribe
        from amazon_transcribe.client import TranscribeStreamingClient
        from amazon_transcribe.handlers import TranscriptResultStreamHandler
        from amazon_transcribe.model import TranscriptEvent
        
        client = TranscribeStreamingClient(
            region=self.region,
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
        )
        
        stream = await client.start_stream_transcription(
            language_code=language,
            media_sample_rate_hz=16000,
            media_encoding="pcm",
        )
        
        async def send_audio():
            async for chunk in audio_generator:
                int16 = (chunk * 32767).astype(np.int16)
                await stream.input_stream.send_audio_event(audio_chunk=int16.tobytes())
            await stream.input_stream.end_stream()
        
        class Handler(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, transcript_event: TranscriptEvent):
                for result in transcript_event.transcript.results:
                    if result.is_partial:
                        is_final = False
                    else:
                        is_final = True
                    
                    for alt in result.alternatives:
                        text = alt.transcript.strip()
                        if text:
                            yield StreamingChunk(
                                is_final=is_final,
                                text=text,
                                start=result.start_time,
                                end=result.end_time,
                            )
        
        handler = Handler(stream.output_stream)
        sender_task = asyncio.create_task(send_audio())
        
        async for chunk in handler.handle_events():
            yield chunk
        
        await sender_task
    
    def health_check(self) -> bool:
        if not (self.aws_access_key and self.aws_secret_key):
            return False
        try:
            client = self._get_client()
            client.list_transcription_jobs(MaxResults=1)
            return True
        except Exception:
            return False
