"""Recherche: Formulare je Eingabeart, passiv/aktiv getrennt, laufende Abfragen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QVBoxLayout)

from ...adapters.base import AdapterState
from ...core.errors import PersonIntelError
from ...core.models import QueryKind, QueryMode, QueryState
from ..dialogs import ActiveCheckDialog
from ..style import QUERY_STATE_LABEL
from ..widgets import Page, Table, cell, warn_label


class ResearchPage(Page):
    id = "research"
    title = "Recherche"
    hint = ("Abfragen laufen immer gegen genau eine registrierte Kennung. Passive Prüfungen verarbeiten nur lokal "
            "vorliegende Daten; aktive Prüfungen kontaktieren fremde Dienste und werden einzeln bestätigt.")

    def build(self) -> None:
        self.banner = QLabel()
        self.banner.setObjectName("CaseBanner")
        self.banner.setWordWrap(True)
        self.body.addWidget(self.banner)

        form_box = QGroupBox("Neue Abfrage")
        form = QFormLayout(form_box)
        self.target = QComboBox()
        self.target.currentIndexChanged.connect(self._target_changed)
        form.addRow("Kennung:", self.target)
        self.adapter = QComboBox()
        self.adapter.currentIndexChanged.connect(self._adapter_changed)
        form.addRow("Modul:", self.adapter)
        self.mode_label = QLabel("–")
        self.mode_label.setWordWrap(True)
        form.addRow("Art der Prüfung:", self.mode_label)
        self.options_box = QVBoxLayout()
        self.opt_footprint = QCheckBox("Zusätzlich Suchmaschinen-Suchlinks erzeugen (PhoneInfoga, nur Hinweise)")
        self.opt_footprint.setVisible(False)
        self.options_box.addWidget(self.opt_footprint)
        form.addRow("Optionen:", self._wrap(self.options_box))
        self.body.addWidget(form_box)

        btns = QHBoxLayout()
        self.b_start = QPushButton("Abfrage starten")
        self.b_start.setObjectName("Primary")
        self.b_start.clicked.connect(self._start)
        self.b_file = QPushButton("Berichtsdatei wählen …")
        self.b_file.clicked.connect(self._pick_file)
        self.b_file.setVisible(False)
        btns.addWidget(self.b_start)
        btns.addWidget(self.b_file)
        btns.addStretch(1)
        self.body.addLayout(btns)

        self.notice = warn_label("")
        self.notice.setVisible(False)
        self.body.addWidget(self.notice)

        box = QGroupBox("Abfragen in diesem Fall")
        bl = QVBoxLayout(box)
        self.queries = Table(["Zeitpunkt", "Modul", "Art", "Prüfung", "Status", "Treffer", "Meldung"], stretch=6)
        self.queries.itemSelectionChanged.connect(self._query_pick)
        bl.addWidget(self.queries, 1)
        qb = QHBoxLayout()
        self.b_cancel = QPushButton("Laufende Abfrage abbrechen")
        self.b_cancel.clicked.connect(self._cancel)
        self.b_cancel.setEnabled(False)
        self.b_delq = QPushButton("Abfrage samt Daten löschen")
        self.b_delq.setObjectName("Danger")
        self.b_delq.clicked.connect(self._delete_query)
        self.b_delq.setEnabled(False)
        qb.addWidget(self.b_cancel)
        qb.addWidget(self.b_delq)
        qb.addStretch(1)
        bl.addLayout(qb)
        self.body.addWidget(box, 1)

        self.ctx.query_updated.connect(self._on_query)
        self.ctx.statuses_changed.connect(self._adapter_changed)

    @staticmethod
    def _wrap(layout) -> QLabel:
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        w.setLayout(layout)
        return w

    # ---------------------------------------------------------------- Anzeige
    def refresh(self) -> None:
        case = self.ctx.case
        if case is None:
            self.banner.setText("Kein Fall ausgewählt – bitte unter „Fälle“ einen Fall anlegen oder auswählen.")
            self.target.clear()
            self.queries.fill([])
            self.b_start.setEnabled(False)
            return
        valid = self.engine.gate.purpose_valid(case)
        p = case.purpose
        if not valid:
            self.banner.setText(f"<b>Fall:</b> {case.name} — <span style='color:#a62121'><b>kein gültiger "
                                f"Recherchezweck. Abfragen sind gesperrt.</b></span>")
        else:
            self.banner.setText(
                f"<b>Fall:</b> {case.name} · <b>Zweck:</b> {p.description[:120]} · "
                f"<b>aktive Prüfungen:</b> {'erlaubt' if p.active_checks_allowed else 'nicht erlaubt'} · "
                f"<b>gültig bis:</b> {p.expires_at[:10]}")

        current = self.target.currentData()
        self.target.blockSignals(True)
        self.target.clear()
        for t in self.engine.targets(case.id):
            self.target.addItem(f"{t.kind.label_de}: {t.value}" + (f" ({t.label})" if t.label else ""), t.id)
        if current:
            i = self.target.findData(current)
            if i >= 0:
                self.target.setCurrentIndex(i)
        self.target.blockSignals(False)
        self._target_changed()
        self._render_queries()

    def _selected_target(self):
        tid = self.target.currentData()
        if not tid:
            return None
        return self.engine.repo.get("target", tid)

    def _target_changed(self) -> None:
        t = self._selected_target()
        self.adapter.blockSignals(True)
        self.adapter.clear()
        if t is not None:
            statuses = {s.adapter_id: s for s in self.ctx.statuses}
            for ad in self.engine.adapters():
                cap = ad.capability(t.kind)
                if cap is None:
                    continue
                st = statuses.get(ad.id)
                mark = ""
                if not cap.available:
                    mark = "  — nicht verfügbar"
                elif st is not None and st.state is not AdapterState.AVAILABLE:
                    mark = f"  — {st.state.label_de}"
                self.adapter.addItem(f"{ad.name}{mark}", ad.id)
        self.adapter.blockSignals(False)
        self._adapter_changed()

    def _adapter_changed(self) -> None:
        t = self._selected_target()
        aid = self.adapter.currentData()
        self.opt_footprint.setVisible(aid == "phoneinfoga")
        self.b_file.setVisible(bool(t) and t.kind is QueryKind.REPORT_FILE)
        if t is None or not aid:
            self.mode_label.setText("–")
            self.b_start.setEnabled(False)
            self.notice.setVisible(False)
            return
        ad = self.engine.adapter(aid)
        cap = ad.capability(t.kind)
        case = self.ctx.case
        valid = case is not None and self.engine.gate.purpose_valid(case)
        problems: list[str] = []
        if cap is None:
            self.mode_label.setText("Dieses Modul unterstützt die Kennungsart nicht.")
            self.b_start.setEnabled(False)
            return
        if cap.mode is QueryMode.ACTIVE:
            self.mode_label.setText("<b style='color:#b5651d'>Aktive Prüfung</b> – kontaktiert fremde Dienste, "
                                    "muss gesondert bestätigt werden." + (f"<br>{cap.cost_note}" if cap.cost_note else ""))
            if valid and not case.purpose.active_checks_allowed:
                problems.append("Der Zweck dieses Falls erlaubt keine aktiven Prüfungen. "
                                "Bitte den Zweck entsprechend erneuern.")
        else:
            self.mode_label.setText("<b style='color:#1b7f3a'>Passive Prüfung</b> – verarbeitet nur lokal "
                                    "vorliegende Daten, kontaktiert keine Dritten.")
        if not cap.available:
            problems.append(cap.reason or "Funktion nicht verfügbar.")
        st = {s.adapter_id: s for s in self.ctx.statuses}.get(aid)
        if st is not None and st.state is not AdapterState.AVAILABLE:
            problems.append(f"{ad.name}: {st.state.label_de}. {st.requirement or st.message}")
        if valid and t.kind.value not in case.purpose.allowed_kinds:
            problems.append(f"Der Zweck erlaubt keine Abfragen vom Typ „{t.kind.label_de}“.")
        if not valid:
            problems.append("Kein gültiger Recherchezweck – bitte unter „Fälle“ dokumentieren.")
        self.notice.setText("<br>".join("• " + p for p in problems))
        self.notice.setVisible(bool(problems))
        self.b_start.setEnabled(not problems)

    # ---------------------------------------------------------------- Aktionen
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Mr.Holmes-Bericht wählen", "",
                                              "Berichte (*.txt *.json *.md *.html);;Alle Dateien (*)")
        if not path:
            return
        try:
            t = self.engine.add_target(self.ctx.case_id, QueryKind.REPORT_FILE, path, "Mr.Holmes-Bericht")
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Datei", str(exc))
            return
        self.refresh()
        i = self.target.findData(t.id)
        if i >= 0:
            self.target.setCurrentIndex(i)

    def _start(self) -> None:
        t = self._selected_target()
        aid = self.adapter.currentData()
        if t is None or not aid:
            return
        ad = self.engine.adapter(aid)
        cap = ad.capability(t.kind)
        confirmation = None
        if cap is not None and cap.mode is QueryMode.ACTIVE:
            dlg = ActiveCheckDialog(ad.name, t.kind, t.value, cost_note=cap.cost_note,
                                    description=cap.description, parent=self)
            if dlg.exec() != dlg.DialogCode.Accepted:
                self.ctx.message.emit("Aktive Prüfung abgebrochen – keine Abfrage gesendet.", False)
                return
            confirmation = dlg.confirmation()
        options = {}
        if aid == "phoneinfoga" and self.opt_footprint.isChecked():
            options["footprint_links"] = True
        try:
            rec = self.engine.run_query(self.ctx.case_id, aid, t.id, confirmation=confirmation, options=options)
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Abfrage nicht möglich", str(exc))
            self.ctx.message.emit(str(exc), True)
            return
        self.ctx.notify(f"Abfrage gestartet: {ad.name} ({t.kind.label_de}).")

    def _cancel(self) -> None:
        qid = self.queries.selected_data(0)
        if qid and self.engine.cancel_query(qid):
            self.ctx.message.emit("Abbruch angefordert.", False)

    def _delete_query(self) -> None:
        qid = self.queries.selected_data(0)
        if not qid:
            return
        ans = QMessageBox.question(self, "Abfrage löschen",
                                   "Abfrage samt Befunden und Quellen unwiderruflich löschen?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans == QMessageBox.Yes:
            n = self.engine.delete_query_data(self.ctx.case_id, qid)
            self.ctx.notify(f"{n} Datensätze gelöscht.")

    def _on_query(self, record) -> None:
        if self.ctx.case_id and record.case_id == self.ctx.case_id:
            self._render_queries()
            if record.state in (QueryState.DONE, QueryState.FAILED, QueryState.CANCELLED):
                self.ctx.message.emit(f"{self.ctx.adapter_name(record.adapter_id)}: "
                                      f"{QUERY_STATE_LABEL[record.state]} – {record.message}",
                                      record.state is QueryState.FAILED)
                self.ctx.data_changed.emit()

    def _render_queries(self) -> None:
        if not self.ctx.has_case():
            return
        rows = []
        for q in sorted(self.engine.queries(self.ctx.case_id), key=lambda q: q.created_at, reverse=True):
            rows.append([cell(q.created_at[:19].replace("T", " "), data=q.id),
                         cell(self.ctx.adapter_name(q.adapter_id)), cell(q.kind.label_de),
                         cell("aktiv" if q.mode is QueryMode.ACTIVE else "passiv"),
                         cell(QUERY_STATE_LABEL.get(q.state, q.state.value)),
                         cell(q.finding_count), cell(q.message, tooltip=q.message)])
        self.queries.fill(rows)
        self._query_pick()

    def _query_pick(self) -> None:
        qid = self.queries.selected_data(0)
        rec = self.engine.repo.get("query", qid) if qid else None
        running = rec is not None and rec.state in (QueryState.QUEUED, QueryState.RUNNING)
        self.b_cancel.setEnabled(bool(running))
        self.b_delq.setEnabled(rec is not None and not running)
