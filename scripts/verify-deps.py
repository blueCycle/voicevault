#!/usr/bin/env python3
"""Dependency verification script for VoiceVault.

Run standalone to check all system dependencies before onboarding:
    python scripts/verify-deps.py

Returns exit code 0 if all critical dependencies are met, 1 otherwise.
"""

import sys
import subprocess
import json
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _check_command(cmd: list, name: str) -> tuple[bool, str]:
    """Run a command and return (success, version_or_error)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
            return True, version
        return False, result.stderr.strip()[:200]
    except FileNotFoundError:
        return False, f"{name} not found in PATH"
    except Exception as e:
        return False, str(e)


def check_ollama() -> dict:
    """Check Ollama binary and daemon status."""
    status = {"name": "Ollama", "required": True, "ok": False, "details": ""}
    
    # Check binary
    ok, version = _check_command(["ollama", "--version"], "Ollama")
    if not ok:
        status["details"] = version
        return status
    
    # Check daemon running
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            has_llama = any("llama3.1" in (m.get("name") or m.get("model", "")) for m in models)
            if has_llama:
                status["ok"] = True
                status["details"] = f"{version} — llama3.1:8b ready"
            else:
                status["ok"] = False
                status["details"] = f"{version} — daemon running but llama3.1:8b not pulled"
        else:
            status["ok"] = False
            status["details"] = f"{version} — daemon returned HTTP {resp.status_code}"
    except Exception as e:
        status["ok"] = False
        status["details"] = f"{version} — daemon not reachable ({e})"
    
    return status


def check_python_deps() -> dict:
    """Check critical Python packages are installed."""
    status = {"name": "Python packages", "required": True, "ok": True, "details": ""}
    
    required = ["numpy", "sounddevice", "requests", "faster_whisper", "rumps", "pynput"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        status["ok"] = False
        status["details"] = f"Missing: {', '.join(missing)} — run: pip install -r requirements.txt"
    else:
        status["details"] = f"All {len(required)} packages installed"
    
    return status


def check_whisper_model() -> dict:
    """Check if a Whisper model is cached locally."""
    status = {"name": "Whisper model", "required": False, "ok": False, "details": ""}
    
    cache_dir = Path.home() / ".cache" / "whisper"
    if cache_dir.exists():
        models = list(cache_dir.glob("*.pt")) + list(cache_dir.glob("*.bin"))
        if models:
            status["ok"] = True
            status["details"] = f"Found {len(models)} cached model(s): {', '.join(m.name for m in models[:3])}"
        else:
            status["details"] = "No models cached — will download on first use (~150MB for base)"
    else:
        status["details"] = "No models cached — will download on first use (~150MB for base)"
    
    return status


def check_microphone() -> dict:
    """Check microphone access via sounddevice."""
    status = {"name": "Microphone", "required": True, "ok": False, "details": ""}
    
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        if input_devices:
            status["ok"] = True
            status["details"] = f"{len(input_devices)} input device(s) found"
        else:
            status["details"] = "No input devices detected — check System Settings > Sound"
    except Exception as e:
        status["details"] = f"Could not query devices: {e}"
    
    return status


def check_blackhole() -> dict:
    """Check if BlackHole is installed for system audio capture."""
    status = {"name": "BlackHole (system audio)", "required": False, "ok": False, "details": ""}
    
    driver_path = Path("/Library/Audio/Plug-Ins/HAL/BlackHole.driver")
    if driver_path.exists():
        status["ok"] = True
        status["details"] = "BlackHole driver installed"
    else:
        status["details"] = "Not installed — optional, needed only for meeting recording capture: brew install blackhole-2ch"
    
    return status


def print_report(results: list):
    """Print formatted dependency report."""
    print()
    print(f"{BOLD}VoiceVault Dependency Report{RESET}")
    print("=" * 50)
    
    critical_ok = True
    for r in results:
        icon = f"{GREEN}✓{RESET}" if r["ok"] else (f"{YELLOW}⚠{RESET}" if not r["required"] else f"{RED}✗{RESET}")
        req = f" {YELLOW}[optional]{RESET}" if not r["required"] else ""
        print(f"{icon} {BOLD}{r['name']}{req}{RESET}")
        print(f"   {r['details']}")
        print()
        if not r["ok"] and r["required"]:
            critical_ok = False
    
    if critical_ok:
        print(f"{GREEN}{BOLD}All critical dependencies satisfied.{RESET}")
    else:
        print(f"{RED}{BOLD}Some critical dependencies are missing.{RESET}")
        print("Run ./scripts/setup.sh to install missing dependencies.")
    
    print()
    return critical_ok


def main() -> int:
    """Run all checks and return exit code."""
    checks = [
        check_python_deps(),
        check_ollama(),
        check_whisper_model(),
        check_microphone(),
        check_blackhole(),
    ]
    
    ok = print_report(checks)
    
    # Also write machine-readable JSON for the onboarding state machine
    report_path = Path.home() / ".voicevault" / "deps_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "all_ok": ok,
            "checks": [{k: (str(v) if isinstance(v, Path) else v) for k, v in c.items()} for c in checks]
        }, f, indent=2)
    
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
