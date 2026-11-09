"""Sichere Ablage der vom Nutzer bereitgestellten Zugangsdaten.

Backends:
* ``EncryptedFileBackend`` - Fernet-verschluesselte Datei (0600), Schluessel per scrypt aus Passphrase.
* ``KeyringBackend``       - System-Schluesselbund (optional, Paket ``keyring``).

Zusaetzlich gelten Umgebungsvariablen ``PERSONINTEL_<ADAPTER>_<FELD>`` (nur lesend; fuer
Headless-/CI-Betrieb). Geheimnisse werden nie in Logs, Audit-Protokoll oder Export geschrieben.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Protocol

from ..core.errors import CredentialError, LockedError
from .crypto import FieldCipher, new_salt


def env_name(adapter_id: str, field: str) -> str:
    return "PERSONINTEL_" + re.sub(r"[^A-Z0-9]", "_", f"{adapter_id}_{field}".upper())


class Backend(Protocol):
    def get(self, adapter_id: str, field: str) -> Optional[str]: ...
    def set(self, adapter_id: str, field: str, value: str) -> None: ...
    def delete(self, adapter_id: str, field: str) -> None: ...
    def fields(self, adapter_id: str) -> list[str]: ...


class EncryptedFileBackend:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._cipher: Optional[FieldCipher] = None
        self._data: dict[str, dict[str, str]] = {}

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self._cipher is not None

    def unlock(self, passphrase: str) -> None:
        from .crypto import MISSING_HINT, have_cryptography
        if not have_cryptography():
            raise CredentialError(
                "Der verschlüsselte Zugangsdatenspeicher ist nicht verfügbar: " + MISSING_HINT
                + " Schlüssel können stattdessen als Umgebungsvariable übergeben werden "
                  "(PERSONINTEL_<MODUL>_<FELD>).")
        if self.path.exists():
            blob = json.loads(self.path.read_text(encoding="utf-8"))
            salt = base64.b64decode(blob["salt"])
            cipher = FieldCipher.from_passphrase(passphrase, salt)
            raw = cipher.decrypt_bytes(blob["data"].encode("ascii"))  # LockedError bei falscher Passphrase
            self._data = json.loads(raw.decode("utf-8"))
            self._cipher = cipher
            self._salt = salt
        else:
            self._salt = new_salt()
            self._cipher = FieldCipher.from_passphrase(passphrase, self._salt)
            self._data = {}
            self._flush()

    def lock(self) -> None:
        self._cipher = None
        self._data = {}

    def _need(self) -> FieldCipher:
        if not self._cipher:
            raise LockedError("Credential-Store ist gesperrt.")
        return self._cipher

    def _flush(self) -> None:
        cipher = self._need()
        blob = {
            "v": 1,
            "salt": base64.b64encode(self._salt).decode("ascii"),
            "data": cipher.encrypt_bytes(json.dumps(self._data).encode("utf-8")).decode("ascii"),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".cred-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(blob, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, adapter_id: str, field: str) -> Optional[str]:
        self._need()
        return self._data.get(adapter_id, {}).get(field)

    def set(self, adapter_id: str, field: str, value: str) -> None:
        self._need()
        self._data.setdefault(adapter_id, {})[field] = value
        self._flush()

    def delete(self, adapter_id: str, field: str) -> None:
        self._need()
        self._data.get(adapter_id, {}).pop(field, None)
        self._flush()

    def fields(self, adapter_id: str) -> list[str]:
        self._need()
        return sorted(self._data.get(adapter_id, {}))


class KeyringBackend:
    SERVICE = "personintel"

    def __init__(self):
        try:
            import keyring  # type: ignore
        except ImportError as exc:
            raise CredentialError("Paket 'keyring' ist nicht installiert (pip install personintel[keyring]).") from exc
        self._kr = keyring

    def get(self, adapter_id, field):
        return self._kr.get_password(self.SERVICE, f"{adapter_id}:{field}")

    def set(self, adapter_id, field, value):
        self._kr.set_password(self.SERVICE, f"{adapter_id}:{field}", value)

    def delete(self, adapter_id, field):
        try:
            self._kr.delete_password(self.SERVICE, f"{adapter_id}:{field}")
        except Exception:
            pass

    def fields(self, adapter_id):  # Schluesselbund kann nicht aufzaehlen; Adapter kennen ihre Felder
        return []


class CredentialStore:
    """Fassade: Umgebungsvariable -> Backend."""

    def __init__(self, backend: Backend):
        self.backend = backend

    def get(self, adapter_id: str, field: str) -> Optional[str]:
        v = os.environ.get(env_name(adapter_id, field))
        if v:
            return v
        try:
            return self.backend.get(adapter_id, field)
        except LockedError:
            return None

    def has(self, adapter_id: str, field: str) -> bool:
        return bool(self.get(adapter_id, field))

    def set(self, adapter_id: str, field: str, value: str) -> None:
        if not value:
            raise CredentialError("Leerer Wert.")
        self.backend.set(adapter_id, field, value)

    def delete(self, adapter_id: str, field: str) -> None:
        self.backend.delete(adapter_id, field)

    def view(self, adapter_id: str) -> "SecretView":
        return SecretView(self, adapter_id)

    @property
    def locked(self) -> bool:
        b = self.backend
        return isinstance(b, EncryptedFileBackend) and not b.unlocked


class SecretView:
    """Nur-Lese-Sicht eines Adapters auf seine eigenen Geheimnisse."""

    def __init__(self, store: CredentialStore, adapter_id: str):
        self._store = store
        self._adapter_id = adapter_id

    def get(self, field: str) -> Optional[str]:
        return self._store.get(self._adapter_id, field)

    def has(self, field: str) -> bool:
        return self._store.has(self._adapter_id, field)

    def __repr__(self) -> str:  # nie Werte ausgeben
        return f"SecretView({self._adapter_id!r})"
