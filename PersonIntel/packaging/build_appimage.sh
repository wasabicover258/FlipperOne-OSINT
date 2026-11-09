#!/usr/bin/env bash
#
# Baut ein AppImage von PersonIntel fuer die *aktuelle* Architektur.
#
# Grundlage ist python-appimage (https://python-appimage.readthedocs.io): es laedt ein
# passendes manylinux-Python-AppImage, installiert PersonIntel samt PySide6 hinein und
# packt das Ergebnis.
#
# Wichtig zur Architektur: python-appimage benennt das Ergebnis nach der Architektur des
# Rechners, auf dem gebaut wird (platform.machine()), und installiert die Abhaengigkeiten
# mit pip aus dieser Laufzeit. Ein ARM64-AppImage entsteht daher nur auf ARM64-Hardware
# (oder in einer ARM64-Umgebung, z. B. qemu-user-static/Docker --platform linux/arm64 oder
# einem arm64-Runner). Dieses Skript bricht bewusst ab, wenn eine fremde Architektur
# verlangt wird, statt eine falsch benannte Datei zu erzeugen.
#
# Bestehende Dateien werden nie ueberschrieben: jeder Build landet unter einem neuen
# Versionsnamen im Ausgabeverzeichnis.
#
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECIPE="$PROJECT/packaging/appimage/personintel"
PYTHON_VERSION="3.12"
ARCH="$(uname -m)"
OUTPUT_DIR=""
SUFFIX=""
KEEP_REQUIREMENTS="no"

usage() {
    cat <<USAGE
Verwendung: $(basename "$0") [Optionen]

  -p, --python-version X.Y   Python-Version der Laufzeit im AppImage (Standard: $PYTHON_VERSION)
  -a, --arch ARCH            Zielarchitektur; muss der des Rechners entsprechen (hier: $ARCH)
  -o, --output-dir VERZ      Ausgabeverzeichnis (Standard: DevBuilds/ im Git-Repo, sonst dist/)
  -s, --suffix TEXT          Zusatz im Dateinamen, z. B. "rc1" -> PersonIntel-0.1.0-rc1-$ARCH.AppImage
      --keep-requirements    erzeugte requirements.txt nach dem Build behalten (Fehlersuche)
  -h, --help                 diese Hilfe

Ergebnis: <Ausgabeverzeichnis>/PersonIntel-<Version>[-<Suffix>]-<Arch>.AppImage
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--python-version) PYTHON_VERSION="$2"; shift 2 ;;
        -a|--arch)           WANT_ARCH="$2"; shift 2 ;;
        -o|--output-dir)     OUTPUT_DIR="$2"; shift 2 ;;
        -s|--suffix)         SUFFIX="$2"; shift 2 ;;
        --keep-requirements) KEEP_REQUIREMENTS="yes"; shift ;;
        -h|--help)           usage; exit 0 ;;
        *) echo "Unbekannte Option: $1" >&2; usage; exit 2 ;;
    esac
done

if [[ -n "${WANT_ARCH:-}" && "$WANT_ARCH" != "$ARCH" ]]; then
    cat >&2 <<MSG
Fehler: Es wurde die Architektur "$WANT_ARCH" verlangt, dieser Rechner ist "$ARCH".
python-appimage baut nur fuer die Architektur des bauenden Systems. Fuer "$WANT_ARCH"
dieses Skript auf entsprechender Hardware ausfuehren, oder in einer passenden Umgebung, z. B.:

  docker run --rm --platform linux/arm64 -v "$PROJECT":/src -w /src \\
      python:${PYTHON_VERSION}-slim bash -c \\
      "apt-get update && apt-get install -y --no-install-recommends file binutils zsync && \\
       pip install python-appimage && packaging/build_appimage.sh"

(benoetigt binfmt/qemu-user-static auf dem Wirt: docker run --rm --privileged tonistiigi/binfmt --install arm64)
MSG
    exit 3
fi

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$PROJECT/src/personintel/__init__.py")"
if [[ -z "$VERSION" ]]; then
    echo "Fehler: Version konnte nicht aus src/personintel/__init__.py gelesen werden." >&2
    exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    REPO_ROOT="$(git -C "$PROJECT" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$REPO_ROOT" && -d "$REPO_ROOT/DevBuilds" ]]; then
        OUTPUT_DIR="$REPO_ROOT/DevBuilds"
    else
        OUTPUT_DIR="$PROJECT/dist"
    fi
fi
mkdir -p "$OUTPUT_DIR"

NAME="PersonIntel-$VERSION"
[[ -n "$SUFFIX" ]] && NAME="$NAME-$SUFFIX"
TARGET="$OUTPUT_DIR/$NAME-$ARCH.AppImage"

if [[ -e "$TARGET" ]]; then
    cat >&2 <<MSG
Fehler: "$TARGET" ist schon vorhanden.
Bestehende Builds werden nicht ueberschrieben. Bitte die Version in
src/personintel/__init__.py erhoehen oder mit --suffix einen neuen Namen waehlen.
MSG
    exit 4
fi

for tool in python-appimage; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Fehler: \"$tool\" fehlt. Installation: pip install python-appimage" >&2
        exit 5
    }
done
# appimagetool braucht diese Hilfsprogramme; sonst bricht der Build spaeter mit unklarer Meldung ab.
MISSING=""
for tool in file; do command -v "$tool" >/dev/null 2>&1 || MISSING="$MISSING $tool"; done
if [[ -n "$MISSING" ]]; then
    echo "Fehler: folgende Programme fehlen:$MISSING (z. B. 'apt-get install file')" >&2
    exit 5
fi

echo "== PersonIntel $VERSION -> $TARGET"
echo "   Architektur: $ARCH · Python im AppImage: $PYTHON_VERSION"

# requirements.txt mit absolutem Projektpfad erzeugen: python-appimage uebergibt jede Zeile
# unveraendert an pip und arbeitet dabei in einem temporaeren Verzeichnis.
sed "s|@PROJECT@|$PROJECT|" "$RECIPE/requirements.txt.in" > "$RECIPE/requirements.txt"
cleanup() {
    [[ "$KEEP_REQUIREMENTS" == "yes" ]] || rm -f "$RECIPE/requirements.txt"
}
trap cleanup EXIT

BUILD_DIR="$(mktemp -d)"
pushd "$BUILD_DIR" >/dev/null
python-appimage build app -p "$PYTHON_VERSION" "$RECIPE"
popd >/dev/null

BUILT="$BUILD_DIR/PersonIntel-$ARCH.AppImage"
if [[ ! -f "$BUILT" ]]; then
    BUILT="$(find "$BUILD_DIR" -maxdepth 1 -name '*.AppImage' | head -n1)"
fi
if [[ -z "$BUILT" || ! -f "$BUILT" ]]; then
    echo "Fehler: python-appimage hat kein AppImage erzeugt (siehe Ausgabe oben)." >&2
    exit 6
fi

mv "$BUILT" "$TARGET"
chmod +x "$TARGET"
rm -rf "$BUILD_DIR"

SIZE="$(du -h "$TARGET" | cut -f1)"
echo "== Fertig: $TARGET ($SIZE)"
echo "   Pruefsumme:"
sha256sum "$TARGET"
cat <<HINT

Hinweise:
* Start:            "$TARGET"
* Kommandozeile:    "$TARGET" --help    (die Oberflaeche kennt --data-dir)
* Die zehn Recherchemodule sind *nicht* im AppImage enthalten. Lokale Werkzeuge
  (holehe, sherlock, mosint, phoneinfoga, ignorant, Mr.Holmes) werden zur Laufzeit im PATH
  bzw. an den in den Einstellungen angegebenen Pfaden gesucht; Zugangsdaten kommerzieller
  Anbieter werden in den Einstellungen hinterlegt. Siehe docs/INSTALL.md.
HINT
