import json
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import statistics

from src.providers.base import ProviderRegistry, STTProvider, LLMProvider, TranscriptResult, LLMResponse
from src.config import CONFIG


@dataclass
class EvalScore:
    """Score from LLM judge for a single provider output."""
    provider: str
    criterion: str  # e.g., "accuracy", "completeness", "formatting", "hallucination_free"
    score: float  # 1-10 or 0-1
    reasoning: str
    confidence: float  # judge's confidence in score


@dataclass
class EvalReport:
    """Complete evaluation report for a provider."""
    provider: str
    type: str  # "stt" or "llm"
    task_description: str
    
    # Performance
    processing_time_seconds: float
    cost_usd: Optional[float]
    
    # Judge scores
    scores: List[EvalScore] = field(default_factory=list)
    overall_score: float = 0.0
    
    # Raw output
    raw_output: Optional[str] = None
    raw_output_truncated: bool = False
    
    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMJudge:
    """Uses an LLM (Anthropic Claude or Ollama) to evaluate provider outputs qualitatively.
    
    Inspired by AssemblyAI's LLM Vibe Eval and the Pipecat STT benchmark's Semantic WER.
    """
    
    def __init__(self, provider_name: str = "anthropic", model: str = "claude-3-5-sonnet-20241022", api_key: str = None):
        self.provider_name = provider_name
        self.model = model
        self.api_key = api_key or CONFIG.get(f"{provider_name.upper()}_API_KEY")
        self._provider: Optional[LLMProvider] = None
    
    def _get_provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = ProviderRegistry.get_llm(self.provider_name, api_key=self.api_key, model=self.model)
        return self._provider
    
    async def evaluate_stt(self, reference: str, hypothesis: TranscriptResult, audio_duration: float) -> EvalReport:
        """Evaluate an STT transcript against a reference."""
        
        system_prompt = """You are an expert speech-to-text evaluator. Evaluate transcription quality against a ground truth reference.

Score each criterion 1-10 (10 = perfect). Be strict but fair. Consider what actually matters for downstream LLM use — minor punctuation or capitalization differences don't matter, but missing names, numbers, negations, or action items do.

Format your response as a JSON object with this exact schema:
{
  "accuracy": {"score": float, "reasoning": "string"},
  "completeness": {"score": float, "reasoning": "string"},
  "formatting": {"score": float, "reasoning": "string"},
  "hallucination_free": {"score": float, "reasoning": "string"},
  "semantic_preserved": {"score": float, "reasoning": "string"},
  "overall_score": {"score": float, "reasoning": "string"},
  "confidence": float
}

Criteria:
- accuracy: Word-level correctness. Ignore punctuation/capitalization. Penalize wrong names, numbers, technical terms, negations.
- completeness: Did the transcript capture all spoken content? Penalize missing segments, dropped words, early truncation.
- formatting: Is the output well-structured? Paragraphs, speaker labels, timestamps where appropriate. Penalize wall-of-text or broken sentences.
- hallucination_free: No invented content. Score 10 if nothing was added. Score lower for words/phrases not in the reference.
- semantic_preserved: Does the meaning match? "Health care" vs "healthcare" is fine. "Didn't approve" vs "approved" is not.
"""
        
        # Truncate if needed to fit context window
        ref_text = reference[:8000]
        hyp_text = hypothesis.text[:8000]
        
        user_prompt = f"""REFERENCE TRANSCRIPT (ground truth):
{ref_text}

HYPOTHESIS TRANSCRIPT (from {hypothesis.provider}):
{hyp_text}

Audio duration: {audio_duration:.1f} seconds
Processing time: {hypothesis.processing_time_seconds:.1f} seconds
Cost: ${hypothesis.cost_usd or 0:.4f}

Evaluate the hypothesis against the reference."""
        
        start = time.time()
        response = await self._get_provider().generate(user_prompt, system_prompt=system_prompt)
        elapsed = time.time() - start
        
        # Parse JSON from response
        try:
            # Extract JSON from markdown code blocks if present
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            data = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError) as e:
            # Fallback: try to parse entire text
            try:
                data = json.loads(text.strip())
            except json.JSONDecodeError:
                data = {}
        
        scores = []
        for criterion in ["accuracy", "completeness", "formatting", "hallucination_free", "semantic_preserved"]:
            if criterion in data:
                scores.append(EvalScore(
                    provider=hypothesis.provider,
                    criterion=criterion,
                    score=data[criterion].get("score", 0),
                    reasoning=data[criterion].get("reasoning", "N/A"),
                    confidence=data.get("confidence", 0.5),
                ))
        
        overall = data.get("overall_score", {}).get("score", 0)
        
        return EvalReport(
            provider=hypothesis.provider,
            type="stt",
            task_description="STT transcription evaluation",
            processing_time_seconds=hypothesis.processing_time_seconds,
            cost_usd=hypothesis.cost_usd,
            scores=scores,
            overall_score=overall,
            raw_output=hypothesis.text[:2000],
            raw_output_truncated=len(hypothesis.text) > 2000,
            metadata={
                "judge_provider": self.provider_name,
                "judge_model": self.model,
                "judge_time_seconds": elapsed,
                "audio_duration_seconds": audio_duration,
            }
        )
    
    async def evaluate_llm_summary(self, reference_summary: str, hypothesis: LLMResponse, transcript: str) -> EvalReport:
        """Evaluate an LLM meeting summary against a reference."""
        
        system_prompt = """You are an expert meeting summarization evaluator. Evaluate a generated summary against a reference summary.

Score each criterion 1-10 (10 = perfect). Be strict about factual accuracy and completeness.

Format your response as a JSON object with this exact schema:
{
  "accuracy": {"score": float, "reasoning": "string"},
  "completeness": {"score": float, "reasoning": "string"},
  "conciseness": {"score": float, "reasoning": "string"},
  "action_items": {"score": float, "reasoning": "string"},
  "hallucination_free": {"score": float, "reasoning": "string"},
  "overall_score": {"score": float, "reasoning": "string"},
  "confidence": float
}

Criteria:
- accuracy: Facts match the transcript and reference. No invented dates, names, or decisions.
- completeness: All key points from reference are present. Missing important topics lowers score.
- conciseness: Not overly verbose but not so brief it misses context. Good balance.
- action_items: Specific, actionable items with assignees if present in reference. Vague items score lower.
- hallucination_free: Nothing invented not supported by the transcript.
"""
        
        ref_text = reference_summary[:4000]
        hyp_text = hypothesis.text[:4000]
        trans_text = transcript[:4000]
        
        user_prompt = f"""TRANSCRIPT (source material):
{trans_text}

REFERENCE SUMMARY (ground truth):
{ref_text}

GENERATED SUMMARY (from {hypothesis.provider} / {hypothesis.model}):
{hyp_text}

Processing time: {hypothesis.processing_time_seconds:.1f} seconds
Cost: ${hypothesis.cost_usd or 0:.4f}

Evaluate the generated summary against the reference."""
        
        start = time.time()
        response = await self._get_provider().generate(user_prompt, system_prompt=system_prompt)
        elapsed = time.time() - start
        
        try:
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            data = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            try:
                data = json.loads(text.strip())
            except json.JSONDecodeError:
                data = {}
        
        scores = []
        for criterion in ["accuracy", "completeness", "conciseness", "action_items", "hallucination_free"]:
            if criterion in data:
                scores.append(EvalScore(
                    provider=hypothesis.provider,
                    criterion=criterion,
                    score=data[criterion].get("score", 0),
                    reasoning=data[criterion].get("reasoning", "N/A"),
                    confidence=data.get("confidence", 0.5),
                ))
        
        overall = data.get("overall_score", {}).get("score", 0)
        
        return EvalReport(
            provider=hypothesis.provider,
            type="llm",
            task_description="Meeting summarization evaluation",
            processing_time_seconds=hypothesis.processing_time_seconds,
            cost_usd=hypothesis.cost_usd,
            scores=scores,
            overall_score=overall,
            raw_output=hypothesis.text[:2000],
            raw_output_truncated=len(hypothesis.text) > 2000,
            metadata={
                "judge_provider": self.provider_name,
                "judge_model": self.model,
                "judge_time_seconds": elapsed,
            }
        )
    
    def evaluate_cheap(self, reference: str, hypothesis_text: str) -> float:
        """Cheap local WER-based comparison without calling LLM. Use for quick filtering."""
        try:
            import jiwer
            ref_words = reference.lower().split()
            hyp_words = hypothesis_text.lower().split()
            wer = jiwer.wer(ref_words, hyp_words)
            return max(0, 1.0 - wer) * 10  # Convert to 0-10 scale
        except ImportError:
            # Fallback: simple word overlap
            ref_set = set(reference.lower().split())
            hyp_set = set(hypothesis_text.lower().split())
            if not ref_set:
                return 0
            overlap = len(ref_set & hyp_set) / len(ref_set)
            return overlap * 10