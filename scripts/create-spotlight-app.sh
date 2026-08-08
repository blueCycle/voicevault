#!/bin/bash
# Create a VoiceVault macOS .app bundle for Spotlight launching
#
# Usage: ./scripts/create-spotlight-app.sh [--reinstall]
#
# Produces ~/Applications/VoiceVault.app with:
#   - real .icns icon (multi-resolution, embedded in Info.plist)
#   - Info.plist declaring LSUIElement (no Dock icon)
#   - ad-hoc codesigned bundle
#   - single-instance check via ~/.voicevault/voicevault.pid
#
# To launch from Spotlight: Cmd+Space -> "VoiceVault" -> Return.
# To add to Dock: right-click app -> Options -> Keep in Dock.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${HOME}/Applications/VoiceVault.app"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
ICONSET_DIR="${REPO_ROOT}/data/VoiceVault.iconset"
ICNS_PATH="${RESOURCES_DIR}/VoiceVault.icns"

echo "Building VoiceVault.app at ${APP_DIR}..."

# 1) Ensure source icons exist
if [ ! -f "${REPO_ROOT}/data/icon_master.png" ]; then
    echo "  generating source icons..."
    "${REPO_ROOT}/venv/bin/python" "${REPO_ROOT}/scripts/build-icon.py"
fi

# 2) Build a full multi-resolution .iconset from the master PNG using sips
echo "  building .iconset..."
rm -rf "${ICONSET_DIR}"
mkdir -p "${ICONSET_DIR}"
SRC="${REPO_ROOT}/data/icon_master.png"
sips -z 16 16     "${SRC}" --out "${ICONSET_DIR}/icon_16x16.png"        >/dev/null
sips -z 32 32     "${SRC}" --out "${ICONSET_DIR}/icon_16x16@2x.png"     >/dev/null
sips -z 32 32     "${SRC}" --out "${ICONSET_DIR}/icon_32x32.png"        >/dev/null
sips -z 64 64     "${SRC}" --out "${ICONSET_DIR}/icon_32x32@2x.png"     >/dev/null
sips -z 128 128   "${SRC}" --out "${ICONSET_DIR}/icon_128x128.png"      >/dev/null
sips -z 256 256   "${SRC}" --out "${ICONSET_DIR}/icon_128x128@2x.png"   >/dev/null
sips -z 256 256   "${SRC}" --out "${ICONSET_DIR}/icon_256x256.png"      >/dev/null
sips -z 512 512   "${SRC}" --out "${ICONSET_DIR}/icon_256x256@2x.png"   >/dev/null
sips -z 512 512   "${SRC}" --out "${ICONSET_DIR}/icon_512x512.png"      >/dev/null
sips -z 1024 1024 "${SRC}" --out "${ICONSET_DIR}/icon_512x512@2x.png"   >/dev/null

# 3) Bundle Contents/ skeleton
mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"

# 4) Pack iconset -> .icns
iconutil -c icns "${ICONSET_DIR}" --output "${ICNS_PATH}"
echo "  icns: ${ICNS_PATH}"

# 5) Write the launcher executable
cat > "${MACOS_DIR}/VoiceVault" <<EOF
#!/bin/bash
# VoiceVault launcher

REPO_ROOT="${REPO_ROOT}"
PIDFILE="\${HOME}/.voicevault/voicevault.pid"

if [ -f "\${PIDFILE}" ]; then
    PID="\$(cat "\${PIDFILE}")"
    if ps -p "\${PID}" > /dev/null 2>&1; then
        exit 0
    fi
fi

cd "\${REPO_ROOT}"
# shellcheck disable=SC1091
source venv/bin/activate

# Generate icon if missing (first launch after fresh repo clone)
if [ ! -f "data/voicevault_icon.png" ]; then
    python scripts/build-icon.py >/dev/null 2>&1 || true
fi

nohup python src/app.py > "\${HOME}/.voicevault/voicevault.log" 2>&1 &
echo \$! > "\${PIDFILE}"
disown
EOF
chmod +x "${MACOS_DIR}/VoiceVault"

# 6) Info.plist with icon declared
cat > "${CONTENTS_DIR}/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>VoiceVault</string>
    <key>CFBundleIdentifier</key>
    <string>ai.voicevault.macos</string>
    <key>CFBundleName</key>
    <string>VoiceVault</string>
    <key>CFBundleDisplayName</key>
    <string>VoiceVault</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>VoiceVault</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# 7) Ad-hoc codesign so launchd/install/launch services trust the bundle
#    (ad-hoc = no Developer ID; required for personal use, sufficient for
#    self-launching and LaunchAgent load)
if codesign --force --deep --sign - "${APP_DIR}" 2>/dev/null; then
    echo "  ad-hoc signed"
else
    echo "  (skipped signing: codesign not available)"
fi

cat <<EOF

Installed: ${APP_DIR}

Launch via Spotlight
  Cmd+Space -> type "VoiceVault" -> Return

Launch from Terminal
  open ${APP_DIR}

Add to Dock
  Right-click the app in Finder -> Options -> Keep in Dock
EOF
