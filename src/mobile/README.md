# Mobile Architecture

VoiceVault supports a mobile companion for on-the-go voice capture. Since running full Whisper on mobile is battery-intensive and memory-constrained, the mobile architecture uses a hybrid approach.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Mobile App    │────▶│  VoiceVault API  │────▶│  Desktop App    │
│ (iOS/Android)   │     │  (self-hosted)   │     │ (macOS/Windows) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                         │                       │
        ▼                         ▼                       ▼
  Native STT (quick)      Whisper (full)          Obsidian vault
  or Cloud STT             + Ollama summary        + Local sync
```

## Mobile App (React Native / SwiftUI / Flutter)

### Recording
- Uses native microphone APIs
- Records to compressed audio (M4A/Opus) to minimize bandwidth
- Supports background recording for long meetings

### Transcription Options (configurable)

| Option | Privacy | Speed | Quality | Setup |
|--------|---------|-------|---------|-------|
| **On-device (iOS)** | High | Instant | Good | Zero setup - uses SFSpeechRecognizer |
| **On-device (Android)** | High | Instant | Good | Zero setup - uses SpeechRecognizer |
| **Self-hosted API** | High | Fast | Best | Requires running VoiceVault API on home server/VPN |
| **OpenAI Whisper API** | Medium | Fast | Best | API key, audio sent to OpenAI (no retention) |
| **AssemblyAI** | Medium | Fast | Best | API key, configurable data retention |
| **Deepgram** | Medium | Fast | Best | API key, on-prem option available |

### Recommended: Hybrid Mode
1. **Quick capture**: Use on-device STT for instant transcription while recording
2. **Full processing**: Upload audio to self-hosted API or desktop app for Whisper + Ollama summarization
3. **Sync**: Results synced back to mobile via the API

## VoiceVault API Server (self-hosted)

A lightweight FastAPI/Go server that runs on your home network or VPS:

```python
# voicevault-api/main.py (FastAPI)
from fastapi import FastAPI, UploadFile, File
import tempfile

app = FastAPI()

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Receive audio from mobile, transcribe with Whisper, return text."""
    # Save uploaded file
    # Transcribe with local Whisper
    # Return transcript + optional summary
    pass

@app.post("/sync")
async def sync_to_desktop(data: dict):
    """Push mobile recordings to desktop app."""
    pass

@app.get("/meetings")
async def list_meetings():
    """List all meetings for mobile sync."""
    pass
```

### Deployment Options

| Option | Privacy | Cost | Complexity |
|--------|---------|------|------------|
| **Home server** (Raspberry Pi 5, old laptop) | High | Low | Medium |
| **Tailscale/VPN** | High | Low | Medium |
| **Cloud VPS** (Hetzner, Linode) | Medium | $5-10/mo | Low |
| **Local WiFi sync** | High | Free | Low |

## Sync Strategies

### Option 1: Direct LAN Sync (most private)
- Desktop and phone on same WiFi
- Desktop app exposes API on local network
- Mobile app discovers via mDNS/Bonjour
- No internet required

### Option 2: Tailscale/WireGuard Mesh
- Create private mesh network
- Phone and desktop connect via VPN
- API accessible securely from anywhere
- No cloud exposure

### Option 3: Cloud Relay (optional)
- Lightweight relay server for when devices are on different networks
- End-to-end encrypted (Signal Protocol, age encryption, or simple AES)
- Server can't read content, only forwards

### Option 4: iCloud / Dropbox / Syncthing (simplest)
- Mobile saves audio to shared folder
- Desktop watches folder, processes, saves results back
- Works with existing sync tools

## Mobile UI Design

```
┌─────────────────────┐
│  VoiceVault Mobile  │
│                     │
│  [🔴 Record]        │
│  [⏹ Stop]           │
│                     │
│  Recent:            │
│  • Team Standup     │
│  • Client Call      │
│  • Lecture Notes    │
│                     │
│  [Settings]         │
│  [Sync Status] 🟢   │
└─────────────────────┘
```

## Data Flow

### Mobile Recording → Desktop Processing
1. Mobile records meeting audio → saves as M4A
2. Option A: Quick on-device STT for instant preview
3. Uploads to API (or syncs via shared folder)
4. Desktop API receives audio → Whisper transcription → Ollama summary
5. Results saved to Obsidian vault on desktop
6. Mobile can view final notes via API or sync

### Mobile Quick Note (Dictation mode on phone)
1. Hold button in app → record short audio
2. On-device STT transcribes instantly
3. Text available for copy/paste or sharing
4. Optional: sync to desktop for better Whisper processing

## Implementation Priority

**Phase 1 (MVP)**: 
- Mobile app records audio
- Uploads to desktop via local WiFi or Tailscale
- Desktop processes and saves to Obsidian
- Mobile can view results via web UI or API

**Phase 2**:
- On-device STT for instant preview
- Self-hosted API for remote processing
- Push notifications when processing complete
- Offline queue (record now, sync when connected)

**Phase 3**:
- Full iOS/Android native apps
- Background recording
- Apple Watch / Wear OS companion
- Widget for quick record

## Privacy Considerations

- **On-device STT**: Audio never leaves phone (iOS/Android native APIs)
- **Self-hosted API**: Audio processed on your hardware, no third-party
- **Cloud STT**: If used, audio is transient - deleted after transcription
- **Encryption**: All mobile-to-desktop sync should use HTTPS/TLS or WireGuard
- **Local-first**: Original audio and transcripts stored on desktop, not mobile cloud

## Tech Stack Options

| Layer | Option A | Option B |
|-------|----------|----------|
| Mobile app | React Native + Expo | SwiftUI (iOS) + Jetpack Compose (Android) |
| Audio recording | Expo Audio / AVFoundation | flutter_sound / native |
| On-device STT | Expo Speech / SFSpeechRecognizer | flutter_speech_to_text |
| API backend | FastAPI (Python) | Go + Gin |
| Sync | Tailscale + mDNS | iCloud / Syncthing |
| Storage | SQLite (mobile) + desktop Obsidian | Shared files |
