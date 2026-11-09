"""Gemeinsame Testhilfen.

Die "lokalen Tools" sind echte, ausfuehrbare Skripte, die die *dokumentierte* Ausgabe der Originale
nachbilden (CSV-Dateien, JSON-Dateien, Textausgabe). Sie pruefen damit die tatsaechliche Prozess-,
Datei- und Parsing-Logik der Adapter - nicht die Originaltools. Die Anbieter-APIs werden durch einen
lokalen HTTP-Server mit dokumentiertem Antwortformat ersetzt.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import stat
import sys
import textwrap
import threading
import urllib.parse
from pathlib import Path

import pytest

from personintel.api import (ActiveConfirmation, AppPaths, Engine, Purpose, QueryKind)
from personintel.security.credentials import CredentialStore, EncryptedFileBackend


def write_tool(bin_dir: Path, name: str, body: str) -> Path:
    path = bin_dir / name
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def bin_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{d}:/usr/bin:/bin")
    for k in list(os.environ):
        if k.startswith("PERSONINTEL_"):
            monkeypatch.delenv(k, raising=False)
    return d


@pytest.fixture
def engine(tmp_path, bin_dir):
    paths = AppPaths(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    store = CredentialStore(EncryptedFileBackend(paths.credentials_path))
    store.backend.unlock("test-passphrase")
    eng = Engine(paths, credential_store=store)
    eng.settings.limits.min_active_interval_seconds = 0.0
    yield eng
    eng.close()


PURPOSE_TEXT = "Verifikation einer Quelle fuer einen Artikel ueber Foerdermittel"


def make_case(eng: Engine, *, active: bool = True, name: str = "Testfall"):
    case = eng.create_case(name)
    return eng.set_purpose(case.id, Purpose(category="journalism", description=PURPOSE_TEXT,
                                            authorized_by="Redaktionsleitung", active_checks_allowed=active))


def confirm(value: str) -> ActiveConfirmation:
    return ActiveConfirmation(typed_target=value, acknowledges_third_party_contact=True,
                              acknowledges_terms_of_service=True, note="test")


def run(eng: Engine, case_id: str, adapter_id: str, kind: str, value: str, *, options=None, timeout: float = 60):
    """Registriert die Kennung, startet die Abfrage mit Bestaetigung und wartet auf das Ergebnis."""
    kind = QueryKind(kind)
    existing = [t for t in eng.targets(case_id) if t.kind is kind and t.value.lower() == value.lower()]
    t = existing[0] if existing else eng.add_target(case_id, kind, value)
    rec = eng.run_query(case_id, adapter_id, t.id, confirmation=confirm(t.value), options=options)
    rec = eng.wait(rec.id, timeout)
    fs = [f for f in eng.findings(case_id) if f.query_id == rec.id]
    return rec, fs


# ----------------------------------------------------------------------------
# Lokaler HTTP-Server fuer Anbieter-APIs (dokumentiertes Antwortformat)
# ----------------------------------------------------------------------------
class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "FakeVendor/1"

    def log_message(self, *a):  # still
        pass

    def _hdrs(self) -> dict:
        """Header-Namen sind laut HTTP gross-/kleinschreibungsunabhaengig -> fuer Tests normalisieren."""
        return {k.lower(): v for k, v in self.headers.items()}

    def _send(self, status: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # Pipl: application/x-www-form-urlencoded
        n = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        self.server.calls.append(("POST", self.path, form, self._hdrs()))
        if form.get("key") != "good-key":
            return self._send(403, {"error": "invalid key"})
        if form.get("email") == "clark.kent@example.com":
            return self._send(200, {"@persons_count": 1, "person": {"names": [{"display": "Clark Kent"}]}})
        return self._send(200, self.server.pipl_response)

    def do_GET(self):  # Spokeo: X-api-key
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        self.server.calls.append(("GET", u.path, q, self._hdrs()))
        if self.headers.get("X-api-key") != "good-key":
            return self._send(403, {"message": "forbidden"})
        if self.server.spokeo_status != 200:
            return self._send(self.server.spokeo_status, {"message": "limit"})
        return self._send(200, self.server.spokeo_response)


class FakeVendorServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls: list = []
        self.spokeo_status = 200
        self.pipl_response = {"@search_id": "1", "@persons_count": 1,
                              "person": {"names": [{"display": "Erika Beispiel"}],
                                         "emails": [{"address": "erika@example.org"}],
                                         "addresses": [{"display": "Musterstr. 1, Berlin"}],
                                         "dob": {"display": "1980-01-01"},
                                         "usernames": [{"content": "erika_b"}],
                                         "urls": [{"url": "https://example.org/erika"}],
                                         "jobs": [{"display": "Redakteurin bei Beispiel GmbH"}]},
                              "possible_persons": [{"names": [{"display": "Erika B."}], "@match": 0.4}]}
        self.spokeo_response = {
            "data": {"owners": [{"id": 77, "first_name": "Erika", "last_name": "Beispiel", "age": 44,
                                 "is_current_owner": True, "phones": ["2125550100"],
                                 "emails": [{"email": "erika@example.org"}],
                                 "addresses": [{"street": "Musterstr. 1"}],
                                 "relatives": [{"name": "Max Beispiel"}], "date_of_birth": "1980-01-01"}],
                     "social_profiles": [{"network": "mastodon", "profile_url": "https://example.social/@erika",
                                          "is_primary_match": True, "username": "erika"}]},
            "metadata": {"request_id": "r-1"}}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


@pytest.fixture
def vendor_server():
    srv = FakeVendorServer()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
