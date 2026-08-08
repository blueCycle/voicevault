"""SQLite + sqlite-vec storage for the notes-search index.

Uses pysqlite3 instead of the stdlib sqlite3 module because most
prebuilt Python interpreters (including the one this repo was
developed against) ship without loadable-extension support, which
sqlite-vec requires. See requirements.txt / scripts/setup.sh for how
pysqlite3 gets built with that support enabled.
"""

from pathlib import Path

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3  # falls back to stdlib; load_index() will raise clearly

import sqlite_vec

EMBEDDING_DIMS = 768  # nomic-embed-text


def _db_path() -> Path:
    from src.config import CONFIG
    return CONFIG.data_dir / "search_index.sqlite3"


def connect() -> "sqlite3.Connection":
    """Open the search index DB, creating schema and loading sqlite-vec."""
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))

    if not hasattr(db, "enable_load_extension"):
        raise RuntimeError(
            "This Python's sqlite3 has no loadable-extension support and "
            "pysqlite3 isn't installed. Notes search is unavailable — see "
            "scripts/setup.sh for how to install pysqlite3."
        )

    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    _ensure_schema(db)
    return db


def _ensure_schema(db: "sqlite3.Connection") -> None:
    db.executescript(f"""
        CREATE TABLE IF NOT EXISTS sources (
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            PRIMARY KEY (source_type, source_id)
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,   -- 'dictation' | 'meeting'
            source_id TEXT NOT NULL,     -- dictation: "YYYY-MM-DD HH:MM:SS", meeting: session id
            source_title TEXT,
            source_date TEXT,            -- YYYY-MM-DD, for display/sort
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_source
            ON chunks(source_type, source_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_text
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
            embedding float[{EMBEDDING_DIMS}]
        );
    """)
    db.commit()
