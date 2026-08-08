#!/bin/bash
# Remove the VoiceVault LaunchAgent and unload it from launchd.
#
# Counterpart to install-launchagent.sh.

set -euo pipefail

LABEL="ai.voicevault.macos"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if [ -f "${PLIST}" ]; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    rm -f "${PLIST}"
    echo "Uninstalled LaunchAgent: ${PLIST}"
else
    echo "VoiceVault LaunchAgent was not installed (no plist at ${PLIST})."
fi
