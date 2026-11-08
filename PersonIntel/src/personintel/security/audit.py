"""Manipulationssichtbares Audit-Protokoll (Hash-Kette, ohne Rechercheinhalte).

Kennungen werden nie im Klartext protokolliert, sondern als HMAC-Referenz mit einem
lokalen, zufaelligen Schluessel (``target_ref``). So laesst sich nachvollziehen, *dass*
und *wie oft* eine Kennung abgefragt wurde, ohne sie im Protokoll offenzulegen.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..core.ids import now_iso
from ..storage.repository import Repository

GENESIS = "0" * 64
_SENSITIVE_KEY = re.compile(r"(key|secret|pass|token|credential|auth)", re.I)


@dataclass
class AuditEntry:
    seq: int
    ts: str
    case_id: str
    action: str
    detail: dict
    prev_hash: str
    hash: str


def _clean(detail: Optional[dict]) -> dict:
    out: dict[str, Any] = {}
    for k, v in (detail or {}).items():
        if _SENSITIVE_KEY.search(k):
            continue
        out[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return out


def _digest(prev: str, ts: str, case_id: str, action: str, payload: str) -> str:
    return hashlib.sha256("|".join((prev, ts, case_id or "", action, payload)).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, repo: Repository, actor: str = "local-user"):
        self.repo = repo
        self.actor = actor
        if not repo.get_meta("audit_key"):
            repo.set_meta("audit_key", os.urandom(32).hex())

    def target_ref(self, value: str) -> str:
        key = bytes.fromhex(self.repo.get_meta("audit_key") or "")
        return hmac.new(key, value.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    def record(self, action: str, *, case_id: str = "", adapter_id: str = "", target_ref: str = "",
               detail: Optional[dict] = None) -> AuditEntry:
        ts = now_iso()
        body = {"actor": self.actor, "adapter": adapter_id, "target_ref": target_ref, **_clean(detail)}
        payload = json.dumps(body, sort_keys=True, ensure_ascii=False)
        with self.repo.lock:
            row = self.repo.conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            h = _digest(prev, ts, case_id, action, payload)
            cur = self.repo.conn.execute(
                "INSERT INTO audit(ts,case_id,action,payload,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                (ts, case_id, action, payload, prev, h))
            self.repo.conn.commit()
            seq = int(cur.lastrowid)
        return AuditEntry(seq, ts, case_id, action, body, prev, h)

    def entries(self, case_id: Optional[str] = None) -> list[AuditEntry]:
        q = "SELECT * FROM audit"
        args: tuple = ()
        if case_id:
            q += " WHERE case_id=?"
            args = (case_id,)
        q += " ORDER BY seq"
        with self.repo.lock:
            rows = self.repo.conn.execute(q, args).fetchall()
        return [AuditEntry(r["seq"], r["ts"], r["case_id"] or "", r["action"], json.loads(r["payload"]),
                           r["prev_hash"], r["hash"]) for r in rows]

    def verify(self) -> tuple[bool, Optional[int]]:
        """Prueft die gesamte Kette. Liefert (ok, erste_fehlerhafte_seq)."""
        with self.repo.lock:
            rows = self.repo.conn.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        prev = GENESIS
        for r in rows:
            if r["prev_hash"] != prev or r["hash"] != _digest(
                    prev, r["ts"], r["case_id"] or "", r["action"], r["payload"]):
                return False, int(r["seq"])
            prev = r["hash"]
        return True, None

    def rechain(self) -> None:
        """Baut die Kette nach einem bewussten Loeschen (purge_audit) neu auf und protokolliert dies."""
        with self.repo.lock:
            rows = self.repo.conn.execute("SELECT * FROM audit ORDER BY seq").fetchall()
            prev = GENESIS
            for r in rows:
                h = _digest(prev, r["ts"], r["case_id"] or "", r["action"], r["payload"])
                self.repo.conn.execute("UPDATE audit SET prev_hash=?, hash=? WHERE seq=?", (prev, h, r["seq"]))
                prev = h
            self.repo.conn.commit()
        self.record("audit.rechain", detail={"reason": "purge"})
