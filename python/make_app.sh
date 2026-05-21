#!/bin/bash
# macOS camera permission fix - creates a wrapper app for Python scripts
# Run once: bash python/make_app.sh

APP_NAME="ESP32Matrix"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"
APP_DIR="$PROJECT_DIR/$APP_NAME.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
RES_DIR="$APP_DIR/Contents/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RES_DIR"

cat > "$MACOS_DIR/launcher" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$DIR/.venv/bin/activate"
python3 "$DIR/python/rock_paper_scissors_game.py"
LAUNCHER
chmod +x "$MACOS_DIR/launcher"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.esp32matrix.camera</string>
    <key>CFBundleName</key>
    <string>ESP32Matrix</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>NSCameraUsageDescription</key>
    <string>ESP32-Matrix needs camera access for hand gesture detection and webcam streaming.</string>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP_DIR" 2>/dev/null

echo "App bundle created: $APP_DIR"
echo "Run: open $APP_DIR"
echo ""
echo "The first time you run it, macOS will ask for camera permission."
echo "Click 'Allow' and the script will work."
