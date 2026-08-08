"""Chunk + embed dictations and meeting notes into the search index.

Two source types, both already have clean structured readers elsewhere
in the codebase:
  - dictations: TranscriptLog.list_entries() (src/transcript_log.py)
  - meetings:   MeetingManager.list_sessions() (src/meeting/session.py)

Re-indexing is incremental: each source's full text is hashed, and a
source is only re-chunked/re-embedded if its hash changed since the
last index run (tracked in the `sources` table).
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
import sqlite_vec

from src.config import CONFIG
from src.search.db import connect

OLLAMA_EMBED_MODEL = "nomic-embed-text"
CHUNK_MAX_WORDS = 400


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embed(text: str) -> List[float]:
    resp = requests.post(
        f"{CONFIG.ollama_url}/api/embeddings",
        json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _chunk_text(text: str, max_words: int = CHUNK_MAX_WORDS) -> List[str]:
    """Greedily group paragraphs into ~max_words-sized chunks."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_words = 0
    for para in paragraphs:
        words = len(para.split())
        if current and current_words + words > max_words:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(para)
        current_words += words
    if current:
        chunks.append("\n\n".join(current))
    if not chunks and text.strip():
        chunks = [text.strip()]
    return chunks


def _dictation_sources() -> List[Dict[str, Any]]:
    from src.transcript_log import TranscriptLog

    log = TranscriptLog(CONFIG.data_dir)
    sources = []
    for entry in log.list_entries():
        sources.append({
            "source_type": "dictation",
            "source_id": entry["timestamp"],
            "source_title": f"Dictation @ {entry['time']}",
            "source_date": entry["date"],
            "text": entry["text"],
        })
    return sources


def _meeting_sources() -> List[Dict[str, Any]]:
    from src.meeting.session import MeetingManager

    manager = MeetingManager()
    sources = []
    for session in manager.list_sessions():
        parts = []
        if session.summary:
            parts.append(f"Summary:\n{session.summary}")
        if session.notes:
            parts.append("Notes:\n" + "\n".join(
                f"- {n.text}" for n in session.notes
            ))
        if session.transcript_segments:
            parts.append("Transcript:\n" + "\n".join(
                seg.get("text", "") for seg in session.transcript_segments
            ))
        text = "\n\n".join(parts).strip()
        if not text:
            continue
        sources.append({
            "source_type": "meeting",
            "source_id": session.id,
            "source_title": session.title,
            "source_date": session.started_at.strftime("%Y-%m-%d"),
            "text": text,
        })
    return sources


def index_all() -> Dict[str, int]:
    """Re-index anything new/changed. Returns {"indexed": n, "skipped": n, "total_chunks": n}."""
    db = connect()
    indexed = skipped = total_chunks = 0

    all_sources = _dictation_sources() + _meeting_sources()

    for src in all_sources:
        content_hash = _hash(src["text"])
        row = db.execute(
            "SELECT content_hash FROM sources WHERE source_type = ? AND source_id = ?",
            (src["source_type"], src["source_id"]),
        ).fetchone()

        if row and row[0] == content_hash:
            skipped += 1
            continue

        # Remove stale chunks for this source before re-inserting.
        old_ids = [r[0] for r in db.execute(
            "SELECT id FROM chunks WHERE source_type = ? AND source_id = ?",
            (src["source_type"], src["source_id"]),
        ).fetchall()]
        for old_id in old_ids:
            db.execute("DELETE FROM chunks_fts WHERE rowid = ?", (old_id,))
            db.execute("DELETE FROM chunks_vec WHERE rowid = ?", (old_id,))
        db.execute(
            "DELETE FROM chunks WHERE source_type = ? AND source_id = ?",
            (src["source_type"], src["source_id"]),
        )

        chunks = _chunk_text(src["text"])
        for i, chunk in enumerate(chunks):
            embedding = _embed(chunk)
            cur = db.execute(
                "INSERT INTO chunks (source_type, source_id, source_title, source_date, chunk_index, chunk_text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (src["source_type"], src["source_id"], src["source_title"], src["source_date"], i, chunk),
            )
            chunk_id = cur.lastrowid
            db.execute("INSERT INTO chunks_fts (rowid, chunk_text) VALUES (?, ?)", (chunk_id, chunk))
            db.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (chunk_id, sqlite_vec.serialize_float32(embedding)),
            )
            total_chunks += 1

        db.execute(
            "INSERT INTO sources (source_type, source_id, content_hash, indexed_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(source_type, source_id) DO UPDATE SET content_hash = excluded.content_hash, "
            "indexed_at = excluded.indexed_at",
            (src["source_type"], src["source_id"], content_hash, datetime.now(timezone.utc).isoformat()),
        )
        indexed += 1

    db.commit()
    db.close()
    return {"indexed": indexed, "skipped": skipped, "total_chunks": total_chunks}
