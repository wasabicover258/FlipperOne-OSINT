"""Bericht: Belegstufen getrennt, Quellen/Zeitstempel genannt, HTML maskiert."""

import json

from personintel.api import Evidence, FindingStatus, ReviewState
from personintel.core.ids import new_id
from personintel.core.models import (Finding, QueryKind, QueryMode, QueryRecord, QueryState, Source)
from personintel.reports.export import LIMITATIONS
from conftest import make_case


def _case_with_findings(engine):
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    src = Source(id=new_id("src"), case_id=case.id, adapter_id="sherlock", kind="tool_output",
                 description="sherlock CSV", url="https://github.com/jdoe", tool_version="sherlock 0.16.0",
                 active=True)
    engine.repo.put("source", src, ts=src.retrieved_at)
    q = QueryRecord(id=new_id("qry"), case_id=case.id, adapter_id="sherlock", target_id=t.id, kind=QueryKind.USERNAME,
                    mode=QueryMode.ACTIVE, state=QueryState.DONE, message="ok", finding_count=6)
    engine.repo.put("query", q, ts=q.created_at)
    mk = lambda **kw: Finding(id=new_id("fnd"), case_id=case.id, adapter_id="sherlock", source_id=src.id,
                              target_id=t.id, query_id=q.id, **kw)
    items = [
        mk(type="profile", title="GitHub-Profil", value="jdoe", url="https://github.com/jdoe",
           status=FindingStatus.FOUND, evidence=Evidence.CONFIRMED, review_state=ReviewState.REVIEWED,
           reviewer_note="Von der Person selbst bestätigt"),
        mk(type="profile", title="Mastodon-Profil", status=FindingStatus.FOUND, evidence=Evidence.INDICATION),
        mk(type="link_hint", title="Suchtreffer", status=FindingStatus.INFO, evidence=Evidence.UNCONFIRMED),
        mk(type="profile", title="Ohne-Treffer-Eintrag", status=FindingStatus.NOT_FOUND, evidence=Evidence.UNCONFIRMED),
        mk(type="profile", title="Verworfener-Eintrag", status=FindingStatus.FOUND, evidence=Evidence.INDICATION,
           review_state=ReviewState.REJECTED),
        mk(type="summary", title="Fehlgeschlagener-Eintrag", status=FindingStatus.FAILED, evidence=Evidence.UNCONFIRMED),
    ]
    for f in items:
        engine.repo.put("finding", f, ts=f.observed_at)
    return case, t, src, items


def test_report_sections_and_evidence_grouping(engine):
    case, t, src, items = _case_with_findings(engine)
    md = engine.build_report(case.id).to_markdown()
    for head in ("1. Zweck und Berechtigung", "2. Methodik", "3. Ergebnisse nach Belegstufe",
                 "4. Belegte Verbindungen", "5. Chronologie", "6. Einschränkungen und Hinweise",
                 "7. Protokollzusammenfassung"):
        assert f"## {head}" in md or f"# {head}" in md, head
    assert "### unmittelbar belegt (1)" in md
    assert "### Indiz (1)" in md          # der verworfene Befund zaehlt nicht mit
    assert "### unbestätigt (1)" in md
    assert "GitHub-Profil" in md
    assert "Verworfener-Eintrag" not in md and "Ohne-Treffer-Eintrag" not in md
    assert "Fehlgeschlagener-Eintrag" not in md   # Fehler sind Hinweis, kein Befund
    assert "sherlock 0.16.0" in md and src.retrieved_at in md
    assert "Von der Person selbst bestätigt" in md
    assert "aktiv (Drittkontakt)" in md or "passiv" in md
    assert LIMITATIONS[0][:40] in md
    assert "1 Befund/Befunde wurden vom Bearbeiter verworfen" in md
    assert "fehlgeschlagen" in md and "unvollständig" in md


def test_options_control_content(engine):
    case, *_ = _case_with_findings(engine)
    md = engine.build_report(case.id, include_unconfirmed=False).to_markdown()
    assert "### unbestätigt (0)" in md and "Suchtreffer" not in md
    md = engine.build_report(case.id, include_rejected=True).to_markdown()
    assert "Verworfener-Eintrag" in md
    md = engine.build_report(case.id, include_not_found=True).to_markdown()
    assert "Ohne-Treffer-Eintrag" in md
    md = engine.build_report(case.id, include_audit_summary=False).to_markdown()
    assert "Protokollzusammenfassung" not in md


def test_identifier_masking(engine):
    case = make_case(engine)
    engine.add_target(case.id, "email", "erika.beispiel@example.org")
    engine.add_target(case.id, "phone", "+4930123456")
    md = engine.build_report(case.id, mask_identifiers=True).to_markdown()
    assert "erika.beispiel@example.org" not in md and "e***@example.org" in md
    assert "+4930123456" not in md and "+493" in md
    assert "erika.beispiel@example.org" in engine.build_report(case.id).to_markdown()


def test_html_escapes_tool_output(engine):
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="sherlock", type="profile",
                title='<script>alert("x")</script>', value="a & b", url="https://x/?a=1&b=2",
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION, target_id=t.id)
    engine.repo.put("finding", f, ts=f.observed_at)
    rep = engine.build_report(case.id)
    html = rep.to_html()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "a &amp; b" in html
    assert html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>")
    assert "a=1&amp;b=2" in html


def test_markdown_table_cells_are_escaped(engine):
    case = make_case(engine)
    engine.add_target(case.id, "username", "a-b")
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="x", type="profile", title="Pipe | im | Titel",
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION)
    engine.repo.put("finding", f, ts=f.observed_at)
    md = engine.build_report(case.id).to_markdown()
    assert "Pipe \\| im \\| Titel" in md


def test_json_report_is_machine_readable(engine):
    case, t, src, items = _case_with_findings(engine)
    data = json.loads(engine.build_report(case.id).to_json())
    assert data["format"] == "personintel.report" and data["case"]["id"] == case.id
    assert data["case"]["purpose"]["authorized_by"] == "Redaktionsleitung"
    assert [f["evidence_label"] for f in data["findings"] if f["title"] == "GitHub-Profil"] == ["unmittelbar belegt"]
    got = next(f for f in data["findings"] if f["title"] == "GitHub-Profil")
    assert got["source"]["tool_version"] == "sherlock 0.16.0"
    assert data["limitations"] and data["audit_summary"]


def test_report_without_purpose_says_so(engine):
    case = engine.create_case("ohne Zweck")
    md = engine.build_report(case.id).to_markdown()
    assert "kein Recherchezweck dokumentiert" in md


def test_report_mentions_graph_connections(engine):
    case, t, src, items = _case_with_findings(engine)
    g = engine.graph
    a = g.add_node(case.id, "person", "Zielperson")
    b = g.add_node(case.id, "account", "GitHub")
    g.link(case.id, a.id, b.id, "has_account", [items[0].id], note="Profil belegt")
    md = engine.build_report(case.id).to_markdown()
    assert "hat Konto/Profil" in md and "Profil belegt" in md
    assert "ausschließlich manuell" in md


def test_timeline_is_chronological(engine):
    case, t, src, items = _case_with_findings(engine)
    tl = engine.timeline(case.id)
    assert [e.ts for e in tl] == sorted(e.ts for e in tl)
    kinds = {e.kind for e in tl}
    assert kinds == {"event", "finding"}
    titles = [e.summary for e in tl if e.kind == "finding"]
    assert any("GitHub-Profil" in s for s in titles)
    assert not any("Verworfener-Eintrag" in s for s in titles)       # verworfene Befunde nicht in der Chronologie
