"""Dialoge: Passphrase, Zweckdokumentation, Bestaetigung aktiver Pruefungen, Graph-Verbindung."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout)

from ..core.models import Evidence, Purpose, QueryKind
from ..graph.model import NODE_TYPES, RELATIONS
from ..security.authorization import ActiveConfirmation, PURPOSE_CATEGORIES
from .widgets import warn_label


class PassphraseDialog(QDialog):
    """Passphrase fuer verschluesselte Datenbank / Zugangsdatenspeicher."""

    def __init__(self, title: str, info: str, *, confirm: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lab = QLabel(info)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        form = QFormLayout()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        form.addRow("Passphrase:", self.pw)
        self.pw2: Optional[QLineEdit] = None
        if confirm:
            self.pw2 = QLineEdit()
            self.pw2.setEchoMode(QLineEdit.Password)
            form.addRow("Wiederholen:", self.pw2)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#a62121")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _accept(self) -> None:
        if not self.pw.text():
            self.error.setText("Bitte eine Passphrase eingeben.")
            return
        if self.pw2 is not None and self.pw.text() != self.pw2.text():
            self.error.setText("Die Eingaben stimmen nicht überein.")
            return
        self.accept()

    @property
    def passphrase(self) -> str:
        return self.pw.text()


class PurposeDialog(QDialog):
    """Dokumentierte Zweck- und Berechtigungspruefung eines Falls."""

    def __init__(self, purpose: Optional[Purpose] = None, *, min_chars: int = 20, max_days: int = 90, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recherchezweck und Berechtigung dokumentieren")
        self.setMinimumWidth(620)
        p = purpose or Purpose()
        lay = QVBoxLayout(self)
        lay.addWidget(warn_label(
            "Jeder Fall braucht einen dokumentierten Zweck. Ohne gültigen Zweck sind keine Abfragen möglich. "
            "Aktive Prüfungen (Abfragen bei Drittdiensten im Namen der Recherche) müssen hier ausdrücklich "
            "freigegeben werden und erfordern zusätzlich pro Abfrage eine Bestätigung."))
        form = QFormLayout()
        self.category = QComboBox()
        for key, label in PURPOSE_CATEGORIES.items():
            self.category.addItem(label, key)
        if p.category:
            i = self.category.findData(p.category)
            if i >= 0:
                self.category.setCurrentIndex(i)
        form.addRow("Kategorie:", self.category)

        self.description = QPlainTextEdit(p.description)
        self.description.setPlaceholderText(
            f"Konkreter Recherchezweck (mind. {min_chars} Zeichen), z. B. "
            "„Verifikation der Identität einer Quelle für die Berichterstattung über …“")
        self.description.setFixedHeight(80)
        form.addRow("Zweck:", self.description)

        self.authorized_by = QLineEdit(p.authorized_by)
        self.authorized_by.setPlaceholderText("Verantwortliche Person / Redaktion / Auftraggeber")
        form.addRow("Verantwortlich:", self.authorized_by)

        self.legal = QPlainTextEdit(p.legal_basis_note)
        self.legal.setPlaceholderText("Notiz zur Rechtsgrundlage, Auftrag, Abstimmung mit der Rechtsabteilung …")
        self.legal.setFixedHeight(60)
        form.addRow("Rechtsgrundlage:", self.legal)

        self.days = QSpinBox()
        self.days.setRange(1, max_days)
        self.days.setValue(30)
        self.days.setSuffix(" Tage")
        form.addRow("Zweckbindung gültig:", self.days)

        self.active = QCheckBox("Aktive Prüfungen erlauben (Abfragen kontaktieren fremde Dienste)")
        self.active.setChecked(p.active_checks_allowed)
        form.addRow("", self.active)
        lay.addLayout(form)

        lay.addWidget(QLabel("Erlaubte Kennungsarten:"))
        self.kinds = QListWidget()
        self.kinds.setSelectionMode(QListWidget.NoSelection)
        self.kinds.setFixedHeight(120)
        for k in QueryKind:
            it = QListWidgetItem(k.label_de)
            it.setData(Qt.UserRole, k.value)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if k.value in p.allowed_kinds else Qt.Unchecked)
            self.kinds.addItem(it)
        lay.addWidget(self.kinds)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#a62121")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Zweck bestätigen")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self._min_chars = min_chars

    def _accept(self) -> None:
        if len(self.description.toPlainText().strip()) < self._min_chars:
            self.error.setText(f"Der Zweck muss konkret beschrieben werden (mind. {self._min_chars} Zeichen).")
            return
        if not self.authorized_by.text().strip():
            self.error.setText("Bitte die verantwortliche Person oder Stelle angeben.")
            return
        if not self.allowed_kinds():
            self.error.setText("Mindestens eine Kennungsart muss erlaubt sein.")
            return
        self.accept()

    def allowed_kinds(self) -> list[str]:
        return [self.kinds.item(i).data(Qt.UserRole) for i in range(self.kinds.count())
                if self.kinds.item(i).checkState() == Qt.Checked]

    def purpose(self) -> Purpose:
        return Purpose(category=self.category.currentData(), description=self.description.toPlainText().strip(),
                       authorized_by=self.authorized_by.text().strip(),
                       legal_basis_note=self.legal.toPlainText().strip(),
                       active_checks_allowed=self.active.isChecked(), allowed_kinds=self.allowed_kinds())

    @property
    def days_valid(self) -> int:
        return self.days.value()


class ActiveCheckDialog(QDialog):
    """Gesonderte Bestaetigung einer aktiven Pruefung - pro Abfrage, nie fuer Listen."""

    def __init__(self, adapter_name: str, kind: QueryKind, value: str, *, cost_note: str = "",
                 description: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aktive Prüfung bestätigen")
        self.setMinimumWidth(620)
        self._value = value
        lay = QVBoxLayout(self)
        lay.addWidget(warn_label(
            f"<b>{adapter_name}</b> übermittelt die Kennung an fremde Dienste bzw. prüft dort, ob ein Konto "
            f"existiert. Das kann für die betroffene Person sichtbar sein (z. B. Hinweis-E-Mails) und unterliegt "
            f"den Nutzungsbedingungen der Anbieter. Es werden keine Konten übernommen, keine Zugangsdaten "
            f"verwendet und keine Zugangsbeschränkungen umgangen."))
        info = QLabel(f"Abfrage: <b>{kind.label_de}</b> · Modul: <b>{adapter_name}</b>"
                      + (f"<br>{description}" if description else "")
                      + (f"<br><i>{cost_note}</i>" if cost_note else ""))
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        self.typed = QLineEdit()
        self.typed.setPlaceholderText("Kennung zur Bestätigung erneut eingeben")
        form.addRow("Kennung:", self.typed)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optionale Notiz für das Protokoll (z. B. Abstimmung, Begründung)")
        form.addRow("Notiz:", self.note)
        lay.addLayout(form)

        self.cb_third = QCheckBox("Mir ist bewusst, dass dabei Dritte kontaktiert werden und die Abfrage "
                                  "für die betroffene Person sichtbar sein kann.")
        self.cb_tos = QCheckBox("Die Nutzungsbedingungen der abgefragten Dienste werden eingehalten; die Abfrage "
                                "erfolgt im Rahmen des dokumentierten Zwecks.")
        for cb in (self.cb_third, self.cb_tos):
            lay.addWidget(cb)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#a62121")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Aktive Prüfung starten")
        self.ok_button.setEnabled(False)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        for w in (self.typed,):
            w.textChanged.connect(self._update)
        for cb in (self.cb_third, self.cb_tos):
            cb.toggled.connect(self._update)

    def _update(self) -> None:
        ready = (self.typed.text().strip().lower() == self._value.lower()
                 and self.cb_third.isChecked() and self.cb_tos.isChecked())
        self.ok_button.setEnabled(ready)

    def _accept(self) -> None:
        if self.typed.text().strip().lower() != self._value.lower():
            self.error.setText("Die eingegebene Kennung stimmt nicht mit der registrierten überein.")
            return
        self.accept()

    def confirmation(self) -> ActiveConfirmation:
        return ActiveConfirmation(typed_target=self.typed.text().strip(),
                                  acknowledges_third_party_contact=self.cb_third.isChecked(),
                                  acknowledges_terms_of_service=self.cb_tos.isChecked(),
                                  note=self.note.text().strip())


class NodeDialog(QDialog):
    def __init__(self, findings: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Knoten hinzufügen")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.type = QComboBox()
        for key, label in NODE_TYPES.items():
            self.type.addItem(label, key)
        form.addRow("Art:", self.type)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Bezeichnung, z. B. „Zielperson“ oder „github.com/jdoe“")
        form.addRow("Bezeichnung:", self.label)
        lay.addLayout(form)
        lay.addWidget(QLabel("Zugrundeliegende Befunde (optional):"))
        self.findings = QListWidget()
        self.findings.setSelectionMode(QListWidget.NoSelection)
        self.findings.setFixedHeight(160)
        for f in findings:
            it = QListWidgetItem(f"[{f.evidence.label_de}] {f.title} ({f.adapter_id})")
            it.setData(Qt.UserRole, f.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.findings.addItem(it)
        lay.addWidget(self.findings)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def values(self) -> tuple[str, str, list[str]]:
        ids = [self.findings.item(i).data(Qt.UserRole) for i in range(self.findings.count())
               if self.findings.item(i).checkState() == Qt.Checked]
        return self.type.currentData(), self.label.text().strip(), ids


class LinkDialog(QDialog):
    """Verbindung zwischen zwei Knoten - nur mit Basisbefund und Begruendung."""

    def __init__(self, nodes: list, findings: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verbindung übernehmen")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.addWidget(warn_label(
            "Verbindungen werden nie automatisch erzeugt. Jede Verbindung braucht mindestens einen Befund als "
            "Beleg; ihre Belegstufe kann die der Befunde nicht übersteigen. Eine Gleichsetzung zweier Identitäten "
            "ist allein aufgrund gleicher Benutzernamen nicht zulässig."))
        form = QFormLayout()
        self.source = QComboBox()
        self.target = QComboBox()
        for n in nodes:
            for combo in (self.source, self.target):
                combo.addItem(f"{n.label} ({NODE_TYPES.get(n.type, n.type)})", n.id)
        if self.target.count() > 1:
            self.target.setCurrentIndex(1)
        form.addRow("Von:", self.source)
        self.relation = QComboBox()
        for key, label in RELATIONS.items():
            self.relation.addItem(label, key)
        form.addRow("Beziehung:", self.relation)
        form.addRow("Nach:", self.target)
        self.evidence = QComboBox()
        self.evidence.addItem("automatisch (beste Belegstufe der Befunde)", None)
        for ev in (Evidence.CONFIRMED, Evidence.INDICATION, Evidence.UNCONFIRMED):
            self.evidence.addItem(ev.label_de, ev.value)
        form.addRow("Belegstufe:", self.evidence)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Begründung: warum belegen die ausgewählten Befunde diese Verbindung?")
        self.note.setFixedHeight(70)
        form.addRow("Begründung:", self.note)
        lay.addLayout(form)
        lay.addWidget(QLabel("Basisbefunde (mindestens einer):"))
        self.findings = QListWidget()
        self.findings.setSelectionMode(QListWidget.NoSelection)
        self.findings.setFixedHeight(170)
        for f in findings:
            it = QListWidgetItem(f"[{f.evidence.label_de}] {f.title} – {f.value or f.url or ''} ({f.adapter_id})")
            it.setData(Qt.UserRole, f.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.findings.addItem(it)
        lay.addWidget(self.findings)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#a62121")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _accept(self) -> None:
        if not self.basis():
            self.error.setText("Bitte mindestens einen Basisbefund auswählen.")
            return
        if self.source.currentData() == self.target.currentData():
            self.error.setText("Quelle und Ziel müssen verschieden sein.")
            return
        self.accept()

    def basis(self) -> list[str]:
        return [self.findings.item(i).data(Qt.UserRole) for i in range(self.findings.count())
                if self.findings.item(i).checkState() == Qt.Checked]

    def values(self) -> dict:
        return {"source": self.source.currentData(), "target": self.target.currentData(),
                "relation": self.relation.currentData(), "basis_finding_ids": self.basis(),
                "note": self.note.toPlainText().strip(),
                "evidence": Evidence(self.evidence.currentData()) if self.evidence.currentData() else None}


class ReviewDialog(QDialog):
    """Pruefvermerk zu einem Befund (Belegstufe nur mit Begruendung heraufsetzen)."""

    def __init__(self, finding, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Befund prüfen")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        info = QLabel(f"<b>{finding.title}</b><br>{finding.value or ''} {finding.url or ''}"
                      f"<br>Modul: {finding.adapter_id} · bisher: {finding.evidence.label_de}")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.state = QComboBox()
        self.state.addItem("geprüft und übernommen", "reviewed")
        self.state.addItem("verworfen", "rejected")
        self.state.addItem("ungeprüft", "unreviewed")
        form.addRow("Prüfergebnis:", self.state)
        self.evidence = QComboBox()
        self.evidence.addItem("unverändert", None)
        for ev in (Evidence.CONFIRMED, Evidence.INDICATION, Evidence.UNCONFIRMED):
            self.evidence.addItem(ev.label_de, ev.value)
        form.addRow("Belegstufe:", self.evidence)
        self.note = QPlainTextEdit(finding.reviewer_note)
        self.note.setPlaceholderText("Begründung / Prüfvermerk (für „unmittelbar belegt“ verpflichtend)")
        self.note.setFixedHeight(80)
        form.addRow("Notiz:", self.note)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#a62121")
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _accept(self) -> None:
        if self.evidence.currentData() == Evidence.CONFIRMED.value and not self.note.toPlainText().strip():
            self.error.setText("Für „unmittelbar belegt“ ist eine Begründung erforderlich.")
            return
        self.accept()

    def values(self) -> dict:
        ev = self.evidence.currentData()
        return {"state": self.state.currentData(), "note": self.note.toPlainText().strip(),
                "evidence": Evidence(ev) if ev else None}
