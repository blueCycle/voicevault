from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from src.config import CONFIG

if TYPE_CHECKING:
    from src.meeting.session import MeetingSession


class ObsidianExporter:
    """Export meeting sessions to Obsidian-compatible Markdown files."""
    
    def export_meeting(self, session: "MeetingSession") -> Optional[Path]:
        """Export a meeting session to Obsidian vault.
        
        Creates a Markdown file with YAML frontmatter, transcript timeline,
        user notes, and summary.
        """
        if not CONFIG.obsidian_vault:
            print("[Obsidian] No vault configured, skipping export")
            return None
        
        if not CONFIG.obsidian_vault.exists():
            CONFIG.obsidian_vault.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        date_str = session.started_at.strftime("%Y-%m-%d")
        time_str = session.started_at.strftime("%H:%M")
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in session.title)
        filename = f"{date_str} {time_str} {safe_title}.md"
        filepath = CONFIG.obsidian_vault / filename
        
        # Build markdown content
        content = self._build_markdown(session)
        
        with open(filepath, 'w') as f:
            f.write(content)
        
        print(f"[Obsidian] Exported: {filepath}")
        return filepath
    
    def _build_markdown(self, session: "MeetingSession") -> str:
        """Build Obsidian markdown with YAML frontmatter."""
        date_str = session.started_at.strftime("%Y-%m-%d")
        time_str = session.started_at.strftime("%H:%M")
        duration_mins = int(session.duration / 60)
        
        # YAML frontmatter
        frontmatter = f"""---
id: {session.id}
title: {session.title}
date: {date_str}
time: {time_str}
duration: {duration_mins}min
type: meeting
recording: {session.audio_path.name if session.audio_path else 'none'}
---

# {session.title}

*Date: {date_str} at {time_str} | Duration: {duration_mins} minutes*

"""
        
        # Summary section
        if session.summary:
            frontmatter += f"""## Summary

{session.summary}

---

"""
        
        # User notes section
        if session.notes:
            frontmatter += """## My Notes

| Time | Tag | Note |
|------|-----|------|
"""
            for note in session.notes:
                tag = note.tag or "" 
                frontmatter += f"| {note.formatted_time} | {tag} | {note.text} |\n"
            
            frontmatter += "\n---\n\n"
        
        # Transcript section
        if session.transcript_segments:
            frontmatter += """## Transcript

"""
            for seg in session.transcript_segments:
                start_mins = int(seg['start'] / 60)
                start_secs = int(seg['start'] % 60)
                timestamp = f"{start_mins}:{start_secs:02d}"
                frontmatter += f"**[{timestamp}]** {seg['text']}\n\n"
        
        # Backlinks / tags
        frontmatter += f"""
---

#meeting #{date_str.replace('-', '')} #voicevault
"""
        
        return frontmatter


def export_all_meetings():
    """Export all saved meetings to Obsidian."""
    from src.meeting.session import MeetingManager
    manager = MeetingManager()
    exporter = ObsidianExporter()
    
    sessions = manager.list_sessions()
    for session in sessions:
        exporter.export_meeting(session)
    
    print(f"[Obsidian] Exported {len(sessions)} meetings")
