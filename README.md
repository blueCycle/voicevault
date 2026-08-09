# VoiceVault

Privacy-first, open-source voice note-taking combining the best of **Dictation** (voice-to-text anywhere) and **Meeting** (meeting recording with AI summaries). All processing runs locally — no cloud required.

## What It Does

| Mode | Trigger | Behavior | Output |
|------|---------|----------|--------|
| **Dictation** | Hold `Fn` key (configurable) | Streams microphone → Whisper → inserts text at cursor | Text typed into any app |
| **Meeting** | Dashboard → Record tab → Start Recording | Records full meeting, transcribes + summarizes in the background | Transcript + AI summary + Obsidian export |

## Architecture

```
VoiceVault (macOS menu bar app)
├── Dictation
│   ├── Microphone stream capture (push-to-talk or double-tap hands-free)
│   ├── Local Whisper transcription (mlx-whisper on Apple Silicon by default)
│   └── Text injection at cursor (clipboard+paste → Accessibility API fallback)
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
git clone git@github.com:blueCycle/voicevault.git
cd voicevault

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
- Apple Silicon (M-series) for the default `mlx-whisper` backend — Intel Macs should set `VV_WHISPER_BACKEND=faster-whisper` / `VV_WHISPER_DEVICE=cpu` in `.env`
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
VV_DATA_DIR=~/Library/Application Support/VoiceVault  # default if unset; where recordings/transcripts/notes/search index live
VV_WHISPER_BACKEND=mlx-whisper                       # mlx-whisper (Apple Silicon) | faster-whisper (Intel/CPU)
VV_WHISPER_MODEL=mlx-community/whisper-large-v3-turbo # model id or HF repo; tiny/base/small/medium/large for faster-whisper
VV_WHISPER_DEVICE=mps        # mps (Apple Silicon), cpu, cuda — mlx-whisper ignores this, always uses Metal
VV_OLLAMA_MODEL=llama3.1:8b  # Any model pulled in Ollama
VV_OBSIDIAN_VAULT=~/Obsidian/voicevault
VV_DICTATE_HOTKEY=fn         # fn, ctrl, cmd, alt, f13, or any letter — hold for push-to-talk, double-tap for hands-free

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

**Push-to-talk (default):**
1. Hold `Fn` key (or whatever you set `VV_DICTATE_HOTKEY` to)
2. Speak naturally
3. Release key
4. Transcribed text appears at your cursor position in any app

**Hands-free:** double-tap the hotkey within ~0.35s to start recording without holding the key; a single press stops it and injects the text — useful for longer dictations.

The hotkey defaults to `Fn` so it matches Wispr Flow's own hotkey — if you have both installed, whichever app is actually running owns the key, no remapping needed. Set `VV_DICTATE_HOTKEY` to `ctrl`, `cmd`, `alt`, `f13`–`f20`, or any single letter to change it.

**If you use the `Fn` hotkey, hands-free (double-tap) needs one System Settings change**: Keyboard → "Press 🌐 Fn key to: Do Nothing". Push-to-talk (hold) works fine without it, but a double-tap is two quick taps — exactly what macOS's own Emoji & Symbols/Dictation picker responds to by default — and that picker popping up steals window focus mid-dictation, so your words get transcribed correctly but pasted nowhere useful. Setting it to "Do Nothing" frees the key for double-tap without affecting push-to-talk at all.

Every finished dictation is appended to a daily Markdown log (menu bar → "Open Today's Log") and can be re-pasted via "Replay Last Dictation".

**Text injection fallback chain:**
1. Clipboard + simulated Cmd+V (primary — most reliable, preserves formatting)
2. AppleScript keystroke injection (fallback — works without clipboard permission)
3. Clipboard only (final fallback — user pastes manually)

### Meeting Recording

Recording starts and stops from the [Dashboard](#dashboard-browse-search--ask)'s **Record** tab — a visible window, not a menu-bar dialog. This mirrors how Granola and Wispr Flow do it, and avoids the class of focus/stuck-menu bugs that came from trying to drive a start/stop flow through a native macOS alert triggered from an accessory (no-Dock-icon) app.

1. Menu bar → **Meeting** (or **Open Dashboard**) → opens the dashboard to the Record tab
2. Optionally type a title (left blank, one is inferred from the transcript once you stop)
3. Click **Start Recording** — capture begins (mic + optional system audio); the menu bar and the dashboard's REC indicator both show a live timer
4. Click **Stop Recording** when done
5. Auto-processing, all local:
   - Transcribe with timestamps (mlx-whisper)
   - Generate AI summary via Ollama
   - Export to Obsidian as Markdown with YAML frontmatter
6. The dashboard jumps straight to the finished note (summary + collapsible full transcript)

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

## Dashboard: Browse, Search & Ask

Click the menu bar icon → **Open Dashboard** (or **Meeting**) to launch VoiceVault's Electron app — a **Record** tab for starting/stopping meetings, browsing every past dictation and meeting, searching across all of them, and asking questions answered by your local LLM with citations back to the source notes.

**First-time setup** (one-time, ~2-3 minutes):
```bash
cd electron
npm install
npm run build   # packages a real VoiceVault.app; skip this and it'll
                 # still launch via `npm start`, but shows up as generic
                 # "Electron" in the Dock/Cmd+Tab instead of "VoiceVault"
```

**How it works:**
- The menu bar app runs a small local API (`src/api/server.py`, FastAPI, bound to `127.0.0.1` only — never reachable over the network) alongside dictation/meeting mode.
- The dashboard's **Record** tab talks to that same API (`/meetings/start`, `/meetings/stop`, `/meetings/current`) to control the same `MeetingManager` the menu bar uses — start it from either place, both stay in sync.
- On startup it indexes anything new into a local SQLite database (`sqlite-vec` for semantic search + FTS5 for keyword search), using local embeddings via Ollama's `nomic-embed-text` model. Re-indexing is incremental — unchanged notes are skipped.
- The **search box** combines semantic + keyword search (reciprocal rank fusion) so both "the meeting about the Q3 roadmap" and exact-phrase lookups work.
- The **Ask VoiceVault** tab retrieves the most relevant notes for your question and asks your local `llama3.1:8b` model to answer using only that context — citing which note(s) it used, and telling you plainly if the notes don't contain an answer.
- Everything — recording, indexing, embeddings, search, and chat — runs locally. Nothing leaves your machine.

Both `npm install` and `npm run build` need Node.js (`brew install node` if you don't have it). Re-run `npm run build` after pulling changes that touch `electron/`.

## Performance & Resource Usage

### Component lifecycle

| Component | Runs when | Notes |
|---|---|---|
| VoiceVault menu bar app | You start/quit it | Owns the hotkey listener, audio capture, and the local API server |
| Whisper (`mlx-whisper`) | Loads on your first dictation/transcription, stays resident until VoiceVault quits | Lives *inside* the VoiceVault process — tied 1:1 to its lifecycle |
| Electron dashboard | Only while its window is open | Separate process(es), independent of the menu bar app |
| **Ollama server** | **Independent of VoiceVault** — a background service started at login | VoiceVault just calls it over HTTP (`localhost:11434`); it's running whether or not VoiceVault is |
| **`llama3.1:8b` model weights** | **Independent of VoiceVault** — Ollama loads them on the first request (from anything, not just VoiceVault) and unloads them after `OLLAMA_KEEP_ALIVE` idle time | This is the one to watch — see below |

The Whisper/Ollama distinction matters: quitting VoiceVault frees Whisper's memory immediately, but the LLM's memory is governed entirely by Ollama's own idle timeout, not by VoiceVault starting or stopping.

### Measured footprint

Snapshot taken on a 48GB M-series Mac, VoiceVault + dashboard both open:

| Process | RSS (memory) | CPU |
|---|---|---|
| VoiceVault menu bar app (incl. loaded Whisper model) | ~1.4 GB | ~1-2% idle |
| Electron dashboard (main + 3 helper processes) | ~360 MB | ~0% idle |
| Ollama background service (no model loaded) | ~150 MB | ~0% |
| `llama3.1:8b` model (while loaded) | ~9.2 GB | spikes during generation |

Worst case (everything open, Ollama actively summarizing) is roughly **~11 GB**. On lower-RAM Macs, the 9.2GB Ollama spike — not VoiceVault itself — is the number to plan around, and it's controlled by Ollama's settings, not VoiceVault's.

### Tuning: free LLM memory faster

By default Ollama keeps a model loaded for 5 minutes after its last use (`OLLAMA_KEEP_ALIVE`). To free that ~9GB sooner between meetings/chats, lower it — e.g. in a LaunchAgent that runs `launchctl setenv` at login (so it persists across reboots and applies before Ollama starts):

```xml
<key>ProgramArguments</key>
<array>
    <string>/bin/sh</string>
    <string>-c</string>
    <string>launchctl setenv OLLAMA_KEEP_ALIVE 2m</string>
</array>
<key>RunAtLoad</key>
<true/>
```

Restart Ollama after changing it (`killall Ollama && open -a Ollama`) for the new default to take effect. This is an Ollama-wide setting — it affects any app using your local Ollama, not just VoiceVault. Going lower than a minute or two risks reloading the model mid-conversation if you pause between Ask-tab questions.

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
- [x] MVP: Working Dictation + Meeting modes on macOS
- [x] Hands-free dictation mode, dashboard, daily transcript log
- [x] Meeting recording moved into the dashboard's Record tab (Granola-style)
- [x] Dashboard packaged as a real macOS app (`electron-builder`), not a bare dev process
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
