#!/usr/bin/env bash
# OSINT ARM64 release build. The published name always ends in -aarch64.
# No older AppImage is overwritten and no "Fusion" branding is used.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
OUT="$HERE/artifacts"
TOOL="${APPIMAGETOOL:?Set APPIMAGETOOL to appimagetool-aarch64.AppImage}"
STAMP="${BUILD_STAMP:?Set BUILD_STAMP}"
[[ "$STAMP" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || { echo "Invalid version: $STAMP" >&2; exit 3; }
test "$(uname -m)" = "aarch64" || { echo "AArch64 runner required" >&2; exit 2; }
for cmd in git go gcc sdl2-config readelf sha256sum python3; do
    command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 2; }
done
test -x "$TOOL"
mkdir -p "$OUT"
OUTPUT="$OUT/FlipperOne-OSINT-$STAMP-aarch64.AppImage"
test ! -e "$OUTPUT" || { echo "Refusing to overwrite $OUTPUT" >&2; exit 4; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/OSINT.AppDir"
mkdir -p "$APP"
cp -a "$ROOT/app-ordner/app/FlipperOneOSINT.AppDir/." "$APP/"
mkdir -p "$APP/usr/bin" "$APP/usr/lib/personintel"

(
    cd "$ROOT/app-ordner/src/cli"
    go test ./...
    CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.Version=$STAMP" \
        -o "$APP/usr/bin/osint-cli" .
)

gcc -std=gnu99 -O2 -Wall -DAPP_VERSION="\"$STAMP\"" \
    "$ROOT/app-ordner/src/ui/osint-ui.c" \
    -o "$APP/usr/bin/osint-ui" $(sdl2-config --cflags --libs)
"$APP/usr/bin/osint-ui" --selftest

# Existing optional PersonIntel source is retained; no changed search logic.
cp -a "$ROOT/PersonIntel/src/personintel" "$APP/usr/lib/personintel/"
find "$APP/usr/lib/personintel" -type d -name '__pycache__' -prune -exec rm -rf {} +

# Root app.toml and supplied 14x14 RGBA alpha mask must be packaged unchanged.
# The Flipper shelf uses this PNG's alpha channel as a one-bit shape.
python3 "$HERE/check_shelf_icon.py" "$APP"

# The old opaque 128px theme icon must not be accidentally packaged.
if test -e "$APP/usr/share/icons/hicolor/128x128/apps/flipperone-osint.png"; then
    echo "ERROR: stale 128px shelf icon still present" >&2
    exit 5
fi

chmod +x "$APP/AppRun" "$APP/usr/bin/osint-ui" "$APP/usr/bin/osint-cli"
for bin in osint-ui osint-cli; do
    readelf -h "$APP/usr/bin/$bin" | grep -q AArch64
done
"$APP/usr/bin/osint-cli" phone "0171 1234567" | grep -q '+491711234567'

ARCH=aarch64 "$TOOL" --appimage-extract-and-run --no-appstream "$APP" "$OUTPUT"
readelf -h "$OUTPUT" | grep -q AArch64
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
echo "OSINT release built: $OUTPUT"
