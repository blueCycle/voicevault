"""Local HTTP API for the Electron notes dashboard.

Runs inside the VoiceVault menu bar app process (see src/app.py), bound
to 127.0.0.1 only — this is a single-user local tool, not a service
meant to be reachable from the network. CORS is wide open because the
only client is the Electron app's file:// renderer (Origin: null) and
a localhost dev server; the loopback bind is the actual security
boundary, not CORS.
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

DEFAULT_PORT = 8765

app = FastAPI(title="VoiceVault Notes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    k: int = 6


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dictations")
def list_dictations():
    from src.config import CONFIG
    from src.transcript_log import TranscriptLog

    log = TranscriptLog(CONFIG.data_dir)
    return log.list_entries()


@app.get("/meetings")
def list_meetings():
    from src.meeting.session import MeetingManager

    manager = MeetingManager()
    sessions = manager.list_sessions()
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return [s.to_dict() for s in sessions]


@app.get("/search")
def search(q: str, k: int = 8):
    from src.search.query import hybrid_search

    return hybrid_search(q, k=k)


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    from src.search.query import ask

    return ask(req.question, k=req.k)


@app.post("/ask/stream")
def ask_stream_endpoint(req: AskRequest):
    from src.search.query import ask_stream

    def gen():
        for event in ask_stream(req.question, k=req.k):
            yield json.dumps(event) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/reindex")
def reindex():
    from src.search.indexer import index_all

    return index_all()


def run(port: int = DEFAULT_PORT):
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
