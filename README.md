# VoiceVault

Privacy-first, open-source voice note-taking combining the best of **Dictation** (voice-to-text anywhere) and **Meeting** (meeting recording with AI summaries). All processing runs locally — no cloud required.

## What It Does

| Mode | Trigger | Behavior | Output |
|------|---------|----------|--------|
| **Dictation** | Hold `Ctrl` key | Streams microphone → Whisper → inserts text at cursor | Text typed into any app |
| **Meeting** | Click menu bar → Start Meeting | Records full meeting + inline notes | Transcript + AI summary + Obsidian export |

## Architecture

```
VoiceVault (macOS menu bar app)
├── Dictation
│   ├── Microphone stream capture
│   ├── Whisper real-time transcription
│   └── Text injection at cursor (Accessibility API → paste fallback)
│
├── Meeting Recording
│   ├── Audio recording (mic + optional system audio via BlackHole)
│   ├── Inline note-taking with timestamps
│   ├── Whisper transcription with timestamps
│   ├── Ollama LLM summary generation
│   └── Obsidian Markdown export (YAML frontmatter)
│
└── Mobile Companion (planned)
    ├── iOS/Android app for on-the-go capture
    ├── On-device STT (SFSpeechRecognizer / SpeechRecognizer)
    └── Sync to desktop via LAN / Tailscale / self-hosted API
```

## Quick Start

```bash
# 1. Clone and enter the directory
cd ~/code/experiments/voicevault

# 2. Run setup (installs deps, checks Ollama, runs onboarding)
./scripts/setup.sh

# 3. Create a Spotlight app for easy launching
./scripts/create-spotlight-app.sh

# 4. Run the app (or launch via Spotlight after step 3)
./scripts/run.sh
```

## First-Time Permissions

The first time you run VoiceVault, macOS will prompt for:
- **Microphone** — required for both dictation and meeting recording
- **Accessibility** — required for text injection at cursor (dictation mode)

## Prerequisites

- macOS 14+ (Sonoma or later)
- Python 3.10+
- [Homebrew](https://brew.sh) (for Ollama and BlackHole)
- [Ollama](https://ollama.com) for meeting summarization (local, no cloud)
- Optional: [BlackHole](https://github.com/ExistentialAudio/BlackHole) for system audio capture in meetings

## Installation Steps

```bash
# 1. Install Ollama (if not already installed)
brew install ollama
ollama pull llama3.1:8b

# 2. Install VoiceVault dependencies
./scripts/setup.sh

# 3. (Optional) Install BlackHole for meeting audio capture
brew install blackhole-2ch
# Then open Audio MIDI Setup and create a Multi-Output Device

# 4. Create a Spotlight app for launching
./scripts/create-spotlight-app.sh
```

### Launching VoiceVault

After running `create-spotlight-app.sh`, you can launch VoiceVault in two ways:

**Via Spotlight (easiest):**
1. Press `Cmd+Space`
2. Type `VoiceVault`
3. Press `Enter`

**Via Terminal:**
```bash
./scripts/run.sh
```

**Add to Dock:**
Right-click the VoiceVault app in Spotlight results → `Options` → `Keep in Dock`

## Configuration

All settings are in `~/.voicevault/user.json` (created during onboarding) and `.env` (copied from `.env.example` during setup). Edit `.env` to change defaults:

```env
# Core settings
VV_WHISPER_MODEL=base        # tiny/base/small/medium/large
VV_WHISPER_DEVICE=cpu        # cpu, cuda, mps (Apple Silicon)
VV_OLLAMA_MODEL=llama3.1:8b  # Any model pulled in Ollama
VV_OBSIDIAN_VAULT=~/Obsidian/voicevault
VV_DICTATE_HOTKEY=ctrl       # ctrl, cmd, alt, f13, or any letter

# Provider selection (fallback chain)
VV_STT_PROVIDER=local        # local | deepgram | assemblyai | speechmatics | revai | aws
VV_LLM_PROVIDER=ollama      # ollama | groq | anthropic | openrouter | mistral
VV_JUDGE_PROVIDER=anthropic  # llm-as-judge provider

# Optional cloud API keys (only add what you want to use)
DEEPGRAM_API_KEY=...
ASSEMBLYAI_API_KEY=...
SPEECHMATICS_API_KEY=...
REVAI_API_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
MISTRAL_API_KEY=...
```

## How It Works

### Dictation

1. Hold `Ctrl` key
2. Speak naturally
3. Release key
4. Transcribed text appears at your cursor position in any app

**Fallback chain:**
1. macOS Accessibility API (keystroke injection)
2. Clipboard + Cmd+V simulation
3. Clipboard only (manual paste)

### Meeting Recording

1. Click menu bar icon → Start Meeting
2. Enter meeting title
3. Record begins (mic + optional system audio)
4. Take inline notes anytime (via API or future floating window)
5. Click Stop when done
6. Auto-processing:
   - Transcribe with timestamps
   - Generate AI summary via Ollama
   - Export to Obsidian as Markdown with YAML frontmatter

## Obsidian Export Format

Each meeting exports as:

```markdown
---
id: 20260703_070000
title: Team Standup
date: 2026-07-03
time: 07:00
duration: 15min
type: meeting
recording: meeting_20260703_070000.wav
---

# Team Standup

*Date: 2026-07-03 at 07:00 | Duration: 15 minutes*

## Summary

AI-generated summary here...

## My Notes

| Time | Tag | Note |
|------|-----|------|
| 0:05 | action | Follow up with design team |

## Transcript

**[0:00]** Let's get started...
**[0:15]** Update on the API migration...
```

## Mobile Companion

See [src/mobile/README.md](src/mobile/README.md) for mobile architecture.

**Key idea:** Mobile app records audio, uses on-device STT for quick preview, then syncs to your desktop for full Whisper + Ollama processing. The desktop app remains the "brain" — all storage, transcription, and summarization stays local.

## Privacy

- **100% local**: Whisper runs on-device, Ollama runs locally, no API keys needed
- **No cloud**: No audio, transcripts, or summaries leave your machine
- **No telemetry**: No analytics, no tracking, no data collection
- **Open source**: Inspect every line of code

## Provider Architecture

VoiceVault supports a **plugin-based provider system** for both STT and LLM. All providers implement a common interface (`src/providers/base.py`) and are auto-discovered via health checks.

### STT Providers

| Provider | Type | Streaming | Batch | Diarization | Cost/min | Best For |
|----------|------|-----------|-------|-----------|----------|----------|
| **Local Whisper** | Local | Yes | Yes | Yes | $0 | Privacy-first, offline |
| **Deepgram Nova-2** | Cloud | Yes | Yes | Yes | $0.0043 | Fastest streaming, lowest latency |
| **AssemblyAI Universal** | Cloud | Yes | Yes | Yes | $0.0062 | PII redaction, topic detection, speaker IDs |
| **Speechmatics** | Cloud | Yes | Yes | Yes | ~$0.005 | 50+ languages, on-prem option |
| **Rev.ai** | Cloud | Yes | Yes | Yes | $0.035 | Highest accuracy, HIPAA |
| **AWS Transcribe** | Cloud | Yes | Yes | Yes | $0.024 | Enterprise compliance, BAA, GovCloud |

### LLM Providers

| Provider | Type | Speed | Cost/1K tokens | Best For |
|----------|------|-------|----------------|----------|
| **Ollama** | Local | Variable | $0 | Default, privacy-native |
| **Groq** | Cloud | <100ms | $0.0001 | Fast real-time summaries |
| **Anthropic Claude 3.5** | Cloud | Fast | $3/$15 per 1M | Best quality, judge/evaluator |
| **OpenRouter** | Cloud | Variable | Varies | Aggregator, model variety |
| **Mistral (La Plateforme)** | Cloud | Fast | $2/$6 per 1M | EU-native, GDPR-first, no training |

### Evaluation

Run the test harness to auto-detect available providers and evaluate them head-to-head:

```bash
python -m src.evaluation.harness \
  --audio test_meeting.wav \
  --reference-transcript test_meeting.txt \
  --reference-summary test_summary.txt \
  --output eval_report.md
```

This runs every provider you have API keys for, uses an LLM-as-judge (Claude 3.5 Sonnet by default) to score quality, and produces a ranked Markdown report with cost/quality tradeoffs. See [`docs/PROVIDER_DECISIONS.md`](docs/PROVIDER_DECISIONS.md) for the full provider selection rationale.

## Roadmap

- [x] Provider plugin architecture (STT + LLM)
- [x] 6 STT providers (Local, Deepgram, AssemblyAI, Speechmatics, Rev.ai, AWS)
- [x] 4 LLM providers (Ollama, Groq, Anthropic, OpenRouter)
- [x] LLM-as-judge evaluation framework
- [x] Test harness with auto-discovery and ranked reports
- [ ] MVP: Working Dictation + Meeting modes on macOS
- [ ] Floating note window for Meeting mode
- [ ] Speaker diarization (who said what)
- [ ] Mobile companion app (React Native / SwiftUI)
- [ ] Self-hosted API for mobile-desktop sync
- [ ] RAG search across all meeting transcripts
- [ ] Custom summary templates
- [ ] Windows/Linux support (cross-platform Tauri rewrite)

## License

MIT

## Credits

- [Dictation](https://wisprflow.ai/) — inspiration for voice-to-text-anywhere
- [Meeting](https://www.granola.ai/) — inspiration for meeting notes + AI
- [OpenAI Whisper](https://github.com/openai/whisper) — local speech recognition
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — optimized Whisper inference
- [Ollama](https://ollama.com) — local LLM for summarization
