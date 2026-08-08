import asyncio
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import statistics

from src.config import CONFIG
from src.providers.base import ProviderRegistry, STTProvider, LLMProvider, TranscriptResult, LLMResponse
from src.evaluation.judge import LLMJudge, EvalReport


def _provider_kwargs(name: str) -> Dict[str, Any]:
    """Constructor kwargs (API keys etc.) for a registered provider, sourced from CONFIG."""
    return {
        "deepgram": {"api_key": CONFIG.deepgram_api_key},
        "assemblyai": {"api_key": CONFIG.assemblyai_api_key},
        "speechmatics": {"api_key": CONFIG.speechmatics_api_key},
        "revai": {"api_key": CONFIG.revai_api_key},
        "aws": {"aws_access_key": CONFIG.aws_access_key, "aws_secret_key": CONFIG.aws_secret_key,
                "region": CONFIG.aws_region},
        "groq": {"api_key": CONFIG.groq_api_key},
        "anthropic": {"api_key": CONFIG.anthropic_api_key},
        "openrouter": {"api_key": CONFIG.openrouter_api_key},
        "mistral": {"api_key": CONFIG.mistral_api_key},
    }.get(name, {})


class ProviderTestHarness:
    """Test harness that runs all configured providers against a sample and produces a ranked report.
    
    Features:
    - Auto-detects available providers via health checks (knobs via API keys)
    - Runs all STT providers on a test audio file
    - Runs all LLM providers on generated summaries
    - Uses LLM-as-judge to score quality
    - Produces a ranked report with cost/quality tradeoffs
    """
    
    def __init__(self, audio_path: Optional[Path] = None, reference_transcript: Optional[str] = None,
                 reference_summary: Optional[str] = None, judge_provider: str = "anthropic",
                 stt_providers: Optional[List[str]] = None,
                 llm_providers: Optional[List[str]] = None):
        self.audio_path = audio_path
        self.reference_transcript = reference_transcript
        self.reference_summary = reference_summary
        self.judge = LLMJudge(provider_name=judge_provider)
        
        # Auto-discover providers if not specified
        self.stt_providers = stt_providers or self._discover_stt()
        self.llm_providers = llm_providers or self._discover_llm()
    
    def _discover_stt(self) -> List[str]:
        """Discover available STT providers via health check."""
        available = []
        for name in ProviderRegistry.list_stt():
            try:
                provider = ProviderRegistry.get_stt(name, **_provider_kwargs(name))
                if provider.health_check():
                    available.append(name)
                    print(f"[Harness] STT provider available: {name}")
                else:
                    print(f"[Harness] STT provider unavailable (health check failed): {name}")
            except Exception as e:
                print(f"[Harness] STT provider unavailable: {name} - {e}")
        return available
    
    def _discover_llm(self) -> List[str]:
        """Discover available LLM providers via health check."""
        available = []
        for name in ProviderRegistry.list_llm():
            try:
                provider = ProviderRegistry.get_llm(name, **_provider_kwargs(name))
                if provider.health_check():
                    available.append(name)
                    print(f"[Harness] LLM provider available: {name}")
                else:
                    print(f"[Harness] LLM provider unavailable (health check failed): {name}")
            except Exception as e:
                print(f"[Harness] LLM provider unavailable: {name} - {e}")
        return available
    
    async def run_stt_evaluation(self) -> Dict[str, Any]:
        """Run all available STT providers on the test audio and judge."""
        if not self.audio_path or not self.audio_path.exists():
            raise ValueError("No audio path provided for STT evaluation")
        
        results = {}
        reports = []
        
        for name in self.stt_providers:
            print(f"\n[Harness] Evaluating STT: {name}")
            try:
                provider = ProviderRegistry.get_stt(name, **_provider_kwargs(name))
                result = await provider.transcribe_file(self.audio_path)
                results[name] = result
                
                if self.reference_transcript:
                    report = await self.judge.evaluate_stt(self.reference_transcript, result, 
                                                           result.duration_seconds)
                    reports.append(report)
                    print(f"  Score: {report.overall_score:.1f}/10 | Cost: ${result.cost_usd or 0:.4f} | Time: {result.processing_time_seconds:.1f}s")
                else:
                    print(f"  Transcript length: {len(result.text)} chars | Cost: ${result.cost_usd or 0:.4f} | Time: {result.processing_time_seconds:.1f}s")
                    
            except Exception as e:
                print(f"  ERROR: {e}")
                results[name] = None
        
        return {"results": results, "reports": reports}
    
    async def run_llm_evaluation(self, transcript: str) -> Dict[str, Any]:
        """Run all available LLM providers on a transcript and judge summaries."""
        results = {}
        reports = []
        
        for name in self.llm_providers:
            print(f"\n[Harness] Evaluating LLM: {name}")
            try:
                provider = ProviderRegistry.get_llm(name, **_provider_kwargs(name))
                summary = await provider.summarize_meeting(transcript)
                results[name] = summary
                
                if self.reference_summary:
                    report = await self.judge.evaluate_llm_summary(self.reference_summary, summary, transcript)
                    reports.append(report)
                    print(f"  Score: {report.overall_score:.1f}/10 | Cost: ${summary.cost_usd or 0:.4f} | Time: {summary.processing_time_seconds:.1f}s")
                else:
                    print(f"  Summary length: {len(summary.text)} chars | Cost: ${summary.cost_usd or 0:.4f} | Time: {summary.processing_time_seconds:.1f}s")
                    
            except Exception as e:
                print(f"  ERROR: {e}")
                results[name] = None
        
        return {"results": results, "reports": reports}
    
    def _rank_reports(self, reports: List[EvalReport]) -> List[Dict]:
        """Rank reports by overall score, with cost/quality ratio."""
        ranked = []
        for r in reports:
            if r.cost_usd and r.cost_usd > 0:
                quality_per_dollar = r.overall_score / r.cost_usd
            else:
                quality_per_dollar = float('inf')
            
            ranked.append({
                "provider": r.provider,
                "type": r.type,
                "overall_score": r.overall_score,
                "cost_usd": r.cost_usd,
                "processing_time_seconds": r.processing_time_seconds,
                "quality_per_dollar": quality_per_dollar,
                "scores": {s.criterion: s.score for s in r.scores},
                "report": r,
            })
        
        # Sort by overall score descending, then by cost ascending
        ranked.sort(key=lambda x: (-x["overall_score"], x["cost_usd"] or 0))
        return ranked
    
    def generate_report(self, stt_results: Dict, llm_results: Dict, output_path: Optional[Path] = None) -> str:
        """Generate a Markdown report of the evaluation."""
        
        lines = [
            "# VoiceVault Provider Evaluation Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Methodology",
            "",
            "- **STT Evaluation**: Each provider transcribed the same test audio file.",
            "- **LLM Evaluation**: Each provider summarized the same transcript.",
            "- **Judging**: LLM-as-judge (Claude 3.5 Sonnet) scored accuracy, completeness, formatting, hallucinations, semantics.",
            "- **Metrics**: Overall score (1-10), cost per minute, processing time.",
            "",
            "## STT Provider Rankings",
            "",
        ]
        
        if stt_results.get("reports"):
            lines.append("| Rank | Provider | Score | Cost/Min | Time | Quality/$ |")
            lines.append("|------|----------|-------|----------|------|----------|")
            for i, r in enumerate(self._rank_reports(stt_results["reports"]), 1):
                cost_per_min = (r["cost_usd"] / (stt_results["reports"][0].metadata.get("audio_duration_seconds", 60) / 60)) if r["cost_usd"] else 0
                lines.append(f"| {i} | {r['provider']} | {r['overall_score']:.1f} | ${cost_per_min:.4f} | {r['processing_time_seconds']:.1f}s | {'∞' if r['quality_per_dollar'] == float('inf') else f'{r['quality_per_dollar']:.1f}'} |")
            
            lines.append("")
            lines.append("### Detailed STT Scores")
            lines.append("")
            for r in self._rank_reports(stt_results["reports"]):
                lines.append(f"#### {r['provider']}")
                for criterion, score in r["scores"].items():
                    lines.append(f"- {criterion}: {score:.1f}/10")
                lines.append("")
        
        lines.append("## LLM Provider Rankings")
        lines.append("")
        
        if llm_results.get("reports"):
            lines.append("| Rank | Provider | Score | Cost | Time | Quality/$ |")
            lines.append("|------|----------|-------|------|------|----------|")
            for i, r in enumerate(self._rank_reports(llm_results["reports"]), 1):
                lines.append(f"| {i} | {r['provider']} | {r['overall_score']:.1f} | ${r['cost_usd'] or 0:.4f} | {r['processing_time_seconds']:.1f}s | {'∞' if r['quality_per_dollar'] == float('inf') else f'{r['quality_per_dollar']:.1f}'} |")
            
            lines.append("")
            lines.append("### Detailed LLM Scores")
            lines.append("")
            for r in self._rank_reports(llm_results["reports"]):
                lines.append(f"#### {r['provider']}")
                for criterion, score in r["scores"].items():
                    lines.append(f"- {criterion}: {score:.1f}/10")
                lines.append("")
        
        lines.append("## Recommendations")
        lines.append("")
        
        # Best overall
        if stt_results.get("reports"):
            best_stt = self._rank_reports(stt_results["reports"])[0]
            lines.append(f"- **Best STT overall**: {best_stt['provider']} (score: {best_stt['overall_score']:.1f})")
        
        # Best value
        if stt_results.get("reports"):
            best_value = max(self._rank_reports(stt_results["reports"]), key=lambda x: x["quality_per_dollar"] if x["quality_per_dollar"] != float('inf') else 0)
            if best_value["quality_per_dollar"] != float('inf'):
                lines.append(f"- **Best STT value**: {best_value['provider']} (quality per dollar: {best_value['quality_per_dollar']:.1f})")
        
        if llm_results.get("reports"):
            best_llm = self._rank_reports(llm_results["reports"])[0]
            lines.append(f"- **Best LLM overall**: {best_llm['provider']} (score: {best_llm['overall_score']:.1f})")
        
        lines.append("")
        lines.append("---")
        lines.append("*Report generated by VoiceVault Provider Test Harness*")
        
        report_text = "\n".join(lines)
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report_text)
            print(f"\n[Harness] Report saved to: {output_path}")
        
        return report_text
    
    async def run_full_evaluation(self, output_path: Optional[Path] = None) -> str:
        """Run complete STT + LLM evaluation and generate report."""
        print("="*60)
        print("VoiceVault Provider Test Harness")
        print("="*60)
        print(f"STT providers: {self.stt_providers}")
        print(f"LLM providers: {self.llm_providers}")
        print("")
        
        stt_results = {"results": {}, "reports": []}
        llm_results = {"results": {}, "reports": []}
        
        if self.audio_path and self.stt_providers:
            stt_results = await self.run_stt_evaluation()
        
        # Use best STT transcript or reference for LLM evaluation
        transcript = self.reference_transcript
        if not transcript and stt_results["results"]:
            # Pick the highest-scoring STT result
            best = max(stt_results["results"].values(), key=lambda r: len(r.text) if r else 0)
            if best:
                transcript = best.text
        
        if transcript and self.llm_providers:
            llm_results = await self.run_llm_evaluation(transcript)
        
        return self.generate_report(stt_results, llm_results, output_path)


async def main():
    """CLI entry point for test harness."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="VoiceVault Provider Test Harness")
    parser.add_argument("--audio", type=Path, help="Path to test audio file")
    parser.add_argument("--reference-transcript", type=Path, help="Path to reference transcript")
    parser.add_argument("--reference-summary", type=Path, help="Path to reference summary")
    parser.add_argument("--stt-providers", nargs="+", help="STT providers to test (auto-detect if omitted)")
    parser.add_argument("--llm-providers", nargs="+", help="LLM providers to test (auto-detect if omitted)")
    parser.add_argument("--judge", default="anthropic", help="Judge LLM provider")
    parser.add_argument("--output", type=Path, default=Path("eval_report.md"), help="Output report path")
    args = parser.parse_args()
    
    ref_transcript = None
    if args.reference_transcript:
        with open(args.reference_transcript) as f:
            ref_transcript = f.read()
    
    ref_summary = None
    if args.reference_summary:
        with open(args.reference_summary) as f:
            ref_summary = f.read()
    
    harness = ProviderTestHarness(
        audio_path=args.audio,
        reference_transcript=ref_transcript,
        reference_summary=ref_summary,
        judge_provider=args.judge,
        stt_providers=args.stt_providers,
        llm_providers=args.llm_providers,
    )
    
    report = await harness.run_full_evaluation(output_path=args.output)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
