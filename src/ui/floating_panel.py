"""Wispr-Flow-style floating dictation pill.

A borderless NSWindow with vibrancy/blur, anchored near the bottom of
the main screen. Visible only while dictation is active. Animated
left-side waveform bars + rolling transcript text on the right.

Thread-safety
-------------
.show / .update_text / .dismiss may be invoked from any thread. State
is held behind a lock and applied on the main thread by a rumps.Timer
that fires while the application is running.

Lifecycle
---------
- show(initial_text): panel appears ~30ms later on the main thread
- update_text(text): ties into the streaming dictation deltas
- dismiss(): panel disappears on the next tick
- Quit-from-menubar kills the rumps.Timer, so the panel is GC'd with
  the app, matching Wispr Flow's "hotkey goes away when you quit"
  behavior.
"""

from __future__ import annotations

import math
import threading
from typing import List, Optional

import rumps
from PyObjCTools import AppHelper
from AppKit import (
    NSColor,
    NSFont,
    NSFontWeightSemibold,
    NSLineBreakByTruncatingTail,
    NSScreen,
    NSTextField,
    NSView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialHUDWindow,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowStyleMaskBorderless,
    NSFloatingWindowLevel,
    NSBackingStoreBuffered,
)
from Foundation import NSMakeRect

# Visuals
PANEL_WIDTH = 720.0
PANEL_HEIGHT = 80.0
PANEL_CORNER_RADIUS = 22.0
DOCK_CLEARANCE = 96.0            # points above the Dock
WAVE_BAR_COUNT = 5
WAVE_BAR_WIDTH = 4.0
WAVE_BAR_GAP = 4.0
WAVE_BAR_MIN_HEIGHT = 8.0
WAVE_BAR_MAX_HEIGHT = 44.0

# Animation
TICK_INTERVAL = 0.033            # ~30 fps when dictating


class DictationFloatPanel:
    """Main-thread-driven floating pill showing dictation state."""

    def __init__(self) -> None:
        self._window: Optional[NSWindow] = None
        self._text_field: Optional[NSTextField] = None
        self._status_field: Optional[NSTextField] = None
        self._wave_bars: List[NSView] = []
        self._tick_count: int = 0
        self._visible: bool = False
        self._pending_text: str = ""
        self._pending_mode: str = ""
        self._lock = threading.Lock()
        self._timer = None  # type: ignore[var-annotated]

    # -- Public surface (any thread) -----------------------------------

    def show(self, initial_text: str = "", mode: str = "Listening") -> None:
        with self._lock:
            self._visible = True
            self._pending_text = initial_text
            self._pending_mode = mode
        self._ensure_timer()

    def update_text(self, text: str) -> None:
        with self._lock:
            self._pending_text = text

    def update_mode(self, mode: str) -> None:
        """Update the top-left status caption (e.g. "Hands-free")."""
        with self._lock:
            self._pending_mode = mode

    def dismiss(self) -> None:
        with self._lock:
            self._visible = False
            self._pending_text = ""
            self._pending_mode = ""

    # -- Internal pump (main thread) -----------------------------------

    def _ensure_timer(self) -> None:
        # show() can be called from the pynput hotkey-listener thread (not
        # the app's main thread). Constructing the rumps.Timer there would
        # schedule its NSTimer on that thread's run loop instead of the
        # main one, so every tick — including NSWindow creation in
        # _build_window — would fire off-main-thread and crash. Dispatch
        # the actual construction onto the main thread via AppHelper.
        if self._timer is None:
            AppHelper.callAfter(self._create_timer)

    def _create_timer(self) -> None:
        if self._timer is None:
            self._timer = rumps.Timer(self._on_tick, TICK_INTERVAL)
            self._timer.start()

    def _on_tick(self, _sender) -> None:
        with self._lock:
            visible = self._visible
            text = self._pending_text
            mode = self._pending_mode

        if visible:
            if self._window is None:
                self._build_window()
            self._tick_count += 1
            # Animate waveform ~20 fps (every other tick)
            if self._tick_count % 2 == 0:
                self._animate_waveform()
            if self._text_field is not None and self._text_field.stringValue() != text:
                self._text_field.setStringValue_(text)
            if self._status_field is not None:
                target = f"\u25CF {mode.upper()}" if mode else "\u25CF LISTENING"
                if self._status_field.stringValue() != target:
                    self._status_field.setStringValue_(target)
        else:
            if self._window is not None:
                self._tear_down_window()

    # -- Window construction (main thread) -----------------------------

    def _panel_origin_in_screen(self) -> tuple[float, float]:
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - PANEL_WIDTH) / 2.0
        # NSWindow uses bottom-left origin; sit just above Dock
        y = DOCK_CLEARANCE
        return x, y

    def _build_window(self) -> None:
        x, y = self._panel_origin_in_screen()

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_screen_(
            NSMakeRect(x, y, PANEL_WIDTH, PANEL_HEIGHT),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
            NSScreen.mainScreen(),
        )
        win.setFrame_display_(win.frame(), False)
        win.setLevel_(NSFloatingWindowLevel + 1)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(True)
        win.setMovableByWindowBackground_(False)
        # Critical: clicks pass through to the app behind the panel
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        win.setCanHide_(False)

        # Vibrancy container
        visual = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        )
        visual.setMaterial_(NSVisualEffectMaterialHUDWindow)
        visual.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        visual.setState_(NSVisualEffectStateActive)
        visual.setWantsLayer_(True)
        visual.layer().setCornerRadius_(PANEL_CORNER_RADIUS)
        visual.layer().setMasksToBounds_(True)
        # resize with window
        visual.setAutoresizingMask_(2 | 16)  # NSViewWidthSizable | NSViewHeightSizable

        win.setContentView_(visual)

        # Left: waveform bars
        self._wave_bars = []
        bx = 16.0
        for i in range(WAVE_BAR_COUNT):
            bar_x = bx + i * (WAVE_BAR_WIDTH + WAVE_BAR_GAP)
            bar = NSView.alloc().initWithFrame_(
                NSMakeRect(bar_x, self._bar_y(WAVE_BAR_MIN_HEIGHT), WAVE_BAR_WIDTH, WAVE_BAR_MIN_HEIGHT)
            )
            bar.setWantsLayer_(True)
            bar.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
            bar.layer().setCornerRadius_(2.0)
            visual.addSubview_(bar)
            self._wave_bars.append(bar)

        # Top: small "LISTENING" status caption
        status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(60.0, PANEL_HEIGHT - 22.0, 200.0, 16.0)
        )
        status.setFont_(NSFont.systemFontOfSize_weight_(10, NSFontWeightSemibold))
        status.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.6))
        status.setStringValue_("\u25CF LISTENING")
        status.setBezeled_(False)
        status.setDrawsBackground_(False)
        status.setEditable_(False)
        status.setSelectable_(False)
        visual.addSubview_(status)
        self._status_field = status

        # Center/bottom: rolling transcript text
        text_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(60.0, 8.0, PANEL_WIDTH - 80.0, PANEL_HEIGHT - 40.0)
        )
        text_field.setFont_(NSFont.systemFontOfSize_(20))
        text_field.setTextColor_(NSColor.whiteColor())
        text_field.setBezeled_(False)
        text_field.setDrawsBackground_(False)
        text_field.setEditable_(False)
        text_field.setSelectable_(False)
        text_field.setLineBreakMode_(NSLineBreakByTruncatingTail)
        text_field.setStringValue_("")
        text_field.setAutoresizingMask_(2 | 16)
        visual.addSubview_(text_field)
        self._text_field = text_field

        win.orderFrontRegardless()
        self._window = win

    def _animate_waveform(self) -> None:
        if not self._wave_bars:
            return
        phase = self._tick_count * 0.15
        for i, bar in enumerate(self._wave_bars):
            wave = math.sin(phase + i * 0.6)            # -1..1
            height = WAVE_BAR_MIN_HEIGHT + (wave + 1.0) * (
                (WAVE_BAR_MAX_HEIGHT - WAVE_BAR_MIN_HEIGHT) / 2.0
            )
            cur = bar.frame()
            bar.setFrame_(NSMakeRect(cur.origin.x, self._bar_y(height), cur.size.width, height))

    @staticmethod
    def _bar_y(height: float) -> float:
        return (PANEL_HEIGHT - height) / 2.0

    def _tear_down_window(self) -> None:
        if self._window is not None:
            self._window.orderOut_(None)
            self._window = None
        self._text_field = None
        self._status_field = None
        self._wave_bars = []
        self._tick_count = 0
