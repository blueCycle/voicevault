# VoiceVault Provider Architecture Decisions

**Date:** 2026-07-03
**Author:** VoiceVault team
**Status:** Approved

## Problem Statement

We need a privacy-first, open-source voice note-taking app that supports both real-time voice-to-text (dictation mode) and meeting recording with AI summaries (meeting mode). The app must run primarily on local hardware, but we want the ability to evaluate and optionally integrate cloud providers for better accuracy or mobile support. We need an automated way to compare providers on cost, quality, latency, and privacy.

## Provider Selection Philosophy

### Core Principles

1. **Privacy-first by default**: Local Whisper + Ollama are the default. Cloud providers are opt-in via API keys.
2. **Knobs not switches**: Every provider can be turned on/off via API keys. If a key is present, the provider is available. If not, it gracefully skips.
3. **Evaluate before you trust**: Every provider goes through an LLM-as-judge evaluation before being recommended for production use.
4. **Cost transparency**: Every provider reports estimated cost per minute so users can make informed tradeoffs.

### How Providers Are Turned On/Off

| Provider | Knob (Environment Variable) | Auto-detected? | Fallback position |
|----------|----------------------------|----------------|-------------------|
| **Local Whisper** | Always available (no key) | Yes | Primary (default) |
| **Deepgram** | `DEEPGRAM_API_KEY` | Health check | Streaming alternative |
| **AssemblyAI** | `ASSEMBLYAI_API_KEY` | Health check | Feature-rich alternative |
| **Speechmatics** | `SPEECHMATICS_API_KEY` | Health check | Multilingual alternative |
| **Rev.ai** | `REVAI_API_KEY` | Health check | Accuracy-at-premium |
| **AWS Transcribe** | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | Health check | Enterprise/compliance |
| **Ollama** | Always available (local) | Health check | Primary LLM (default) |
| **Groq** | `GROQ_API_KEY` | Health check | Fast cloud LLM |
| **Anthropic** | `ANTHROPIC_API_KEY` | Health check | Best quality LLM / Judge |
|| **OpenRouter** | `OPENROUTER_API_KEY` | Health check | Aggregator fallback |
|| **Mistral** | `MISTRAL_API_KEY` | Health check | EU-native, GDPR-first LLM |

The `ProviderRegistry` auto-discovers available providers via `health_check()` calls. The test harness (`src/evaluation/harness.py`) only runs providers that pass their health check.

## STT Provider Decisions

### Why These 5 Cloud Providers + Local?

| Provider | Why Included | Privacy Posture | Best For | Cost/min |
|----------|---------------|-----------------|----------|----------|
| **Local Whisper** | Zero trust, zero network, zero cost | Maximum | Privacy-critical users, offline | $0 |
| **Deepgram Nova-2** | Best real-time streaming API, lowest latency | Zero-retention, SOC 2 | Dictation streaming mode | $0.0043 |
| **AssemblyAI Universal** | Best feature set: PII redaction, topic detection, speaker diarization | Zero-retention, SOC 2, GDPR | Meeting transcription with rich metadata | $0.0062 |
| **Speechmatics** | Best multilingual (50+ languages), enterprise on-prem option | Enterprise privacy, on-prem available | Non-English meetings, global teams | ~$0.005 |
| **Rev.ai** | Human-level accuracy, HIPAA-eligible | Zero-retention, SOC 2, HIPAA | Medical/legal where accuracy is paramount | $0.035 |
| **AWS Transcribe** | Enterprise standard, BAA/HIPAA, GovCloud | BAA-eligible, no retention by default | Regulated industries, existing AWS infra | $0.024 |

### Why Not Google Cloud Speech?

**Excluded.** Google does not offer explicit zero-retention by default. Training opt-out is manual and unclear. For a privacy-first app, this is a non-starter. AWS, Azure, and the specialist providers all have clearer privacy postures.

### Why Not Azure Speech?

**Deferred.** Azure has strong privacy (DPA, containerized on-prem) and would be a good addition, but AWS covers the "enterprise compliance" slot. If a user specifically requests Azure, it can be added with the same plugin pattern.

### Why Not OpenAI Whisper API?

**Excluded.** The Whisper API uses the same model as local Whisper but sends audio to OpenAI. OpenAI has no explicit zero-retention policy for audio. For users who want Whisper quality in the cloud, Deepgram Nova-2 or AssemblyAI offer better privacy and lower latency.

### Model Recommendations by Use Case

| Use Case | Recommended STT | Why |
|----------|-----------------|-----|
| **Privacy-critical (Dictation)** | Local Whisper (`tiny` or `base` for speed, `small` for accuracy) | No audio leaves device |
| **Privacy-critical (meetings)** | Local Whisper (`small` or `medium`) + Ollama summary | Complete offline pipeline |
| **Fast streaming (Dictation)** | Deepgram Nova-2 | <300ms TTFS, best streaming API |
| **Meeting with speaker IDs** | AssemblyAI Universal | Best diarization + PII redaction |
| **Multilingual meetings** | Speechmatics | 50+ languages, on-prem option |
| **Medical/legal transcription** | Rev.ai | Highest accuracy, HIPAA |
| **Enterprise compliance** | AWS Transcribe | BAA, GovCloud, existing IAM |

## LLM Provider Decisions

### Why These 5 Providers + Local?

||| Provider | Why Included | Privacy Posture | Best For | Cost/1K tokens |
|||----------|---------------|-----------------|----------|------------------|
||| **Ollama** | Zero cost, zero cloud, runs on your hardware | Maximum | Default for all summarization | $0 |
||| **Groq** | Fastest inference (<100ms), zero-retention on API data, no training | No training; ZDR negotiable (enterprise); DPA enterprise-only; 30-day abuse logs | Real-time summaries, low latency | $0.0001 |
||| **Anthropic Claude 3.5 Sonnet** | Best quality for nuanced summaries, excellent judge; SOC 2 Type I & II, ISO 27001, HIPAA BAA | 30-day default retention; ZDR available (enterprise); no training on API data; US-based + SCCs | Judge/evaluator, high-stakes summaries | $3/$15 per 1M |
||| **OpenRouter** | Aggregator, 70+ providers; SOC 2 Type 2; ZDR per-request + account-wide | ZDR enforceable per model group; EU in-region routing (enterprise); upstream policy varies | Flexibility, model variety | Varies |
||| **Mistral (La Plateforme)** | EU-native, no training on API data, SOC 2 Type II; open-weight models available | GDPR-native; no SCCs needed for EU customers; 30-day retention | EU users, GDPR-first deployments, open-weight self-hosting | $2/$6 per 1M |

### Verified LLM Compliance Details

| Provider | SOC 2 / ISO 27001 | Default Retention | Zero Data Retention (ZDR) | Trains on API Data? | GDPR / EU Residency | Notes |
|----------|-------------------|-------------------|---------------------------|---------------------|---------------------|-------|
| **Groq** | Self-attested; no public SOC 2 Type II cert as of early 2026 | Max 180 days after contract termination; ~30-day abuse logs | Enterprise-negotiable only; no self-serve toggle | No | US-only; no EU residency option; DPA enterprise-only | Fastest inference, but weakest enterprise compliance of the 3 |
| **Anthropic** | SOC 2 Type I & II, ISO 27001:2022, ISO 42001:2023 | 30 days (API inputs/outputs) | Yes — request via sales; enabled per-organization | No (commercial API) | US-based; SCCs in DPA; EU residency via AWS Bedrock / GCP Vertex | Strongest compliance + ZDR option; HIPAA BAA available |
| **OpenRouter** | SOC 2 Type 2 | Prompts not stored by default (opt-in logging only); metadata retained | Per-request (`zdr: true`) + account-wide + guardrail-level | No (OpenRouter layer); upstream varies | EU in-region routing for enterprise (`eu.openrouter.ai`); SCCs | Best routing-layer privacy controls; upstream provider policies vary |

Sources: Groq Privacy Policy / DPA (May 2024), Groq Service Terms (Nov 2025), Anthropic Trust Center / Privacy Center (June 2026), OpenRouter Privacy Docs / ZDR docs (Apr 2026).

### Why Not OpenAI GPT-4?

**Deferred.** GPT-4 is high quality but OpenAI's direct API privacy posture is weaker than Anthropic for a privacy-first app: OpenAI does not offer ZDR by default, and the DPA requires explicit opt-in. Anthropic is the preferred cloud LLM for quality-sensitive tasks. OpenRouter can route to GPT-4 via Azure (which has stronger privacy) if a user explicitly wants it, but we don't directly integrate OpenAI.

### Why Not Google Vertex AI / Gemini API?

**Deferred.** Google Vertex AI (enterprise) does not train on API data and offers EU regions, but the latest Gemini 3.x models are not yet available in EU regions as of mid-2026. Consumer Google AI Studio trains by default. For a privacy-first app, Google adds complexity without clear advantage over Anthropic or Mistral.

### Judge Provider Recommendation

**Anthropic Claude 3.5 Sonnet** is the default judge. It is the best model for nuanced evaluation tasks (detecting subtle hallucinations, semantic equivalence, factual accuracy). Groq is too fast but occasionally less nuanced. Ollama is too slow for evaluation tasks and may lack the reasoning depth for reliable scoring.

## Evaluation Methodology

### Inspired By

Our evaluation framework is inspired by:

1. **Pipecat STT Benchmark** (`pipecat-ai/stt-benchmark`): TTFS (Time To Final Segment) latency measurement, semantic WER, Pareto frontier charts.
2. **AssemblyAI STT Benchmarking SDK**: LLM Vibe Eval, lazy transcription, batch processing, speaker matching.
3. **Whissle ASR Benchmark**: Real-world datasets (accents, noise, domain-specific), WER/CER by scenario.
4. **Soniox STT Benchmarks**: 60-language evaluation, normalized ground truth, manual review of high-WER outliers.

### Metrics We Measure

| Metric | Why It Matters | How We Measure |
|--------|---------------|----------------|
| **WER (Word Error Rate)** | Standard accuracy metric | `jiwer` library against reference transcript |
| **Semantic WER** | Accuracy that matters for downstream LLM | LLM judge scores whether errors affect meaning |
| **TTFS (Time To Final Segment)** | Streaming latency — critical for Dictation | `time.time()` from audio stop to final transcript |
| **Processing Time** | Total wall-clock time for batch transcription | `time.time()` from start to result |
| **Cost per minute** | Direct cost comparison | Provider-specific pricing constants |
| **Quality per dollar** | Value metric | Judge score / cost |
| **Hallucination rate** | Critical for meeting summaries | LLM judge detects invented content |
| **Completeness** | Did we capture everything? | LLM judge scores against reference |
| **Formatting** | Is output usable? | LLM judge scores structure, paragraphs, speaker labels |

### LLM-as-Judge Criteria

**For STT evaluation:**
- `accuracy` (1-10): Word-level correctness, penalizes wrong names/numbers/negations
- `completeness` (1-10): All spoken content captured
- `formatting` (1-10): Well-structured, paragraphs, speaker labels
- `hallucination_free` (1-10): No invented content
- `semantic_preserved` (1-10): Meaning matches ("health care" vs "healthcare" is fine)

**For LLM summary evaluation:**
- `accuracy` (1-10): Facts match transcript and reference
- `completeness` (1-10): All key points present
- `conciseness` (1-10): Good balance of detail and brevity
- `action_items` (1-10): Specific, actionable items with assignees
- `hallucination_free` (1-10): Nothing invented

### Cheap vs. Full Evaluation

| Mode | When to Use | Method | Cost |
|------|-------------|--------|------|
| **Cheap** | Quick filtering, CI gates | `jiwer` WER comparison | Free |
| **Full** | Final provider selection, benchmarking | LLM-as-judge (Claude 3.5 Sonnet) | ~$0.01-0.05 per evaluation |

## Test Harness Usage

### Auto-detect and run all available providers

```bash
python -m src.evaluation.harness \
  --audio test_meeting.wav \
  --reference-transcript test_meeting.txt \
  --reference-summary test_summary.txt \
  --output eval_report.md
```

### Run specific providers only

```bash
python -m src.evaluation.harness \
  --audio test_meeting.wav \
  --stt-providers local deepgram \
  --llm-providers ollama groq \
  --output eval_report.md
```

### Use different judge

```bash
python -m src.evaluation.harness \
  --audio test_meeting.wav \
  --judge ollama \
  --output eval_report.md
```

## Configuration Summary

```bash
# Required (local-only mode)
# Nothing - just run the app

# Optional cloud STT
export DEEPGRAM_API_KEY=...
export ASSEMBLYAI_API_KEY=...
export SPEECHMATICS_API_KEY=...
export REVAI_API_KEY=...
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Optional cloud LLM
export GROQ_API_KEY=...
export ANTHROPIC_API_KEY=...
export OPENROUTER_API_KEY=...
export MISTRAL_API_KEY=...

# Provider selection
export VV_STT_PROVIDER=local        # default
export VV_LLM_PROVIDER=ollama       # default
export VV_JUDGE_PROVIDER=anthropic  # default
```

## Future Considerations

### STT Providers

1. **Azure Speech**: Add if enterprise users specifically request it. Strong DPA, containerized on-prem.
2. **ElevenLabs Scribe v2**: Strong accuracy (3.1% WER in benchmarks), but newer and less proven at scale. Monitor.
3. **NVIDIA Riva/Nemotron**: For users with NVIDIA GPUs who want on-prem cloud quality. Requires GPU infra.
4. **Google Cloud Speech**: Only if Google adds explicit zero-retention with no training.

### LLM Providers

5. **Mistral API (La Plateforme)** — *Top candidate for next addition.*
   - EU-native: headquartered in Paris, data processed in EU data centers by default.
   - No training on API data; GDPR-native (no SCCs needed for EU customers).
   - SOC 2 Type II certified.
   - Competitive pricing (~30-60% cheaper than OpenAI for comparable tiers).
   - Open-weight models (Mistral 7B, Mixtral, Mistral Large) available under Apache 2.0 for self-hosting.
   - Best for: European users, GDPR-first deployments, teams wanting EU data residency without enterprise negotiation.

6. **Cohere (Enterprise)** — *Good for enterprise on-prem/VPC.*
   - No consumer product (by design); no training on API data.
   - Enterprise agreements include DPA, GDPR, HIPAA, SOC 2, ISO 27001.
   - On-premises, VPC, and private cloud deployments available.
   - Best for: Regulated enterprises needing air-gapped or VPC inference.

7. **AWS Bedrock** — *Good for multi-model AWS-native compliance.*
   - Does not train on customer data; covered under AWS DPA.
   - Multi-model catalog: Claude, Llama, Mistral, Titan, Cohere.
   - SOC 2, HIPAA, GDPR, FedRAMP; EU regions (eu-west-1, eu-central-1).
   - ~10-15% AWS infrastructure margin on top of model pricing.
   - Best for: Teams already on AWS needing a single compliant endpoint for multiple models.

8. **Azure OpenAI Service** — *Good for Microsoft-first shops.*
   - Does not train on customer data; Microsoft enterprise DPA (MSDPA) includes GDPR SCCs + UK IDTA.
   - EU regions available (West Europe, North Europe, Sweden Central).
   - 90+ compliance certifications; FedRAMP High, HIPAA.
   - Only OpenAI models (GPT-4o, o1, etc.).
   - Best for: Organizations already on Microsoft 365 / Azure AD needing deep integration.

9. **Together AI** — *Fast open-source inference, weaker compliance.*
   - No training on API data by default.
   - Enterprise DPA available, but fewer public certifications than Anthropic/Mistral.
   - Best for: Open-source model variety at speed, when compliance is secondary to cost/speed.

### Priority for Next Implementation

| Priority | Provider | Rationale | Effort |
|----------|----------|-----------|--------|
| **P1** | **Mistral API** | Strongest EU privacy posture, good model quality, easy OpenAI-compatible API, competitive pricing | Low — same SDK pattern as Groq |
| **P2** | **AWS Bedrock** | Adds enterprise multi-model compliance + AWS integration; users already have AWS keys for Transcribe | Medium — requires boto3 + model ID routing |
| **P3** | **Cohere Enterprise** | On-prem/VPC option is unique among cloud providers; strong for regulated healthcare/finance | Medium — separate SDK, enterprise onboarding |
| **P4** | **Azure OpenAI** | Only valuable if user specifically requests Microsoft stack; redundant with Anthropic + Bedrock | Medium |

## Decision Log

| Date | Decision | Rationale | Reversibility |
|------|----------|-----------|---------------|
| 2026-07-03 | Local Whisper as default STT | Privacy-first, zero cost, no network | Reversible via config |
| 2026-07-03 | Exclude Google Cloud Speech | No zero-retention, unclear training policy | Reversible if Google changes policy |
| 2026-07-03 | Exclude OpenAI Whisper API | Same model as local, but audio hits OpenAI servers | Reversible if OpenAI adds zero-retention |
| 2026-07-03 | Deepgram as primary streaming alternative | Best TTFS, lowest latency, zero-retention | Reversible via API key removal |
| 2026-07-03 | AssemblyAI as feature-rich alternative | PII redaction, topic detection, best diarization | Reversible via API key removal |
| 2026-07-03 | Rev.ai as premium accuracy option | Highest accuracy, HIPAA, but expensive | Reversible via API key removal |
| 2026-07-03 | Ollama as default LLM | Zero cost, local, privacy-native | Reversible via config |
| 2026-07-03 | Anthropic as default judge | Best reasoning for nuanced evaluation | Reversible via `VV_JUDGE_PROVIDER` |
| 2026-07-03 | Groq as fast cloud LLM | <100ms inference, good for real-time | Reversible via API key removal |
| 2026-07-03 | Verified Anthropic compliance | SOC 2 Type II, ISO 27001, HIPAA BAA, ZDR available | Preferred cloud judge + quality LLM |
| 2026-07-03 | Verified Groq compliance | No training, DPA enterprise-only, no public SOC 2 cert yet | Fast inference; weaker enterprise compliance |
| 2026-07-03 | Verified OpenRouter compliance | SOC 2 Type 2, ZDR per-request, EU routing enterprise | Best aggregator controls; watch upstream policies |
| 2026-07-03 | Mistral API as next LLM candidate | EU-native, GDPR-first, SOC 2 Type II, no SCCs needed | Add if EU users need data residency |
