"""SQLite-Repository mit optionaler Feldverschluesselung und gezieltem Loeschen."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional, TypeVar

from ..core.errors import LockedError, StorageError
from ..core.ids import now_iso
from ..core.models import (Case, Event, Finding, Model, QueryMode, QueryRecord, Source, Target)
from ..security.crypto import FieldCipher, new_salt
from .migrations import LATEST_VERSION, migrate

T = TypeVar("T", bound=Model)

KINDS = {"target": Target, "source": Source, "finding": Finding, "query": QueryRecord, "event": Event}


class Repository:
    """Persistenz fuer Faelle und Datensaetze.

    Verschluesselung: Ist die Datenbank als verschluesselt markiert (``meta.encrypted``),
    muss beim Oeffnen eine Passphrase uebergeben werden. Verschluesselt werden alle
    Payloads (Fallname, Kennungen, Befunde ...); IDs, Zeitstempel und Datensatzart
    bleiben als Index im Klartext.
    """

    def __init__(self, path: str | Path, passphrase: Optional[str] = None):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA secure_delete = ON")
        if self.path != ":memory:":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        migrate(self._conn)
        self._cipher: Optional[FieldCipher] = None
        self._open_encryption(passphrase)

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self._conn.commit()

    @property
    def schema_version(self) -> int:
        return LATEST_VERSION

    # ------------------------------------------------------------ encryption
    @property
    def is_encrypted(self) -> bool:
        return self.get_meta("encrypted") == "1"

    def _open_encryption(self, passphrase: Optional[str]) -> None:
        if self.is_encrypted:
            if not passphrase:
                raise LockedError("Die Datenbank ist verschluesselt - Passphrase erforderlich.")
            salt = bytes.fromhex(self.get_meta("enc_salt") or "")
            cipher = FieldCipher.from_passphrase(passphrase, salt)
            if not cipher.verify_check(self.get_meta("enc_check") or ""):
                raise LockedError("Falsche Passphrase.")
            self._cipher = cipher
        elif passphrase and self._is_empty():
            self._init_encryption(passphrase)

    def _is_empty(self) -> bool:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0

    def _init_encryption(self, passphrase: str) -> None:
        salt = new_salt()
        cipher = FieldCipher.from_passphrase(passphrase, salt)
        self.set_meta("enc_salt", salt.hex())
        self.set_meta("enc_check", cipher.make_check())
        self.set_meta("encrypted", "1")
        self._cipher = cipher

    def encrypt_existing(self, passphrase: str) -> None:
        """Verschluesselt eine bestehende, unverschluesselte Datenbank nachtraeglich."""
        if self.is_encrypted:
            raise StorageError("Datenbank ist bereits verschluesselt.")
        with self._lock:
            plain_cases = [(r["id"], r["payload"]) for r in self._conn.execute("SELECT id,payload FROM cases")]
            plain_recs = [(r["id"], r["payload"]) for r in self._conn.execute("SELECT id,payload FROM records")]
            self._init_encryption(passphrase)
            assert self._cipher
            for cid, p in plain_cases:
                self._conn.execute("UPDATE cases SET payload=? WHERE id=?", (self._cipher.encrypt(p), cid))
            for rid, p in plain_recs:
                self._conn.execute("UPDATE records SET payload=? WHERE id=?", (self._cipher.encrypt(p), rid))
            self._conn.commit()
            self._conn.execute("VACUUM")

    def _enc(self, obj: dict[str, Any]) -> str:
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        return self._cipher.encrypt(text) if self._cipher else text

    def _dec(self, text: str) -> dict[str, Any]:
        if text.startswith("enc1:"):
            if not self._cipher:
                raise LockedError("Datensatz ist verschluesselt und die Datenbank gesperrt.")
            text = self._cipher.decrypt(text)
        return json.loads(text)

    # ----------------------------------------------------------------- cases
    def save_case(self, case: Case) -> None:
        case.updated_at = now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO cases(id,created_at,updated_at,payload) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload",
                (case.id, case.created_at, case.updated_at, self._enc(case.to_dict())))
            self._conn.commit()

    def get_case(self, case_id: str) -> Optional[Case]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM cases WHERE id=?", (case_id,)).fetchone()
        return Case.from_dict(self._dec(row["payload"])) if row else None

    def list_cases(self) -> list[Case]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM cases ORDER BY created_at DESC").fetchall()
        return [Case.from_dict(self._dec(r["payload"])) for r in rows]

    def case_exists(self, case_id: str) -> bool:
        with self._lock:
            return self._conn.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone() is not None

    def delete_case(self, case_id: str, *, purge_audit: bool = False) -> int:
        """Loescht den Fall und alle zugehoerigen Datensaetze unwiderruflich (secure_delete + VACUUM).

        Das Audit-Protokoll enthaelt keine Rechercheinhalte und bleibt standardmaessig
        erhalten (Nachvollziehbarkeit); ``purge_audit=True`` entfernt auch diese Eintraege
        (die Hash-Kette wird dabei bewusst neu aufgebaut, siehe AuditLog.rechain)."""
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM records WHERE case_id=?", (case_id,)).fetchone()[0]
            self._conn.execute("DELETE FROM records WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM cases WHERE id=?", (case_id,))
            if purge_audit:
                self._conn.execute("DELETE FROM audit WHERE case_id=?", (case_id,))
            self._conn.commit()
            self._conn.execute("VACUUM")
        return int(n)

    # --------------------------------------------------------------- records
    def put(self, kind: str, obj: Model, *, ts: str = "", ref: str = "") -> None:
        if kind not in KINDS and kind not in ("node", "edge"):
            raise StorageError(f"Unbekannte Datensatzart: {kind}")
        data = obj.to_dict() if isinstance(obj, Model) else dict(obj)  # type: ignore[arg-type]
        with self._lock:
            self._conn.execute(
                "INSERT INTO records(id,case_id,kind,ts,ref,payload) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, ref=excluded.ref, payload=excluded.payload",
                (data["id"], data["case_id"], kind, ts or data.get("ts") or data.get("created_at") or now_iso(),
                 ref, self._enc(data)))
            self._conn.commit()

    def put_raw(self, kind: str, data: dict[str, Any], *, ts: str = "", ref: str = "") -> None:
        """Fuer Graph-Knoten/-Kanten (Dicts, die nicht als Model gefuehrt werden)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO records(id,case_id,kind,ts,ref,payload) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, ref=excluded.ref, payload=excluded.payload",
                (data["id"], data["case_id"], kind, ts or data.get("created_at") or now_iso(), ref, self._enc(data)))
            self._conn.commit()

    def list_raw(self, kind: str, case_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM records WHERE case_id=? AND kind=? ORDER BY ts, id", (case_id, kind)).fetchall()
        return [self._dec(r["payload"]) for r in rows]

    def get_raw(self, record_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM records WHERE id=?", (record_id,)).fetchone()
        return self._dec(row["payload"]) if row else None

    def list(self, kind: str, case_id: str) -> list:
        cls = KINDS[kind]
        return [cls.from_dict(d) for d in self.list_raw(kind, case_id)]

    def get(self, kind: str, record_id: str):
        d = self.get_raw(record_id)
        return KINDS[kind].from_dict(d) if d else None

    def delete_record(self, record_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM records WHERE id=?", (record_id,))
            self._conn.commit()
            self._conn.execute("VACUUM")

    def delete_records(self, ids: Iterable[str]) -> None:
        ids = list(ids)
        with self._lock:
            self._conn.executemany("DELETE FROM records WHERE id=?", [(i,) for i in ids])
            self._conn.commit()
            self._conn.execute("VACUUM")

    # -------------------------------------------------------------- queries
    def count_active_queries(self, case_id: str, since_iso: str) -> int:
        return sum(1 for q in self.list("query", case_id)
                   if q.mode is QueryMode.ACTIVE and (q.created_at or "") >= since_iso)

    def last_active_query_ts(self, case_id: str, adapter_id: str) -> str:
        times = [q.created_at for q in self.list("query", case_id)
                 if q.mode is QueryMode.ACTIVE and q.adapter_id == adapter_id]
        return max(times) if times else ""

    # ------------------------------------------------------------ audit raw
    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def close(self) -> None:
        with self._lock:
            self._conn.close()
