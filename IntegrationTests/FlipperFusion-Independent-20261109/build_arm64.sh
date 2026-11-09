#!/usr/bin/env bash
# A/B ARM64 Build: independent fresh images, no existing AppImages are overwritten.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
OUT="$HERE/artifacts"
TOOL="$APPIMAGETOOL"
if [[ "$(uname -m)" != "aarch64" ]]; then echo "AArch64 runner required" >&2; exit 2; fi
for x in git go gcc sdl2-config readelf sha256sum file tar python3; do
 command -v "$x" >/dev/null || { echo "Missing dependency: $x" >&2; exit 2; }
done
test -x "$TOOL" || { echo "Set APPIMAGETOOL to an executable appimagetool" >&2; exit 2; }
git -C "$ROOT" show-ref --verify -q refs/remotes/origin/main || { echo "Fetch origin/main first" >&2; exit 2; }
mkdir -p "$OUT"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/control"
git -C "$ROOT" archive origin/main app-ordner | tar -x -C "$WORK/control"
echo "Control commit: $(git -C "$ROOT" rev-parse origin/main)"
echo "Fusion commit: $(git -C "$ROOT" rev-parse HEAD)"
STAMP="$BUILD_STAMP"
[[ "$STAMP" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid BUILD_STAMP" >&2; exit 3; }
build_one() {
 local kind="$1" source="$2" app="$WORK/$1/AppDir"
 local output="$OUT/FlipperOne-OSINT-LAB-$kind-$STAMP-aarch64.AppImage"
 test ! -e "$output" && test ! -e "$output.sha256" || { echo "Refusing to overwrite $output" >&2; return 5; }
 mkdir -p "$app"
 cp -a "$source/app-ordner/app/FlipperOneOSINT.AppDir/." "$app/"
 mkdir -p "$app/usr/bin"
 (
  cd "$source/app-ordner/src/cli"
  go test ./...
  CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.Version=$STAMP" -o "$app/usr/bin/osint-cli" .
 )
 gcc -std=gnu99 -O2 -Wall -DAPP_VERSION="\"$STAMP\"" \
  "$source/app-ordner/src/ui/osint-ui.c" -o "$app/usr/bin/osint-ui" $(sdl2-config --cflags --libs)
 if [[ "$kind" == "FUSION" ]]; then
  "$app/usr/bin/osint-ui" --selftest
  mkdir -p "$app/usr/lib/personintel"
  cp -a "$ROOT/PersonIntel/src/personintel" "$app/usr/lib/personintel/"
  find "$app/usr/lib/personintel" -type d -name '__pycache__' -prune -exec rm -rf {} +
 else
  rm -rf "$app/usr/lib/personintel"
 fi
 python3 - "$app/app.toml" "OSINT LAB $kind" <<'PY'
import pathlib,re,sys
p=pathlib.Path(sys.argv[1])
data,n=re.subn(r'(?m)^name\s*=\s*"[^"]*"', 'name = "'+sys.argv[2]+'"',p.read_text())
assert n==1
p.write_text(data)
PY
 chmod +x "$app/AppRun" "$app/usr/bin/osint-ui" "$app/usr/bin/osint-cli"
 for bin in osint-ui osint-cli; do
  readelf -h "$app/usr/bin/$bin" | grep -q AArch64
 done
 "$app/usr/bin/osint-cli" phone "0171 1234567" | grep -q '+491711234567'
 if [[ "$kind" == "FUSION" ]]; then
  APPDIR="$app" "$app/usr/bin/osint-cli" pi-status x > "$WORK/pi-status.txt"
  grep -q PersonIntel "$WORK/pi-status.txt"
 fi
 ARCH=aarch64 "$TOOL" --appimage-extract-and-run --no-appstream "$app" "$output"
 readelf -h "$output" | grep -q AArch64
 sha256sum "$output" > "$output.sha256"
 echo "$kind built: $output"
}
build_one CONTROL "$WORK/control"
build_one FUSION "$ROOT"
echo "Build done. Emulator execution remains untested."
