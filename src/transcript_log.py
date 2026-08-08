"""Daily transcript log for completed dictations.

Each completed dictation (i.e. on `_stop_dictation` after the final
flush) is appended as a timestamped section to:

    data/log/transcripts_YYYY-MM-DD.md

Files are simple Markdown so they can be opened in any editor or
Obsidian without a special viewer. The log is a free-form running
history — auditable, searchable with `ripgrep` / VS Code search, and
useful when you dictated into the wrong field and want to recover
yesterday's words.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_ENTRY_HEADER_RE = re.compile(r"^## (.+) @ (\d{2}:\d{2}:\d{2})$", re.MULTILINE)


class TranscriptLog:
    """Append-only, day-rolled Markdown log of finished dictations."""

    def __init__(self, root: Path):
        self._log_dir = Path(root) / "log"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def todays_file(self) -> Path:
        return self._log_dir / f"transcripts_{datetime.now():%Y-%m-%d}.md"

    def append(self, text: str, *, label: str = "Dictation") -> Path | None:
        """Append a finished dictation. Returns the path written, or None
        when the input was empty."""
        text = (text or "").strip()
        if not text:
            return None
        stamp = datetime.now().strftime("%H:%M:%S")
        path = self.todays_file()
        # First entry of the day: a Markdown H1 date header
        is_new_file = not path.exists()
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(f"# Dictation log — {datetime.now():%Y-%m-%d}\n\n")
                f.write(f"## {label} @ {stamp}\n\n")
                f.write(text)
                f.write("\n\n")
        return path

    def list_entries(self) -> List[Dict[str, Any]]:
        """Parse every daily log file into individual entries, newest first."""
        entries: List[Dict[str, Any]] = []
        for path in self._log_dir.glob("transcripts_*.md"):
            date_str = path.stem.removeprefix("transcripts_")
            text = path.read_text(encoding="utf-8")
            matches = list(_ENTRY_HEADER_RE.finditer(text))
            for i, m in enumerate(matches):
                label, time_str = m.group(1), m.group(2)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                entries.append({
                    "date": date_str,
                    "time": time_str,
                    "label": label,
                    "text": text[start:end].strip(),
                    "timestamp": f"{date_str} {time_str}",
                })
        entries.sort(key=lambda e: e["timestamp"], reverse=True)
        return entries
