#!/bin/bash
# Install a macOS LaunchAgent to start VoiceVault at login.
#
# Creates:  ~/Library/LaunchAgents/ai.voicevault.macos.plist
# Points at: ~/Applications/VoiceVault.app/Contents/MacOS/VoiceVault
#
# Behaviors:
#   - RunAtLoad = true: launched once when the user logs in.
#   - KeepAlive.SuccessfulExit = false: relaunches on crash, but respects
#     a clean quit (so Quit-from-menubar sticks until next login).
#
# Run ./scripts/uninstall-launchagent.sh to remove.

set -euo pipefail

LABEL="ai.voicevault.macos"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PROGRAM="${HOME}/Applications/VoiceVault.app/Contents/MacOS/VoiceVault"
LOG_DIR="${HOME}/.voicevault"

if [ ! -x "${PROGRAM}" ]; then
    echo "VoiceVault bundle not found at:" >&2
    echo "  ${PROGRAM}" >&2
    echo "Run ./scripts/create-spotlight-app.sh first." >&2
    exit 1
fi

mkdir -p "${LOG_DIR}" "$(dirname "${PLIST}")"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROGRAM}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchagent.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchagent.err.log</string>
</dict>
</plist>
EOF

# Load (or reload) the agent in launchd
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"

echo "Installed LaunchAgent: ${PLIST}"
echo "VoiceVault will start automatically at next login."
echo "(If you want it to start right now, run:"
echo "    launchctl kickstart -k gui/\$(id -u)/${LABEL}"
echo " or open Spotlight and launch VoiceVault once.)"
