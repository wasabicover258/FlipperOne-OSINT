"""Zugangsdaten: Verschluesselte Datei, Sperre, Umgebungsvariablen, keine Werte in Repr."""

import json

import pytest

from personintel.api import CredentialError, LockedError
from personintel.security.credentials import CredentialStore, EncryptedFileBackend, env_name


def test_encrypted_file_backend_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "cred.enc"
    be = EncryptedFileBackend(path)
    with pytest.raises(LockedError):
        be.get("pipl", "api_key")
    be.unlock("pw")
    be.set("pipl", "api_key", "SEHR-GEHEIM")
    assert be.get("pipl", "api_key") == "SEHR-GEHEIM"
    assert be.fields("pipl") == ["api_key"]
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert b"SEHR-GEHEIM" not in path.read_bytes()
    assert set(json.loads(path.read_text())) == {"v", "salt", "data"}

    be2 = EncryptedFileBackend(path)
    with pytest.raises(LockedError):
        be2.unlock("falsch")
    be2.unlock("pw")
    assert be2.get("pipl", "api_key") == "SEHR-GEHEIM"
    be2.delete("pipl", "api_key")
    assert be2.get("pipl", "api_key") is None
    be2.lock()
    assert not be2.unlocked


def test_store_prefers_environment_variable(tmp_path, monkeypatch):
    store = CredentialStore(EncryptedFileBackend(tmp_path / "c.enc"))
    store.backend.unlock("pw")
    store.set("pipl", "api_key", "aus-datei")
    assert store.get("pipl", "api_key") == "aus-datei"
    monkeypatch.setenv(env_name("pipl", "api_key"), "aus-umgebung")
    assert store.get("pipl", "api_key") == "aus-umgebung"
    assert env_name("pipl", "api_key") == "PERSONINTEL_PIPL_API_KEY"


def test_locked_store_reports_locked_and_reads_empty(tmp_path):
    store = CredentialStore(EncryptedFileBackend(tmp_path / "c.enc"))
    assert store.locked is True
    assert store.get("pipl", "api_key") is None      # keine Ausnahme, nur "nicht vorhanden"
    assert store.has("pipl", "api_key") is False
    store.backend.unlock("pw")
    assert store.locked is False


def test_empty_value_is_rejected_and_view_hides_values(tmp_path):
    store = CredentialStore(EncryptedFileBackend(tmp_path / "c.enc"))
    store.backend.unlock("pw")
    with pytest.raises(CredentialError):
        store.set("pipl", "api_key", "")
    store.set("pipl", "api_key", "GEHEIM")
    view = store.view("pipl")
    assert view.has("api_key") and view.get("api_key") == "GEHEIM"
    assert "GEHEIM" not in repr(view)
    assert view.get("unbekannt") is None


def test_engine_configure_adapter_never_writes_secrets_to_settings(engine):
    engine.configure_adapter("pipl", secrets={"api_key": "KEY-123"}, config={"include_contact_details": "false"})
    text = json.dumps(engine.settings.to_dict())
    assert "KEY-123" not in text
    assert engine.credentials.get("pipl", "api_key") == "KEY-123"
    engine.configure_adapter("pipl", clear_secrets=["api_key"])
    assert engine.credentials.get("pipl", "api_key") is None


def test_configure_adapter_rejects_unknown_secret_field(engine):
    from personintel.api import ValidationError
    with pytest.raises(ValidationError):
        engine.configure_adapter("pipl", secrets={"kein_feld": "x"})


# --------------------------------------------- Betrieb ohne 'cryptography'
def _hide_cryptography(monkeypatch):
    """Simuliert ein System ohne das Paket 'cryptography' (schlankes Geraetebuendel)."""
    import builtins
    import sys
    real_import = builtins.__import__

    def fake(name, *a, **kw):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("no module named cryptography")
        return real_import(name, *a, **kw)

    for mod in [m for m in sys.modules if m.startswith("cryptography")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_personintel_works_without_cryptography(tmp_path, monkeypatch):
    """Ohne 'cryptography' muss alles laufen, was keine Verschlüsselung braucht."""
    from personintel.api import AppPaths, Engine, Purpose
    from personintel.security.crypto import have_cryptography
    _hide_cryptography(monkeypatch)
    assert have_cryptography() is False

    paths = AppPaths(data_dir=tmp_path / "d", config_dir=tmp_path / "c")
    eng = Engine(paths)
    try:
        assert len(eng.statuses()) == 10          # Dashboard funktioniert
        case = eng.create_case("ohne Krypto")
        eng.set_purpose(case.id, Purpose(category="journalism",
                                         description="Verifikation einer Quelle für Artikel X",
                                         authorized_by="Redaktion", active_checks_allowed=True))
        t = eng.add_target(case.id, "username", "jdoe")
        assert t.value == "jdoe"
        assert eng.build_report(case.id).to_markdown()
        assert eng.audit.verify() == (True, None)
        assert eng.export_case(case.id)["format"] == "personintel.case"
    finally:
        eng.close()


def test_encryption_without_cryptography_fails_clearly(tmp_path, monkeypatch):
    from personintel.api import CredentialError, LockedError, StorageError
    from personintel.security.credentials import CredentialStore, EncryptedFileBackend
    from personintel.security.crypto import CryptographyMissing, FieldCipher
    from personintel.storage.repository import Repository
    _hide_cryptography(monkeypatch)

    with pytest.raises(CryptographyMissing, match="cryptography"):
        FieldCipher.from_passphrase("pw", b"0123456789abcdef")
    store = CredentialStore(EncryptedFileBackend(tmp_path / "c.enc"))
    with pytest.raises(CredentialError, match="cryptography"):
        store.backend.unlock("pw")
    with pytest.raises((StorageError, CryptographyMissing)):
        Repository(tmp_path / "x.db", "pw")


def test_api_keys_from_environment_still_work_without_cryptography(tmp_path, monkeypatch):
    """Auf dem Gerät kommen Schlüssel über Umgebungsvariablen statt aus dem Speicher."""
    from personintel.api import AppPaths, Engine
    from personintel.security.credentials import env_name
    monkeypatch.setenv(env_name("pipl", "api_key"), "KEY-FROM-ENV")
    _hide_cryptography(monkeypatch)
    eng = Engine(AppPaths(data_dir=tmp_path / "d2", config_dir=tmp_path / "c2"))
    try:
        assert eng.adapter("pipl").secrets.get("api_key") == "KEY-FROM-ENV"
        assert eng.adapter("pipl").has_key()
        st = {s.adapter_id: s for s in eng.statuses()}["pipl"]
        assert st.state.value in ("unverified", "available")
    finally:
        eng.close()


def test_phone_validation_without_phonenumbers(monkeypatch):
    """Das Gerätebündel bringt 'phonenumbers' nicht mit (24 MB Metadaten): die strengere
    Prüfung entfällt dann, die Grundprüfung muss weiter greifen."""
    import builtins
    import sys
    from personintel.api import ValidationError
    from personintel.core.validation import normalize_phone
    real_import = builtins.__import__

    def fake(name, *a, **kw):
        if name == "phonenumbers":
            raise ImportError("no module named phonenumbers")
        return real_import(name, *a, **kw)

    monkeypatch.delitem(sys.modules, "phonenumbers", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake)
    assert normalize_phone("+49 30 1234567") == "+49301234567"
    assert normalize_phone("(+1) 212-555-0100") == "+12125550100"
    for bad in ("030 1234567", "+49", "keine nummer", "+0 123456789"):
        with pytest.raises(ValidationError):
            normalize_phone(bad)
