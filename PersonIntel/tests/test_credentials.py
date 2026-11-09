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
