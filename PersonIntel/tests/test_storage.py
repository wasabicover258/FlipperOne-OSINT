"""Speicher: Migrationen, Verschluesselung ruhender Daten, gezieltes Loeschen."""

import json
import sqlite3

import pytest

from personintel.api import AppPaths, Engine, LockedError, Purpose, StorageError
from personintel.core.models import Case, Finding, FindingStatus
from personintel.core.ids import new_id
from personintel.storage.migrations import LATEST_VERSION, current_version, migrate
from personintel.storage.repository import Repository
from conftest import PURPOSE_TEXT, make_case


def test_migrations_are_applied_and_idempotent(tmp_path):
    db = tmp_path / "x.db"
    conn = sqlite3.connect(db)
    assert current_version(conn) == 0
    assert migrate(conn) == LATEST_VERSION
    assert migrate(conn) == LATEST_VERSION   # zweiter Lauf aendert nichts
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "cases", "records", "audit"} <= tables
    conn.close()
    repo = Repository(db)           # oeffnet eine bereits migrierte Datenbank
    assert repo.schema_version == LATEST_VERSION
    repo.close()


def test_database_file_permissions_are_restrictive(tmp_path):
    repo = Repository(tmp_path / "p.db")
    assert oct((tmp_path / "p.db").stat().st_mode)[-3:] == "600"
    repo.close()


def test_roundtrip_and_selective_delete(tmp_path):
    repo = Repository(tmp_path / "r.db")
    case = Case(id=new_id("case"), name="Fall A")
    repo.save_case(case)
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="holehe", type="account", title="T",
                status=FindingStatus.FOUND)
    repo.put("finding", f, ts=f.observed_at)
    assert [x.id for x in repo.list("finding", case.id)] == [f.id]
    assert repo.get("finding", f.id).title == "T"
    repo.delete_record(f.id)
    assert repo.list("finding", case.id) == []
    assert repo.get_case(case.id) is not None
    repo.close()


def test_unknown_record_kind_is_rejected(tmp_path):
    repo = Repository(tmp_path / "k.db")
    case = Case(id=new_id("case"), name="x")
    repo.save_case(case)
    with pytest.raises(StorageError):
        repo.put("unsinn", Finding(id=new_id("fnd"), case_id=case.id, adapter_id="a", type="t", title="t"))
    repo.close()


def test_encryption_at_rest_hides_payloads(tmp_path):
    path = tmp_path / "enc.db"
    repo = Repository(path, "geheim")
    assert repo.is_encrypted
    case = Case(id=new_id("case"), name="Sehr vertraulicher Fallname")
    repo.save_case(case)
    repo.put("finding", Finding(id=new_id("fnd"), case_id=case.id, adapter_id="a", type="account",
                                title="kontoname@example.org"))
    repo.close()
    blob = path.read_bytes()
    assert b"Sehr vertraulicher Fallname" not in blob
    assert b"kontoname@example.org" not in blob
    assert b"enc1:" in blob

    with pytest.raises(LockedError):
        Repository(path)                   # ohne Passphrase
    with pytest.raises(LockedError):
        Repository(path, "falsch")
    repo = Repository(path, "geheim")
    assert repo.get_case(case.id).name == "Sehr vertraulicher Fallname"
    repo.close()


def test_encrypt_existing_database_afterwards(tmp_path):
    path = tmp_path / "later.db"
    repo = Repository(path)
    case = Case(id=new_id("case"), name="Klartextfall")
    repo.save_case(case)
    repo.put("finding", Finding(id=new_id("fnd"), case_id=case.id, adapter_id="a", type="account", title="geheim-x"))
    assert b"Klartextfall" in path.read_bytes()
    repo.encrypt_existing("neu")
    assert repo.is_encrypted
    with pytest.raises(StorageError):
        repo.encrypt_existing("noch-neuer")
    repo.close()
    blob = path.read_bytes()
    assert b"Klartextfall" not in blob and b"geheim-x" not in blob
    repo = Repository(path, "neu")
    assert repo.get_case(case.id).name == "Klartextfall"
    assert repo.list("finding", case.id)[0].title == "geheim-x"
    repo.close()


def test_delete_case_removes_all_records_but_keeps_audit(engine, tmp_path):
    case = make_case(engine)
    engine.add_target(case.id, "email", "a@example.org")
    engine.graph.add_node(case.id, "person", "Zielperson")
    n = engine.delete_case(case.id, purge_audit=False)
    assert n >= 1
    assert engine.cases() == []
    assert engine.repo.conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
    actions = [e.action for e in engine.audit.entries()]
    assert "case.create" in actions and "case.delete" in actions
    assert engine.audit.verify() == (True, None)


def test_delete_case_with_purge_audit_rechains(engine):
    case = make_case(engine)
    engine.add_target(case.id, "email", "a@example.org")
    other = make_case(engine, name="bleibt")
    engine.delete_case(case.id, purge_audit=True)
    assert all(e.case_id != case.id for e in engine.audit.entries())
    assert any(e.case_id == other.id for e in engine.audit.entries())
    assert engine.audit.verify() == (True, None)   # Kette nach dem Loeschen neu aufgebaut


def test_remove_target_deletes_its_data_only(engine):
    case = make_case(engine)
    t1 = engine.add_target(case.id, "email", "a@example.org")
    t2 = engine.add_target(case.id, "email", "b@example.org")
    for t in (t1, t2):
        engine.repo.put("finding", Finding(id=new_id("fnd"), case_id=case.id, adapter_id="x", type="account",
                                           title=f"zu {t.value}", target_id=t.id))
    engine.remove_target(case.id, t1.id, delete_data=True)
    titles = [f.title for f in engine.findings(case.id)]
    assert titles == ["zu b@example.org"]
    assert [t.id for t in engine.targets(case.id)] == [t2.id]


def test_settings_file_is_private_and_roundtrips(tmp_path):
    paths = AppPaths(data_dir=tmp_path / "d", config_dir=tmp_path / "c")
    paths.ensure()
    eng = Engine(paths)
    eng.configure_adapter("holehe", enabled=False)
    eng.close()
    assert oct(paths.settings_path.stat().st_mode)[-3:] == "600"
    data = json.loads(paths.settings_path.read_text())
    assert data["enabled_adapters"]["holehe"] is False
    eng2 = Engine(paths)
    assert eng2.settings.is_enabled("holehe") is False
    assert eng2.adapter("holehe").enabled is False
    eng2.close()
