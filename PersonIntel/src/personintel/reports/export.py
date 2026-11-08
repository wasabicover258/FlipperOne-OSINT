"""Berichtsgenerator fuer die journalistische Dokumentation (Markdown, HTML, JSON).

Der Bericht trennt strikt nach Belegstufe, nennt je Befund Quelle, Zeitstempel, Werkzeug/Version und
Pruefstatus, dokumentiert Zweck, Methodik (passiv/aktiv), Verbindungen und Einschraenkungen.
Alle Inhalte werden fuer HTML maskiert (kein Einschleusen von Markup durch Tool-Ausgaben).
"""

from __future__ import annotations

import html
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .. import RESULT_SCHEMA_VERSION, __version__
from ..core.ids import now_iso
from ..core.models import Evidence, Finding, FindingStatus, ReviewState
from ..graph.model import NODE_TYPES, RELATIONS

LIMITATIONS = (
    "Treffer sind Hinweise aus den genannten Quellen, keine Identitätsnachweise. Gleiche Benutzernamen, "
    "Telefonnummern oder E-Mail-Adressen belegen für sich genommen nicht, dass es sich um dieselbe Person handelt.",
    "„Nicht gefunden“ bedeutet nur, dass das jeweilige Werkzeug zum Abfragezeitpunkt nichts gemeldet hat; "
    "Dienste können Abfragen blockieren, begrenzen oder falsche Ergebnisse liefern.",
    "Einträge der Belegstufe „Indiz“ oder „unbestätigt“ müssen vor einer Veröffentlichung unabhängig verifiziert werden.",
    "Der Bericht enthält nur normalisierte Befunde; Rohdaten der Werkzeuge werden nicht gespeichert.",
    "Es wurden keine privaten Leak-Datenbanken, gestohlenen Zugangsdaten oder Konto-Übernahmen verwendet.",
)


@dataclass
class ReportOptions:
    include_unconfirmed: bool = True
    include_rejected: bool = False
    include_not_found: bool = False
    mask_identifiers: bool = False
    include_audit_summary: bool = True


@dataclass
class Report:
    title: str
    generated_at: str
    blocks: list[tuple] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        return render_markdown(self)

    def to_html(self) -> str:
        return render_html(self)

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True)


def _mask(value: str) -> str:
    if "@" in value:
        local, _, dom = value.partition("@")
        return (local[:1] + "***@" + dom) if local else "***@" + dom
    if value.startswith("+") and len(value) > 6:
        return value[:4] + "*" * (len(value) - 6) + value[-2:]
    return (value[:2] + "***") if len(value) > 2 else "***"


def _cell(text: Any) -> str:
    return str(text if text is not None else "").replace("\r", " ").replace("\n", " ")


def build_report(engine, case_id: str, options: ReportOptions | None = None) -> Report:
    o = options or ReportOptions()
    case = engine.case(case_id)
    targets = engine.targets(case_id)
    findings = engine.findings(case_id, include_rejected=True)
    sources = {s.id: s for s in engine.sources(case_id)}
    queries = engine.queries(case_id)
    nodes = {n.id: n for n in engine.graph.nodes(case_id)}
    edges = engine.graph.edges(case_id)
    timeline = engine.timeline(case_id)
    adapters = {a.id: a.name for a in engine.adapters()}
    tvalues = {t.id: (_mask(t.value) if o.mask_identifiers else t.value) for t in targets}

    def aname(aid: str) -> str:
        return adapters.get(aid, aid)

    rejected = [f for f in findings if f.review_state is ReviewState.REJECTED]
    usable = [f for f in findings if f.review_state is not ReviewState.REJECTED or o.include_rejected]
    if not o.include_not_found:
        shown = [f for f in usable if f.status not in (FindingStatus.NOT_FOUND,)]
    else:
        shown = list(usable)
    if not o.include_unconfirmed:
        shown = [f for f in shown if f.evidence is not Evidence.UNCONFIRMED]
    not_found_n = sum(1 for f in usable if f.status is FindingStatus.NOT_FOUND)
    failed_n = sum(1 for f in findings if f.status is FindingStatus.FAILED)

    title = f"Recherchebericht: {case.name}"
    now = now_iso()
    B: list[tuple] = []
    B.append(("h1", title))
    B.append(("kv", [("Fall-ID", case.id), ("Erstellt am", case.created_at), ("Bericht erzeugt", now),
                     ("Software", f"PersonIntel {__version__} (Schema {RESULT_SCHEMA_VERSION})")]))
    if case.description:
        B.append(("p", case.description))

    # --- Zweck
    B.append(("h2", "1. Zweck und Berechtigung"))
    p = case.purpose
    if p:
        B.append(("kv", [("Kategorie", p.category), ("Zweck", p.description), ("Verantwortlich/Auftraggeber", p.authorized_by),
                         ("Rechtsgrundlage/Notiz", p.legal_basis_note or "–"), ("Bestätigt am", p.confirmed_at),
                         ("Gültig bis", p.expires_at),
                         ("Aktive Prüfungen erlaubt", "ja" if p.active_checks_allowed else "nein"),
                         ("Erlaubte Kennungsarten", ", ".join(p.allowed_kinds))]))
    else:
        B.append(("p", "Für diesen Fall ist kein Recherchezweck dokumentiert."))

    # --- Methodik
    B.append(("h2", "2. Methodik"))
    B.append(("p", "Registrierte Kennungen (Fallumfang):"))
    B.append(("table", ["ID", "Art", "Kennung", "Bezeichnung"],
              [[t.id, t.kind.label_de, tvalues[t.id], t.label or "–"] for t in targets]))
    rows = []
    for q in sorted(queries, key=lambda q: q.created_at):
        src_versions = sorted({s.tool_version for s in sources.values() if s.query_id == q.id and s.tool_version})
        rows.append([q.created_at, aname(q.adapter_id), q.kind.label_de,
                     "aktiv (Drittkontakt)" if q.mode.value == "active" else "passiv",
                     q.state.value, ", ".join(src_versions) or "–"])
    B.append(("p", "Durchgeführte Abfragen:"))
    B.append(("table", ["Zeitpunkt", "Modul", "Art", "Modus", "Status", "Werkzeug-Version"], rows))

    # --- Ergebnisse
    B.append(("h2", "3. Ergebnisse nach Belegstufe"))
    counts = Counter(f.evidence for f in shown)
    B.append(("p", f"Unmittelbar belegt: {counts[Evidence.CONFIRMED]} · Indiz: {counts[Evidence.INDICATION]} · "
                   f"Unbestätigt: {counts[Evidence.UNCONFIRMED]}"))
    for ev in (Evidence.CONFIRMED, Evidence.INDICATION, Evidence.UNCONFIRMED):
        group = [f for f in shown if f.evidence is ev]
        B.append(("h3", f"{ev.label_de} ({len(group)})"))
        if not group:
            B.append(("p", "Keine Einträge."))
            continue
        trs = []
        for f in sorted(group, key=lambda f: (f.adapter_id, f.observed_at)):
            s = sources.get(f.source_id)
            src = "–"
            if s:
                src = f"{aname(s.adapter_id)} · {s.retrieved_at}" + (f" · {s.tool_version}" if s.tool_version else "")
                if s.url:
                    src += f" · {s.url}"
            trs.append([f.title, f.value or "–", f.url or "–", f.status.value, src,
                        f"{f.review_state.value}" + (f": {f.reviewer_note}" if f.reviewer_note else "")])
        B.append(("table", ["Befund", "Wert", "URL", "Status", "Quelle / Zeitpunkt", "Prüfung"], trs))
    notes = []
    if not o.include_not_found and not_found_n:
        notes.append(f"{not_found_n} Abfrage(n) ohne Treffer sind nicht aufgeführt.")
    if failed_n:
        notes.append(f"{failed_n} Abfrage(n)/Teilabfrage(n) sind fehlgeschlagen (z. B. Rate-Limit, Timeout) – "
                     "die Ergebnislage ist dadurch unvollständig.")
    if rejected:
        notes.append(f"{len(rejected)} Befund/Befunde wurden vom Bearbeiter verworfen"
                     f"{' und sind aufgeführt' if o.include_rejected else ' und nicht aufgeführt'}.")
    if notes:
        B.append(("ul", notes))

    # --- Verbindungen
    B.append(("h2", "4. Belegte Verbindungen"))
    if edges:
        by_id = {f.id: f for f in findings}
        trs = []
        for e in edges:
            a, b = nodes.get(e.source), nodes.get(e.target)
            basis = "; ".join(by_id[i].title for i in e.basis_finding_ids if i in by_id) or "–"
            trs.append([a.label if a else e.source, RELATIONS.get(e.relation, e.relation), b.label if b else e.target,
                        e.evidence.label_de, basis, e.note or "–"])
        B.append(("table", ["Von", "Beziehung", "Nach", "Belegstufe", "Basisbefunde", "Begründung"], trs))
        B.append(("p", "Verbindungen wurden ausschließlich manuell vom Bearbeiter übernommen."))
    else:
        B.append(("p", "Es wurden keine Verbindungen übernommen."))
    if nodes:
        B.append(("p", "Knoten: " + ", ".join(f"{n.label} ({NODE_TYPES.get(n.type, n.type)})" for n in nodes.values())))

    # --- Chronologie
    B.append(("h2", "5. Chronologie"))
    B.append(("table", ["Zeitpunkt", "Ereignis", "Belegstufe"],
              [[t.ts, t.summary, t.evidence or "–"] for t in timeline]))

    # --- Einschraenkungen
    B.append(("h2", "6. Einschränkungen und Hinweise"))
    B.append(("ul", list(LIMITATIONS)))

    # --- Audit
    audit_summary: dict[str, int] = {}
    if o.include_audit_summary:
        entries = engine.audit.entries(case_id)
        audit_summary = dict(Counter(e.action for e in entries))
        ok, bad = engine.audit.verify()
        B.append(("h2", "7. Protokollzusammenfassung"))
        B.append(("table", ["Aktion", "Anzahl"], [[k, v] for k, v in sorted(audit_summary.items())]))
        B.append(("p", "Integrität des Audit-Protokolls: " + ("geprüft, keine Auffälligkeiten."
                                                              if ok else f"FEHLER ab Eintrag {bad}.")))

    data = {
        "format": "personintel.report", "schema_version": RESULT_SCHEMA_VERSION, "generated_at": now,
        "case": {"id": case.id, "name": case.name, "purpose": case.purpose.to_dict() if case.purpose else None},
        "targets": [{"id": t.id, "kind": t.kind.value, "value": tvalues[t.id]} for t in targets],
        "findings": [_finding_dict(f, sources) for f in shown],
        "connections": [e.to_dict() for e in edges],
        "limitations": list(LIMITATIONS),
        "audit_summary": audit_summary,
    }
    return Report(title=title, generated_at=now, blocks=B, data=data)


def _finding_dict(f: Finding, sources) -> dict[str, Any]:
    d = f.to_dict()
    s = sources.get(f.source_id)
    d["source"] = s.to_dict() if s else None
    d["evidence_label"] = f.evidence.label_de
    return d


# ---------------------------------------------------------------- Renderer
def _md_escape_cell(text: Any) -> str:
    return _cell(text).replace("|", "\\|")


def render_markdown(rep: Report) -> str:
    out: list[str] = []
    for blk in rep.blocks:
        kind = blk[0]
        if kind == "h1":
            out += [f"# {blk[1]}", ""]
        elif kind == "h2":
            out += [f"## {blk[1]}", ""]
        elif kind == "h3":
            out += [f"### {blk[1]}", ""]
        elif kind == "p":
            out += [_cell(blk[1]), ""]
        elif kind == "ul":
            out += [f"- {_cell(i)}" for i in blk[1]] + [""]
        elif kind == "kv":
            out += [f"- **{k}:** {_cell(v)}" for k, v in blk[1]] + [""]
        elif kind == "table":
            headers, rows = blk[1], blk[2]
            if not rows:
                out += ["_Keine Einträge._", ""]
                continue
            out.append("| " + " | ".join(headers) + " |")
            out.append("|" + "|".join("---" for _ in headers) + "|")
            out += ["| " + " | ".join(_md_escape_cell(c) for c in r) + " |" for r in rows]
            out.append("")
    return "\n".join(out)


_CSS = ("body{font-family:sans-serif;max-width:1000px;margin:2em auto;padding:0 1em;color:#111}"
        "table{border-collapse:collapse;width:100%;margin:.5em 0 1em}th,td{border:1px solid #bbb;padding:4px 6px;"
        "text-align:left;vertical-align:top;font-size:90%}th{background:#eee}h1{font-size:1.6em}"
        "dt{font-weight:bold}.kv td:first-child{width:25%;font-weight:bold}")


def render_html(rep: Report) -> str:
    e = html.escape
    parts = ["<!DOCTYPE html>", '<html lang="de"><head><meta charset="utf-8">',
             f"<title>{e(rep.title)}</title>", f"<style>{_CSS}</style></head><body>"]
    for blk in rep.blocks:
        kind = blk[0]
        if kind in ("h1", "h2", "h3"):
            parts.append(f"<{kind}>{e(blk[1])}</{kind}>")
        elif kind == "p":
            parts.append(f"<p>{e(_cell(blk[1]))}</p>")
        elif kind == "ul":
            parts.append("<ul>" + "".join(f"<li>{e(_cell(i))}</li>" for i in blk[1]) + "</ul>")
        elif kind == "kv":
            parts.append('<table class="kv">' + "".join(
                f"<tr><td>{e(k)}</td><td>{e(_cell(v))}</td></tr>" for k, v in blk[1]) + "</table>")
        elif kind == "table":
            headers, rows = blk[1], blk[2]
            if not rows:
                parts.append("<p><em>Keine Einträge.</em></p>")
                continue
            parts.append("<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in headers) + "</tr></thead><tbody>")
            for r in rows:
                parts.append("<tr>" + "".join(f"<td>{e(_cell(c))}</td>" for c in r) + "</tr>")
            parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "\n".join(parts)
