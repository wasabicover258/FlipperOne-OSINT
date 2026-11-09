"""Kommandozeile (headless): Status, Faelle, Export/Import, Bericht, Audit-Pruefung."""

import json

import pytest

from personintel.cli import main
from conftest import make_case


@pytest.fixture
def cli(tmp_path, monkeypatch, bin_dir):
    base = tmp_path / "home-cli"
    monkeypatch.delenv("PERSONINTEL_DB_PASSPHRASE", raising=False)

    def run(*args):
        return main(["--data-dir", str(base), *args])
    return run, base


def test_status_lists_all_ten_modules(cli, capsys):
    run, _ = cli
    assert run("status") == 0
    out = capsys.readouterr().out
    for name in ("Holehe", "Mosint", "Sherlock", "PhoneInfoga", "Ignorant", "Mr.Holmes",
                 "Pipl", "Spokeo", "ShadowDragon", "Babel Street"):
        assert name in out, name
    assert "Voraussetzung:" in out


def test_status_json_is_machine_readable(cli, capsys):
    run, _ = cli
    assert run("status", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 10
    assert all({"adapter_id", "state", "name", "message"} <= set(d) for d in data)


def test_audit_verify_and_cases(cli, capsys):
    run, base = cli
    assert run("audit-verify") == 0
    assert "OK" in capsys.readouterr().out
    assert run("cases") == 0
    assert capsys.readouterr().out == ""


def test_export_report_import_roundtrip(cli, capsys, tmp_path):
    run, base = cli
    from personintel.api import AppPaths, Engine
    paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    eng = Engine(paths)
    case = make_case(eng)
    eng.add_target(case.id, "email", "erika@example.org")
    eng.close()

    assert run("cases") == 0
    assert case.id in capsys.readouterr().out

    out = tmp_path / "bundle.json"
    assert run("export", case.id, "-o", str(out)) == 0
    capsys.readouterr()
    bundle = json.loads(out.read_text())
    assert bundle["case"]["id"] == case.id
    assert oct(out.stat().st_mode)[-3:] == "600"

    assert run("import", str(out)) == 0
    assert "Importiert:" in capsys.readouterr().out

    md = tmp_path / "bericht.md"
    assert run("report", case.id, "--format", "md", "-o", str(md)) == 0
    capsys.readouterr()
    assert "Recherchebericht" in md.read_text()

    assert run("report", case.id, "--format", "html") == 0
    assert "<!DOCTYPE html>" in capsys.readouterr().out

    assert run("report", case.id, "--format", "json") == 0
    assert json.loads(capsys.readouterr().out)["format"] == "personintel.report"

    assert run("report", case.id, "--mask") == 0
    text = capsys.readouterr().out
    assert "erika@example.org" not in text and "e***@example.org" in text


def test_unknown_case_is_a_clean_error(cli, capsys):
    run, _ = cli
    assert run("export", "case_ffffffffffffffff") == 1
    assert "Fehler:" in capsys.readouterr().err


def test_broken_bundle_is_a_clean_error(cli, capsys, tmp_path):
    run, _ = cli
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "etwas.anderes"}')
    assert run("import", str(bad)) == 1
    assert "Fehler:" in capsys.readouterr().err


def test_version_and_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "personintel" in capsys.readouterr().out


def test_encrypted_database_needs_passphrase(cli, capsys, monkeypatch, tmp_path):
    run, base = cli
    from personintel.api import AppPaths, Engine
    paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    eng = Engine(paths, db_passphrase="geheim")
    make_case(eng)
    eng.close()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert run("cases") == 2
    assert "Passphrase" in capsys.readouterr().err
    monkeypatch.setenv("PERSONINTEL_DB_PASSPHRASE", "geheim")
    assert run("cases") == 0
    assert "Testfall" in capsys.readouterr().out
