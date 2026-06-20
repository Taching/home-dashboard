#!/bin/zsh
set -euo pipefail

cd "${0:A:h}"
swift build -c release

app_path="build/Chili Calendar Bridge.app"
rm -rf "$app_path"
mkdir -p "$app_path/Contents/MacOS"
cp .build/release/chili-calendar-bridge "$app_path/Contents/MacOS/chili-calendar-bridge"
cp Info.plist "$app_path/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$app_path"
echo "$app_path"
