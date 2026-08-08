"""Unit tests for the recently added features.

Uses stdlib `unittest` only. Runs without rumps / pynput / mlx-whisper
so it's safe to execute in CI.

Covers:
- src.transcript_log.TranscriptLog.append / todays_file
- VoiceVaultApp._build_initial_prompt (without instantiating rumps)

NOTE: _build_initial_prompt is not implemented — see
docs/DICTATION_CONTEXT_PROMPT.md for why it was deferred.
BuildInitialPromptTests below is expected to fail (AttributeError)
until that's revisited.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.transcript_log import TranscriptLog  # noqa: E402
from src.config import CONFIG  # noqa: E402

# Imported lazily inside cases that need it; avoids ModelKit/PyObjC side
# effects at collection time.
SRC_APP = ROOT / "src" / "app.py"


class TranscriptLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._root = Path(self._tmp.name)
        self._log = TranscriptLog(self._root)

    def test_log_dir_is_created(self):
        self.assertTrue(self._log.log_dir.exists())

    def test_todays_file_uses_yyyy_mm_dd(self):
        expected = self._log.log_dir / f"transcripts_{datetime.now():%Y-%m-%d}.md"
        self.assertEqual(self._log.todays_file(), expected)

    def test_append_returns_path_and_writes_markdown(self):
        path = self._log.append("Hello, world.")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        body = path.read_text(encoding="utf-8")
        self.assertIn("# Dictation log —", body)
        self.assertIn("Hello, world.", body)
        self.assertIn("## Dictation @", body)

    def test_append_empty_text_returns_none(self):
        self.assertIsNone(self._log.append(""))
        self.assertIsNone(self._log.append("    "))
        # No file should have been created.
        self.assertFalse(self._log.todays_file().exists())

    def test_multiple_appends_keep_growing(self):
        self._log.append("First.")
        self._log.append("Second.")
        body = self._log.todays_file().read_text(encoding="utf-8")
        self.assertIn("First.", body)
        self.assertIn("Second.", body)
        # Heading appears once, not per append.
        self.assertEqual(body.count("# Dictation log —"), 1)

    def test_concurrent_appends_do_not_corrupt(self):
        import threading
        def worker(i: int):
            self._log.append(f"entry {i}")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        body = self._log.todays_file().read_text(encoding="utf-8")
        for i in range(20):
            self.assertIn(f"entry {i}", body)


class BuildInitialPromptTests(unittest.TestCase):
    """Exercise `_build_initial_prompt` without instantiating rumps.App."""

    def setUp(self) -> None:
        # Bypass `__init__` so we don't trigger pynput/rumps setup.
        from src.app import VoiceVaultApp
        self._cls = VoiceVaultApp
        self._app = VoiceVaultApp.__new__(VoiceVaultApp)
        self._app._dictation_injected_text = ""
        # Snapshot/restore CONFIG.initial_prompt around the case
        self._orig = CONFIG.initial_prompt
        self.addCleanup(lambda: setattr(CONFIG, "initial_prompt", self._orig))

    def test_empty_when_no_prompt_no_text(self):
        CONFIG.initial_prompt = ""
        self._app._dictation_injected_text = ""
        self.assertEqual(self._cls._build_initial_prompt(self._app), "")

    def test_only_user_prompt(self):
        CONFIG.initial_prompt = "Names: John Smith."
        self._app._dictation_injected_text = ""
        self.assertEqual(
            self._cls._build_initial_prompt(self._app),
            "Names: John Smith.",
        )

    def test_only_tail(self):
        CONFIG.initial_prompt = ""
        self._app._dictation_injected_text = "this is the trailing context"
        self.assertEqual(
            self._cls._build_initial_prompt(self._app),
            "this is the trailing context",
        )

    def test_combined_reverse_order(self):
        CONFIG.initial_prompt = "Names: John."
        self._app._dictation_injected_text = "tail context"
        result = self._cls._build_initial_prompt(self._app)
        self.assertIn("Names: John.", result)
        self.assertIn("tail context", result)
        # User prompt is prepended so Whisper sees glossary first.
        self.assertTrue(result.startswith("Names: John."))

    def test_long_tail_truncated_to_500_chars(self):
        CONFIG.initial_prompt = ""
        self._app._dictation_injected_text = "x" * 5000
        result = self._cls._build_initial_prompt(self._app)
        # Tail in result should be the last 500 chars of the input.
        self.assertEqual(len(result), 500)
        self.assertEqual(result, "x" * 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
