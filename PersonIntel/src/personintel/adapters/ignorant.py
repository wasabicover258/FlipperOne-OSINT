"""Ignorant (megadose/ignorant) - Registrierungspruefung einer Rufnummer.

Dokumentierte Schnittstelle: CLI ``ignorant <laendervorwahl> <nummer>`` sowie die Python-Module
``ignorant.modules.*`` (Funktion ``<modul>(phone, country_code, client, out)``; Ausgabe je Modul:
``{"name","domain","method","frequent_rate_limit","rateLimit","exists"}``). Die Textausgabe der CLI ist
nicht formal dokumentiert, daher nutzt dieser Adapter die dokumentierten Module in einem Hilfsprozess
(derselbe Python-Interpreter, in dem Ignorant installiert ist) und liest strukturierte Daten.

Kontrollen:
* **Aktive Pruefung** (kontaktiert Amazon/Instagram/Snapchat etc. mit der Nummer) -> gesonderte Bestaetigung.
* Module laufen *sequenziell*; beim ersten Rate-Limit wird abgebrochen. Kein Umgehen von CAPTCHA,
  Zugriffsbeschraenkungen oder Rate-Limits, kein Wiederholen, kein IP-Wechsel.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Optional

from ..core.errors import AdapterError, AdapterNotAvailable, QueryCancelled
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._local import LocalToolAdapter
from ._norm import make_finding, make_source, truthy
from ._process import clean_env, find_executable
from .base import Capability, ConfigField, InstallInfo, RawResult

RUNNER_SOURCE = r'''
import importlib, json, pkgutil, sys
import httpx, trio
import ignorant.modules as _m

async def _main(phone, cc):
    results, stopped = [], ""
    async with httpx.AsyncClient() as client:
        mods = sorted((i for i in pkgutil.walk_packages(_m.__path__, _m.__name__ + ".") if not i.ispkg),
                      key=lambda i: i.name)
        for info in mods:
            name = info.name.rsplit(".", 1)[1]
            try:
                fn = getattr(importlib.import_module(info.name), name, None)
            except Exception as exc:
                results.append({"name": name, "error": type(exc).__name__})
                continue
            if fn is None:
                continue
            out = []
            try:
                await fn(phone, cc, client, out)
            except Exception as exc:
                out = [{"name": name, "domain": "", "error": type(exc).__name__}]
            results.extend(out)
            if any(o.get("rateLimit") for o in out):
                stopped = name  # Rate-Limit respektieren: nicht fortfahren, nicht wiederholen
                break
    print(json.dumps({"results": results, "stopped_at_rate_limit": stopped}))

trio.run(_main, sys.argv[1], sys.argv[2])
'''


def _shebang_python(script: str) -> Optional[str]:
    try:
        first = Path(script).read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None
    if first.startswith("#!"):
        parts = first[2:].strip().split()
        if parts and Path(parts[0]).name == "env" and len(parts) > 1:
            return find_executable(parts[1])
        if parts and Path(parts[0]).exists():
            return parts[0]
    return None


class IgnorantAdapter(LocalToolAdapter):
    id = "ignorant"
    name = "Ignorant"
    category = "Telefonnummern"
    description = "Prüft, ob eine Rufnummer bei Diensten registriert ist (aktive Prüfung, Rate-Limits werden respektiert)."
    homepage = "https://github.com/megadose/ignorant"
    executable_name = "ignorant"
    version_argv = ()
    install_text = "Installation: pipx install ignorant (oder pip install ignorant)."
    config_fields: ClassVar[tuple[ConfigField, ...]] = LocalToolAdapter.config_fields + (
        ConfigField("python_path", "Python-Interpreter mit Ignorant (optional)",
                    help="Nur nötig, wenn der Interpreter nicht aus dem 'ignorant'-Skript ermittelt werden kann."),
    )

    def _python(self) -> Optional[str]:
        override = str(self.config.get("python_path", "") or "")
        if override:
            return override if Path(override).is_file() else None
        exe = self.exe()
        if exe:
            py = _shebang_python(exe)
            if py:
                return py
        try:  # im selben Interpreter installiert?
            import importlib.util
            if importlib.util.find_spec("ignorant"):
                return sys.executable
        except Exception:
            pass
        return None

    def detect_installation(self) -> InstallInfo:
        py = self._python()
        if not py:
            return InstallInfo(False, message="Ignorant wurde nicht gefunden.")
        return InstallInfo(True, path=self.exe() or py or "", message=f"Interpreter: {py}")

    def get_capabilities(self) -> list[Capability]:
        ok = self._python() is not None
        return [Capability(
            QueryKind.PHONE, QueryMode.ACTIVE, "Registrierungsprüfung (aktive Abfrage)",
            "Kontaktiert Drittdienste mit der Rufnummer. Nur für ausdrücklich autorisierte Prüfungen; "
            "bei Rate-Limit wird abgebrochen (keine Umgehung).",
            available=ok, reason="" if ok else self.install_hint())]

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.PHONE)
        py = self._python()
        if not py:
            raise AdapterNotAvailable("Ignorant ist nicht installiert.", self.install_hint())
        try:
            import phonenumbers
            parsed = phonenumbers.parse(aq.value, None)
            cc, national = str(parsed.country_code), str(parsed.national_number)
        except Exception as exc:
            raise AdapterError(f"Rufnummer konnte nicht in Ländervorwahl/Nummer zerlegt werden: {exc}") from exc
        started = now_iso()
        with tempfile.TemporaryDirectory(prefix="pi-ignorant-") as tmp:
            script = Path(tmp) / "runner.py"
            script.write_text(RUNNER_SOURCE, encoding="utf-8")
            res = self.runner.run(aq.query_id, [py, "-I", str(script), national, cc], cwd=tmp,
                                  timeout=self.timeout(), env=clean_env())
        if res.cancelled:
            raise QueryCancelled("Abfrage abgebrochen.")
        if res.timed_out:
            raise AdapterError("Ignorant: Zeitlimit überschritten.")
        last = next((ln for ln in reversed(res.stdout.splitlines()) if ln.strip().startswith("{")), "")
        if not last:
            raise AdapterError(f"Ignorant lieferte keine auswertbare Ausgabe (Code {res.returncode}): "
                               f"{res.stderr.strip()[-300:]}")
        try:
            payload = json.loads(last)
        except ValueError as exc:
            raise AdapterError(f"Ignorant-Ausgabe ist kein gültiges JSON: {exc}") from exc
        return self._raw(aq, started, payload)

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Ignorant (Registrierungsprüfung bei Drittdiensten)", active=True)
        batch.sources.append(src)
        found = failed = checked = 0
        failed_names: list[str] = []
        for r in raw.payload.get("results", []):
            checked += 1
            name = str(r.get("domain") or r.get("name") or "?")
            if r.get("error") or truthy(r.get("rateLimit")):
                failed += 1
                failed_names.append(name)
                continue
            if truthy(r.get("exists")):
                found += 1
                batch.findings.append(make_finding(
                    raw, src, "account", f"Rufnummer bei {name} registriert (laut Ignorant)", value=name,
                    url=f"https://{name}" if "." in name else "", status=FindingStatus.FOUND,
                    evidence=Evidence.INDICATION, data={"method": r.get("method", "")},
                    tags=["active-check", "registration-check"]))
        stopped = raw.payload.get("stopped_at_rate_limit") or ""
        batch.findings.append(make_finding(
            raw, src, "summary", f"Ignorant: {found} Treffer, {failed} fehlgeschlagen (von {checked} Modulen)",
            status=FindingStatus.INFO,
            data={"checked": checked, "found": found, "failed": failed, "failed_modules": failed_names,
                  "stopped_at_rate_limit": stopped,
                  "hinweis": "Rate-Limits wurden respektiert; die Abfrage wurde dort abgebrochen, nicht umgangen."}))
        if stopped:
            batch.notes.append(f"Rate-Limit bei Modul '{stopped}': Prüfung wurde abgebrochen (keine Umgehung).")
        return batch
