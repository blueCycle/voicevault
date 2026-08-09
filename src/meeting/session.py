from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import json
import threading
from src.config import CONFIG
from src.audio.recorder import AudioRecorder
from src.transcription.engine import ENGINE
from src.obsidian.exporter import ObsidianExporter


@dataclass
class MeetingNote:
    """A user note taken during a meeting with timestamp."""
    timestamp: float  # seconds from meeting start
    text: str
    tag: Optional[str] = None  # e.g., "action", "decision", "question"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "text": self.text,
            "tag": self.tag,
            "formatted_time": str(timedelta(seconds=int(self.timestamp)))
        }


@dataclass
class MeetingSession:
    """A complete meeting recording session."""
    id: str
    title: str
    started_at: datetime
    audio_path: Optional[Path] = None
    transcript_segments: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[MeetingNote] = field(default_factory=list)
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    
    @property
    def duration(self) -> float:
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "transcript_segments": self.transcript_segments,
            "notes": [n.to_dict() for n in self.notes],
            "summary": self.summary
        }
    
    def save(self) -> Path:
        """Save session metadata to JSON."""
        path = CONFIG.notes_dir / f"{self.id}.json"
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return path


class MeetingManager:
    """Manages meeting recording sessions."""
    
    def __init__(self):
        self._current_session: Optional[MeetingSession] = None
        self._recorder = AudioRecorder()
        self._exporter = ObsidianExporter()
        
    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording
    
    @property
    def current_session(self) -> Optional[MeetingSession]:
        return self._current_session
    
    def start(self, title: str) -> MeetingSession:
        """Start a new meeting recording session."""
        if self.is_recording:
            raise RuntimeError("Already recording a meeting")
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_session = MeetingSession(
            id=session_id,
            title=title,
            started_at=datetime.now()
        )
        
        audio_path = self._recorder.start(title=title)
        self._current_session.audio_path = audio_path
        
        print(f"[Meeting] Started: {title}")
        return self._current_session
    
    def add_note(self, text: str, tag: Optional[str] = None) -> MeetingNote:
        """Add a note during the meeting."""
        if not self._current_session or not self.is_recording:
            raise RuntimeError("No active meeting")
        
        note = MeetingNote(
            timestamp=self._recorder.duration,
            text=text,
            tag=tag
        )
        self._current_session.notes.append(note)
        print(f"[Meeting] Note at {note.formatted_time}: {text[:50]}...")
        return note
    
    def stop(self) -> MeetingSession:
        """Stop recording and process the meeting."""
        if not self.is_recording or not self._current_session:
            raise RuntimeError("No active meeting")
        
        # Stop recording
        audio_path = self._recorder.stop()
        self._current_session.ended_at = datetime.now()
        
        # Transcribe with timestamps
        print("[Meeting] Transcribing...")
        self._current_session.transcript_segments = ENGINE.transcribe_file_with_timestamps(audio_path)

        # If the user left the title as the dialog's placeholder, infer a
        # real one from the transcript instead of shipping "Meeting" to
        # the Obsidian vault. An explicit user-provided title is left alone.
        self._infer_title()

        # Save raw session
        self._current_session.save()
        
        # Generate summary via Ollama if enabled
        if CONFIG.summarize_meetings:
            self._summarize()
        
        # Export to Obsidian
        self._exporter.export_meeting(self._current_session)
        
        session = self._current_session
        self._current_session = None
        
        print(f"[Meeting] Complete: {session.title} ({session.duration:.0f}s)")
        return session
    
    _PLACEHOLDER_TITLES = {"meeting", "untitled meeting"}

    def _infer_title(self):
        """Ask the local LLM for a concise title when the user left the
        Start Meeting dialog's placeholder unchanged."""
        if self._current_session.title.strip().lower() not in self._PLACEHOLDER_TITLES:
            return  # user typed an explicit title — respect it
        if not self._current_session.transcript_segments:
            return
        try:
            import requests

            transcript_text = " ".join(
                s["text"] for s in self._current_session.transcript_segments
            )[:4000]
            prompt = (
                "Give a concise 3-6 word title for this meeting based on the "
                "transcript below. Respond with only the title — no quotes, "
                "no punctuation, no preamble.\n\n"
                f"TRANSCRIPT:\n{transcript_text}"
            )
            response = requests.post(
                f"{CONFIG.ollama_url}/api/generate",
                json={"model": CONFIG.ollama_model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            if response.status_code == 200:
                title = response.json().get("response", "").strip().strip('"').strip()
                if title:
                    self._current_session.title = title
                    print(f"[Meeting] Inferred title: {title}")
        except Exception as e:
            print(f"[Meeting] Title inference failed: {e}")

    def _summarize(self):
        """Generate meeting summary via Ollama."""
        try:
            import requests
            
            transcript_text = "\n".join([
                f"[{s['start']:.1f}s] {s['text']}"
                for s in self._current_session.transcript_segments
            ])
            
            notes_text = "\n".join([
                f"[{n.formatted_time}] {n.tag or 'note'}: {n.text}"
                for n in self._current_session.notes
            ])
            
            prompt = f"""Summarize this meeting. Provide:
1. A brief summary (2-3 sentences)
2. Key discussion points
3. Action items (if any)
4. Decisions made

TRANSCRIPT:
{transcript_text}

USER NOTES:
{notes_text}
"""
            
            response = requests.post(
                f"{CONFIG.ollama_url}/api/generate",
                json={
                    "model": CONFIG.ollama_model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120
            )
            
            if response.status_code == 200:
                self._current_session.summary = response.json().get("response", "")
                print("[Meeting] Summary generated")
            else:
                print(f"[Meeting] Summary failed: {response.status_code}")
                
        except Exception as e:
            print(f"[Meeting] Summary error: {e}")
    
    def list_sessions(self) -> List[MeetingSession]:
        """List all saved meeting sessions."""
        sessions = []
        for path in CONFIG.notes_dir.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                session = MeetingSession(
                    id=data["id"],
                    title=data["title"],
                    started_at=datetime.fromisoformat(data["started_at"]),
                    ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
                    audio_path=Path(data["audio_path"]) if data.get("audio_path") else None,
                    transcript_segments=data.get("transcript_segments", []),
                    # MeetingNote.to_dict() adds a computed "formatted_time"
                    # field that the constructor doesn't accept — pick only
                    # the real fields back out rather than **n.
                    notes=[
                        MeetingNote(timestamp=n["timestamp"], text=n["text"], tag=n.get("tag"))
                        for n in data.get("notes", [])
                    ],
                    summary=data.get("summary")
                )
                sessions.append(session)
            except Exception as e:
                print(f"[Meeting] Skipping unreadable session file {path.name}: {e}")

        return sorted(sessions, key=lambda s: s.started_at, reverse=True)
