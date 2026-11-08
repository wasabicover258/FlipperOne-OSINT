"""PhoneInfoga (sundowndev/phoneinfoga v2) - Rufnummern-Metadaten.

Dokumentierte Schnittstellen (Swagger/README, verifiziert):
* CLI:  ``phoneinfoga scan -n <number>``, ``phoneinfoga serve [-p PORT] [--no-client]``
* REST: ``GET /api/v2/scanners`` (Bereitschaftspruefung), ``GET /api/numbers/{number}/scan/local``
        (lokale Analyse, Antwort ``{"success": bool, "result": {...}}``; als *deprecated* markiert, aber
        weiterhin Teil der veroeffentlichten API), ``GET /api/numbers/{number}/scan/googlesearch``
        (erzeugt nur Such-Links/Dorks - es wird nichts aufgerufen).

Sicherheit: Der REST-Server wird nur gestartet, wenn ``serve --help`` einen Schalter fuer die
Bind-Adresse anbietet (dann auf 127.0.0.1). Sonst wird die CLI-Ausgabe (``scan``) verwendet, damit
nie ein Dienst auf allen Netzwerkschnittstellen lauscht.

Es werden ausschliesslich *lokale* Scanner genutzt (kein Drittkontakt => passiv). Rufnummern-Metadaten
(Land, Leitungstyp, Carrier) sind Indizien: Carrier-Angaben koennen durch Portierung veraltet sein, und
eine Zuordnung zu einer Person wird **nicht** behauptet.
"""

from __future__ import annotations

import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
from typing import Any, Optional

from ..core.errors import AdapterError, QueryCancelled
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from . import _http
from ._local import LocalToolAdapter
from ._norm import make_finding, make_source
from ._process import clean_env, help_text
from .base import Capability, RawResult

_KV = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ()_/\-]{1,40}):\s+(\S.*?)\s*$")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _collect_links(obj: Any, category: str = "") -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(obj, dict):
        url = obj.get("URL") or obj.get("url") or obj.get("Url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            out.append({"category": category, "url": url, "dork": str(obj.get("Dork") or obj.get("dork") or "")})
        for k, v in obj.items():
            out.extend(_collect_links(v, str(k) if not category else category))
    elif isinstance(obj, list):
        for i in obj:
            out.extend(_collect_links(i, category))
    return out


class PhoneInfogaAdapter(LocalToolAdapter):
    id = "phoneinfoga"
    name = "PhoneInfoga"
    category = "Telefonnummern"
    description = "Rufnummern-Metadaten (Land, Format, Leitungstyp, Carrier) und manuelle Suchlinks – ohne Personenzuordnung."
    homepage = "https://github.com/sundowndev/phoneinfoga"
    executable_name = "phoneinfoga"
    version_argv = ("version",)
    install_text = "Installation: Binary von https://github.com/sundowndev/phoneinfoga/releases (nach PATH legen)."

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._servers: dict[str, subprocess.Popen] = {}
        self._cancel: set[str] = set()
        self._lock = threading.Lock()

    def get_capabilities(self) -> list[Capability]:
        return [Capability(
            QueryKind.PHONE, QueryMode.PASSIVE, "Rufnummern-Metadaten (lokal)",
            "Lokale Analyse der Rufnummer; Option 'footprint_links' erzeugt zusätzlich manuelle Suchlinks "
            "(werden nicht aufgerufen). Keine Behauptung einer Personenzuordnung.",
            available=bool(self.exe()), reason="" if self.exe() else self.install_hint())]

    # ------------------------------------------------------------------
    def cancel_query(self, query_id: str) -> bool:
        with self._lock:
            self._cancel.add(query_id)
            srv = self._servers.get(query_id)
        ok = self.runner.cancel(query_id)
        if srv is not None:
            self._stop(srv)
            return True
        return ok

    @staticmethod
    def _stop(proc: subprocess.Popen) -> None:
        import os
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    @staticmethod
    def _host_flag(exe: str) -> Optional[str]:
        try:
            res = subprocess.run([exe, "serve", "--help"], capture_output=True, timeout=15, env=clean_env(),
                                 stdin=subprocess.DEVNULL, check=False)
            text = (res.stdout or b"").decode("utf-8", "replace") + (res.stderr or b"").decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r"--(host|address|listen-address|bind)\b", text)
        return f"--{m.group(1)}" if m else None

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.PHONE)
        exe = self.require_exe()
        started = now_iso()
        version = self.tool_version(exe)
        want_links = bool(aq.option("footprint_links", False))
        number_digits = aq.value.lstrip("+")
        host_flag = self._host_flag(exe)
        payload: dict[str, Any]
        if host_flag:
            try:
                payload = self._via_rest(aq.query_id, exe, host_flag, number_digits, want_links)
                payload["transport"] = "rest"
                return self._raw(aq, started, payload, version=version)
            except QueryCancelled:
                raise
            except AdapterError as exc:  # REST-Weg gescheitert -> CLI-Fallback, Grund bleibt sichtbar
                rest_error = str(exc)
        else:
            rest_error = "serve bietet keinen Schalter für die Bind-Adresse; REST wird aus Sicherheitsgründen nicht genutzt."
        payload = self._via_cli(aq.query_id, exe, aq.value)
        payload["transport"] = "cli"
        payload["rest_note"] = rest_error
        return self._raw(aq, started, payload, version=version, errors=[rest_error] if host_flag else [])

    def _via_rest(self, query_id: str, exe: str, host_flag: str, number: str, want_links: bool) -> dict[str, Any]:
        port = _free_port()
        proc = subprocess.Popen([exe, "serve", "--no-client", host_flag, "127.0.0.1", "-p", str(port)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                env=clean_env(), start_new_session=True)
        with self._lock:
            self._servers[query_id] = proc
        base = f"http://127.0.0.1:{port}/api"
        try:
            deadline = time.time() + 20
            while time.time() < deadline:
                with self._lock:
                    if query_id in self._cancel:
                        raise QueryCancelled("Abfrage abgebrochen.")
                if proc.poll() is not None:
                    raise AdapterError("PhoneInfoga-Server beendete sich unerwartet.")
                try:
                    r = _http.request("GET", f"{base}/v2/scanners", timeout=2)
                    if r.status == 200:
                        break
                except AdapterError:
                    time.sleep(0.4)
            else:
                raise AdapterError("PhoneInfoga-Server wurde nicht rechtzeitig bereit.")
            enc = urllib.parse.quote(number, safe="")
            out: dict[str, Any] = {"scanners": (r.json if isinstance(r.json, (dict, list)) else None)}
            local = _http.request("GET", f"{base}/numbers/{enc}/scan/local", timeout=30)
            if local.status != 200 or not isinstance(local.json, dict) or not local.json.get("success", False):
                raise AdapterError(f"Lokaler Scan fehlgeschlagen (HTTP {local.status}): {local.text[:200]}")
            out["local"] = local.json.get("result")
            if want_links:
                g = _http.request("GET", f"{base}/numbers/{enc}/scan/googlesearch", timeout=30)
                if g.status == 200 and isinstance(g.json, dict) and g.json.get("success", False):
                    out["googlesearch"] = g.json.get("result")
            return out
        finally:
            self._stop(proc)
            with self._lock:
                self._servers.pop(query_id, None)
                self._cancel.discard(query_id)

    def _via_cli(self, query_id: str, exe: str, number: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="pi-phoneinfoga-") as tmp:
            res = self.runner.run(query_id, [exe, "scan", "-n", number], cwd=tmp, timeout=self.timeout(),
                                  env=clean_env())
        if res.cancelled:
            raise QueryCancelled("Abfrage abgebrochen.")
        if res.timed_out:
            raise AdapterError("PhoneInfoga: Zeitlimit überschritten.")
        if res.returncode not in (0, None):
            raise AdapterError(f"PhoneInfoga endete mit Code {res.returncode}: {res.stderr.strip()[:300]}")
        return {"cli_text": res.stdout[:20000]}

    # ------------------------------------------------------------------
    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, f"PhoneInfoga ({raw.payload.get('transport', '?')}, lokaler Scan)", kind="tool_output")
        batch.sources.append(src)
        note = ("Metadaten zur Rufnummer – keine Zuordnung zu einer Person belegt; Carrier-/Regionsangaben "
                "können durch Rufnummernportierung veraltet sein.")
        local = raw.payload.get("local")
        if isinstance(local, dict) and local:
            summary = ", ".join(f"{k}={v}" for k, v in local.items() if isinstance(v, (str, int, float, bool)) and v != "")
            batch.findings.append(make_finding(
                raw, src, "metadata", "Rufnummern-Metadaten (lokaler Scan)", value=summary[:300],
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION, data={"result": local, "hinweis": note},
                tags=["phone-metadata"]))
        text = raw.payload.get("cli_text")
        if text:
            kv = {m.group(1).strip(): m.group(2).strip() for line in text.splitlines() if (m := _KV.match(line))}
            batch.findings.append(make_finding(
                raw, src, "metadata", "Rufnummern-Metadaten (CLI-Ausgabe, nicht strukturiert)",
                value=", ".join(f"{k}={v}" for k, v in list(kv.items())[:12])[:300], status=FindingStatus.FOUND,
                evidence=Evidence.INDICATION, data={"parsed_lines": kv, "excerpt": text[:4000], "hinweis": note},
                tags=["phone-metadata", "unstructured"]))
            batch.notes.append("CLI-Ausgabe wurde zeilenweise ('Name: Wert') ausgewertet; Format ist nicht formal dokumentiert.")
        for link in _collect_links(raw.payload.get("googlesearch"))[:50]:
            batch.findings.append(make_finding(
                raw, src, "link_hint", f"Suchlink (manuell prüfen): {link['category'] or 'allgemein'}",
                value=link["dork"], url=link["url"], status=FindingStatus.INFO, evidence=Evidence.UNCONFIRMED,
                data={"hinweis": "Von PhoneInfoga erzeugter Such-Link; es wurde nichts abgerufen. Kein Treffer."},
                tags=["manual-check"]))
        if not batch.findings:
            batch.notes.append("PhoneInfoga lieferte keine auswertbaren Daten.")
        for e in raw.errors:
            batch.notes.append(e)
        return batch
