# VoiceVault Onboarding Flow

**Design philosophy:** "One immediate win, zero doubts left." Borrowed from Dictation's sequential doubt-removal and Meeting's 2-minute demo meeting.

**Target time-to-first-value:** Under 90 seconds.
**Inputs required from user:** 2 (name + vault folder). Everything else is automatic or has a sensible default.

---

## The 5-Step Flow

### Step 1: Welcome (5 seconds)

Single screen, one sentence, no buttons except "Get Started".

```
VoiceVault turns your voice into structured notes
in your own Obsidian vault — entirely offline.

[Get Started]
```

**Why:** Sets the frame (local-first, Obsidian, simple). No configuration, no choices. Just momentum.

---

### Step 2: Your Name (10 seconds)

```
What should we call you?

[Alex]                    [Continue]
```

- Used for meeting note attribution (e.g. `Hosted by: Alex`)
- Stored in `~/.voicevault/user.json` (not the vault, so it persists across vault moves)
- Optional: if we later support voice profile training, this is the seed label

**Why:** One field, no explanation needed. Creates ownership.

---

### Step 3: Vault Folder (15 seconds)

```
Where should VoiceVault store your notes?

~/Obsidian/voicevault      [Change]

[Continue]  (creates folder if it doesn't exist)
```

- Default: `~/Obsidian/{name}-voicevault`
- If `~/Obsidian` doesn't exist, default to `~/voicevault-notes`
- Clicking "Change" opens a native folder picker (macOS `NSOpenPanel` or simple path input for MVP)
- Creates the folder immediately, plus subfolders: `Meetings/`, `Dictations/`, `Templates/`

**Why:** This is the only setup decision that matters. Everything else (models, hotkeys, audio) is automatic. The user must know *where their notes live*.

---

### Step 4: Dependency Check (10 seconds, background)

Silently check two things:

1. **Ollama running?** `curl http://localhost:11434/api/tags`
2. **Whisper model downloaded?** Check `~/.cache/whisper/` or first-run flag

If Ollama is not running:
```
Ollama is needed for AI summaries. It's already installed.

[Start Ollama]   (runs `ollama run llama3.1:8b` in background)
```

If Ollama is not installed:
```
Ollama powers the AI summaries. Install it now?

[Install Ollama]   (opens Terminal with `brew install ollama && ollama pull llama3.1:8b`)
```

If Whisper model is missing:
- Download starts automatically in background. Show a thin progress bar: `Downloading speech model... 12%`

**Why:** Removes the "will it work?" fear before the user tries anything. This is the doubt-removal step that Dictation uses with its mic test. We check dependencies instead because our value is summarization, not just dictation.

---

### Step 5: The Test Sentence (30 seconds, the Immediate Win)

```
Say this out loud:

"VoiceVault is ready for my first meeting."

[Listening...]  →  [Heard: "VoiceVault is ready for my first meeting."]

[You're Ready]
```

- Captures 3 seconds of audio
- Transcribes with Local Whisper
- Shows the result in real-time on screen
- If transcription is accurate: green checkmark, auto-advance to final screen
- If transcription is garbage: "We couldn't hear you clearly. Try checking your mic volume in System Settings. [Try Again]"

**Why:** This is the Meeting demo meeting moment, but compressed to 30 seconds. The user *feels* the product work before they are "done" with setup. This removes the final doubt: "Will my voice actually turn into text?"

---

### Step 6: First Demo Note (optional, 10 seconds)

```
Here's what a meeting note looks like in your vault:

[Preview of a sample note with summary, transcript, action items]

[Open Vault]    [Start Using VoiceVault]
```

- Creates a sample note in the vault: `Meetings/demo-voicevault-onboarding.md`
- Contains a fictional meeting summary, so the user sees the output format before their first real meeting
- Uses their name (from Step 2) in the note: `Attendees: {name}, Sarah, David`

**Why:** Meeting's co-founder demo video proves the output format. We do the same with a static note — the user sees exactly what their vault will look like. No surprises later.

---

## After Onboarding

The menu bar app starts. No restart needed. The user can immediately:
- Hold `Fn` to dictate (Dictation mode)
- Click the menu bar icon → "Start Meeting" (Meeting mode)

---

## What We Deliberately Do NOT Ask

| Question | Why We Skip It |
|----------|---------------|
| Language | Default to English; let user change in Settings later |
| **Hotkey** | Default to `Fn` (matches Wispr Flow); power users can remap in Settings |
| Whisper model size | Default to `base` for dictation, `small` for meetings; auto-detect M1/M2 and use `mps` |
| Cloud provider preferences | Not relevant for local MVP; Settings page has these when providers are added |
| Calendar connection | Not needed for MVP; manual meeting start only |

---

## State Machine

```
[First Launch?]
    │
    ├── No → Start App normally
    │
    └── Yes → [Welcome]
                │
                ↓
            [Name] ──→ store in ~/.voicevault/user.json
                │
                ↓
            [Vault Folder] ──→ create folder + subfolders
                │
                ↓
            [Dependency Check] ──→ background: check Ollama, download Whisper if needed
                │
                ↓
            [Test Sentence] ──→ transcribe live, show result
                │
                ↓
            [Demo Note] ──→ create sample markdown in vault
                │
                ↓
            [App Starts] ──→ menu bar icon appears, ready to use
```

---

## Implementation Notes

### First-Launch Detection

```python
# On app startup
FIRST_RUN_FLAG = Path.home() / ".voicevault" / "first_run_complete"

if not FIRST_RUN_FLAG.exists():
    show_onboarding()
    FIRST_RUN_FLAG.touch()
```

### Persisted Onboarding State

```python
# ~/.voicevault/user.json
{
    "name": "Alex",
    "vault_path": "/Users/alex/Obsidian/voicevault",
    "onboarded_at": "2026-07-03T08:30:00Z",
    "first_run_complete": true
}
```

### Why a separate `~/.voicevault/` folder?

- Keeps user identity separate from the vault (which might be shared, synced, or moved)
- Stores onboarding flag, preferences, voice profiles, and other app metadata
- Vault = *user content*. `~/.voicevault` = *app state*.

---

## Comparison to Inspiration

| Principle | Dictation | Meeting | VoiceVault |
|-----------|-----------|---------|------------|
| **Doing > Telling** | Mic test before config | 2-min demo video | Live test sentence |
| **Remove doubts in sequence** | Shortcut → mic test → practice ×4 | Install → sign-in → permissions → demo | Name → folder → deps → mic test → demo note |
| **One immediate win** | First dictation works in 30s | Demo meeting proves output | Test sentence + demo note in 60s |
| **Required user inputs** | 4 (language, shortcut, etc.) | 1 (Google/Microsoft sign-in) | 2 (name, folder) |
| **Time to first value** | ~2 minutes | ~5 minutes | ~90 seconds |

---

## Open Questions

1. **GUI framework:** For MVP, onboarding could be a CLI/TUI wizard (using `rich` or `inquirer`) since the main app is a menu bar app. A native GUI onboarding can be added later.
2. **Ollama auto-start:** Should we try to start Ollama via `subprocess` or just show a button that runs a terminal command? Starting a daemon silently might be surprising; better to ask.
3. **Folder picker:** macOS native folder picker requires `PyObjC` or `tkinter`. For MVP, a text input with the default pre-filled is acceptable.
4. **Demo note content:** Should the fictional meeting be generic or personalized with the user's name? Personalized is better for the "aha" moment.

---

## Draft UI (CLI/TUI Version for MVP)

If we implement this as a TUI before the native GUI:

```bash
$ python src/app.py

╔══════════════════════════════════════════════════════════════╗
║  VoiceVault                                                  ║
║  Your voice → structured notes. Entirely offline.             ║
╚══════════════════════════════════════════════════════════════╝

What should we call you? [Alex]: Alex

Where should VoiceVault store your notes?
[~/Obsidian/voicevault]: (press Enter to accept)

Checking dependencies...
✓ Ollama is running (llama3.1:8b available)
✓ Whisper model ready

Say this out loud:

  "VoiceVault is ready for my first meeting."

[Listening...] ████████░░ 80%

Heard: "VoiceVault is ready for my first meeting."
✓ Transcription looks good!

Created a sample meeting note in your vault:
  ~/Obsidian/voicevault/Meetings/demo-voicevault-onboarding.md

VoiceVault is running in your menu bar. Hold Fn to dictate.
```
