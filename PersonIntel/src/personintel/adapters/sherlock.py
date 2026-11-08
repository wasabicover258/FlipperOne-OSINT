"""Sherlock (sherlock-project/sherlock) - Benutzername -> oeffentliche Profile.

Verifizierte CLI: ``sherlock USERNAME --csv --print-found --no-color --timeout N``; die CSV-Datei
``<username>.csv`` (Spalten ``username,name,url_main,url_user,exists,http_status,response_time_s``)
wird im Arbeitsverzeichnis erzeugt. Sherlock ruft oeffentliche Profil-URLs bei hunderten Seiten ab
und ist daher eine **aktive Pruefung**.

Wichtig: Identischer Benutzername ist *kein* Beleg fuer dieselbe Person. Befunde bleiben Indizien;
Zusammenhaenge entstehen ausschliesslich durch manuelle Uebernahme in den Recherchegraphen.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

from ..core.errors import AdapterError, QueryCancelled
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._local import LocalToolAdapter
from ._norm import make_finding, make_source
from ._process import clean_env, help_text
from .base import Capability, RawResult


class SherlockAdapter(LocalToolAdapter):
    id = "sherlock"
    name = "Sherlock"
    category = "Benutzernamen und öffentliche Profile"
    description = "Sucht öffentlich auffindbare Profile zu einem Benutzernamen (aktive Prüfung)."
    homepage = "https://github.com/sherlock-project/sherlock"
    executable_name = "sherlock"
    version_argv = ("--version",)
    install_text = "Installation: pipx install sherlock-project (oder pip install sherlock-project)."

    def get_capabilities(self) -> list[Capability]:
        return [Capability(
            QueryKind.USERNAME, QueryMode.ACTIVE, "Profile zu Benutzernamen suchen",
            "Ruft öffentliche Profil-URLs bei vielen Plattformen ab. Treffer sind Indizien – gleicher "
            "Benutzername ≠ gleiche Person.",
            available=bool(self.exe()), reason="" if self.exe() else self.install_hint())]

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.USERNAME)
        exe = self.require_exe()
        started = now_iso()
        help_ = help_text(exe)
        argv = [exe, aq.value, "--csv", "--print-found", "--no-color"]
        if "--timeout" in help_ or not help_:
            argv += ["--timeout", "30"]
        with tempfile.TemporaryDirectory(prefix="pi-sherlock-") as tmp:
            res = self.runner.run(aq.query_id, argv, cwd=tmp, timeout=self.timeout(), env=clean_env())
            if res.cancelled:
                raise QueryCancelled("Abfrage abgebrochen.")
            if res.timed_out:
                raise AdapterError("Sherlock: Zeitlimit überschritten.")
            rows: list[dict[str, str]] = []
            for f in sorted(Path(tmp).glob("*.csv")):
                with f.open(encoding="utf-8", newline="") as fh:
                    rows.extend(csv.DictReader(fh))
            if not rows and res.returncode not in (0, None):
                raise AdapterError(f"Sherlock endete mit Code {res.returncode}: {res.stderr.strip()[:300]}")
        return self._raw(aq, started, {"rows": rows, "username": aq.value}, version=self.tool_version(exe))

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Sherlock-Lauf (öffentliche Profil-URLs)", active=True)
        batch.sources.append(src)
        claimed = unknown = 0
        username = raw.payload.get("username", "")
        for r in raw.payload.get("rows", []):
            status = (r.get("exists") or "").strip().lower()
            if status == "claimed":
                claimed += 1
                batch.findings.append(make_finding(
                    raw, src, "profile", f"Profil „{username}“ auf {r.get('name', '?')} (laut Sherlock)",
                    value=username, url=(r.get("url_user") or "").strip(), status=FindingStatus.FOUND,
                    evidence=Evidence.INDICATION,
                    data={"platform": r.get("name", ""), "url_main": r.get("url_main", ""),
                          "http_status": r.get("http_status", ""), "check_status": "Claimed",
                          "identity_link": "none",
                          "hinweis": "Gleicher Benutzername ist kein Beleg für dieselbe Person."},
                    tags=["username-match", "unreviewed-identity"]))
            elif status:
                unknown += 1
        batch.findings.append(make_finding(
            raw, src, "summary", f"Sherlock: {claimed} Profile gefunden für „{username}“",
            status=FindingStatus.INFO,
            data={"claimed": claimed, "other_status": unknown,
                  "hinweis": "Keine automatische Gleichsetzung von Personen anhand des Benutzernamens."}))
        return batch
