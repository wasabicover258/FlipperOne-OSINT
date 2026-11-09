"""Berichtsgenerator fuer die journalistische Dokumentation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QGroupBox, QHBoxLayout, QFileDialog, QMessageBox, QPushButton,
                               QTextBrowser, QVBoxLayout)

from ...core.errors import PersonIntelError
from ..widgets import Page


class ReportPage(Page):
    id = "report"
    title = "Bericht"
    hint = ("Dokumentation der Recherche: Zweck, Methodik, Befunde nach Belegstufe, übernommene Verbindungen, "
            "Chronologie, Einschränkungen und Protokollzusammenfassung.")

    def build(self) -> None:
        box = QGroupBox("Umfang")
        o = QHBoxLayout(box)
        self.cb_unconfirmed = QCheckBox("Unbestätigte Befunde einbeziehen")
        self.cb_unconfirmed.setChecked(True)
        self.cb_rejected = QCheckBox("Verworfene Befunde ausweisen")
        self.cb_notfound = QCheckBox("Abfragen ohne Treffer auflisten")
        self.cb_mask = QCheckBox("Kennungen maskieren")
        self.cb_audit = QCheckBox("Protokollzusammenfassung")
        self.cb_audit.setChecked(True)
        for cb in (self.cb_unconfirmed, self.cb_rejected, self.cb_notfound, self.cb_mask, self.cb_audit):
            cb.toggled.connect(self._render)
            o.addWidget(cb)
        o.addStretch(1)
        self.body.addWidget(box)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.body.addWidget(self.preview, 1)

        btns = QHBoxLayout()
        self.b_md = QPushButton("Als Markdown speichern …")
        self.b_md.clicked.connect(lambda: self._save("md"))
        self.b_html = QPushButton("Als HTML speichern …")
        self.b_html.clicked.connect(lambda: self._save("html"))
        self.b_json = QPushButton("Als JSON speichern …")
        self.b_json.clicked.connect(lambda: self._save("json"))
        self.b_pdf = QPushButton("Als PDF speichern …")
        self.b_pdf.setObjectName("Primary")
        self.b_pdf.clicked.connect(self._save_pdf)
        for b in (self.b_pdf, self.b_html, self.b_md, self.b_json):
            btns.addWidget(b)
        btns.addStretch(1)
        self.body.addLayout(btns)

    def _options(self) -> dict:
        return {"include_unconfirmed": self.cb_unconfirmed.isChecked(),
                "include_rejected": self.cb_rejected.isChecked(),
                "include_not_found": self.cb_notfound.isChecked(),
                "mask_identifiers": self.cb_mask.isChecked(),
                "include_audit_summary": self.cb_audit.isChecked()}

    def refresh(self) -> None:
        self._render()

    def _report(self):
        if not self.ctx.has_case():
            return None
        return self.engine.build_report(self.ctx.case_id, **self._options())

    def _render(self) -> None:
        enabled = self.ctx.has_case()
        for b in (self.b_md, self.b_html, self.b_json, self.b_pdf):
            b.setEnabled(enabled)
        if not enabled:
            self.preview.setHtml("<i>Kein Fall ausgewählt.</i>")
            return
        try:
            rep = self._report()
        except PersonIntelError as exc:
            self.preview.setHtml(f"<p style='color:#a62121'>{exc}</p>")
            return
        self.preview.setHtml(rep.to_html())

    def _save(self, fmt: str) -> None:
        rep = self._report()
        if rep is None:
            return
        name = f"{self.ctx.case.name}-bericht.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Bericht speichern", name, f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        text = {"md": rep.to_markdown, "html": rep.to_html, "json": rep.to_json}[fmt]()
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Speichern", str(exc))
            return
        self.ctx.message.emit(f"Bericht gespeichert: {path}", False)

    def _save_pdf(self) -> None:
        rep = self._report()
        if rep is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Bericht als PDF speichern",
                                              f"{self.ctx.case.name}-bericht.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            from PySide6.QtGui import QPageSize, QTextDocument
            from PySide6.QtPrintSupport import QPrinter
            doc = QTextDocument()
            doc.setHtml(rep.to_html())
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setOutputFileName(path)
            doc.print_(printer)
        except ImportError:
            QMessageBox.information(
                self, "PDF-Export",
                "Für den PDF-Export fehlt das Qt-Druckmodul (QtPrintSupport). Bitte den Bericht als HTML "
                "speichern und im Browser nach PDF drucken.")
            return
        except Exception as exc:
            QMessageBox.warning(self, "PDF-Export", f"{type(exc).__name__}: {exc}")
            return
        self.ctx.message.emit(f"Bericht als PDF gespeichert: {path}", False)
