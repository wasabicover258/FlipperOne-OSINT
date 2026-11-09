"""Rezept und Buildskript fuer das AppImage.

Der eigentliche AppImage-Bau laedt ein Python-Basisimage von GitHub und laeuft daher nicht in
der Testumgebung. Geprueft wird hier alles, was ohne Netzwerk pruefbar ist: dass das Rezept die
von python-appimage erwarteten Dateien in der erwarteten Benennung enthaelt, dass der
Einstiegspunkt nur dokumentierte Platzhalter verwendet und dass das Buildskript seine
Schutzmechanismen einhaelt (Architekturpruefung, kein Ueberschreiben bestehender Builds).
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
RECIPE = PROJECT / "packaging" / "appimage" / "personintel"
SCRIPT = PROJECT / "packaging" / "build_appimage.sh"

# Von python-appimage ersetzte Platzhalter (python_appimage/commands/build/app.py)
KNOWN_PLACEHOLDERS = {"architecture", "linux-tag", "python-executable", "python-fullversion",
                      "python-tag", "python-version", "requirements"}


def test_recipe_contains_the_expected_files():
    assert RECIPE.is_dir()
    assert RECIPE.name == "personintel"          # Ordnername = Anwendungsname
    names = {p.name for p in RECIPE.iterdir()}
    assert "entrypoint.sh" in names
    assert "requirements.txt.in" in names        # wird vom Skript zu requirements.txt gemacht
    assert len([n for n in names if n.endswith(".desktop")]) == 1
    assert len([n for n in names if n.endswith(".appdata.xml")]) == 1


def test_desktop_entry_is_valid_and_matches_the_icon():
    text = (RECIPE / "personintel.desktop").read_text(encoding="utf-8")
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    assert text.startswith("[Desktop Entry]")
    assert fields["Type"] == "Application"
    assert fields["Name"] == "PersonIntel"       # bestimmt den Dateinamen des AppImage
    assert fields["Exec"] == "personintel"
    assert fields["Terminal"] == "false"
    icon = fields["Icon"]
    assert (RECIPE / f"{icon}.svg").is_file() or (RECIPE / f"{icon}.png").is_file()


def test_appdata_is_wellformed_and_links_the_desktop_entry():
    import xml.etree.ElementTree as ET
    root = ET.parse(RECIPE / "personintel.appdata.xml").getroot()
    assert root.tag == "component" and root.get("type") == "desktop-application"
    assert root.findtext("id") == "personintel"
    assert root.findtext("launchable") == "personintel.desktop"
    assert root.findtext("name") == "PersonIntel"
    assert root.findtext("project_license")


def test_icon_is_usable_svg():
    svg = (RECIPE / "personintel.svg").read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<?xml") and "<svg" in svg and "viewBox" in svg


def test_entrypoint_uses_only_documented_placeholders():
    text = (RECIPE / "entrypoint.sh").read_text(encoding="utf-8")
    assert text.startswith("#!")
    used = set(re.findall(r"\{\{\s*([a-z-]+)\s*\}\}", text))
    assert used, "Der Einstiegspunkt muss die Python-Laufzeit des AppImage verwenden."
    assert used <= KNOWN_PLACEHOLDERS, f"Unbekannte Platzhalter: {used - KNOWN_PLACEHOLDERS}"
    assert "python-executable" in used
    assert "-m personintel" in text              # startet die Oberflaeche


def test_requirements_template_installs_this_project_with_ui_extra():
    text = (RECIPE / "requirements.txt.in").read_text(encoding="utf-8")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    assert "@PROJECT@[ui]" in lines
    assert any(l.startswith("PySide6") for l in lines)


def test_ui_extra_exists_in_project_metadata():
    text = (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ui = [" in text and "PySide6" in text
    assert 'personintel = "personintel.__main__:main"' in text
    assert "ui/resources/*.svg" in text          # Icon muss mitinstalliert werden


# ----------------------------------------------------------------- Buildskript
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash fehlt")
def test_script_has_valid_syntax_and_is_executable():
    assert os.access(SCRIPT, os.X_OK)
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def _run(*args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=e)


def test_help_names_the_output_pattern():
    r = _run("--help")
    assert r.returncode == 0
    assert "PersonIntel-<Version>" in r.stdout and "--output-dir" in r.stdout


def test_foreign_architecture_is_refused_with_instructions():
    other = "aarch64" if platform.machine() != "aarch64" else "x86_64"
    r = _run("--arch", other)
    assert r.returncode == 3
    assert "nur fuer die Architektur des bauenden Systems" in r.stderr
    assert "linux/arm64" in r.stderr or "docker run" in r.stderr


def test_existing_build_is_never_overwritten(tmp_path):
    version = re.search(r'__version__ = "(.*)"',
                        (PROJECT / "src" / "personintel" / "__init__.py").read_text()).group(1)
    target = tmp_path / f"PersonIntel-{version}-{platform.machine()}.AppImage"
    target.write_bytes(b"alter Build")
    r = _run("--output-dir", str(tmp_path))
    assert r.returncode == 4
    assert "schon vorhanden" in r.stderr
    assert target.read_bytes() == b"alter Build"      # unveraendert


def test_missing_tooling_is_reported_clearly(tmp_path):
    """Fehlt python-appimage, muss das Skript den Installationsbefehl nennen - nicht abstuerzen."""
    # Standardwerkzeuge bleiben erreichbar, nur die Verzeichnisse mit python-appimage fallen weg.
    tool = shutil.which("python-appimage")
    base = [d for d in ("/usr/bin", "/bin") if Path(d).is_dir()]
    assert base, "Testumgebung ohne /usr/bin"
    if tool and str(Path(tool).parent) in base:
        pytest.skip("python-appimage liegt in einem Standardverzeichnis")
    r = _run("--output-dir", str(tmp_path), env={"PATH": ":".join(base)})
    assert r.returncode == 5, r.stderr
    assert "python-appimage" in r.stderr


def test_script_reads_the_project_version(tmp_path):
    """Der Zieldateiname muss die Version aus dem Paket tragen (kein fester Name)."""
    version = re.search(r'__version__ = "(.*)"',
                        (PROJECT / "src" / "personintel" / "__init__.py").read_text()).group(1)
    (tmp_path / f"PersonIntel-{version}-{platform.machine()}.AppImage").write_bytes(b"x")
    r = _run("--output-dir", str(tmp_path))
    assert version in r.stderr and r.returncode == 4


def test_generated_requirements_are_cleaned_up(tmp_path):
    """Nach einem Abbruch darf keine erzeugte requirements.txt zurueckbleiben."""
    generated = RECIPE / "requirements.txt"
    existed = generated.exists()
    other = "aarch64" if platform.machine() != "aarch64" else "x86_64"
    _run("--arch", other)
    if not existed:
        assert not generated.exists()
