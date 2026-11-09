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

# Validate shelf/desktop metadata and that the actual 128x128 icon is present.
python3 - "$APP" <<'PY'
from pathlib import Path
import struct,sys
p=Path(sys.argv[1])
toml=(p/'app.toml').read_text()
desktop=(p/'flipperone-osint.desktop').read_text()
assert 'name = "OSINT"' in toml, "shelf must show OSINT"
assert 'icon = "flipperone-osint.png"' in toml
assert 'Name=OSINT' in desktop and 'Icon=flipperone-osint' in desktop
for rel in ('flipperone-osint.png',
            'usr/share/icons/hicolor/128x128/apps/flipperone-osint.png'):
    data=(p/rel).read_bytes()
    assert data.startswith(b'\x89PNG\r\n\x1a\n'), f"invalid PNG {rel}"
    assert struct.unpack('>II',data[16:24]) == (128,128), f"invalid icon size {rel}"
print("PASS: Shelf Name=OSINT, desktop Name=OSINT, matching 128px PNG icon")
PY

chmod +x "$APP/AppRun" "$APP/usr/bin/osint-ui" "$APP/usr/bin/osint-cli"
for bin in osint-ui osint-cli; do
    readelf -h "$APP/usr/bin/$bin" | grep -q AArch64
done
"$APP/usr/bin/osint-cli" phone "0171 1234567" | grep -q '+491711234567'

ARCH=aarch64 "$TOOL" --appimage-extract-and-run --no-appstream "$APP" "$OUTPUT"
readelf -h "$OUTPUT" | grep -q AArch64
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
echo "OSINT release built: $OUTPUT"
