"""Plugin-Registrierung und stabile Paket-Schnittstelle (Fusion)."""

import pytest

from personintel import EXCHANGE_FORMAT, RESULT_SCHEMA_VERSION, __version__
from personintel.adapters import BUILTIN_ADAPTERS
from personintel.adapters.base import Capability, InstallInfo, ConfigValidation
from personintel.api import Adapter, PersonIntel, PersonIntelError
from personintel.core.models import NormalizedBatch, QueryKind, QueryMode
from personintel.core.plugins import ADAPTER_GROUP, UI_GROUP, PageSpec, PluginRegistry


class DemoAdapter(Adapter):
    id = "demo"
    name = "Demo"
    category = "Test"

    def detect_installation(self):
        return InstallInfo(True, message="da")

    def get_capabilities(self):
        return [Capability(QueryKind.USERNAME, QueryMode.PASSIVE, "Demo")]

    def validate_configuration(self, config=None):
        return ConfigValidation(True)

    def execute_authorized_query(self, query):
        aq = self._authorize(query)
        return self._raw(aq, "t0", {"ok": True})

    def normalize_results(self, raw):
        return NormalizedBatch()


def test_ten_builtin_adapters_in_dashboard_order():
    ids = [c.id for c in BUILTIN_ADAPTERS]
    assert ids == ["holehe", "mosint", "sherlock", "phoneinfoga", "ignorant", "mrholmes",
                   "pipl", "spokeo", "shadowdragon", "babelstreet"]
    assert len(set(ids)) == 10
    for cls in BUILTIN_ADAPTERS:
        assert cls.name and cls.category and cls.description


def test_every_adapter_implements_the_full_interface():
    for cls in BUILTIN_ADAPTERS:
        ad = cls()
        for method in ("detect_installation", "get_capabilities", "validate_configuration",
                       "execute_authorized_query", "cancel_query", "normalize_results", "get_status"):
            assert callable(getattr(ad, method)), f"{cls.id}.{method}"
        st = ad.get_status()
        assert st.adapter_id == cls.id and st.checked_at
        caps = ad.get_capabilities()
        assert caps and all(isinstance(c.kind, QueryKind) and isinstance(c.mode, QueryMode) for c in caps)
        for c in caps:
            assert c.available or c.reason, f"{cls.id}: nicht verfuegbare Funktion ohne Begruendung"


def test_registry_rejects_foreign_classes_and_duplicates():
    r = PluginRegistry()
    r.load_builtin()
    assert len(r.adapter_classes()) == 10
    r.load_builtin()                    # zweiter Lauf ist idempotent
    assert len(r.adapter_classes()) == 10
    with pytest.raises(PersonIntelError):
        r.register_adapter(object)      # type: ignore[arg-type]
    with pytest.raises(PersonIntelError):
        r.register_adapter(BUILTIN_ADAPTERS[0])
    r.register_adapter(DemoAdapter)
    assert r.adapter_class("demo") is DemoAdapter
    r.register_adapter(DemoAdapter, replace=True)


def test_pages_are_ordered():
    r = PluginRegistry()
    r.register_page(PageSpec("b", "B", lambda engine: None, order=10))
    r.register_page(PageSpec("a", "A", lambda engine: None, order=5))
    assert [p.id for p in r.pages()] == ["a", "b"]
    with pytest.raises(PersonIntelError):
        r.register_page(PageSpec("a", "A2", lambda engine: None))


def test_engine_accepts_runtime_registered_adapter(engine):
    engine.register_adapter(DemoAdapter)
    assert engine.adapter("demo").name == "Demo"
    assert "demo" in [s.adapter_id for s in engine.statuses()]
    from conftest import make_case
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    rec = engine.wait(engine.run_query(case.id, "demo", t.id).id, 20)   # passiv: ohne Bestaetigung
    assert rec.state.value == "done"


def test_entry_point_groups_and_bad_plugins_are_not_fatal(monkeypatch):
    import importlib.metadata as md

    class EP:
        def __init__(self, name, obj):
            self.name, self._obj = name, obj

        def load(self):
            if isinstance(self._obj, Exception):
                raise self._obj
            return self._obj

    class EPS:
        def select(self, group):
            if group == ADAPTER_GROUP:
                return [EP("demo", DemoAdapter), EP("kaputt", RuntimeError("Importfehler"))]
            if group == UI_GROUP:
                return [EP("seite", PageSpec("p", "P", lambda engine: None))]
            return []

    monkeypatch.setattr(md, "entry_points", lambda: EPS())
    r = PluginRegistry()
    problems = r.load_entry_points()
    assert r.adapter_class("demo") is DemoAdapter
    assert [p.id for p in r.pages()] == ["p"]
    assert len(problems) == 1 and "kaputt" in problems[0]


def test_public_api_surface_is_stable():
    import personintel.api as api
    for name in ("PersonIntel", "Engine", "AppPaths", "Settings", "Limits", "Adapter", "AdapterStatus",
                 "Capability", "ConfigField", "PluginRegistry", "PageSpec", "ActiveConfirmation",
                 "Case", "Target", "Source", "Finding", "QueryRecord", "Purpose", "Evidence", "QueryKind",
                 "QueryMode", "ReviewState", "ReportOptions", "export_case", "import_case", "validate_bundle"):
        assert hasattr(api, name), name
    assert PersonIntel is api.Engine
    assert RESULT_SCHEMA_VERSION == "1.0" and EXCHANGE_FORMAT == "personintel.case" and __version__


def test_ids_are_prefixed_and_unique(engine):
    from conftest import make_case
    case = make_case(engine)
    t = engine.add_target(case.id, "username", "jdoe")
    node = engine.graph.add_node(case.id, "person", "A")
    assert case.id.startswith("case_") and t.id.startswith("tgt_") and node.id.startswith("nod_")
    from personintel.core.ids import is_valid_id
    assert all(is_valid_id(i) for i in (case.id, t.id, node.id))
