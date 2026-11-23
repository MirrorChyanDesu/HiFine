#!/bin/sh
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
root=$(dirname "$(dirname "$here")")
bundle=${1:-"$root/dist/HiFine.app"}
out=${2:-"$root/release"}
test -x "$bundle/Contents/MacOS/HiFine"
extension="$bundle/Contents/PlugIns/HiFineThumbnail.appex"
mkdir -p "$extension/Contents/MacOS" "$out"
cp "$here/Extension.plist" "$extension/Contents/Info.plist"
xcrun clang -O2 -fobjc-arc -fblocks -fapplication-extension -mmacosx-version-min=14.0 \
    -framework Foundation -framework QuickLookThumbnailing -framework CoreGraphics -framework ImageIO \
    -Wl,-e,_NSExtensionMain "$here/ThumbnailProvider.m" -o "$extension/Contents/MacOS/HiFineThumbnail"
codesign --force --sign - --entitlements "$here/Extension.entitlements" "$extension"
codesign --force --sign - "$bundle"
codesign --verify --deep --strict "$bundle"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
ditto "$bundle" "$stage/HiFine.app"
ln -s /Applications "$stage/Applications"
hdiutil create -ov -format UDZO -volname HiFine -srcfolder "$stage" "$out/HiFine-0.1.0-macOS-$(uname -m).dmg"
