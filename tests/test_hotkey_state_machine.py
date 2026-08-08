"""State-machine tests for the push-to-talk / hands-free hotkey logic.

Builds an `VoiceVaultApp` instance without calling its `__init__` (which
would start rumps + pynput). Replaces `_start_dictation` / `_stop_dictation`
with mocks and exercises the press / release decision path. Uses only the
unittest standard-library module so no pytest dependency is required.
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.app import HOTKEY_DOUBLE_TAP_WINDOW_SEC, VoiceVaultApp  # noqa: E402


class MockStreamer:
    def __init__(self) -> None:
        self.is_streaming = True


def _make_app():
    """Skip rumps App __init__; install mock start/stop."""
    app = VoiceVaultApp.__new__(VoiceVaultApp)
    app._dictation_streamer = None
    app._hands_free = False
    app._last_release_monotonic = 0.0
    app._calls = {"start": 0, "stop": 0}

    def mock_start():
        app._calls["start"] += 1
        app._dictation_streamer = MockStreamer()

    def mock_stop():
        app._calls["stop"] += 1
        if app._dictation_streamer is not None:
            app._dictation_streamer.is_streaming = False
        app._dictation_streamer = None
        app._hands_free = False

    app._start_dictation = mock_start
    app._stop_dictation = mock_stop
    return app


class HotkeyStateMachine(unittest.TestCase):
    def test_push_to_talk_hold_release(self):
        """Single press + hold + release = one start, one stop."""
        a = _make_app()
        a._on_hotkey_press()
        self.assertEqual(a._calls, {"start": 1, "stop": 0})
        self.assertIsNotNone(a._dictation_streamer)
        self.assertTrue(a._dictation_streamer.is_streaming)
        a._on_hotkey_release()
        self.assertEqual(a._calls, {"start": 1, "stop": 1})
        self.assertIsNone(a._dictation_streamer)
        self.assertFalse(a._hands_free)

    def test_double_tap_enters_hands_free(self):
        """Press-release-press-release within window = hands-free ON after
        second press; second release does NOT stop dictation."""
        a = _make_app()
        a._on_hotkey_press()
        a._on_hotkey_release()
        self.assertFalse(a._hands_free)
        time.sleep(HOTKEY_DOUBLE_TAP_WINDOW_SEC * 0.3)
        a._on_hotkey_press()
        self.assertTrue(a._hands_free)
        self.assertEqual(a._calls["start"], 2)
        self.assertTrue(a._dictation_streamer.is_streaming)
        a._on_hotkey_release()
        self.assertEqual(a._calls, {"start": 2, "stop": 1})
        self.assertTrue(a._dictation_streamer.is_streaming)

    def test_third_press_exits_hands_free(self):
        """Press while hands-free is on stops dictation and exits hands-free."""
        a = _make_app()
        a._on_hotkey_press()
        a._on_hotkey_release()
        time.sleep(HOTKEY_DOUBLE_TAP_WINDOW_SEC * 0.3)
        a._on_hotkey_press()
        self.assertTrue(a._hands_free)
        a._on_hotkey_press()
        self.assertEqual(a._calls, {"start": 2, "stop": 2})
        self.assertFalse(a._hands_free)
        self.assertIsNone(a._dictation_streamer)

    def test_slow_double_press_no_hands_free(self):
        """Two presses separated by more than the window count as two
        independent push-to-talk sessions."""
        a = _make_app()
        a._on_hotkey_press()
        a._on_hotkey_release()
        time.sleep(HOTKEY_DOUBLE_TAP_WINDOW_SEC + 0.05)
        a._on_hotkey_press()
        self.assertFalse(a._hands_free)
        a._on_hotkey_release()
        self.assertEqual(a._calls, {"start": 2, "stop": 2})

    def test_extra_press_while_holding_is_noop(self):
        """Holding the hotkey sends multiple press events; only the first
        should call `_start_dictation`."""
        a = _make_app()
        a._on_hotkey_press()
        for _ in range(5):
            a._on_hotkey_press()
        self.assertEqual(a._calls, {"start": 1, "stop": 0})

    def test_release_while_idle_is_noop(self):
        """Spurious keyup should not crash or invoke `_stop_dictation`."""
        a = _make_app()
        a._on_hotkey_release()
        self.assertEqual(a._calls, {"start": 0, "stop": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
