"""Fallverwaltung: Zweck, Kennungen (Fallumfang), Export/Import, selektives Loeschen."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QComboBox, QPushButton, QSplitter, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from ...core.errors import PersonIntelError
from ...core.models import QueryKind
from ..dialogs import PurposeDialog
from ..widgets import Page, Table, cell, warn_label


class CasesPage(Page):
    id = "cases"
    title = "Fälle"
    hint = ("Jede Recherche läuft in einem Fall mit dokumentiertem Zweck und einem begrenzten Umfang an Kennungen. "
            "Ohne gültigen Zweck sind keine Abfragen möglich.")

    def build(self) -> None:
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Fälle"))
        self.cases = Table(["Fall", "Angelegt", "Zweck"], stretch=0)
        self.cases.itemSelectionChanged.connect(self._pick)
        ll.addWidget(self.cases, 1)
        br = QHBoxLayout()
        b_new = QPushButton("Neuer Fall")
        b_new.setObjectName("Primary")
        b_new.clicked.connect(self._new_case)
        b_imp = QPushButton("Importieren …")
        b_imp.clicked.connect(self._import)
        self.b_exp = QPushButton("Exportieren …")
        self.b_exp.clicked.connect(self._export)
        self.b_del = QPushButton("Fall löschen")
        self.b_del.setObjectName("Danger")
        self.b_del.clicked.connect(self._delete)
        for b in (b_new, b_imp, self.b_exp, self.b_del):
            br.addWidget(b)
        br.addStretch(1)
        ll.addLayout(br)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.purpose_box = QGroupBox("Zweck und Berechtigung")
        pl = QVBoxLayout(self.purpose_box)
        self.purpose_label = QLabel("Kein Fall ausgewählt.")
        self.purpose_label.setWordWrap(True)
        self.purpose_label.setTextFormat(Qt.RichText)
        pl.addWidget(self.purpose_label)
        pb = QHBoxLayout()
        self.b_purpose = QPushButton("Zweck dokumentieren / erneuern …")
        self.b_purpose.setObjectName("Primary")
        self.b_purpose.clicked.connect(self._edit_purpose)
        pb.addWidget(self.b_purpose)
        pb.addStretch(1)
        pl.addLayout(pb)
        rl.addWidget(self.purpose_box)

        self.target_box = QGroupBox("Kennungen im Fallumfang")
        tl = QVBoxLayout(self.target_box)
        self.limit_label = QLabel("")
        tl.addWidget(self.limit_label)
        self.targets = Table(["Art", "Kennung", "Bezeichnung", "Registriert"], stretch=1)
        self.targets.itemSelectionChanged.connect(self._target_pick)
        tl.addWidget(self.targets, 1)
        add = QHBoxLayout()
        self.kind = QComboBox()
        for k in QueryKind:
            self.kind.addItem(k.label_de, k.value)
        self.value = QLineEdit()
        self.value.setPlaceholderText("genau eine Kennung – keine Listen, keine Platzhalter")
        self.value.returnPressed.connect(self._add_target)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Bezeichnung (optional)")
        self.label.setMaximumWidth(220)
        b_add = QPushButton("Hinzufügen")
        b_add.clicked.connect(self._add_target)
        self.b_rm = QPushButton("Kennung samt Daten löschen")
        self.b_rm.setObjectName("Danger")
        self.b_rm.clicked.connect(self._remove_target)
        add.addWidget(self.kind)
        add.addWidget(self.value, 1)
        add.addWidget(self.label)
        add.addWidget(b_add)
        tl.addLayout(add)
        rm = QHBoxLayout()
        rm.addWidget(self.b_rm)
        rm.addStretch(1)
        tl.addLayout(rm)
        rl.addWidget(self.target_box, 1)
        rl.addWidget(warn_label(
            "Der Fallumfang ist bewusst begrenzt: eine Recherche pro Person bzw. Vorgang. Für eine weitere Person "
            "wird ein eigener Fall mit eigenem Zweck angelegt. Massenabfragen sind nicht möglich."))
        split.addWidget(right)
        split.setSizes([420, 700])
        self.body.addWidget(split, 1)
        self.ctx.cases_changed.connect(self.refresh)

    # ------------------------------------------------------------- Aktionen
    def _new_case(self) -> None:
        name, ok = QInputDialog.getText(self, "Neuer Fall", "Bezeichnung des Falls:")
        if not ok or not name.strip():
            return
        try:
            case = self.engine.create_case(name.strip())
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Fall anlegen", str(exc))
            return
        self.ctx.set_case(case.id)
        self.ctx.cases_changed.emit()
        self.ctx.notify(f"Fall „{case.name}“ angelegt. Bitte jetzt den Recherchezweck dokumentieren.")
        self._edit_purpose()

    def _edit_purpose(self) -> None:
        case = self.ctx.case
        if case is None:
            return
        lim = self.engine.settings.limits
        dlg = PurposeDialog(case.purpose, min_chars=lim.min_purpose_chars, max_days=lim.max_purpose_days, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            self.engine.set_purpose(case.id, dlg.purpose(), days_valid=dlg.days_valid)
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Zweck", str(exc))
            return
        self.ctx.notify("Recherchezweck dokumentiert.")
        self.ctx.cases_changed.emit()

    def _add_target(self) -> None:
        if not self.ctx.has_case():
            QMessageBox.information(self, "Kennung", "Bitte zuerst einen Fall auswählen.")
            return
        value = self.value.text().strip()
        if not value:
            return
        try:
            t = self.engine.add_target(self.ctx.case_id, self.kind.currentData(), value, self.label.text().strip())
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Kennung nicht übernommen", str(exc))
            return
        self.value.clear()
        self.label.clear()
        self.ctx.notify(f"Kennung registriert: {t.value}")

    def _remove_target(self) -> None:
        tid = self.targets.selected_data(0)
        if not tid:
            return
        ans = QMessageBox.question(
            self, "Kennung löschen",
            "Die Kennung und alle zu ihr gehörenden Befunde und Abfragen werden unwiderruflich gelöscht.\n\n"
            "Fortfahren?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        n = self.engine.remove_target(self.ctx.case_id, tid, delete_data=True)
        self.ctx.notify(f"{n} Datensätze gelöscht.")

    def _delete(self) -> None:
        case = self.ctx.case
        if case is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Fall löschen")
        box.setText(f"Fall „{case.name}“ und alle zugehörigen Daten unwiderruflich löschen?")
        box.setInformativeText("Das Protokoll (ohne Rechercheinhalte) bleibt für die Nachvollziehbarkeit erhalten, "
                               "sofern nicht ausdrücklich mitgelöscht.")
        box.setStandardButtons(QMessageBox.Cancel)
        b_keep = box.addButton("Löschen, Protokoll behalten", QMessageBox.DestructiveRole)
        b_all = box.addButton("Löschen, auch Protokoll", QMessageBox.DestructiveRole)
        box.exec()
        if box.clickedButton() not in (b_keep, b_all):
            return
        n = self.engine.delete_case(case.id, purge_audit=box.clickedButton() is b_all)
        self.ctx.set_case("")
        self.ctx.cases_changed.emit()
        self.ctx.notify(f"Fall gelöscht ({n} Datensätze).")

    def _export(self) -> None:
        if not self.ctx.has_case():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Fall exportieren", f"{self.ctx.case.name}.personintel.json",
                                              "JSON (*.json)")
        if not path:
            return
        try:
            data = self.engine.export_case(self.ctx.case_id)
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (PersonIntelError, OSError) as exc:
            QMessageBox.warning(self, "Export", str(exc))
            return
        self.ctx.notify(f"Fall exportiert: {path}", data=False)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Fall importieren", "", "JSON (*.json)")
        if not path:
            return
        try:
            case = self.engine.import_case(json.loads(Path(path).read_text(encoding="utf-8")))
        except (PersonIntelError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Import", str(exc))
            return
        self.ctx.set_case(case.id)
        self.ctx.cases_changed.emit()
        self.ctx.notify(f"Fall importiert: {case.name}")

    # -------------------------------------------------------------- Anzeige
    def _pick(self) -> None:
        cid = self.cases.selected_data(0)
        if cid:
            self.ctx.set_case(cid)

    def _target_pick(self) -> None:
        self.b_rm.setEnabled(bool(self.targets.selected_data(0)))

    def refresh(self) -> None:
        cases = self.engine.cases()
        rows = []
        for c in cases:
            ok = self.engine.gate.purpose_valid(c)
            purpose = "gültig bis " + c.purpose.expires_at[:10] if ok and c.purpose else (
                "abgelaufen" if c.purpose else "nicht dokumentiert")
            rows.append([cell(c.name, data=c.id, tooltip=c.description), cell(c.created_at[:16].replace("T", " ")),
                         cell(purpose)])
        self.cases.fill(rows)
        for r, c in enumerate(cases):
            if c.id == self.ctx.case_id:
                self.cases.selectRow(r)
                break

        case = self.ctx.case
        has = case is not None
        for w in (self.b_exp, self.b_del, self.b_purpose, self.target_box):
            w.setEnabled(has)
        self.b_rm.setEnabled(False)
        if not has:
            self.purpose_label.setText("Kein Fall ausgewählt.")
            self.targets.fill([])
            self.limit_label.setText("")
            return
        p = case.purpose
        if p is None:
            self.purpose_label.setText("<b style='color:#a62121'>Kein Zweck dokumentiert – Abfragen sind gesperrt.</b>")
        else:
            valid = self.engine.gate.purpose_valid(case)
            color = "#1b7f3a" if valid else "#a62121"
            state = f"gültig bis {p.expires_at[:16].replace('T', ' ')}" if valid else "ABGELAUFEN – Abfragen gesperrt"
            self.purpose_label.setText(
                f"<b>Kategorie:</b> {p.category}<br>"
                f"<b>Zweck:</b> {p.description}<br>"
                f"<b>Verantwortlich:</b> {p.authorized_by}<br>"
                f"<b>Rechtsgrundlage:</b> {p.legal_basis_note or '–'}<br>"
                f"<b>Bestätigt:</b> {p.confirmed_at[:16].replace('T', ' ')} · "
                f"<span style='color:{color}'><b>{state}</b></span><br>"
                f"<b>Aktive Prüfungen:</b> {'erlaubt' if p.active_checks_allowed else 'nicht erlaubt'}<br>"
                f"<b>Erlaubte Kennungsarten:</b> {', '.join(QueryKind(k).label_de for k in p.allowed_kinds)}")
        targets = self.engine.targets(case.id)
        self.targets.fill([[cell(t.kind.label_de, data=t.id), cell(t.value), cell(t.label or "–"),
                            cell(t.created_at[:16].replace("T", " "))] for t in targets])
        lim = self.engine.settings.limits.max_targets_per_case
        self.limit_label.setText(f"{len(targets)} von höchstens {lim} Kennungen registriert.")
