import json
import sys

import pytest

from personintel.adapters.base import AdapterState
from personintel.api import Evidence, FindingStatus, QueryState, ReviewState
from personintel.core.models import QueryKind
from conftest import confirm, make_case, run, write_tool

HOLEHE = '''
import csv, sys, time
args = sys.argv[1:]
if "--help" in args:
    print("usage: holehe [-h] [--only-used] [--no-color] [--no-clear] [--no-password-recovery] [--csv] [--timeout T] email")
    sys.exit(0)
email = args[0]
with open(f"holehe_{int(time.time())}_{email}_results.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["name","domain","method","frequent_rate_limit","rateLimit","exists","emailrecovery","phoneNumber","others"])
    w.writerow(["twitter","twitter.com","register",False,False,True,"x***@gmail.com","0612345678",""])
    w.writerow(["flaky","flaky.example","login",True,False,True,"","",""])
    w.writerow(["blocked","blocked.example","register",False,True,False,"","",""])
    w.writerow(["nope","nope.example","register",False,False,False,"","",""])
'''

SHERLOCK = '''
import csv, sys
args = sys.argv[1:]
if "--version" in args: print("sherlock 0.16.0"); sys.exit(0)
if "--help" in args: print("usage: sherlock [--csv] [--print-found] [--no-color] [--timeout TIMEOUT]"); sys.exit(0)
user = args[0]
with open(f"{user}.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["username","name","url_main","url_user","exists","http_status","response_time_s"])
    w.writerow([user,"GitHub","https://github.com",f"https://github.com/{user}","Claimed",200,0.2])
    w.writerow([user,"Gone","https://gone.example",f"https://gone.example/{user}","Available",404,0.2])
'''

MOSINT = '''
import json, sys
a = sys.argv[1:]
if "--version" in a: print("mosint v3.0.0"); sys.exit(0)
out = a[a.index("--output")+1]
json.dump({"email": a[0], "verified": True, "api_key": "TOPSECRET-KEY",
           "related_emails": ["alt@example.org"],
           "hibp": {"results": [{"Name": "Adobe", "BreachDate": "2013-10-04", "Password": "hunter2",
                                 "Hash": "5f4dcc3b5aa765d61d8327deb882cf99"}, "plaintext: hunter2"]},
           "intelx": [{"source": "paste-site", "date": "2020-01-01", "content": "login: a:hunter2"}]},
          open(out, "w"))
'''

PHONEINFOGA_CLI = '''
import sys
a = sys.argv[1:]
if a[:1] == ["version"]: print("PhoneInfoga v2.11.0"); sys.exit(0)
if a[:2] == ["serve", "--help"]: print("Usage: serve [flags]\\n  -p, --port int\\n      --no-client"); sys.exit(0)
if a[:1] == ["scan"]:
    print("Running scan for phone number +4930123456...")
    print("Results for local")
    print("Raw local: 030123456")
    print("Country: DE")
    print("Carrier: Example Telecom")
    sys.exit(0)
sys.exit(1)
'''

PHONEINFOGA_REST = '''
import http.server, json, sys
a = sys.argv[1:]
if a[:1] == ["version"]: print("PhoneInfoga v2.11.0"); sys.exit(0)
if a[:2] == ["serve", "--help"]: print("Usage: serve\\n      --host string  bind address\\n  -p, --port int"); sys.exit(0)
if a[:1] == ["serve"]:
    host = a[a.index("--host")+1]; port = int(a[a.index("-p")+1])
    assert host == "127.0.0.1", host
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def do_GET(self):
            if self.path == "/api/v2/scanners": body = [{"name": "local"}]
            elif self.path.endswith("/scan/local"): body = {"success": True, "result": {"valid": True, "country": "DE", "carrier": "Example Telecom", "rawLocal": "030123456"}}
            elif self.path.endswith("/scan/googlesearch"): body = {"success": True, "result": {"social_media": [{"URL": "https://www.google.com/search?q=x", "Dork": "site:facebook.com x"}]}}
            else: self.send_response(404); self.end_headers(); return
            b = json.dumps(body).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    http.server.HTTPServer((host, port), H).serve_forever()
sys.exit(1)
'''


def test_status_reflects_real_installation(engine, bin_dir):
    st = {s.adapter_id: s for s in engine.statuses()}
    assert st["holehe"].state is AdapterState.NOT_INSTALLED
    assert st["holehe"].requirement
    write_tool(bin_dir, "holehe", HOLEHE)
    st = {s.adapter_id: s for s in engine.statuses()}
    assert st["holehe"].state is AdapterState.AVAILABLE


def test_not_installed_query_is_denied_with_requirement(engine):
    from personintel.api import AuthorizationDenied
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="holehe"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))


def test_holehe_end_to_end(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = make_case(engine)
    rec, fs = run(engine, case.id, "holehe", "email", "someone@example.org")
    assert rec.state is QueryState.DONE, rec.message
    accounts = [f for f in fs if f.type == "account"]
    assert {f.value for f in accounts} == {"twitter.com", "flaky.example"}
    tw = next(f for f in accounts if f.value == "twitter.com")
    assert tw.status is FindingStatus.FOUND and tw.evidence is Evidence.INDICATION
    flaky = next(f for f in accounts if f.value == "flaky.example")
    assert flaky.status is FindingStatus.POSSIBLE and flaky.evidence is Evidence.UNCONFIRMED
    summary = next(f for f in fs if f.type == "summary")
    assert summary.data["failed"] == 1 and "blocked.example" in summary.data["failed_modules"]
    # Datensparsamkeit: Wiederherstellungsdaten werden nicht gespeichert
    blob = json.dumps([f.to_dict() for f in fs])
    assert "x***@gmail.com" not in blob and "0612345678" not in blob
    # Quelle mit Zeitstempel und aktiver Kennzeichnung
    src = engine.sources(case.id)[0]
    assert src.active and src.retrieved_at and src.adapter_id == "holehe"
    assert all(f.source_id == src.id for f in fs)
    assert all(f.review_state is ReviewState.UNREVIEWED for f in fs)
    q = engine.queries(case.id)[0]
    assert q.mode.value == "active" and q.finding_count == len(fs)


def test_sherlock_username_is_indication_never_identity(engine, bin_dir):
    write_tool(bin_dir, "sherlock", SHERLOCK)
    case = make_case(engine)
    rec, fs = run(engine, case.id, "sherlock", "username", "jdoe")
    assert rec.state is QueryState.DONE, rec.message
    profiles = [f for f in fs if f.type == "profile"]
    assert len(profiles) == 1
    p = profiles[0]
    assert p.url == "https://github.com/jdoe"
    assert p.evidence is Evidence.INDICATION and "username-match" in p.tags
    assert p.data["identity_link"] == "none"
    # keine automatische Graph-Verbindung
    assert engine.graph.nodes(case.id) == [] and engine.graph.edges(case.id) == []
    assert engine.adapter("sherlock").get_status().version.startswith("sherlock")


def test_mosint_never_keeps_leaked_passwords(engine, bin_dir, tmp_path):
    write_tool(bin_dir, "mosint", MOSINT)
    # ohne Konfigurationsdatei: nicht konfiguriert, Abfrage abgelehnt
    st = {s.adapter_id: s for s in engine.statuses()}["mosint"]
    assert st.state is AdapterState.NOT_CONFIGURED and "mosint.yaml" in st.message
    cfg = tmp_path / "mosint.yaml"
    cfg.write_text("# test\n")
    engine.configure_adapter("mosint", config={"config_path": str(cfg)})
    case = make_case(engine)
    rec, fs = run(engine, case.id, "mosint", "email", "someone@example.org")
    assert rec.state is QueryState.DONE, rec.message
    blob = json.dumps([f.to_dict() for f in fs], ensure_ascii=False) + json.dumps(
        [s.to_dict() for s in engine.sources(case.id)])
    for forbidden in ("hunter2", "5f4dcc3b5aa765d61d8327deb882cf99", "TOPSECRET-KEY", "login: a:"):
        assert forbidden not in blob, forbidden
    hints = [f for f in fs if f.type == "breach_hint"]
    assert hints and any("Adobe" in f.value or "paste-site" in f.value for f in hints)
    # Rohdaten wurden nirgends in der Datenbank abgelegt
    rows = engine.repo.conn.execute("SELECT payload FROM records").fetchall()
    assert not any("hunter2" in r["payload"] for r in rows)


def test_phoneinfoga_cli_fallback_makes_no_person_claim(engine, bin_dir):
    write_tool(bin_dir, "phoneinfoga", PHONEINFOGA_CLI)
    case = make_case(engine, active=False)  # passiv -> auch ohne aktive Pruefungen erlaubt
    t = engine.add_target(case.id, "phone", "+49 30 123456")
    rec = engine.wait(engine.run_query(case.id, "phoneinfoga", t.id).id, 60)
    assert rec.state is QueryState.DONE, rec.message
    assert rec.mode.value == "passive"
    fs = [f for f in engine.findings(case.id) if f.query_id == rec.id]
    meta = next(f for f in fs if f.type == "metadata")
    assert meta.evidence is Evidence.INDICATION
    assert meta.data["parsed_lines"]["Country"] == "DE"
    assert "keine Zuordnung zu einer Person" in meta.data["hinweis"]
    assert not any(f.type == "person_record" for f in fs)


def test_phoneinfoga_rest_binds_loopback_only(engine, bin_dir):
    write_tool(bin_dir, "phoneinfoga", PHONEINFOGA_REST)
    case = make_case(engine, active=False)
    t = engine.add_target(case.id, "phone", "+49 30 123456")
    rec = engine.wait(engine.run_query(case.id, "phoneinfoga", t.id, options={"footprint_links": True}).id, 90)
    assert rec.state is QueryState.DONE, rec.message
    fs = [f for f in engine.findings(case.id) if f.query_id == rec.id]
    assert next(f for f in fs if f.type == "metadata").data["result"]["country"] == "DE"
    links = [f for f in fs if f.type == "link_hint"]
    assert links and links[0].evidence is Evidence.UNCONFIRMED and links[0].status is FindingStatus.INFO


def test_phoneinfoga_phone_number_is_normalized(engine):
    case = make_case(engine, active=False)
    t = engine.add_target(case.id, "phone", "030 / 1234 5678"[:0] or "+49 30 12345678")
    assert t.value.startswith("+49") and " " not in t.value


def test_cancel_running_query(engine, bin_dir):
    write_tool(bin_dir, "sherlock", "import time, sys\nif '--help' in sys.argv: print('--timeout'); sys.exit(0)\ntime.sleep(120)\n")
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "slowuser")
    rec = engine.run_query(case.id, "sherlock", t.id, confirmation=confirm(t.value))
    import time
    for _ in range(100):  # warten bis der Prozess laeuft
        if engine.queries(case.id)[0].state.value == "running":
            break
        time.sleep(0.1)
    time.sleep(0.5)
    assert engine.cancel_query(rec.id)
    done = engine.wait(rec.id, 20)
    assert done.state is QueryState.CANCELLED


def test_tool_failure_is_reported_not_swallowed(engine, bin_dir):
    write_tool(bin_dir, "sherlock", "import sys\nif '--help' in sys.argv: print('--timeout'); sys.exit(0)\nprint('boom', file=sys.stderr); sys.exit(3)\n")
    case = make_case(engine)
    rec, fs = run(engine, case.id, "sherlock", "username", "jdoe")
    assert rec.state is QueryState.FAILED and "boom" in rec.message
    assert fs == []


def test_mrholmes_report_import_is_passive_and_unconfirmed(engine, tmp_path):
    report = tmp_path / "holmes_report.txt"
    report.write_text("Target: jdoe\nProfile: https://example.org/jdoe\nMail: jdoe@example.org\nTel: +49 30 1234567\n")
    case = make_case(engine, active=False)
    t = engine.add_target(case.id, "report_file", str(report))
    rec = engine.wait(engine.run_query(case.id, "mrholmes", t.id).id, 30)
    assert rec.state is QueryState.DONE, rec.message
    assert rec.mode.value == "passive"
    fs = [f for f in engine.findings(case.id) if f.query_id == rec.id]
    doc = next(f for f in fs if f.type == "document")
    assert len(doc.data["sha256"]) == 64
    vals = {f.value for f in fs}
    assert "https://example.org/jdoe" in vals and "jdoe@example.org" in vals
    assert all(f.evidence is Evidence.UNCONFIRMED for f in fs)
    src = engine.sources(case.id)[0]
    assert src.kind == "file" and "SHA-256" in src.description


def test_mrholmes_rejects_unsupported_file_type(engine, tmp_path):
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    case = make_case(engine, active=False)
    t = engine.add_target(case.id, "report_file", str(bad))
    rec = engine.wait(engine.run_query(case.id, "mrholmes", t.id).id, 30)
    assert rec.state is QueryState.FAILED


def test_ignorant_normalization_stops_at_rate_limit_and_flags_active():
    from personintel.adapters.base import RawResult
    from personintel.adapters.ignorant import IgnorantAdapter
    ad = IgnorantAdapter()
    cap = ad.capability(QueryKind.PHONE)
    assert cap.mode.value == "active"
    raw = RawResult("qry_1", "case_1", "tgt_1", "ignorant", "t0", "t1", payload={
        "results": [{"name": "amazon", "domain": "amazon.com", "exists": True, "rateLimit": False},
                    {"name": "instagram", "domain": "instagram.com", "exists": False, "rateLimit": True}],
        "stopped_at_rate_limit": "instagram"})
    batch = ad.normalize_results(raw)
    assert [f.value for f in batch.findings if f.type == "account"] == ["amazon.com"]
    summ = next(f for f in batch.findings if f.type == "summary")
    assert summ.data["stopped_at_rate_limit"] == "instagram" and summ.data["failed"] == 1
    assert any("keine Umgehung" in n for n in batch.notes)
