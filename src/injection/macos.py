import subprocess
import platform
from typing import Optional
import pyperclip
from src.config import CONFIG


def _sanitize_text(text: str) -> str:
    """Remove control characters and normalize text for injection."""
    # Remove control characters that break AppleScript or paste
    text = ''.join(c for c in text if c.isprintable() or c in ' \n\t')
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def inject_text(text: str) -> bool:
    """Inject transcribed text at the current cursor position.
    
    Strategy:
    1. Try clipboard + simulated Cmd+V (most reliable, preserves formatting)
    2. Fallback to AppleScript keystroke (works without clipboard permission)
    3. Fallback to clipboard only (user manually pastes)
    
    Returns True if text was successfully injected.
    """
    if not text:
        return False
    
    text = _sanitize_text(text)
    if not text:
        return False
    
    # Primary: clipboard + paste simulation (most reliable)
    if _inject_via_clipboard(text):
        return True
    
    # Fallback: AppleScript keystroke (macOS only, no clipboard needed)
    if platform.system() == "Darwin":
        if _inject_via_accessibility(text):
            return True
    
    # Ultimate fallback: just copy to clipboard
    pyperclip.copy(text)
    print(f"[Dictate] Text copied to clipboard (manual paste required)")
    return True


def _inject_via_accessibility(text: str) -> bool:
    """Use macOS Accessibility API to type text at cursor.
    
    Requires: System Settings > Privacy & Security > Accessibility permission.
    Only used as fallback when clipboard paste fails.
    """
    try:
        # AppleScript keystroke — limit to alphanumeric to avoid control char issues
        safe_text = ''.join(c for c in text if c.isalnum() or c in ' .,!?-:;')
        if not safe_text:
            return False
        
        script = f'''
        tell application "System Events"
            keystroke "{safe_text.replace('"', '\\"')}"
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _inject_via_clipboard(text: str) -> bool:
    """Copy to clipboard and simulate Cmd+V paste."""
    try:
        import pynput.keyboard as keyboard
        
        # Save current clipboard
        original = pyperclip.paste()
        
        # Copy new text
        pyperclip.copy(text)
        
        # Simulate Cmd+V with a small delay to ensure pasteboard is ready
        import time
        time.sleep(0.05)
        
        controller = keyboard.Controller()
        with controller.pressed(keyboard.Key.cmd):
            controller.press('v')
            controller.release('v')
        
        # Small delay then restore original clipboard
        time.sleep(0.1)
        pyperclip.copy(original)
        
        return True
    except Exception:
        return False
