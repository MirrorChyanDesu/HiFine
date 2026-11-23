#!/bin/sh
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
version=$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$root/pyproject.toml")
bundle=${1:-"$root/dist/HiFine"}
out=${2:-"$root/release"}
test -x "$bundle/HiFine"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
app_id=io.github.hifine.HiFine
mkdir -p "$stage/DEBIAN" "$stage/usr/lib/hifine" "$stage/usr/bin" "$out"
cp -a "$bundle/." "$stage/usr/lib/hifine/"
ln -s ../lib/hifine/HiFine "$stage/usr/bin/hifine"
install -Dm644 "$root/packaging/linux/$app_id.desktop" "$stage/usr/share/applications/$app_id.desktop"
install -Dm644 "$root/packaging/linux/hifine.thumbnailer" "$stage/usr/share/thumbnailers/hifine.thumbnailer"
install -Dm644 "$root/src/hifine/assets/HiFine.png" "$stage/usr/share/icons/hicolor/256x256/apps/$app_id.png"
arch=$(dpkg --print-architecture)
cat > "$stage/DEBIAN/control" <<EOF
Package: hifine
Version: $version
Architecture: $arch
Maintainer: HiFine contributors
Section: graphics
Priority: optional
Depends: libc6 (>= 2.39), libstdc++6, libfontconfig1, libgl1, libegl1, libglib2.0-0t64, libdbus-1-3, libx11-6, libx11-xcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-sync1, libxcb-xfixes0, libxcb-randr0, libxcb-xkb1, libxkbcommon-x11-0, libwayland-client0, libwayland-cursor0, libwayland-egl1, shared-mime-info
Recommends: fonts-noto-cjk | fonts-wqy-microhei
Description: Desktop image viewer with built-in HEIF decoding
 View photos, inspect EXIF metadata and browse camera HIF files.
EOF
dpkg-deb --root-owner-group -Zxz -z4 --build "$stage" "$out/HiFine-$version-linux-$arch.deb"
