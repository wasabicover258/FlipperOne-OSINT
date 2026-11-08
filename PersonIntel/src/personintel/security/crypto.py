"""Verschluesselung ruhender Daten (Fernet, Schluessel per scrypt aus Passphrase)."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from ..core.errors import LockedError

_PREFIX = "enc1:"
_CHECK_PLAINTEXT = "personintel-key-check"


def new_salt() -> bytes:
    return os.urandom(16)


def derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise LockedError("Leere Passphrase.")
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


class FieldCipher:
    """Verschluesselt/entschluesselt Textfelder; erkennt bereits verschluesselte Werte am Praefix."""

    def __init__(self, key: bytes):
        self._f = Fernet(key)

    @classmethod
    def from_passphrase(cls, passphrase: str, salt: bytes) -> "FieldCipher":
        return cls(derive_key(passphrase, salt))

    def encrypt(self, text: str) -> str:
        return _PREFIX + self._f.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, text: str) -> str:
        if not text.startswith(_PREFIX):
            return text
        try:
            return self._f.decrypt(text[len(_PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise LockedError("Entschluesselung fehlgeschlagen (falsche Passphrase?).") from exc

    def make_check(self) -> str:
        return self.encrypt(_CHECK_PLAINTEXT)

    def verify_check(self, token: str) -> bool:
        try:
            return self.decrypt(token) == _CHECK_PLAINTEXT
        except LockedError:
            return False

    # Rohbytes (fuer Export-Buendel / Credential-Datei)
    def encrypt_bytes(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt_bytes(self, token: bytes) -> bytes:
        try:
            return self._f.decrypt(token)
        except InvalidToken as exc:
            raise LockedError("Entschluesselung fehlgeschlagen (falsche Passphrase?).") from exc


def is_encrypted(text: str) -> bool:
    return text.startswith(_PREFIX)
