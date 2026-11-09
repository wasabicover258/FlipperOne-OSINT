"""Brueckenbetrieb (NDJSON): das Protokoll, auf das die Flipper-Oberflaeche sich stuetzt."""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from personintel.bridge import PROTOCOL_VERSION, Bridge
from conftest import PURPOSE_TEXT, write_tool

SHERLOCK = '''
import csv, sys
a = sys.argv[1:]
if "--version" in a: print("sherlock 0.16.0"); sys.exit(0)
if "--help" in a: print("usage: sherlock [--csv] [--print-found] [--no-color] [--timeout TIMEOUT]"); sys.exit(0)
u = a[0]
with open(f"{u}.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["username","name","url_main","url_user","exists","http_status","response_time_s"])
    w.writerow([u,"GitHub","https://github.com",f"https://github.com/{u}","Claimed",200,0.2])
    w.writerow([u,"Gone","https://gone.example",f"https://gone.example/{u}","Available",404,0.1])
'''


class Pipe:
    """Fuehrt Anfragen durch die Bruecke und sammelt die Antwortzeilen."""

    def __init__(self, engine):
        self.out = io.StringIO()
        self.bridge = Bridge(engine, self.out)

    def send(self, **req) -> list[dict]:
        req.setdefault("id", 1)
        start = self.out.tell()
        self.bridge.handle_line(json.dumps(req))
        self.out.seek(start)
        lines = [json.loads(l) for l in self.out.read().splitlines() if l.strip()]
        self.out.seek(0, io.SEEK_END)
        return lines

    def final(self, **req) -> dict:
        return self.send(**req)[-1]

    def events(self, kind: str, lines: list[dict]) -> list[dict]:
        return [l for l in lines if l.get("event") == kind]


@pytest.fixture
def pipe(engine):
    return Pipe(engine)


def _open_case(pipe, active=True):
    return pipe.final(op="case_open", purpose=PURPOSE_TEXT, authorized_by="Redaktion", active=active, days=1)


# ----------------------------------------------------------------- Protokoll
def test_hello_reports_version_and_protocol(pipe):
    r = pipe.final(op="hello")
    assert r["ok"] and r["protocol"] == PROTOCOL_VERSION
    assert r["adapters"] == 10 and r["schema"] == "1.0"


def test_unknown_and_broken_requests_do_not_crash(pipe):
    assert pipe.final(op="gibtsnicht")["error"].startswith("Unbekannte Anweisung")
    pipe.bridge.handle_line("kein json")
    pipe.bridge.handle_line("[1,2,3]")
    r = pipe.final(op="hello")
    assert r["ok"]                      # die Bruecke lebt weiter


def test_every_answer_carries_the_request_id(pipe):
    lines = pipe.send(op="status", id="abc")
    assert lines and all(l["id"] == "abc" for l in lines)
    assert lines[-1]["ok"] is True


def test_status_lists_all_ten_modules_with_real_state(pipe):
    lines = pipe.send(op="status")
    events = pipe.events("status", lines)
    assert len(events) == 10 and lines[-1]["count"] == 10
    for e in events:
        assert e["state"] and e["state_label"] and e["name"]
        if e["state"] != "available":
            assert e["requirement"] or e["message"]
    ids = [e["adapter"] for e in events]
    assert ids == ["holehe", "mosint", "sherlock", "phoneinfoga", "ignorant", "mrholmes",
                   "pipl", "spokeo", "shadowdragon", "babelstreet"]


def test_vendor_modules_are_reported_unavailable(pipe):
    events = pipe.events("status", pipe.send(op="status"))
    for aid in ("shadowdragon", "babelstreet"):
        e = next(x for x in events if x["adapter"] == aid)
        assert e["state"] == "unavailable_vendor" and e["requirement"]
        assert e["kinds"] == []


# -------------------------------------------------------------- Fall / Zweck
def test_query_without_case_is_refused(pipe):
    r = pipe.final(op="query", kind="username", value="jdoe")
    assert not r["ok"] and "Kein Fall" in r["error"]


def test_case_open_requires_a_concrete_purpose(pipe):
    r = pipe.final(op="case_open", purpose="zu kurz")
    assert not r["ok"] and "mindestens" in r["error"]
    r = pipe.final(op="case_open", purpose=PURPOSE_TEXT, category="unsinn")
    assert not r["ok"] and "Zweckkategorie" in r["error"]


def test_case_open_creates_and_reuses(pipe, engine):
    r = _open_case(pipe)
    assert r["ok"] and r["case"]["purpose_valid"]
    assert r["case"]["purpose"]["active_checks_allowed"] is True
    first = r["case"]["id"]
    again = _open_case(pipe)["case"]["id"]
    assert again == first                      # gleicher Gerätefall, Zweck erneuert
    assert len(engine.cases()) == 1
    fresh = pipe.final(op="case_open", purpose=PURPOSE_TEXT, new=True)["case"]["id"]
    assert fresh != first and len(engine.cases()) == 2


def test_case_info_and_targets(pipe):
    _open_case(pipe)
    r = pipe.final(op="target_add", kind="username", value="jdoe")
    assert r["ok"] and r["target"]["value"] == "jdoe"
    same = pipe.final(op="target_add", kind="username", value="JDOE")
    assert same["target"]["id"] == r["target"]["id"]      # keine Doppelregistrierung
    info = pipe.final(op="case_info")["case"]
    assert len(info["targets"]) == 1 and info["targets_max"] == 10


def test_invalid_target_is_refused(pipe):
    _open_case(pipe)
    for bad in ("a@example.org, b@example.org", "a@example.org b@example.org", "keine-mail"):
        r = pipe.final(op="target_add", kind="email", value=bad)
        assert not r["ok"], bad
        assert "E-Mail" in r["error"] or "Kennung" in r["error"], r["error"]


# ------------------------------------------------------------------ Abfrage
def test_active_query_needs_confirmation(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    lines = pipe.send(op="query", kind="username", value="jdoe")
    denied = pipe.events("denied", lines)
    assert any("Bestätigung" in d["reason"] or "Bestaetigung" in d["reason"] for d in denied)
    assert lines[-1]["findings"] == 0


def test_confirmed_active_query_streams_findings(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    lines = pipe.send(op="query", kind="username", value="jdoe", adapters=["sherlock"],
                      confirm={"typed_target": "jdoe", "third_party": True, "tos": True, "note": "flipper"})
    assert lines[-1]["ok"] and lines[-1]["started"] == ["sherlock"]
    started = pipe.events("started", lines)
    assert started and started[0]["mode"] == "active"
    findings = pipe.events("finding", lines)
    profile = [f for f in findings if f["type"] == "profile"]
    assert len(profile) == 1
    f = profile[0]
    assert f["url"] == "https://github.com/jdoe"
    assert f["evidence"] == "indication" and f["evidence_label"] == "Indiz"
    assert f["source"]["tool_version"] == "sherlock 0.16.0" and f["source"]["active"] is True
    assert f["source"]["retrieved_at"]
    done = pipe.events("query", lines)
    assert done and done[0]["state"] == "done"


def test_wrong_confirmation_is_refused(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    lines = pipe.send(op="query", kind="username", value="jdoe", adapters=["sherlock"],
                      confirm={"typed_target": "jemand.anderes", "third_party": True, "tos": True})
    assert any("stimmt nicht" in d["reason"] for d in pipe.events("denied", lines))


def test_passive_query_needs_no_confirmation(pipe, bin_dir):
    write_tool(bin_dir, "phoneinfoga", '''
import sys
a = sys.argv[1:]
if a[:1] == ["version"]: print("PhoneInfoga v2.11.0"); sys.exit(0)
if a[:2] == ["serve", "--help"]: print("Usage: serve [flags]\\n  -p, --port int"); sys.exit(0)
if a[:1] == ["scan"]:
    print("Results for local"); print("Country: DE"); print("Carrier: Example"); sys.exit(0)
sys.exit(1)
''')
    pipe.final(op="case_open", purpose=PURPOSE_TEXT, active=False, days=1)
    lines = pipe.send(op="query", kind="phone", value="+49 30 123456", adapters=["phoneinfoga"])
    assert lines[-1]["ok"] and lines[-1]["started"] == ["phoneinfoga"]
    assert pipe.events("started", lines)[0]["mode"] == "passive"


def test_unavailable_modules_are_skipped_not_failed(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    lines = pipe.send(op="query", kind="username", value="jdoe",
                      confirm={"typed_target": "jdoe", "third_party": True, "tos": True})
    r = lines[-1]
    assert "sherlock" in r["started"]
    # Nicht installierte und nicht freigegebene Module werden uebersprungen, mit Begruendung
    skipped = {s["adapter"]: s for s in pipe.events("skipped", lines)}
    assert {"spokeo", "shadowdragon", "babelstreet"} <= set(skipped)
    assert all(s["reason"] for s in skipped.values())
    assert r["findings"] >= 1                 # die uebrigen Module liefern trotzdem


def test_query_for_unsupported_kind(pipe):
    _open_case(pipe)
    r = pipe.final(op="query", kind="report_file", value="/nicht/vorhanden.txt", adapters=["sherlock"])
    assert not r["ok"] and "Kein Modul" in r["error"]


# ---------------------------------------------------------------- Ergebnisse
def test_findings_review_and_report(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    pipe.send(op="query", kind="username", value="jdoe", adapters=["sherlock"],
              confirm={"typed_target": "jdoe", "third_party": True, "tos": True})
    lines = pipe.send(op="findings")
    items = pipe.events("finding", lines)
    assert items and all(i["evidence"] in ("indication", "unconfirmed") for i in items)
    fid = next(i["finding_id"] for i in items if i["type"] == "profile")
    r = pipe.final(op="review", finding_id=fid, state="reviewed", note="Von der Quelle bestätigt",
                   evidence="confirmed")
    assert r["ok"] and r["evidence"] == "confirmed"
    r = pipe.final(op="review", finding_id=fid, state="reviewed", note="", evidence="confirmed")
    assert not r["ok"]                        # ohne Begruendung nicht erlaubt

    lines = pipe.send(op="report", format="md")
    text = "\n".join(l["text"] for l in pipe.events("line", lines))
    assert "Recherchebericht" in text and "unmittelbar belegt (1)" in text

    r = pipe.final(op="audit_verify")
    assert r["ok"] and r["intact"] and r["entries"] > 0


def test_report_to_file(pipe, tmp_path):
    _open_case(pipe)
    out = tmp_path / "bericht.md"
    r = pipe.final(op="report", format="md", output=str(out))
    assert r["ok"] and out.is_file() and oct(out.stat().st_mode)[-3:] == "600"
    r = pipe.final(op="report", format="docx")
    assert not r["ok"]


def test_graph_and_timeline(pipe, engine, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    pipe.send(op="query", kind="username", value="jdoe", adapters=["sherlock"],
              confirm={"typed_target": "jdoe", "third_party": True, "tos": True})
    lines = pipe.send(op="timeline")
    assert pipe.events("entry", lines)
    case_id = pipe.final(op="case_info")["case"]["id"]
    fid = [f.id for f in engine.findings(case_id) if f.type == "profile"][0]
    a = engine.graph.add_node(case_id, "person", "Quelle")
    b = engine.graph.add_node(case_id, "account", "github.com/jdoe", finding_ids=[fid])
    engine.graph.link(case_id, a.id, b.id, "has_account", [fid], note="Profil gefunden")
    lines = pipe.send(op="graph_nodes")
    assert len(pipe.events("node", lines)) == 2
    edge = pipe.events("edge", lines)[0]
    assert edge["source"] == "Quelle" and edge["evidence_label"] == "Indiz"


def test_suggestions_are_only_hints(pipe, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    _open_case(pipe)
    pipe.send(op="query", kind="username", value="jdoe", adapters=["sherlock"],
              confirm={"typed_target": "jdoe", "third_party": True, "tos": True})
    lines = pipe.send(op="graph_suggest")
    for s in pipe.events("suggestion", lines):
        assert s["evidence"] == "unconfirmed" and "kein Beleg" in s["description"]


# ----------------------------------------------------------- echter Prozess
def test_bridge_runs_as_a_real_process(tmp_path, bin_dir):
    """So startet die Flipper-App die Bruecke: ein kurzlebiger Prozess, NDJSON auf stdout."""
    requests = "\n".join([json.dumps({"op": "hello", "id": 1}),
                          json.dumps({"op": "status", "id": 2}),
                          json.dumps({"op": "bye", "id": 3})]) + "\n"
    proc = subprocess.run([sys.executable, "-m", "personintel.cli", "--data-dir", str(tmp_path / "d"), "bridge"],
                          input=requests, capture_output=True, text=True, timeout=120,
                          env={**__import__("os").environ, "PYTHONPATH": "src"})
    assert proc.returncode == 0, proc.stderr[-2000:]
    lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    assert lines[0]["ok"] and lines[0]["app"] == "personintel"
    assert sum(1 for l in lines if l.get("event") == "status") == 10
    assert lines[-1]["ok"]
    # stdout enthaelt ausschliesslich JSON-Zeilen
    for l in proc.stdout.splitlines():
        if l.strip():
            json.loads(l)
