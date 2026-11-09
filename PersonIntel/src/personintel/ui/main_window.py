"""Hauptfenster: Seitennavigation, Fallauswahl, Statusleiste."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core.plugins import PageSpec
from .context import AppContext
from .pages.cases import CasesPage
from .pages.dashboard import DashboardPage
from .pages.graph import GraphPage
from .pages.report import ReportPage
from .pages.research import ResearchPage
from .pages.results import ResultsPage
from .pages.settings import SettingsPage
from .pages.timeline import TimelinePage
from .style import STYLESHEET

BUILTIN_PAGES = (DashboardPage, CasesPage, ResearchPage, ResultsPage, GraphPage, TimelinePage, ReportPage,
                 SettingsPage)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"PersonIntel {__version__} – Personenrecherche mit Belegpflicht")
        self.resize(1280, 860)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 14, 0, 14)
        sl.setSpacing(2)
        brand = QLabel("  PersonIntel")
        brand.setStyleSheet("color:#eaf1f8; font-size:16px; font-weight:bold; padding:6px 10px;")
        sl.addWidget(brand)
        sub = QLabel("  journalistische Recherche")
        sub.setStyleSheet("color:#8ea4b8; font-size:11px; padding:0 10px 10px 10px;")
        sl.addWidget(sub)

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self._order: list[str] = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        for cls in BUILTIN_PAGES:
            self._add_page(cls.id, cls.title, cls(ctx), sl)
        for spec in ctx.engine.registry.pages():
            self._add_plugin_page(spec, sl)
        sl.addStretch(1)
        self.case_hint = QLabel("")
        self.case_hint.setWordWrap(True)
        self.case_hint.setStyleSheet("color:#8ea4b8; font-size:11px; padding:8px 10px;")
        sl.addWidget(self.case_hint)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(18, 10, 18, 0)
        bl.addWidget(QLabel("Aktueller Fall:"))
        self.case_combo = QComboBox()
        self.case_combo.setMinimumWidth(320)
        self.case_combo.currentIndexChanged.connect(self._case_selected)
        bl.addWidget(self.case_combo)
        bl.addStretch(1)
        self.purpose_badge = QLabel("")
        bl.addWidget(self.purpose_badge)
        rl.addWidget(bar)
        rl.addWidget(self.stack, 1)

        lay.addWidget(side)
        lay.addWidget(right, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Bereit.")
        self._build_menu()

        ctx.message.connect(self._message)
        ctx.cases_changed.connect(self._fill_cases)
        ctx.case_changed.connect(lambda _: self._sync_case())
        ctx.data_changed.connect(self._sync_case)
        self._fill_cases()
        self.show_page("dashboard")

    # ------------------------------------------------------------------
    def _add_page(self, pid: str, title: str, widget: QWidget, sidebar_layout) -> None:
        self.pages[pid] = widget
        self._order.append(pid)
        self.stack.addWidget(widget)
        btn = QPushButton(title)
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, p=pid: self.show_page(p))
        self.group.addButton(btn)
        self._buttons[pid] = btn
        sidebar_layout.addWidget(btn)

    def _add_plugin_page(self, spec: PageSpec, sidebar_layout) -> None:
        try:
            widget = spec.factory(self.ctx)
        except Exception as exc:  # Plugins duerfen die Anwendung nicht verhindern
            self.statusBar().showMessage(f"Plugin-Seite „{spec.id}“ nicht geladen: {exc}")
            return
        if isinstance(widget, QWidget) and spec.id not in self.pages:
            self._add_page(spec.id, spec.title, widget, sidebar_layout)

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&Datei")
        a_new = QAction("Neuer Fall …", self)
        a_new.setShortcut(QKeySequence.New)
        a_new.triggered.connect(lambda: (self.show_page("cases"), self.pages["cases"]._new_case()))
        m.addAction(a_new)
        a_exp = QAction("Fall exportieren …", self)
        a_exp.triggered.connect(lambda: (self.show_page("cases"), self.pages["cases"]._export()))
        m.addAction(a_exp)
        a_imp = QAction("Fall importieren …", self)
        a_imp.triggered.connect(lambda: (self.show_page("cases"), self.pages["cases"]._import()))
        m.addAction(a_imp)
        m.addSeparator()
        a_quit = QAction("Beenden", self)
        a_quit.setShortcut(QKeySequence.Quit)
        a_quit.triggered.connect(self.close)
        m.addAction(a_quit)

        v = self.menuBar().addMenu("&Ansicht")
        for pid in self._order:
            act = QAction(self._buttons[pid].text(), self)
            act.triggered.connect(lambda _=False, p=pid: self.show_page(p))
            v.addAction(act)

        t = self.menuBar().addMenu("&Werkzeuge")
        a_status = QAction("Modulstatus neu prüfen", self)
        a_status.setShortcut(QKeySequence.Refresh)
        a_status.triggered.connect(self.ctx.refresh_statuses)
        t.addAction(a_status)
        a_audit = QAction("Protokoll-Integrität prüfen", self)
        a_audit.triggered.connect(self._verify_audit)
        t.addAction(a_audit)

        h = self.menuBar().addMenu("&Hilfe")
        a_about = QAction("Über PersonIntel", self)
        a_about.triggered.connect(self._about)
        h.addAction(a_about)

    # ------------------------------------------------------------------
    def show_page(self, pid: str, **kwargs) -> None:
        widget = self.pages.get(pid)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        btn = self._buttons.get(pid)
        if btn is not None:
            btn.setChecked(True)
        if pid == "settings" and "adapter_id" in kwargs:
            widget.select_adapter(kwargs["adapter_id"])
        if hasattr(widget, "on_shown"):
            widget.on_shown()

    def _fill_cases(self) -> None:
        cases = self.ctx.engine.cases()
        self.case_combo.blockSignals(True)
        self.case_combo.clear()
        self.case_combo.addItem("– kein Fall ausgewählt –", "")
        for c in cases:
            self.case_combo.addItem(c.name, c.id)
        i = self.case_combo.findData(self.ctx.case_id)
        self.case_combo.setCurrentIndex(max(0, i))
        self.case_combo.blockSignals(False)
        self._sync_case()

    def _case_selected(self) -> None:
        self.ctx.set_case(self.case_combo.currentData() or "")

    def _sync_case(self) -> None:
        case = self.ctx.case
        i = self.case_combo.findData(self.ctx.case_id)
        if i >= 0 and i != self.case_combo.currentIndex():
            self.case_combo.blockSignals(True)
            self.case_combo.setCurrentIndex(i)
            self.case_combo.blockSignals(False)
        if case is None:
            self.purpose_badge.setText("")
            self.case_hint.setText("Ohne ausgewählten Fall sind keine Abfragen möglich.")
            return
        valid = self.ctx.engine.gate.purpose_valid(case)
        if valid:
            p = case.purpose
            self.purpose_badge.setText(
                f"<span style='color:#1b7f3a'><b>Zweck gültig</b></span> bis {p.expires_at[:10]} · "
                f"aktive Prüfungen: {'erlaubt' if p.active_checks_allowed else 'nicht erlaubt'}")
            self.case_hint.setText(f"{len(self.ctx.engine.targets(case.id))} Kennung(en) im Fallumfang.")
        else:
            self.purpose_badge.setText("<span style='color:#a62121'><b>kein gültiger Zweck – Abfragen gesperrt"
                                       "</b></span>")
            self.case_hint.setText("Bitte unter „Fälle“ den Recherchezweck dokumentieren.")

    def _message(self, text: str, error: bool) -> None:
        self.statusBar().showMessage(("Fehler: " if error else "") + text, 12000)

    def _verify_audit(self) -> None:
        ok, bad = self.ctx.engine.audit.verify()
        if ok:
            QMessageBox.information(self, "Protokoll", "Die Hash-Kette des Protokolls ist unverändert.")
        else:
            QMessageBox.warning(self, "Protokoll",
                                f"Das Protokoll ist ab Eintrag {bad} nicht mehr schlüssig. Das deutet auf eine "
                                f"Veränderung außerhalb der Anwendung hin.")

    def _about(self) -> None:
        QMessageBox.about(
            self, "Über PersonIntel",
            f"<b>PersonIntel {__version__}</b><br>"
            "Modulares Werkzeug für journalistische Personenrecherche.<br><br>"
            "Alle Daten bleiben lokal. Jede Abfrage erfordert einen dokumentierten Zweck; aktive Prüfungen "
            "werden einzeln bestätigt und protokolliert. Befunde tragen immer eine Belegstufe.<br><br>"
            "Es werden keine privaten Leak-Datenbanken, keine gestohlenen Zugangsdaten und keine Konto-Übernahmen "
            "verwendet.")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt-Namensschema)
        running = [q for c in self.ctx.engine.cases() for q in self.ctx.engine.queries(c.id)
                   if q.state.value in ("queued", "running")]
        if running:
            ans = QMessageBox.question(self, "Beenden", f"{len(running)} Abfrage(n) laufen noch. Trotzdem beenden?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                event.ignore()
                return
        self.ctx.shutdown()
        event.accept()
