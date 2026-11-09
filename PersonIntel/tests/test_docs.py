"""Die Dokumentation wird gegen den Code geprueft: Beispiele laufen, genannte Namen existieren."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from personintel import EXCHANGE_FORMAT, RESULT_SCHEMA_VERSION, __version__
from personintel.adapters import BUILTIN_ADAPTERS
from personintel.core.ids import is_valid_id

PROJECT = Path(__file__).resolve().parent.parent
DOCS = {p.name: p.read_text(encoding="utf-8") for p in
        [PROJECT / "README.md", *(PROJECT / "docs").glob("*.md")]}


def test_all_documents_exist():
    assert set(DOCS) == {"README.md", "INSTALL.md", "ARCHITECTURE.md", "FUSION.md"}


def test_readme_lists_all_ten_modules_with_honest_state():
    text = DOCS["README.md"]
    for cls in BUILTIN_ADAPTERS:
        assert cls.name in text, cls.name
    # Die beiden Anbieter ohne oeffentliche Dokumentation muessen als nicht verfuegbar stehen
    for name in ("ShadowDragon", "Babel Street"):
        i = text.index(name)
        zeile = text[i:text.index("\n", i)]
        assert "nicht verfügbar" in zeile.lower(), zeile


def test_install_guide_matches_the_adapters_install_hints():
    text = DOCS["INSTALL.md"]
    for cls in BUILTIN_ADAPTERS:
        hint = cls().install_hint()
        if not hint:
            continue
        # Mindestens einer der im Hinweis genannten Installationswege muss in der Anleitung stehen
        tokens = re.findall(r"(?:pipx install|pip install|go install) [\w./@\-]+", hint)
        if tokens:
            assert any(t in text for t in tokens), f"{cls.id}: keiner von {tokens} in INSTALL.md"


def test_install_guide_names_environment_variable_scheme(engine):
    from personintel.security.credentials import env_name
    text = DOCS["INSTALL.md"]
    assert env_name("pipl", "api_key") in text
    assert "PERSONINTEL_HOME" in text and "PERSONINTEL_DB_PASSPHRASE" in text


def test_architecture_lists_the_real_package_layout():
    text = DOCS["ARCHITECTURE.md"]
    src = PROJECT / "src" / "personintel"
    for pkg in sorted(p.name for p in src.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if pkg == "resources":
            continue
        assert f"{pkg}/" in text, pkg
    for method in ("detect_installation", "get_capabilities", "validate_configuration",
                   "execute_authorized_query", "cancel_query", "normalize_results", "get_status"):
        assert method in text, method


def test_fusion_doc_names_only_existing_api():
    import personintel.api as api
    text = DOCS["FUSION.md"]
    for name in re.findall(r"`(?:pi|engine)\.([a-z_]+)\(", text):
        assert hasattr(api.Engine, name), f"FUSION.md nennt Engine.{name}, das es nicht gibt"
    for name in re.findall(r"^\| Paketversion \| `personintel\.(\w+)`", text, re.M):
        assert hasattr(__import__("personintel"), name)
    assert RESULT_SCHEMA_VERSION in text and EXCHANGE_FORMAT in text


def test_fusion_doc_enum_values_are_complete_and_correct():
    from personintel.core.models import Evidence, FindingStatus, QueryKind, QueryMode, ReviewState
    text = DOCS["FUSION.md"]
    for field, enum in (("evidence", Evidence), ("status", FindingStatus), ("review_state", ReviewState),
                        ("kind", QueryKind), ("mode", QueryMode)):
        match = re.search(rf"`{field}` = `([a-z_|]+)`", text)
        assert match, field
        documented = set(match.group(1).split("|"))
        assert documented == {m.value for m in enum}, field


def test_fusion_doc_id_prefixes_are_the_real_ones(engine):
    from conftest import make_case
    text = DOCS["FUSION.md"]
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    node = engine.graph.add_node(case.id, "person", "A")
    for value in (case.id, t.id, node.id):
        prefix = value.split("_", 1)[0]
        assert f"`{prefix}_`" in text, prefix
        assert is_valid_id(value)


def test_fusion_api_example_runs_as_documented(tmp_path, bin_dir):
    """Das Hauptbeispiel aus FUSION.md - ohne echte Abfrage, aber mit allen Aufrufen."""
    from pathlib import Path as P

    from personintel.api import ActiveConfirmation, AppPaths, PersonIntel, Purpose, QueryKind

    pi = PersonIntel(AppPaths(data_dir=P(tmp_path / "data"), config_dir=P(tmp_path / "config")))
    try:
        case = pi.create_case("Recherche X")
        pi.set_purpose(case.id, Purpose(category="journalism",
                                        description="Verifikation einer Quelle für Artikel Y",
                                        authorized_by="Redaktionsleitung",
                                        active_checks_allowed=True), days_valid=30)
        target = pi.add_target(case.id, QueryKind.EMAIL, "person@example.org")
        conf = ActiveConfirmation(typed_target="person@example.org",
                                  acknowledges_third_party_contact=True,
                                  acknowledges_terms_of_service=True)
        assert conf.typed_target == "person@example.org"
        for f in pi.findings(case.id):
            assert f.evidence.label_de
        bundle = pi.export_case(case.id)
        assert bundle["format"] == EXCHANGE_FORMAT
        report = pi.build_report(case.id)
        assert report.to_markdown() and report.to_html() and json.loads(report.to_json())
        assert [t.id for t in pi.targets(case.id)] == [target.id]
        assert pi.timeline(case.id)
        assert pi.statuses() and pi.adapters()
    finally:
        pi.close()


def test_fusion_bundle_example_matches_a_real_export(engine):
    """Die im Dokument gezeigten Abschnitte und Felder muessen im echten Export vorkommen."""
    from conftest import make_case
    case = make_case(engine)
    engine.add_target(case.id, "email", "a@example.org")
    bundle = engine.export_case(case.id)
    for section in ("format", "schema_version", "exported_at", "origin", "case", "targets",
                    "sources", "findings", "queries", "events", "graph"):
        assert section in bundle, section
    assert set(bundle["graph"]) == {"nodes", "edges"}
    text = DOCS["FUSION.md"]
    for section in bundle:
        assert f'"{section}"' in text, section


def test_fusion_entry_point_groups_are_the_real_ones():
    from personintel.core.plugins import ADAPTER_GROUP, UI_GROUP
    text = DOCS["FUSION.md"]
    assert f'"{ADAPTER_GROUP}"' in text and f'"{UI_GROUP}"' in text


def test_fusion_ui_embedding_example_imports(qapp_available=None):
    """Die als einbettbar dokumentierten Seiten muessen genau so importierbar sein."""
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from personintel.ui.context import AppContext            # noqa: F401
    from personintel.ui.pages.dashboard import DashboardPage  # noqa: F401
    from personintel.ui.pages.results import ResultsPage      # noqa: F401
    text = DOCS["FUSION.md"]
    for signal in ("case_changed", "data_changed", "cases_changed", "query_updated",
                   "statuses_changed", "message"):
        assert signal in text
        assert hasattr(AppContext, signal), signal
    for method in ("run_async", "set_case", "shutdown"):
        assert hasattr(AppContext, method)


def test_version_in_docs_is_not_stale():
    assert __version__ in DOCS["FUSION.md"]


def test_cli_commands_mentioned_in_docs_exist():
    from personintel.cli import build_parser
    sub = [a for a in build_parser()._actions if hasattr(a, "choices") and a.choices]
    commands = set()
    for a in sub:
        commands |= set(a.choices)
    assert {"status", "cases", "audit-verify", "export", "import", "report"} <= commands
    for doc in ("README.md", "INSTALL.md", "FUSION.md"):
        for cmd in re.findall(r"personintel-cli ([a-z\-]+)", DOCS[doc]):
            if cmd not in ("--help",):
                assert cmd in commands, f"{doc}: personintel-cli {cmd} gibt es nicht"
