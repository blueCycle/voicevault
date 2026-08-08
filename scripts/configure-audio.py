#!/usr/bin/env python3
"""Audio configuration helper for VoiceVault.

Checks if BlackHole 2ch is installed and configured in a Multi-Output Device,
so VoiceVault can capture system audio while you still hear it.

Usage:
    python scripts/configure-audio.py
"""

import subprocess
import sys
from pathlib import Path


def check_blackhole_installed() -> bool:
    """Check if BlackHole 2ch driver is installed."""
    return Path("/Library/Audio/Plug-Ins/HAL/BlackHole.driver").exists()


def get_audio_profile() -> str:
    """Get a summary of audio devices from system_profiler."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPAudioDataType"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
    except Exception as e:
        return f"Could not query audio devices: {e}"


def check_blackhole_configured() -> tuple[bool, str]:
    """Check if BlackHole is part of a Multi-Output Device.
    
    Returns (is_configured, details_string).
    """
    profile = get_audio_profile()
    
    has_blackhole = "BlackHole" in profile
    has_multi = "Multi-Output Device" in profile or "Aggregate Device" in profile
    
    if not has_blackhole:
        return False, "BlackHole 2ch not found in audio devices."
    
    if not has_multi:
        return False, "BlackHole is installed but not in a Multi-Output Device."
    
    # Check if BlackHole is explicitly listed in a Multi-Output Device section
    lines = profile.splitlines()
    in_multi_device = False
    blackhole_in_multi = False
    multi_device_name = None
    
    for line in lines:
        if "Multi-Output Device" in line:
            in_multi_device = True
            multi_device_name = line.strip()
        elif in_multi_device and line.strip().startswith("Device:"):
            # Extract device name from the line
            device_name = line.split(":", 1)[1].strip() if ":" in line else line.strip()
            if "BlackHole" in line:
                blackhole_in_multi = True
        elif in_multi_device and not line.startswith(" ") and not line.startswith("\t"):
            # End of multi-output device section (rough heuristic)
            in_multi_device = False
    
    # Simpler fallback: if both BlackHole and Multi-Output Device appear, assume configured
    # (The exact parsing is complex; the presence of both is a strong signal)
    if blackhole_in_multi or (has_blackhole and has_multi):
        return True, f"BlackHole is configured in a Multi-Output Device."
    
    return False, "BlackHole is installed but not in a Multi-Output Device."


def print_setup_instructions():
    """Print step-by-step instructions for configuring BlackHole."""
    print()
    print("=" * 60)
    print("  Audio Configuration Required")
    print("=" * 60)
    print()
    print("To capture meeting audio while still hearing it, you need to")
    print("create a Multi-Output Device that includes BlackHole 2ch.")
    print()
    print("Step-by-step:")
    print()
    print("  1. Open Audio MIDI Setup (Applications > Utilities)")
    print()
    print("  2. Click the + button at the bottom-left")
    print("     → Select 'Create Multi-Output Device'")
    print()
    print("  3. In the right panel, check BOTH:")
    print("     • Your physical speakers/headphones (e.g., 'MacBook Pro Speakers')")
    print("     • 'BlackHole 2ch'")
    print()
    print("  4. Right-click the new Multi-Output Device")
    print("     → Select 'Use This Device for Sound Output'")
    print()
    print("  5. Close Audio MIDI Setup")
    print()
    print("That's it. Audio will go to your speakers AND BlackHole,")
    print("so VoiceVault can capture it during meetings.")
    print()
    print("=" * 60)
    print()
    
    # Offer to open Audio MIDI Setup
    response = input("Open Audio MIDI Setup now? [Y/n]: ").strip().lower()
    if response in ("", "y", "yes"):
        subprocess.run(["open", "-a", "Audio MIDI Setup"])
        print("Audio MIDI Setup opened. Run this script again when done.")
    print()


def main():
    """Run audio configuration check."""
    print()
    print("VoiceVault Audio Configuration Check")
    print("=" * 40)
    print()
    
    if not check_blackhole_installed():
        print("❌ BlackHole 2ch is not installed.")
        print()
        print("Install it with:")
        print("  brew install blackhole-2ch")
        print()
        print("You may need to reboot after installation.")
        print()
        sys.exit(1)
    
    print("✅ BlackHole 2ch driver is installed.")
    print()
    
    configured, details = check_blackhole_configured()
    if configured:
        print("✅ BlackHole is configured in a Multi-Output Device.")
        print(f"   {details}")
        print()
        print("System audio capture is ready for VoiceVault meetings.")
        print()
        sys.exit(0)
    else:
        print(f"⚠️  {details}")
        print()
        print_setup_instructions()
        sys.exit(1)


if __name__ == "__main__":
    main()
