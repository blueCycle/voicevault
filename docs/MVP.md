# VoiceVault MVP

**Goal:** A privacy-first voice note-taking app that runs entirely offline. One STT provider, one LLM provider, zero cloud dependencies.

**Providers:** Local Whisper (on-device STT) + Ollama (local LLM). Both run on your hardware. No API keys. No internet required.

**Date:** 2026-07-03
**Status:** Draft

---

## MVP Definition

The smallest version of VoiceVault that delivers the core value proposition: *speak, transcribe, summarize — without your data ever leaving your machine.*

### In Scope

| Feature | Provider | Why |
|--------|----------|-----|
| **Speech-to-Text** | **Local Whisper** (`tiny` or `base` model) | Runs on-device, zero network, zero cost, no API keys |
| **Meeting Summarization** | **Ollama** (`llama3.1:8b` or similar) | Runs locally, zero cloud, no data retention concerns |
| **Dictation** | Local Whisper | Hold a hotkey, speak, text appears at cursor |
| **Meeting Recording** | Local Whisper + Ollama | Record a meeting, get a transcript + AI summary |
| **Obsidian Export** | Markdown with YAML frontmatter | Simple, portable, works with any note-taking app |

### Out of Scope (Post-MVP)

- Cloud STT providers (Deepgram, AssemblyAI, etc.)
- Cloud LLM providers (Groq, Anthropic, Mistral, OpenRouter)
- Mobile companion app
- Speaker diarization
- Real-time streaming optimization
- PII redaction
- Multi-language support beyond Whisper's defaults

---

## Architecture

```
┌─────────────────────────────────────┐
│         VoiceVault (macOS)          │
│  ┌─────────────┐  ┌─────────────┐  │
│  │  Dictation │  │   Meeting   │  │
│  │    Mode     │  │   Meeting   │  │
│  └──────┬──────┘  └──────┬──────┘  │
│         │                │         │
│         └────────────────┘         │
│                   │                │
│         ┌─────────▼─────────┐      │
│         │  Local Whisper    │      │
│         │  (tiny/base)      │      │
│         └─────────┬─────────┘      │
│                   │                │
│         ┌─────────▼─────────┐      │
│         │     Ollama        │      │
│         │  (llama3.1:8b)    │      │
│         └─────────┬─────────┘      │
│                   │                │
│         ┌─────────▼─────────┐      │
│         │  Obsidian Export  │      │
│         │  (Markdown + YAML)  │      │
│         └─────────────────────┘      │
└─────────────────────────────────────┘
```

---

## Why Local Whisper + Ollama?

| Dimension | Local Whisper | Ollama |
|-----------|---------------|--------|
| **Privacy** | Audio never leaves device | Prompts never leave device |
| **Cost** | $0 | $0 |
| **Latency** | ~500ms-2s per utterance (model-dependent) | ~1-5s per summary (M1/M2 Mac) |
| **Offline** | Yes | Yes |
| **Setup** | Download model once | Pull model once |
| **Maintenance** | None | None |
| **Limitation** | Slower than cloud on CPU | Smaller model than cloud APIs |

**Trade-off:** We sacrifice speed and cutting-edge model quality for absolute privacy and zero operational cost. This is the correct trade-off for an MVP targeting privacy-conscious users.

---

## Setup (5 Minutes)

### Prerequisites

- macOS Sonoma+
- Python 3.10+
- ~2GB free disk space (for Whisper `base` + Ollama `llama3.1:8b`)

### 1. Install Ollama

```bash
brew install ollama
ollama pull llama3.1:8b
```

### 2. Install Python Dependencies

```bash
cd ~/code/experiments/voicevault
python -m pip install -r requirements.txt
```

### 3. Verify Everything Works

```bash
# Check Ollama
ollama run llama3.1:8b "Hello"

# Check Whisper (downloads model on first run)
python -c "from src.providers.stt.local import LocalWhisperProvider; p = LocalWhisperProvider(); print('Whisper ready:', p.health_check())"
```

### 4. Run the App

```bash
./scripts/run.sh
```

No API keys. No cloud accounts. No configuration files beyond the defaults.

---

## User Flows

### Dictation

1. User holds `Fn` (F13) key
2. Speaks: "Remind me to call Sarah about the contract tomorrow"
3. Releases key
4. Text appears at cursor: `Remind me to call Sarah about the contract tomorrow`

**Implementation:**
- Capture microphone audio while key is held
- Feed audio buffer to Local Whisper
- Inject transcribed text at cursor position via macOS Accessibility API or paste

### Meeting Recording

1. User clicks menu bar icon → "Start Meeting"
2. Enters title: "Q3 Planning"
3. Meeting begins recording
4. User can take inline notes anytime (optional for MVP)
5. User clicks "Stop Meeting"
6. Auto-processing:
   - Save audio file: `recordings/q3_planning_20260703_120000.wav`
   - Transcribe with Local Whisper: `transcripts/q3_planning_20260703_120000.txt`
   - Summarize with Ollama: `notes/q3_planning_20260703_120000.md`
   - Export to Obsidian: `~/Obsidian/amit-voicevault/q3_planning_20260703_120000.md`

---

## Data Model

```
data/
├── recordings/
│   └── q3_planning_20260703_120000.wav
├── transcripts/
│   └── q3_planning_20260703_120000.txt
├── notes/
│   └── q3_planning_20260703_120000.md
└── meetings.jsonl  # append-only log of all meetings
```

---

## Obsidian Export Format

```markdown
---
id: 20260703_120000
title: Q3 Planning
date: 2026-07-03
time: 12:00
duration: 45min
type: meeting
recording: q3_planning_20260703_120000.wav
---

# Q3 Planning

*Date: 2026-07-03 at 12:00 | Duration: 45 minutes*

## Summary

AI-generated summary here...

## Transcript

**[0:00]** Let's kick off the Q3 planning session...
**[5:23]** Revenue projections look strong...
```

---

## Success Criteria

The MVP is complete when:

1. [ ] User can hold a hotkey and have spoken text appear at cursor (Dictation)
2. [ ] User can start/stop a meeting recording and get a transcript + summary (Meeting)
3. [ ] All processing happens offline (no network calls during transcription or summarization)
4. [ ] Output exports to Obsidian-compatible Markdown
5. [ ] App runs from a single script (`./scripts/run.sh`) without cloud API keys

---

## Post-MVP Roadmap

| Priority | Feature | Provider | Rationale |
|----------|---------|----------|-----------|
| **P1** | Faster streaming STT | Deepgram Nova-2 | <300ms latency for real-time feel |
| **P1** | Better summaries | Anthropic Claude 3.5 | Higher quality meeting summaries |
| **P2** | Speaker diarization | AssemblyAI Universal | "Who said what" in meetings |
| **P2** | EU data residency | Mistral API (La Plateforme) | GDPR-first for European users |
| **P3** | Mobile companion | On-device STT + sync | Capture on-the-go |
| **P3** | LLM-as-judge eval | Anthropic Claude 3.5 | Automated quality scoring |

---

## Risk: Local Performance

**Risk:** Local Whisper on CPU may feel slow for real-time Dictation usage.

**Mitigation:**
- Use `tiny` or `base` model for Dictation (fast enough for short utterances)
- Use `small` or `medium` model for Meeting meetings (batch processing, latency less critical)
- M1/M2 Macs with `mps` backend significantly faster than CPU
- If local is too slow, the first cloud upgrade is Deepgram Nova-2 (same API shape, just add API key)

---

## One-Line Pitch

> VoiceVault MVP: Open the app, speak, and your words appear — transcribed by Whisper, summarized by Llama, stored in Obsidian, never touching the internet.
