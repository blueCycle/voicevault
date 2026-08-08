"""Native app dashboard: browse past meetings and dictations.

A normal (titled, resizable, closable) NSWindow with a master-detail
layout — a table of past meetings + dictations on the left, and the
full text (summary/notes/transcript, or dictation text) on the right.

Unlike the floating dictation pill (`floating_panel.py`), this window
has no animation loop: it's built lazily on first `show()`, reloads
its data on every `show()`/Refresh click, and survives being closed
(the red button hides it — `setReleasedWhenClosed_(False)` — rather
than deallocating it) so re-opening is instant.
"""

from __future__ import annotations

import subprocess
from datetime import date
from typing import Any, Dict, List, Optional

from AppKit import (
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTextView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSIndexSet, NSObject

SECTION_HEADER_HEIGHT = 24.0
DAY_HEADER_HEIGHT = 18.0
ENTRY_ROW_HEIGHT = 28.0
DICTATION_PREVIEW_CHARS = 90


def _day_group_label(iso_timestamp: str) -> str:
    """Wispr-Flow-style day grouping: TODAY / YESTERDAY / weekday+date."""
    entry_date = date.fromisoformat(iso_timestamp[:10])
    delta_days = (date.today() - entry_date).days
    if delta_days == 0:
        return "TODAY"
    if delta_days == 1:
        return "YESTERDAY"
    return entry_date.strftime("%A, %B %d").upper()

WINDOW_WIDTH = 900.0
WINDOW_HEIGHT = 560.0
SIDEBAR_WIDTH = 360.0
BUTTON_BAR_HEIGHT = 36.0


def _format_meeting_detail(session) -> str:
    date_str = session.started_at.strftime("%Y-%m-%d %H:%M")
    duration_mins = int(session.duration / 60)
    lines = [session.title, f"{date_str}  |  {duration_mins} min", ""]

    if session.summary:
        lines += ["## Summary", session.summary, ""]

    if session.notes:
        lines.append("## My Notes")
        for note in session.notes:
            tag = f"[{note.tag}] " if note.tag else ""
            lines.append(f"{note.formatted_time}  {tag}{note.text}")
        lines.append("")

    if session.transcript_segments:
        lines.append("## Transcript")
        for seg in session.transcript_segments:
            mins, secs = divmod(int(seg.get("start", 0)), 60)
            lines.append(f"[{mins}:{secs:02d}] {seg.get('text', '')}")

    return "\n".join(lines)


def _format_dictation_detail(entry: Dict[str, Any]) -> str:
    return f"{entry['label']}  —  {entry['date']} {entry['time']}\n\n{entry['text']}"


class _TableDataSource(NSObject):
    """NSTableViewDataSource + delegate: backs the row list and drives
    detail-pane updates on selection change.

    Constructed via plain `alloc().init()`; `_dashboard` is set as a
    normal attribute afterward (see `DashboardWindow._build_window`) to
    avoid overriding NSObject's `init`.
    """

    def numberOfRowsInTableView_(self, table_view) -> int:
        return len(self._dashboard.rows)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row: int):
        return self._dashboard.rows[row]["row_title"]

    def tableView_shouldSelectRow_(self, table_view, row: int) -> bool:
        return not self._dashboard.rows[row]["is_header"]

    def tableView_heightOfRow_(self, table_view, row: int) -> float:
        r = self._dashboard.rows[row]
        if not r["is_header"]:
            return ENTRY_ROW_HEIGHT
        return SECTION_HEADER_HEIGHT if r["header_kind"] == "section" else DAY_HEADER_HEIGHT

    def tableView_willDisplayCell_forTableColumn_row_(self, table_view, cell, column, row: int) -> None:
        r = self._dashboard.rows[row]
        if not r["is_header"]:
            cell.setFont_(NSFont.systemFontOfSize_(13))
            cell.setTextColor_(NSColor.labelColor())
        elif r["header_kind"] == "section":
            cell.setFont_(NSFont.boldSystemFontOfSize_(12))
            cell.setTextColor_(NSColor.labelColor())
        else:
            cell.setFont_(NSFont.boldSystemFontOfSize_(10))
            cell.setTextColor_(NSColor.secondaryLabelColor())

    def tableViewSelectionDidChange_(self, notification) -> None:
        self._dashboard.on_selection_changed()

    def refreshClicked_(self, sender) -> None:
        self._dashboard._reload_entries()

    def openVaultClicked_(self, sender) -> None:
        self._dashboard.open_vault_folder()


class DashboardWindow:
    """Lazily-built native window listing past meetings and dictations."""

    def __init__(self, meeting_manager, transcript_log):
        self._meeting_manager = meeting_manager
        self._transcript_log = transcript_log

        self._window: Optional[NSWindow] = None
        self._table_view: Optional[NSTableView] = None
        self._detail_view: Optional[NSTextView] = None
        self._data_source: Optional[_TableDataSource] = None

        # `rows` is what the table actually renders: day-group header rows
        # interleaved with entry rows (Wispr-Flow-style "TODAY" grouping).
        self.rows: List[Dict[str, Any]] = []

    # -- Public surface --------------------------------------------------

    def show(self) -> None:
        if self._window is None:
            self._build_window()
        self._reload_entries()
        self._window.makeKeyAndOrderFront_(None)

    # -- Data loading ------------------------------------------------------

    def _reload_entries(self) -> None:
        meetings: List[Dict[str, Any]] = []
        for session in self._meeting_manager.list_sessions():
            duration_mins = int(session.duration / 60)
            meetings.append({
                "timestamp": session.started_at.isoformat(),
                "row_title": f"{session.title}  ({duration_mins}m)",
                "detail": _format_meeting_detail(session),
            })

        dictations: List[Dict[str, Any]] = []
        for entry in self._transcript_log.list_entries():
            preview = " ".join(entry["text"].split())
            if len(preview) > DICTATION_PREVIEW_CHARS:
                preview = preview[:DICTATION_PREVIEW_CHARS].rstrip() + "…"
            dictations.append({
                "timestamp": f"{entry['date']}T{entry['time']}",
                "row_title": f"{preview}  ({entry['time']})",
                "detail": _format_dictation_detail(entry),
            })

        # Both lists already come pre-sorted newest-first from their source
        # (MeetingManager.list_sessions / TranscriptLog.list_entries).
        rows: List[Dict[str, Any]] = []

        if meetings:
            rows.append({"is_header": True, "header_kind": "section", "row_title": "MEETINGS"})
            for e in meetings:
                rows.append({"is_header": False, **e})

        if dictations:
            rows.append({"is_header": True, "header_kind": "section", "row_title": "DICTATIONS"})
            last_group = None
            for e in dictations:
                group = _day_group_label(e["timestamp"])
                if group != last_group:
                    rows.append({"is_header": True, "header_kind": "day", "row_title": f"  {group}"})
                    last_group = group
                rows.append({"is_header": False, **e})

        self.rows = rows

        if self._table_view is not None:
            self._table_view.reloadData()
        if self._detail_view is not None:
            first_entry = next((r for r in rows if not r["is_header"]), None)
            self._detail_view.setString_(
                first_entry["detail"] if first_entry else "No meetings or dictations yet."
            )
            if first_entry is not None and self._table_view is not None:
                self._table_view.selectRowIndexes_byExtendingSelection_(
                    NSIndexSet.indexSetWithIndex_(rows.index(first_entry)), False
                )

    def on_selection_changed(self) -> None:
        row = self._table_view.selectedRow()
        if 0 <= row < len(self.rows) and not self.rows[row]["is_header"]:
            self._detail_view.setString_(self.rows[row]["detail"])

    # -- Window construction ------------------------------------------------

    def _build_window(self) -> None:
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 200, WINDOW_WIDTH, WINDOW_HEIGHT),
            style,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("VoiceVault Dashboard")
        win.setReleasedWhenClosed_(False)
        win.setMinSize_((640, 400))

        content = win.contentView()

        # Left: table of past meetings/dictations
        table_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, BUTTON_BAR_HEIGHT, SIDEBAR_WIDTH, WINDOW_HEIGHT - BUTTON_BAR_HEIGHT)
        )
        table_scroll.setHasVerticalScroller_(True)
        table_scroll.setAutoresizingMask_(16)  # NSViewHeightSizable

        table = NSTableView.alloc().init()
        column = NSTableColumn.alloc().initWithIdentifier_("title")
        column.setWidth_(SIDEBAR_WIDTH - 20)
        column.headerCell().setStringValue_("Meetings & Dictations")
        table.addTableColumn_(column)
        table.setHeaderView_(table.headerView())
        table.setRowHeight_(28.0)

        data_source = _TableDataSource.alloc().init()
        data_source._dashboard = self
        table.setDataSource_(data_source)
        table.setDelegate_(data_source)
        self._data_source = data_source  # keep a strong Python ref

        table_scroll.setDocumentView_(table)
        content.addSubview_(table_scroll)
        self._table_view = table

        # Right: detail text view
        detail_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(SIDEBAR_WIDTH, BUTTON_BAR_HEIGHT, WINDOW_WIDTH - SIDEBAR_WIDTH, WINDOW_HEIGHT - BUTTON_BAR_HEIGHT)
        )
        detail_scroll.setHasVerticalScroller_(True)
        detail_scroll.setAutoresizingMask_(2 | 16)  # WidthSizable | HeightSizable

        detail = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, WINDOW_WIDTH - SIDEBAR_WIDTH, WINDOW_HEIGHT - BUTTON_BAR_HEIGHT)
        )
        detail.setEditable_(False)
        detail.setFont_(NSFont.systemFontOfSize_(13))
        detail_scroll.setDocumentView_(detail)
        content.addSubview_(detail_scroll)
        self._detail_view = detail

        # Bottom button bar
        refresh_btn = NSButton.alloc().initWithFrame_(NSMakeRect(8, 4, 90, 28))
        refresh_btn.setTitle_("Refresh")
        refresh_btn.setBezelStyle_(1)  # NSBezelStyleRounded
        refresh_btn.setTarget_(self._data_source)
        refresh_btn.setAction_("refreshClicked:")
        content.addSubview_(refresh_btn)

        vault_btn = NSButton.alloc().initWithFrame_(NSMakeRect(104, 4, 140, 28))
        vault_btn.setTitle_("Open Vault Folder")
        vault_btn.setBezelStyle_(1)
        vault_btn.setTarget_(self._data_source)
        vault_btn.setAction_("openVaultClicked:")
        content.addSubview_(vault_btn)

        self._window = win

    # -- Button actions (invoked via the data source's target/action) ----

    def open_vault_folder(self) -> None:
        from src.config import CONFIG
        if CONFIG.obsidian_vault and CONFIG.obsidian_vault.exists():
            subprocess.run(["open", str(CONFIG.obsidian_vault)])
