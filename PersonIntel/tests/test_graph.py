"""Graph: nur manuell uebernommene, belegte Verbindungen."""

import pytest

from personintel.api import Evidence, FindingStatus, ReviewState, ValidationError
from personintel.core.ids import new_id
from personintel.core.models import Finding
from personintel.graph.model import GraphService
from conftest import make_case


def _finding(engine, case_id, *, title="Befund", evidence=Evidence.INDICATION, tags=(), value="jdoe",
             review=ReviewState.UNREVIEWED):
    f = Finding(id=new_id("fnd"), case_id=case_id, adapter_id="sherlock", type="profile", title=title, value=value,
                status=FindingStatus.FOUND, evidence=evidence, review_state=review, tags=list(tags))
    engine.repo.put("finding", f, ts=f.observed_at)
    return f


def test_nodes_and_edges_need_findings(engine):
    case = make_case(engine)
    g = engine.graph
    a = g.add_node(case.id, "person", "Zielperson")
    b = g.add_node(case.id, "account", "github.com/jdoe")
    assert a.created_by == "analyst" and b.created_by == "analyst"
    with pytest.raises(ValidationError, match="Beleg"):
        g.link(case.id, a.id, b.id, "has_account", [])
    f = _finding(engine, case.id)
    e = g.link(case.id, a.id, b.id, "has_account", [f.id], note="Profil belegt")
    assert e.evidence is Evidence.INDICATION and e.basis_finding_ids == [f.id]
    assert [x.id for x in g.edges(case.id)] == [e.id]


def test_unknown_types_and_self_links_rejected(engine):
    case = make_case(engine)
    g = engine.graph
    with pytest.raises(ValidationError):
        g.add_node(case.id, "ufo", "x")
    with pytest.raises(ValidationError):
        g.add_node(case.id, "person", "   ")
    a = g.add_node(case.id, "person", "A")
    f = _finding(engine, case.id)
    with pytest.raises(ValidationError):
        g.link(case.id, a.id, a.id, "has_account", [f.id])
    with pytest.raises(ValidationError):
        g.link(case.id, a.id, "nod_0000000000000000", "has_account", [f.id])
    with pytest.raises(ValidationError, match="Beziehungsart"):
        g.link(case.id, a.id, g.add_node(case.id, "person", "B").id, "liebt", [f.id])


def test_evidence_of_edge_is_capped_by_its_findings(engine):
    case = make_case(engine)
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "account", "B")
    weak = _finding(engine, case.id, evidence=Evidence.UNCONFIRMED)
    with pytest.raises(ValidationError, match="Belegstufe"):
        g.link(case.id, a.id, b.id, "has_account", [weak.id], evidence=Evidence.CONFIRMED)
    strong = _finding(engine, case.id, evidence=Evidence.CONFIRMED)
    e = g.link(case.id, a.id, b.id, "has_account", [weak.id, strong.id])
    assert e.evidence is Evidence.CONFIRMED


def test_rejected_findings_cannot_support_a_link(engine):
    case = make_case(engine)
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "account", "B")
    bad = _finding(engine, case.id, review=ReviewState.REJECTED)
    with pytest.raises(ValidationError, match="Abgelehnte"):
        g.link(case.id, a.id, b.id, "has_account", [bad.id])


def test_findings_of_other_cases_are_rejected(engine):
    case, other = make_case(engine), make_case(engine, name="anderer")
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "account", "B")
    foreign = _finding(engine, other.id)
    with pytest.raises(ValidationError, match="diesem Fall"):
        g.link(case.id, a.id, b.id, "has_account", [foreign.id])
    with pytest.raises(ValidationError, match="diesem Fall"):
        g.add_node(case.id, "person", "C", finding_ids=[foreign.id])


def test_same_person_never_from_username_alone(engine):
    case = make_case(engine)
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "person", "B")
    u1 = _finding(engine, case.id, tags=["username-match"])
    u2 = _finding(engine, case.id, tags=["username-match"])
    with pytest.raises(ValidationError, match="identischer Benutzernamen"):
        g.link(case.id, a.id, b.id, "same_person", [u1.id, u2.id], note="gleicher Benutzername überall")
    other = _finding(engine, case.id, title="E-Mail in beiden Profilen hinterlegt")
    with pytest.raises(ValidationError, match="Begründung"):
        g.link(case.id, a.id, b.id, "same_person", [u1.id, other.id], note="kurz")
    e = g.link(case.id, a.id, b.id, "same_person", [u1.id, other.id],
               note="Dieselbe E-Mail-Adresse ist in beiden Profilen öffentlich hinterlegt.")
    assert e.evidence is Evidence.INDICATION
    weak = _finding(engine, case.id, evidence=Evidence.UNCONFIRMED, title="nur Vermutung")
    with pytest.raises(ValidationError, match="Indiz"):
        g.link(case.id, a.id, g.add_node(case.id, "person", "C").id, "same_person", [weak.id],
               note="Vermutung aufgrund ähnlicher Schreibweise")


def test_suggestions_are_hints_only_and_never_persisted(engine):
    case = make_case(engine)
    g = engine.graph
    _finding(engine, case.id, tags=["username-match"], value="jdoe", title="GitHub")
    _finding(engine, case.id, tags=["username-match"], value="JDoe", title="Mastodon")
    sug = g.suggest_links(case.id)
    assert len(sug) == 1
    assert sug[0].evidence is Evidence.UNCONFIRMED and "kein Beleg" in sug[0].description
    assert g.edges(case.id) == []


def test_removing_a_node_removes_its_edges(engine):
    case = make_case(engine)
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "account", "B")
    f = _finding(engine, case.id)
    g.link(case.id, a.id, b.id, "has_account", [f.id])
    g.remove_node(case.id, b.id)
    assert g.edges(case.id) == [] and [n.id for n in g.nodes(case.id)] == [a.id]


def test_dot_export_escapes_labels(engine):
    case = make_case(engine)
    g = engine.graph
    g.add_node(case.id, "person", 'Anna "Ann" Beispiel\\x')
    dot = g.to_dot(case.id)
    assert dot.startswith("digraph personintel {") and dot.rstrip().endswith("}")
    assert '\\"Ann\\"' in dot and "\\\\x" in dot


def test_layout_is_deterministic_and_bounded(engine):
    case = make_case(engine)
    g = engine.graph
    nodes = [g.add_node(case.id, "person", f"N{i}") for i in range(6)]
    f = _finding(engine, case.id)
    edges = [g.link(case.id, nodes[0].id, nodes[i].id, "affiliated_with", [f.id]) for i in range(1, 4)]
    from personintel.graph.model import layout
    p1 = layout(nodes, edges)
    p2 = layout(nodes, edges)
    assert p1 == p2 and len(p1) == 6
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in p1.values())
    assert layout([], []) == {}
    assert layout([nodes[0]], []) == {nodes[0].id: (0.5, 0.5)}
