"""Recherchegraph: nur *manuell* uebernommene, durch Befunde belegte Verbindungen.

Regeln:
* Knoten und Kanten entstehen ausschliesslich durch Analysten-Aktionen (``created_by="analyst"``).
* Jede Kante nennt mindestens einen Basisbefund desselben Falls (kein abgelehnter Befund).
* Die Belegstufe einer Kante ist durch die beste Belegstufe ihrer Basisbefunde gedeckelt.
* ``same_person`` (Gleichsetzung zweier Identitaeten) ist nur zulaessig, wenn mindestens ein Basisbefund
  *nicht* allein auf identischem Benutzernamen beruht (Tag ``username-match``) und eine Begruendung vorliegt.
* ``suggest_links`` liefert nur unverbindliche Hinweise; sie werden nie automatisch gespeichert.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.errors import ValidationError
from ..core.ids import new_id, now_iso
from ..core.models import Evidence, Finding, Model, ReviewState
from ..security.audit import AuditLog
from ..storage.repository import Repository

RELATIONS = {
    "uses_identifier": "nutzt Kennung",
    "has_account": "hat Konto/Profil",
    "mentioned_with": "gemeinsam erwähnt",
    "affiliated_with": "verbunden mit",
    "same_person": "ist dieselbe Person wie",
    "other": "sonstiger Zusammenhang",
}
NODE_TYPES = {"person": "Person", "identifier": "Kennung", "account": "Konto/Profil", "organization": "Organisation",
              "document": "Dokument", "other": "Sonstiges"}


@dataclass
class GraphNode(Model):
    id: str
    case_id: str
    type: str
    label: str
    finding_ids: list = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    created_by: str = "analyst"


@dataclass
class GraphEdge(Model):
    id: str
    case_id: str
    source: str
    target: str
    relation: str
    evidence: Evidence = Evidence.UNCONFIRMED
    basis_finding_ids: list = field(default_factory=list)
    note: str = ""
    created_at: str = field(default_factory=now_iso)
    created_by: str = "analyst"

    ENUM_FIELDS = {"evidence": Evidence}


@dataclass
class LinkSuggestion:
    kind: str
    description: str
    finding_ids: list[str]
    evidence: Evidence = Evidence.UNCONFIRMED  # Hinweise sind nie mehr als unbestaetigt


class GraphService:
    def __init__(self, repo: Repository, audit: AuditLog):
        self.repo = repo
        self.audit = audit

    # ----------------------------------------------------------------- lesen
    def nodes(self, case_id: str) -> list[GraphNode]:
        return [GraphNode.from_dict(d) for d in self.repo.list_raw("node", case_id)]

    def edges(self, case_id: str) -> list[GraphEdge]:
        return [GraphEdge.from_dict(d) for d in self.repo.list_raw("edge", case_id)]

    def _findings(self, case_id: str) -> dict[str, Finding]:
        return {f.id: f for f in self.repo.list("finding", case_id)}

    # ---------------------------------------------------------------- Knoten
    def add_node(self, case_id: str, type_: str, label: str, finding_ids: Optional[list[str]] = None) -> GraphNode:
        if type_ not in NODE_TYPES:
            raise ValidationError("Unbekannter Knotentyp.")
        label = (label or "").strip()
        if not label:
            raise ValidationError("Knoten braucht eine Bezeichnung.")
        findings = self._findings(case_id)
        fids = list(finding_ids or [])
        for fid in fids:
            if fid not in findings:
                raise ValidationError("Befund gehört nicht zu diesem Fall.")
        node = GraphNode(id=new_id("nod"), case_id=case_id, type=type_, label=label, finding_ids=fids)
        self.repo.put_raw("node", node.to_dict(), ts=node.created_at)
        self.audit.record("graph.node.add", case_id=case_id, detail={"type": type_})
        return node

    def remove_node(self, case_id: str, node_id: str) -> None:
        edges = [e for e in self.edges(case_id) if node_id in (e.source, e.target)]
        self.repo.delete_records([node_id] + [e.id for e in edges])
        self.audit.record("graph.node.remove", case_id=case_id, detail={"edges_removed": len(edges)})

    # ----------------------------------------------------------------- Kanten
    def link(self, case_id: str, source: str, target: str, relation: str, basis_finding_ids: list[str],
             note: str = "", evidence: Optional[Evidence] = None) -> GraphEdge:
        if relation not in RELATIONS:
            raise ValidationError("Unbekannte Beziehungsart.")
        if source == target:
            raise ValidationError("Quelle und Ziel müssen verschieden sein.")
        nodes = {n.id: n for n in self.nodes(case_id)}
        if source not in nodes or target not in nodes:
            raise ValidationError("Knoten nicht gefunden.")
        if not basis_finding_ids:
            raise ValidationError("Eine Verbindung braucht mindestens einen Basisbefund (Beleg).")
        findings = self._findings(case_id)
        basis: list[Finding] = []
        for fid in basis_finding_ids:
            f = findings.get(fid)
            if f is None:
                raise ValidationError("Basisbefund gehört nicht zu diesem Fall.")
            if f.review_state is ReviewState.REJECTED:
                raise ValidationError("Abgelehnte Befunde können nicht als Beleg dienen.")
            basis.append(f)
        best = max(basis, key=lambda f: f.evidence.rank).evidence
        chosen = evidence or best
        if chosen.rank > best.rank:
            raise ValidationError("Die Belegstufe der Verbindung darf die beste Belegstufe der Basisbefunde nicht übersteigen.")
        if relation == "same_person":
            if len((note or "").strip()) < 10:
                raise ValidationError("Gleichsetzung zweier Identitäten erfordert eine nachvollziehbare Begründung.")
            if all("username-match" in f.tags for f in basis):
                raise ValidationError(
                    "Keine Gleichsetzung allein aufgrund identischer Benutzernamen: mindestens ein weiterer, "
                    "unabhängiger Beleg ist nötig.")
            if chosen is Evidence.UNCONFIRMED:
                raise ValidationError("Gleichsetzung braucht mindestens die Belegstufe 'Indiz'.")
        edge = GraphEdge(id=new_id("edg"), case_id=case_id, source=source, target=target, relation=relation,
                         evidence=chosen, basis_finding_ids=list(basis_finding_ids), note=(note or "").strip())
        self.repo.put_raw("edge", edge.to_dict(), ts=edge.created_at)
        self.audit.record("graph.edge.add", case_id=case_id, detail={"relation": relation, "evidence": chosen.value})
        return edge

    def remove_edge(self, case_id: str, edge_id: str) -> None:
        self.repo.delete_record(edge_id)
        self.audit.record("graph.edge.remove", case_id=case_id)

    # --------------------------------------------------------------- Hinweise
    def suggest_links(self, case_id: str) -> list[LinkSuggestion]:
        """Unverbindliche Hinweise (werden nicht gespeichert, nie ohne Analysten-Entscheidung verwendet)."""
        by_value: dict[str, list[Finding]] = {}
        for f in self._findings(case_id).values():
            if "username-match" in f.tags and f.review_state is not ReviewState.REJECTED:
                by_value.setdefault(f.value.lower(), []).append(f)
        out = []
        for value, fs in by_value.items():
            if len(fs) > 1:
                out.append(LinkSuggestion(
                    "same_username",
                    f"Gleicher Benutzername „{value}“ auf {len(fs)} Plattformen – kein Beleg für dieselbe Person.",
                    [f.id for f in fs]))
        return out

    # ------------------------------------------------------------------ Export
    def to_dict(self, case_id: str) -> dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes(case_id)], "edges": [e.to_dict() for e in self.edges(case_id)]}

    def to_dot(self, case_id: str) -> str:
        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')
        lines = ["digraph personintel {", "  rankdir=LR;"]
        for n in self.nodes(case_id):
            lines.append(f'  "{n.id}" [label="{esc(n.label)}\\n({NODE_TYPES.get(n.type, n.type)})"];')
        for e in self.edges(case_id):
            lines.append(f'  "{e.source}" -> "{e.target}" [label="{esc(RELATIONS.get(e.relation, e.relation))} '
                         f'[{e.evidence.label_de}]"];')
        lines.append("}")
        return "\n".join(lines)


def layout(nodes: list[GraphNode], edges: list[GraphEdge], iterations: int = 200, seed: int = 7) -> dict[str, tuple[float, float]]:
    """Kleines, deterministisches Fruchterman-Reingold-Layout; Koordinaten in [0, 1]."""
    n = len(nodes)
    if n == 0:
        return {}
    if n == 1:
        return {nodes[0].id: (0.5, 0.5)}
    rnd = random.Random(seed)
    pos = {nd.id: [0.5 + 0.4 * math.cos(2 * math.pi * i / n) + rnd.uniform(-0.01, 0.01),
                   0.5 + 0.4 * math.sin(2 * math.pi * i / n) + rnd.uniform(-0.01, 0.01)] for i, nd in enumerate(nodes)}
    k = math.sqrt(1.0 / n)
    t = 0.1
    ids = list(pos)
    for _ in range(iterations):
        disp = {i: [0.0, 0.0] for i in ids}
        for a in range(n):
            for b in range(a + 1, n):
                dx, dy = pos[ids[a]][0] - pos[ids[b]][0], pos[ids[a]][1] - pos[ids[b]][1]
                dist = max(math.hypot(dx, dy), 1e-4)
                f = (k * k) / dist
                disp[ids[a]][0] += dx / dist * f
                disp[ids[a]][1] += dy / dist * f
                disp[ids[b]][0] -= dx / dist * f
                disp[ids[b]][1] -= dy / dist * f
        for e in edges:
            if e.source in pos and e.target in pos:
                dx, dy = pos[e.source][0] - pos[e.target][0], pos[e.source][1] - pos[e.target][1]
                dist = max(math.hypot(dx, dy), 1e-4)
                f = (dist * dist) / k
                disp[e.source][0] -= dx / dist * f
                disp[e.source][1] -= dy / dist * f
                disp[e.target][0] += dx / dist * f
                disp[e.target][1] += dy / dist * f
        for i in ids:
            d = max(math.hypot(*disp[i]), 1e-4)
            pos[i][0] += disp[i][0] / d * min(d, t)
            pos[i][1] += disp[i][1] / d * min(d, t)
        t *= 0.98
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    sx, sy = (maxx - minx) or 1.0, (maxy - miny) or 1.0
    return {i: (0.05 + 0.9 * (p[0] - minx) / sx, 0.05 + 0.9 * (p[1] - miny) / sy) for i, p in pos.items()}
