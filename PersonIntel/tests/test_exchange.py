"""JSON-Austauschformat: Roundtrip, Versionssperre, ID-Neuvergabe."""

import copy
import json

import pytest

from personintel import EXCHANGE_FORMAT, RESULT_SCHEMA_VERSION
from personintel.api import AppPaths, Engine, Evidence, ExchangeError, FindingStatus
from personintel.core.ids import new_id
from personintel.core.models import Finding
from personintel.exchange.schema import export_case, import_case, validate_bundle
from conftest import make_case


def _rich_case(engine):
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="sherlock", type="profile", title="GitHub",
                value="jdoe", url="https://github.com/jdoe", status=FindingStatus.FOUND,
                evidence=Evidence.INDICATION, target_id=t.id, tags=["username-match"])
    engine.repo.put("finding", f, ts=f.observed_at)
    a = engine.graph.add_node(case.id, "person", "Zielperson")
    b = engine.graph.add_node(case.id, "account", "github.com/jdoe", finding_ids=[f.id])
    engine.graph.link(case.id, a.id, b.id, "has_account", [f.id], note="Profil gefunden")
    return case, t, f


def test_bundle_shape(engine):
    case, t, f = _rich_case(engine)
    b = engine.export_case(case.id)
    assert b["format"] == EXCHANGE_FORMAT and b["schema_version"] == RESULT_SCHEMA_VERSION
    assert b["origin"]["app"] == "personintel" and b["exported_at"]
    assert b["case"]["id"] == case.id and b["case"]["purpose"]["category"] == "journalism"
    assert [x["id"] for x in b["targets"]] == [t.id]
    assert [x["id"] for x in b["findings"]] == [f.id]
    assert len(b["graph"]["nodes"]) == 2 and len(b["graph"]["edges"]) == 1
    validate_bundle(b)
    json.dumps(b)   # muss serialisierbar sein


def test_roundtrip_into_a_fresh_database_keeps_ids(engine, tmp_path):
    case, t, f = _rich_case(engine)
    bundle = engine.export_case(case.id)
    paths = AppPaths(data_dir=tmp_path / "d2", config_dir=tmp_path / "c2")
    other = Engine(paths)
    try:
        imported = other.import_case(bundle)
        assert imported.id == case.id and imported.name == case.name
        assert imported.purpose.description == case.purpose.description
        assert [x.id for x in other.targets(case.id)] == [t.id]
        got = other.findings(case.id)[0]
        assert got.id == f.id and got.evidence is Evidence.INDICATION and got.tags == ["username-match"]
        assert len(other.graph.edges(case.id)) == 1
        assert other.export_case(case.id)["findings"] == bundle["findings"]
    finally:
        other.close()


def test_importing_twice_remaps_all_ids_consistently(engine):
    case, t, f = _rich_case(engine)
    bundle = engine.export_case(case.id)
    again = engine.import_case(copy.deepcopy(bundle))
    assert again.id != case.id and again.name.endswith("(Import)")
    assert len(engine.cases()) == 2
    new_t = engine.targets(again.id)
    assert len(new_t) == 1 and new_t[0].id != t.id and new_t[0].value == "jdoe"
    new_f = engine.findings(again.id)
    assert new_f[0].id != f.id and new_f[0].target_id == new_t[0].id
    nodes = {n.id for n in engine.graph.nodes(again.id)}
    edge = engine.graph.edges(again.id)[0]
    assert edge.source in nodes and edge.target in nodes
    assert edge.basis_finding_ids == [new_f[0].id]          # Querverweise mitgezogen
    assert engine.findings(case.id)[0].id == f.id            # Original unberuehrt


def test_incompatible_major_version_is_refused(engine):
    case, _, _ = _rich_case(engine)
    b = engine.export_case(case.id)
    b["schema_version"] = "2.0"
    with pytest.raises(ExchangeError, match="Schemaversion"):
        validate_bundle(b)
    b["schema_version"] = "1.7"       # gleiche Hauptversion -> akzeptiert
    validate_bundle(b)
    b["schema_version"] = "keine"
    with pytest.raises(ExchangeError):
        validate_bundle(b)


@pytest.mark.parametrize("mutate,match", [
    (lambda b: b.update(format="etwas.anderes"), "Format"),
    (lambda b: b.pop("case"), "Fall-ID"),
    (lambda b: b["case"].update(id="keine-id"), "Fall-ID"),
    (lambda b: b.update(targets={}), "Liste"),
    (lambda b: b["targets"][0].update(id="kaputt"), "Ungültige ID"),
    (lambda b: b["targets"][0].update(case_id="case_ffffffffffffffff"), "gehört nicht"),
    (lambda b: b["targets"].append(dict(b["targets"][0])), "Doppelte ID"),
    (lambda b: b["findings"][0].update(evidence="erfunden"), "Ungültiger Datensatz"),
    (lambda b: b["graph"].update(edges="nope"), "graph.edges"),
])
def test_broken_bundles_are_rejected(engine, mutate, match):
    case, _, _ = _rich_case(engine)
    b = engine.export_case(case.id)
    mutate(b)
    with pytest.raises(ExchangeError, match=match):
        validate_bundle(b)


def test_unknown_fields_are_ignored_for_forward_compatibility(engine):
    case, _, _ = _rich_case(engine)
    b = engine.export_case(case.id)
    b["future_section"] = [{"x": 1}]
    b["case"]["spaeteres_feld"] = "egal"
    b["findings"][0]["noch_unbekannt"] = {"a": 1}
    validate_bundle(b)
    imported = engine.import_case(b)
    assert engine.findings(imported.id)[0].title == "GitHub"


def test_export_and_import_are_audited(engine):
    case, _, _ = _rich_case(engine)
    b = engine.export_case(case.id)
    engine.import_case(b)
    actions = [e.action for e in engine.audit.entries()]
    assert "case.export" in actions and "case.import" in actions


def test_export_contains_no_audit_log(engine):
    case, _, _ = _rich_case(engine)
    b = engine.export_case(case.id)
    assert "audit" not in b
