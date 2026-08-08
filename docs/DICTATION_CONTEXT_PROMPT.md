# Dictation Context Prompt — Deferred

**Date:** 2026-08-08
**Author:** VoiceVault team
**Status:** Deferred (not implemented)

## What this is

`tests/test_features.py::BuildInitialPromptTests` specs a method
`VoiceVaultApp._build_initial_prompt` that was never implemented. It's
referenced nowhere in `src/app.py` — `_stop_dictation()`
(`src/app.py:223`) passes `CONFIG.initial_prompt` straight through to
`ENGINE.transcribe_stream()` and stops there.

As specced by the tests, the method would combine two things into
Whisper's `initial_prompt` param:

1. `CONFIG.initial_prompt` — a static glossary set once via `VV_INITIAL_PROMPT`
   in `.env` (names, acronyms, jargon). **This part already works** —
   it's passed through today, just not via this method.
2. The last 500 characters of `self._dictation_injected_text` (the
   previous dictation's output) — a rolling-context tail meant to carry
   continuity from one press-hold-release cycle into the next.

Part 2 is the missing piece, and it's the reason the 5
`BuildInitialPromptTests` cases fail.

## Why it's deferred, not just "todo"

This was originally scoped as "replicate how Wispr Flow keeps
dictations consistent." Checked against Wispr Flow's actual docs
(docs.wisprflow.ai, Aug 2026): Wispr Flow does **not** stitch
consecutive dictations together via a rolling transcript buffer. Its
continuity mechanism is **Context Awareness** — it reads the text
*already present in the active window/textbox* (via macOS
Accessibility APIs) and uses that to inform spelling, punctuation, and
tone, plus a separate personalization layer that learns vocabulary over
time. It is not conditioning the next transcription on the text of the
user's own previous spoken utterance.

So implementing `_build_initial_prompt` as specced would give a
plausible, cheap win (Whisper conditioning on recent output can reduce
style drift across consecutive press-release cycles) but would **not**
be a faithful replica of Wispr Flow's actual mechanism. True parity
would require reading the focused field's existing text via the macOS
Accessibility API — a materially bigger feature that doesn't exist in
this repo in any form yet (no Accessibility API usage anywhere in
`src/`).

## Decision

**Skip implementing `_build_initial_prompt` for now.** Each
press-hold-release dictation continues to be transcribed independently
of the previous one — this is correct, expected behavior and matches
Wispr Flow's own press/release semantics (one hold = one transcription,
release + press again = a new, unrelated transcription). Only the
optional continuity/consistency nudge across separate dictations is
missing; the core dictation loop is unaffected.

`tests/test_features.py::BuildInitialPromptTests` will remain red until
this is either implemented or removed/updated to match the actual
scope.

## If revisited later

Two directions, not mutually exclusive:

- **Cheap version (as originally specced):** implement
  `_build_initial_prompt` combining glossary + last-500-chars tail.
  Small, well-defined, tests already written.
- **Real parity version:** read the focused field's existing text via
  the macOS Accessibility API (`AXUIElement`) and feed *that* as
  context, matching Wispr Flow's actual Context Awareness mechanism.
  Bigger lift — needs Accessibility permissions, per-app handling, and
  privacy consideration (comparable to the incident Wispr Flow itself
  had in late 2025 over undisclosed screenshot capture under this
  feature — any implementation here should be opt-in and clearly
  disclosed).
