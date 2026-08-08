"""Hybrid (semantic + keyword) search and RAG chat over the notes index."""

import re
from typing import Any, Dict, Generator, List

import requests
import sqlite_vec

from src.config import CONFIG
from src.search.db import connect
from src.search.indexer import _embed

RRF_K = 60  # reciprocal rank fusion constant (standard default)


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 MATCH query (avoids syntax errors
    from user input containing FTS5 operators like AND/OR/NOT/- etc)."""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def hybrid_search(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """Combine vector similarity and keyword search via reciprocal rank fusion."""
    db = connect()
    try:
        query_embedding = _embed(query)

        vec_rows = db.execute(
            "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (sqlite_vec.serialize_float32(query_embedding), k * 3),
        ).fetchall()

        fts_rows = db.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (_fts_query(query), k * 3),
        ).fetchall()

        scores: Dict[int, float] = {}
        for rank, (rowid,) in enumerate(vec_rows):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (RRF_K + rank)
        for rank, (rowid,) in enumerate(fts_rows):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (RRF_K + rank)

        ranked_ids = sorted(scores, key=lambda rid: scores[rid], reverse=True)[:k]

        results = []
        for chunk_id in ranked_ids:
            row = db.execute(
                "SELECT source_type, source_id, source_title, source_date, chunk_text "
                "FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            if row:
                results.append({
                    "chunk_id": chunk_id,
                    "source_type": row[0],
                    "source_id": row[1],
                    "source_title": row[2],
                    "source_date": row[3],
                    "chunk_text": row[4],
                    "score": scores[chunk_id],
                })
        return results
    finally:
        db.close()


def _build_prompt(question: str, results: List[Dict[str, Any]]) -> str:
    context = "\n\n---\n\n".join(
        f"[{r['source_title']} ({r['source_date']})]\n{r['chunk_text']}"
        for r in results
    )
    return f"""Answer the question using ONLY the notes below. If the notes don't \
contain the answer, say so plainly — don't make anything up. When you use a \
note, mention which one by its title in parentheses, e.g. (Standup @ 09:15).

NOTES:
{context}

QUESTION: {question}

ANSWER:"""


def ask(question: str, k: int = 6) -> Dict[str, Any]:
    """Non-streaming RAG answer with cited sources."""
    results = hybrid_search(question, k=k)
    prompt = _build_prompt(question, results)
    resp = requests.post(
        f"{CONFIG.ollama_url}/api/generate",
        json={"model": CONFIG.ollama_model, "prompt": prompt, "stream": False},
        timeout=90,
    )
    resp.raise_for_status()
    answer = resp.json().get("response", "").strip()
    return {"answer": answer, "sources": results}


def ask_stream(question: str, k: int = 6) -> Generator[Dict[str, Any], None, None]:
    """Streaming RAG answer. Yields {"sources": [...]} once, then
    {"delta": "..."} per token chunk, then {"done": True}."""
    results = hybrid_search(question, k=k)
    yield {"sources": results}

    prompt = _build_prompt(question, results)
    resp = requests.post(
        f"{CONFIG.ollama_url}/api/generate",
        json={"model": CONFIG.ollama_model, "prompt": prompt, "stream": True},
        timeout=90,
        stream=True,
    )
    resp.raise_for_status()
    import json as _json
    for line in resp.iter_lines():
        if not line:
            continue
        data = _json.loads(line)
        if data.get("response"):
            yield {"delta": data["response"]}
        if data.get("done"):
            break
    yield {"done": True}
