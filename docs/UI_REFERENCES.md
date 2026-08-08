# UI References

Notes captured from screenshots of the real Wispr Flow app shared during a
2026-07-04 testing session. No image files were saved (they were pasted
directly into chat, not files on disk) — this is a text description of
what was observed, for future reference when building VoiceVault's UI.

## Wispr Flow — Home / Dictation Feed

- Left nav: Home, Insights, Dictionary, Snippets, Style, Transforms, Scratchpad — plus Invite team / Get a free month / Settings / Help at the bottom.
- Header: "Welcome back, {name}".
- Promo banner for a feature announcement (not relevant to clone).
- Right sidebar: stat cards — total words, words-per-minute, day streak — plus a "Voice Profile" card showing a named style preset (e.g. "Thesis Builder").
- Main feed: day-grouped header ("TODAY"), each entry shows a time (no date, since grouped by day) and the **full dictated text inline** — no separate list/detail split, the list *is* the detail.

## Wispr Flow — Insights / Analytics

- Tabs: "Your Usage" / "Your Voice".
- Stat cards: WPM (with a percentile ranking, "Top 0.2%"), "Fixes made by Flow" (words corrected + dictionary fixes, each a count), Total words dictated (month-over-month delta, plus a fun equivalence like "you've written 4 complete books").
- "Desktop usage" breakdown by category (AI prompts, other tasks, work messages, emails, personal messages, documents), each a % and a count.
- Streak calendar: GitHub-style heatmap, per-day intensity, current streak + longest streak shown.

## Comparison to VoiceVault today

| Feature | Wispr Flow | VoiceVault |
|---|---|---|
| Dictation history feed | Day-grouped, full text inline | Flat chronological list, truncated preview + detail pane (built 2026-07-04) |
| Meeting/notes browsing | N/A (Wispr Flow is dictation-only) | Dashboard window (built 2026-07-04) |
| Usage stats (words, WPM, streak) | Yes | None |
| Per-app usage breakdown | Yes | None — `inject_text` doesn't record the frontmost app |
| Custom vocabulary UI | Dictionary page | `CONFIG.initial_prompt` exists but has no UI — edit `.env` by hand |
| Style/Voice presets per app | Yes | None |
| Voice-command rewrites (Transforms) | Yes | None |
| Snippets | Yes | None |

## Next steps (prioritized)

1. **Day-grouped feed with inline text** in the existing Dashboard window — cheapest change, reuses the data model already built (`TranscriptLog.list_entries()`, `MeetingManager.list_sessions()`), no new data capture needed.
2. **Local-only "Insights" v1** — total words dictated, meeting count/duration, and a streak calendar, all fully derivable from existing files (`data/log/*.md` filenames for streak, word-count the transcript text). No new data capture required.
3. **New data capture for Insights v2** — per-dictation audio duration (needed for WPM; `TranscriptLog` entries don't currently store it) and frontmost-app name at injection time (needed for the per-app usage breakdown; `inject_text` doesn't currently capture this).
4. **Deferred, larger scope**: Dictionary UI (surface `CONFIG.initial_prompt` as an editable list instead of a raw `.env` string), Voice Profile/Style presets per app, Transforms (voice-command rewrites), Snippets.
5. **Still open from earlier this session** (not Wispr-Flow-reference-related): the Granola-style live meeting-notes floating panel (`MeetingManager.add_note()` exists but nothing in the UI calls it), wiring cloud STT (Deepgram/AssemblyAI, already keyed in 1Password) into the live app instead of only the eval harness, and housekeeping (commit the pending `.gitignore`/untracking changes, consolidate the four leftover test Obsidian vault folders).
