"""Oberflaechentest (offscreen): alle Seiten bauen, Fallwechsel, Pflichtbestaetigung, Berichtsvorschau.

Laeuft ohne Bildschirm (``QT_QPA_PLATFORM=offscreen``). Uebersprungen, wenn PySide6 fehlt.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="PySide6 ist nicht installiert (pip install 'personintel[ui]')")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog             # noqa: E402

from personintel.api import Evidence, FindingStatus, Purpose    # noqa: E402
from personintel.core.ids import new_id                         # noqa: E402
from personintel.core.models import Finding, QueryKind, Source  # noqa: E402
from personintel.ui.app import app_icon, parse_args, resolve_paths  # noqa: E402
from personintel.ui.context import AppContext                   # noqa: E402
from personintel.ui.dialogs import ActiveCheckDialog, LinkDialog, PurposeDialog, ReviewDialog  # noqa: E402
from personintel.ui.main_window import BUILTIN_PAGES, MainWindow  # noqa: E402
from conftest import PURPOSE_TEXT, make_case                    # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, engine):
    ctx = AppContext(engine)
    w = MainWindow(ctx)
    yield w
    ctx.shutdown()
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _pump(qapp, n: int = 6):
    for _ in range(n):
        qapp.processEvents()


# ----------------------------------------------------------------- Aufbau
def test_all_pages_build_and_switch(win, qapp):
    expected = ["dashboard", "cases", "research", "results", "graph", "timeline", "report", "settings"]
    assert [c.id for c in BUILTIN_PAGES] == expected
    assert sorted(win.pages) == sorted(expected)
    for pid in expected:
        win.show_page(pid)
        _pump(qapp)
        assert win.stack.currentWidget() is win.pages[pid]
        assert win._buttons[pid].isChecked()
    assert "PersonIntel" in win.windowTitle()


def test_icon_loads(qapp):
    assert not app_icon().isNull()


def test_dashboard_shows_real_module_status(win, qapp, engine):
    win.ctx.refresh_statuses()
    for _ in range(80):
        _pump(qapp)
        if win.ctx.statuses:
            break
    page = win.pages["dashboard"]
    page.refresh()
    _pump(qapp)
    assert page.table.rowCount() == 10
    names = [page.table.item(r, 1).text() for r in range(10)]
    assert "Holehe" in names and "Babel Street" in names
    # Ohne installierte Werkzeuge muss eine konkrete Voraussetzung dastehen, keine Erfolgsmeldung
    row = names.index("Holehe")
    assert page.table.item(row, 3).text() in ("Nicht installiert", "Bereit")
    assert page.table.item(row, 5).text()
    assert "betriebsbereit" in page.summary.text()


def test_case_selection_propagates_everywhere(win, qapp, engine):
    case = make_case(engine)
    win.ctx.cases_changed.emit()
    win.ctx.set_case(case.id)
    _pump(qapp)
    assert win.case_combo.currentData() == case.id
    assert "Zweck gültig" in win.purpose_badge.text()
    assert case.name in win.pages["research"].banner.text()


def test_research_blocks_without_valid_purpose(win, qapp, engine):
    case = engine.create_case("ohne Zweck")
    win.ctx.cases_changed.emit()
    win.ctx.set_case(case.id)
    engine.add_target(case.id, "email", "a@example.org")
    page = win.pages["research"]
    page.refresh()
    _pump(qapp)
    assert "Abfragen sind gesperrt" in page.banner.text()
    assert page.b_start.isEnabled() is False
    assert page.notice.isVisible() or not page.b_start.isEnabled()


def test_research_blocks_active_check_when_purpose_forbids_it(win, qapp, engine):
    case = make_case(engine, active=False)
    win.ctx.cases_changed.emit()
    win.ctx.set_case(case.id)
    engine.add_target(case.id, "email", "a@example.org")
    page = win.pages["research"]
    page.refresh()
    _pump(qapp)
    i = page.adapter.findData("holehe")
    assert i >= 0
    page.adapter.setCurrentIndex(i)
    _pump(qapp)
    assert "Aktive Prüfung" in page.mode_label.text()
    assert not page.b_start.isEnabled()
    assert "erlaubt keine aktiven" in page.notice.text()


def test_research_marks_passive_check(win, qapp, engine):
    case = make_case(engine, active=False)
    win.ctx.cases_changed.emit()
    win.ctx.set_case(case.id)
    engine.add_target(case.id, "phone", "+4930123456")
    page = win.pages["research"]
    page.refresh()
    _pump(qapp)
    i = page.adapter.findData("phoneinfoga")
    page.adapter.setCurrentIndex(i)
    _pump(qapp)
    assert "Passive Prüfung" in page.mode_label.text()


def test_unavailable_vendor_module_is_marked_in_research(win, qapp, engine):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    engine.add_target(case.id, "email", "a@example.org")
    page = win.pages["research"]
    page.refresh()
    _pump(qapp)
    i = page.adapter.findData("babelstreet")
    assert i >= 0
    assert "nicht verfügbar" in page.adapter.itemText(i)
    page.adapter.setCurrentIndex(i)
    _pump(qapp)
    assert not page.b_start.isEnabled() and page.notice.text()


# ----------------------------------------------------------------- Dialoge
def test_active_check_dialog_requires_typed_target_and_both_acknowledgements(qapp):
    dlg = ActiveCheckDialog("Holehe", QueryKind.EMAIL, "a@example.org", cost_note="", description="")
    assert not dlg.ok_button.isEnabled()
    dlg.typed.setText("a@example.org")
    assert not dlg.ok_button.isEnabled()
    dlg.cb_third.setChecked(True)
    assert not dlg.ok_button.isEnabled()
    dlg.cb_tos.setChecked(True)
    assert dlg.ok_button.isEnabled()
    dlg.typed.setText("jemand.anderes@example.org")
    assert not dlg.ok_button.isEnabled()
    dlg.typed.setText("A@Example.org")           # Gross-/Kleinschreibung egal
    assert dlg.ok_button.isEnabled()
    c = dlg.confirmation()
    assert c.acknowledges_third_party_contact and c.acknowledges_terms_of_service
    dlg.deleteLater()


def test_purpose_dialog_validates(qapp):
    dlg = PurposeDialog(min_chars=20, max_days=90)
    dlg.description.setPlainText("zu kurz")
    dlg.authorized_by.setText("Redaktion")
    dlg._accept()
    assert dlg.result() != QDialog.DialogCode.Accepted and "mind. 20" in dlg.error.text()
    dlg.description.setPlainText(PURPOSE_TEXT)
    dlg.authorized_by.setText("")
    dlg._accept()
    assert "verantwortliche" in dlg.error.text().lower()
    dlg.authorized_by.setText("Redaktionsleitung")
    for i in range(dlg.kinds.count()):
        dlg.kinds.item(i).setCheckState(Qt.Unchecked)
    dlg._accept()
    assert "Kennungsart" in dlg.error.text()
    dlg.kinds.item(0).setCheckState(Qt.Checked)
    dlg._accept()
    p = dlg.purpose()
    assert p.description == PURPOSE_TEXT and p.authorized_by == "Redaktionsleitung"
    assert p.allowed_kinds == [QueryKind.EMAIL.value]
    dlg.deleteLater()


def test_review_dialog_requires_note_for_confirmed(qapp, engine):
    case = make_case(engine)
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="sherlock", type="profile", title="GitHub",
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION)
    dlg = ReviewDialog(f)
    dlg.evidence.setCurrentIndex(dlg.evidence.findData(Evidence.CONFIRMED.value))
    dlg._accept()
    assert "Begründung" in dlg.error.text()
    dlg.note.setPlainText("Von der Person selbst bestätigt.")
    dlg._accept()
    assert dlg.values()["evidence"] is Evidence.CONFIRMED
    dlg.deleteLater()


def test_link_dialog_requires_a_basis_finding(qapp, engine):
    case = make_case(engine)
    g = engine.graph
    a, b = g.add_node(case.id, "person", "A"), g.add_node(case.id, "account", "B")
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="sherlock", type="profile", title="GitHub",
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION)
    engine.repo.put("finding", f, ts=f.observed_at)
    dlg = LinkDialog([a, b], [f])
    dlg._accept()
    assert "Basisbefund" in dlg.error.text()
    dlg.findings.item(0).setCheckState(Qt.Checked)
    dlg._accept()
    v = dlg.values()
    assert v["basis_finding_ids"] == [f.id] and v["source"] == a.id and v["target"] == b.id
    dlg.deleteLater()


# ---------------------------------------------------------------- Ergebnisse
def _add_findings(engine, case_id):
    t = engine.add_target(case_id, "username", "jdoe")
    src = Source(id=new_id("src"), case_id=case_id, adapter_id="sherlock", description="sherlock CSV",
                 tool_version="sherlock 0.16.0", active=True)
    engine.repo.put("source", src, ts=src.retrieved_at)
    out = []
    for title, ev in (("GitHub", Evidence.INDICATION), ("Belegt", Evidence.CONFIRMED), ("Vage", Evidence.UNCONFIRMED)):
        f = Finding(id=new_id("fnd"), case_id=case_id, adapter_id="sherlock", source_id=src.id, target_id=t.id,
                    type="profile", title=title, value="jdoe", url=f"https://x/{title}",
                    status=FindingStatus.FOUND, evidence=ev, tags=["username-match"])
        engine.repo.put("finding", f, ts=f.observed_at)
        out.append(f)
    return out


def test_results_table_filters_and_detail(win, qapp, engine):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    findings = _add_findings(engine, case.id)
    page = win.pages["results"]
    page.refresh()
    _pump(qapp)
    assert page.table.rowCount() == 3
    assert "belegt 1" in page.count.text() and "Indiz 1" in page.count.text()
    # Belegstufe steht in jeder Zeile
    stufen = {page.table.item(r, 2).text() for r in range(3)}
    assert stufen == {"unmittelbar belegt", "Indiz", "unbestätigt"}
    page.f_evidence.setCurrentIndex(page.f_evidence.findData(Evidence.CONFIRMED.value))
    _pump(qapp)
    assert page.table.rowCount() == 1 and page.table.item(0, 0).text() == "Belegt"
    page.table.selectRow(0)
    _pump(qapp)
    html = page.detail.toHtml()
    assert "sherlock 0.16.0" in html and "aktiv (Drittkontakt)" in html
    assert page.b_review.isEnabled()


def test_results_review_and_reject(win, qapp, engine):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    findings = _add_findings(engine, case.id)
    page = win.pages["results"]
    page.refresh()
    page.table.selectRow(0)
    _pump(qapp)
    page._reject()
    _pump(qapp)
    assert any(f.review_state.value == "rejected" for f in engine.findings(case.id))


def test_results_escapes_html_in_detail(win, qapp, engine):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    engine.add_target(case.id, "username", "jdoe")
    f = Finding(id=new_id("fnd"), case_id=case.id, adapter_id="x", type="profile",
                title="<script>alert(1)</script>", status=FindingStatus.FOUND, evidence=Evidence.INDICATION)
    engine.repo.put("finding", f, ts=f.observed_at)
    page = win.pages["results"]
    page.refresh()
    page.table.selectRow(0)
    _pump(qapp)
    assert "&lt;script&gt;" in page.detail.toHtml()


# --------------------------------------------------------------- Graph/Bericht
def test_graph_page_draws_and_shows_hints(win, qapp, engine):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    findings = _add_findings(engine, case.id)
    g = engine.graph
    a = g.add_node(case.id, "person", "Zielperson")
    b = g.add_node(case.id, "account", "github.com/jdoe", finding_ids=[findings[0].id])
    g.link(case.id, a.id, b.id, "has_account", [findings[0].id], note="Profil gefunden")
    page = win.pages["graph"]
    page.refresh()
    _pump(qapp)
    assert page.nodes.rowCount() == 2 and page.edges.rowCount() == 1
    assert page.edges.item(0, 1).text() == "hat Konto/Profil"
    assert page.view.scene().items()
    assert "Benutzername" in page.suggestions.text()     # Hinweis, keine Verbindung


def test_timeline_and_report_preview(win, qapp, engine, tmp_path):
    case = make_case(engine)
    win.ctx.set_case(case.id)
    _add_findings(engine, case.id)
    tl = win.pages["timeline"]
    tl.refresh()
    _pump(qapp)
    assert tl.table.rowCount() >= 3 and "Einträge" in tl.info.text()

    rep = win.pages["report"]
    rep.refresh()
    _pump(qapp)
    html = rep.preview.toHtml()
    assert "Recherchebericht" in html and "Belegstufe" in html or "unmittelbar belegt" in html
    assert rep.b_pdf.isEnabled()

    # Export ohne Dialog pruefen
    report = engine.build_report(case.id, **rep._options())
    out = tmp_path / "b.html"
    out.write_text(report.to_html(), encoding="utf-8")
    assert "<!DOCTYPE html>" in out.read_text()


def test_report_pdf_export_writes_a_file(win, qapp, engine, tmp_path):
    pytest.importorskip("PySide6.QtPrintSupport")
    from PySide6.QtGui import QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter
    case = make_case(engine)
    win.ctx.set_case(case.id)
    _add_findings(engine, case.id)
    rep = engine.build_report(case.id)
    path = tmp_path / "bericht.pdf"
    doc = QTextDocument()
    doc.setHtml(rep.to_html())
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setOutputFileName(str(path))
    doc.print_(printer)
    assert path.exists() and path.read_bytes().startswith(b"%PDF")


# ------------------------------------------------------------- Einstellungen
def test_settings_page_lists_modules_and_masks_secrets(win, qapp, engine):
    page = win.pages["settings"]
    page.refresh()
    _pump(qapp)
    assert page.list.count() == 10
    page.select_adapter("pipl")
    _pump(qapp)
    assert page.form_box.title().startswith("Pipl")
    from PySide6.QtWidgets import QLineEdit
    assert page._widgets["api_key"].echoMode() == QLineEdit.Password
    assert "entsperrt" in page.cred_state.text()
    assert "unverschlüsselt" in page.enc_state.text()


def test_settings_saves_config_and_secret(win, qapp, engine):
    page = win.pages["settings"]
    page.select_adapter("pipl")
    _pump(qapp)
    page._widgets["api_key"].setText("GEHEIM-123")
    page._widgets["base_url"].setText("https://api.example.org")
    page._save_adapter()
    _pump(qapp)
    assert engine.credentials.get("pipl", "api_key") == "GEHEIM-123"
    assert engine.settings.adapter_config["pipl"]["base_url"] == "https://api.example.org"
    import json
    assert "GEHEIM-123" not in json.dumps(engine.settings.to_dict())


def test_settings_limits_are_persisted(win, qapp, engine):
    page = win.pages["settings"]
    page.refresh()
    page.max_targets.setValue(4)
    page.min_interval.setValue(0)
    page._save_limits()
    _pump(qapp)
    assert engine.settings.limits.max_targets_per_case == 4
    assert engine.gate.limits.max_targets_per_case == 4


def test_dashboard_toggle_disables_module(win, qapp, engine):
    page = win.pages["dashboard"]
    win.ctx.refresh_statuses()
    for _ in range(80):
        _pump(qapp)
        if win.ctx.statuses:
            break
    page.refresh()
    _pump(qapp)
    page.table.selectRow(0)
    _pump(qapp)
    aid = page.table.item(0, 0).data(Qt.UserRole)
    page._toggle()
    _pump(qapp)
    assert engine.settings.is_enabled(aid) is False


# --------------------------------------------------------------- Hilfsfunktionen
def test_parse_args_and_paths(tmp_path):
    args = parse_args(["--data-dir", str(tmp_path / "x")])
    paths = resolve_paths(args.data_dir)
    assert paths.data_dir.exists() and paths.config_dir.exists()
    assert oct(paths.data_dir.stat().st_mode)[-3:] == "700"


def test_context_runs_work_in_background(qapp, engine):
    ctx = AppContext(engine)
    got = []
    # Ergebnisse muessen den GUI-Thread erreichen, auch wenn der Threadpool den Auftrag
    # unmittelbar nach der Ausfuehrung verwirft.
    ctx.run_async(lambda: 21 * 2, got.append)
    for _ in range(100):
        _pump(qapp)
        if got:
            break
    assert got == [42]
    errors = []
    ctx.run_async(lambda: 1 / 0, lambda _: None, errors.append)
    for _ in range(100):
        _pump(qapp)
        if errors:
            break
    assert errors and "ZeroDivisionError" in errors[0]
    ctx.shutdown()


# ------------------------------------------------------------- echter Startweg
def test_run_starts_and_quits_cleanly(qapp, tmp_path, monkeypatch, bin_dir):
    """Startet den echten Einstiegspunkt (ui.app.run) und beendet ihn ueber einen Timer."""
    from PySide6.QtCore import QTimer
    from personintel.ui.app import run
    monkeypatch.delenv("PERSONINTEL_DB_PASSPHRASE", raising=False)
    QTimer.singleShot(1200, qapp.quit)
    code = run(["--data-dir", str(tmp_path / "home")])
    assert code == 0
    assert (tmp_path / "home" / "data" / "personintel.db").is_file()


def test_run_reports_version(qapp, capsys):
    from personintel.ui.app import run
    with pytest.raises(SystemExit) as exc:
        run(["--version"])
    assert exc.value.code == 0
    assert "personintel" in capsys.readouterr().out


def test_module_entry_point_starts_the_ui(qapp, tmp_path, bin_dir):
    """`python -m personintel` muss die Oberflaeche aufrufen (hier ohne echtes Fenster)."""
    import personintel.__main__ as main_mod
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1000, qapp.quit)
    assert main_mod.main(["--data-dir", str(tmp_path / "h2")]) == 0


def test_locked_database_asks_for_passphrase(qapp, tmp_path, monkeypatch, bin_dir):
    """Bei verschluesselter Datenbank wird die Passphrase erfragt - und akzeptiert."""
    from personintel.api import AppPaths, Engine
    from personintel.ui import app as app_mod
    base = tmp_path / "enc"
    paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    paths.ensure()
    eng = Engine(paths, db_passphrase="geheim")
    make_case(eng)
    eng.close()
    monkeypatch.delenv("PERSONINTEL_DB_PASSPHRASE", raising=False)
    asked = []

    def ask(info: str) -> str:
        asked.append(info)
        return "geheim"

    engine = app_mod.open_engine(paths, ask_passphrase=ask)
    try:
        assert asked and "Passphrase" in asked[0]
        assert engine.cases()[0].name == "Testfall"
    finally:
        engine.close()
