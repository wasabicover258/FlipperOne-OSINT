"""Holehe (megadose/holehe) - E-Mail -> registrierte Konten.

Schnittstelle (verifiziert gegen die oeffentliche Dokumentation/den Quelltext):
``holehe <email> [--only-used] [--no-color] [--no-clear] [--no-password-recovery] [--csv] [--timeout N]``.
Die CSV-Ausgabe (``holehe_<zeit>_<email>_results.csv``) wird im Arbeitsverzeichnis erzeugt und hier
ausgewertet. Holehe fuehrt Registrierungs-/Passwort-Reset-Pruefungen bei Drittdiensten durch und
ist deshalb eine **aktive Pruefung**.

Statusmodell (Auftrag: bestaetigt / moeglich / fehlgeschlagen):
* ``found``    - Dienst meldet: E-Mail registriert (Indiz).
* ``possible`` - Treffer, aber Modul ist als haeufig ratelimitiert/unzuverlaessig markiert (unbestaetigt).
* ``failed``   - Abfrage fehlgeschlagen (Rate-Limit/Fehler) - sagt nichts ueber das Konto aus.
Keine Treffer-/Fehlschlag-Details werden fuer "nicht registriert" gespeichert (Datensparsamkeit).
"""

from __future__ import annotations

import csv
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..core.errors import AdapterError, QueryCancelled
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._local import LocalToolAdapter
from ._norm import make_finding, make_source, truthy
from ._process import clean_env, help_text
from .base import Capability, RawResult


class HoleheAdapter(LocalToolAdapter):
    id = "holehe"
    name = "Holehe"
    category = "E-Mail-Recherche"
    description = "Prüft, bei welchen Diensten eine E-Mail-Adresse registriert ist (aktive Prüfung)."
    homepage = "https://github.com/megadose/holehe"
    executable_name = "holehe"
    version_argv = ()  # kein dokumentierter Versionsschalter; Version bleibt 'unbekannt'
    install_text = "Installation: pipx install holehe (oder pip install holehe)."

    def get_capabilities(self) -> list[Capability]:
        return [Capability(
            QueryKind.EMAIL, QueryMode.ACTIVE, "Konto-Zuordnungen prüfen",
            "Holehe nutzt Registrierungs-/Passwort-Reset-Abläufe fremder Dienste. Einsatz nur autorisiert und "
            "im Rahmen der Nutzungsbedingungen. Rate-Limits werden nicht umgangen.",
            available=bool(self.exe()), reason="" if self.exe() else self.install_hint())]

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.EMAIL)
        exe = self.require_exe()
        started = now_iso()
        help_ = help_text(exe)
        argv = [exe, aq.value, "--no-color"]
        for flag in ("--no-clear", "--no-password-recovery"):
            if flag in help_:
                argv.append(flag)
        argv += ["--csv"] if "--csv" in help_ or not help_ else []
        argv += ["--timeout", "10"] if "--timeout" in help_ else []
        with tempfile.TemporaryDirectory(prefix="pi-holehe-") as tmp:
            res = self.runner.run(aq.query_id, argv, cwd=tmp, timeout=self.timeout(), env=clean_env())
            if res.cancelled:
                raise QueryCancelled("Abfrage abgebrochen.")
            if res.timed_out:
                raise AdapterError("Holehe: Zeitlimit überschritten.")
            rows: list[dict[str, str]] = []
            for f in sorted(Path(tmp).glob("holehe_*_results.csv")):
                with f.open(encoding="utf-8", newline="") as fh:
                    rows.extend(csv.DictReader(fh))
            if not rows and res.returncode not in (0, None):
                raise AdapterError(f"Holehe endete mit Code {res.returncode}: {res.stderr.strip()[:300]}")
            payload: dict[str, Any] = {"rows": rows, "stdout_fallback": []}
            if not rows:
                # Fallback: Textausgabe ("[+] domain" = registriert)
                payload["stdout_fallback"] = re.findall(r"^\[\+\]\s+(\S+)", res.stdout, flags=re.M)
        return self._raw(aq, started, payload, version=self.tool_version(exe))

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Holehe-Lauf (Registrierungsprüfung bei Drittdiensten)", active=True)
        batch.sources.append(src)
        checked = found = possible = failed = 0
        failed_modules: list[str] = []
        for r in raw.payload.get("rows", []):
            checked += 1
            domain = (r.get("domain") or r.get("name") or "").strip()
            if truthy(r.get("rateLimit")):
                failed += 1
                failed_modules.append(domain)
                continue
            if truthy(r.get("exists")):
                frequent = truthy(r.get("frequent_rate_limit"))
                status = FindingStatus.POSSIBLE if frequent else FindingStatus.FOUND
                evidence = Evidence.UNCONFIRMED if frequent else Evidence.INDICATION
                found += 0 if frequent else 1
                possible += 1 if frequent else 0
                batch.findings.append(make_finding(
                    raw, src, "account",
                    f"E-Mail bei {domain} registriert (laut Holehe)" + (" – möglich/unzuverlässiges Modul" if frequent else ""),
                    value=domain, url=f"https://{domain}" if domain else "", status=status, evidence=evidence,
                    data={"module": r.get("name", ""), "method": r.get("method", ""),
                          "frequent_rate_limit": frequent},
                    tags=["active-check", "registration-check"]))
        for d in raw.payload.get("stdout_fallback", []):
            checked += 1
            found += 1
            batch.findings.append(make_finding(
                raw, src, "account", f"E-Mail bei {d} registriert (laut Holehe-Textausgabe)", value=d,
                url=f"https://{d}", status=FindingStatus.FOUND, evidence=Evidence.INDICATION,
                data={"parsed_from": "stdout"}, tags=["active-check", "registration-check"]))
        batch.findings.append(make_finding(
            raw, src, "summary",
            f"Holehe: {found} Treffer, {possible} möglich, {failed} fehlgeschlagen (von {checked} Modulen)",
            status=FindingStatus.INFO,
            data={"checked": checked, "found": found, "possible": possible, "failed": failed,
                  "failed_modules": sorted(failed_modules),
                  "hinweis": "Fehlgeschlagene Abfragen (z. B. Rate-Limit) sagen nichts über ein Konto aus."}))
        batch.notes.append("Wiederherstellungs-Hinweise (teilweise E-Mail/Telefon) werden nicht übernommen.")
        return batch
