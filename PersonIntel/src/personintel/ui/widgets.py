"""Kleine, wiederverwendbare Bausteine der Oberflaeche."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..adapters.base import AdapterState
from ..core.models import Evidence
from .style import EVIDENCE_COLOR, STATE_COLOR


def dot(color: str, size: int = 12) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pm


def state_item(state: AdapterState) -> QTableWidgetItem:
    it = QTableWidgetItem(state.label_de)
    it.setIcon(dot(STATE_COLOR.get(state, "#6b6b6b")))
    it.setData(Qt.UserRole, state.value)
    return it


def evidence_item(ev: Evidence) -> QTableWidgetItem:
    it = QTableWidgetItem(ev.label_de)
    it.setForeground(QColor(EVIDENCE_COLOR[ev]))
    f = it.font()
    f.setBold(ev is Evidence.CONFIRMED)
    it.setFont(f)
    it.setData(Qt.UserRole, ev.value)
    return it


def cell(text: Any, *, tooltip: str = "", data: Any = None, mono: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem("" if text is None else str(text))
    if tooltip:
        it.setToolTip(tooltip)
    if data is not None:
        it.setData(Qt.UserRole, data)
    if mono:
        it.setFont(QFont("monospace"))
    return it


class Table(QTableWidget):
    """Tabelle mit sinnvollen Standardeinstellungen (nur lesen, ganze Zeile auswaehlen)."""

    def __init__(self, headers: list[str], *, stretch: int = -1, parent: Optional[QWidget] = None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.setWordWrap(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        if stretch >= 0:
            h.setSectionResizeMode(stretch, QHeaderView.Stretch)
        else:
            h.setStretchLastSection(True)

    def fill(self, rows: Iterable[Iterable[QTableWidgetItem]]) -> None:
        rows = [list(r) for r in rows]
        self.setRowCount(len(rows))
        for r, items in enumerate(rows):
            for c, item in enumerate(items):
                self.setItem(r, c, item)
        self.resizeColumnsToContents()
        h = self.horizontalHeader()
        for c in range(self.columnCount()):
            if self.columnWidth(c) > 420:
                self.setColumnWidth(c, 420)
        if h.stretchLastSection():
            h.setStretchLastSection(True)

    def selected_data(self, column: int = 0):
        row = self.currentRow()
        if row < 0:
            return None
        it = self.item(row, column)
        return it.data(Qt.UserRole) if it else None


class Page(QWidget):
    """Grundgeruest einer Seite: Titel, Hinweis, Inhalt."""

    title = ""
    hint = ""

    def __init__(self, ctx, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ctx = ctx
        self.engine = ctx.engine
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)
        head = QLabel(self.title)
        head.setObjectName("PageTitle")
        outer.addWidget(head)
        if self.hint:
            h = QLabel(self.hint)
            h.setObjectName("PageHint")
            h.setWordWrap(True)
            outer.addWidget(h)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)
        self.build()
        ctx.case_changed.connect(lambda _: self.refresh())
        ctx.data_changed.connect(self.refresh)

    def build(self) -> None:  # von Unterklassen zu implementieren
        raise NotImplementedError

    def refresh(self) -> None:
        pass

    def on_shown(self) -> None:
        """Wird aufgerufen, wenn die Seite sichtbar wird."""
        self.refresh()


def warn_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Warning")
    lab.setWordWrap(True)
    return lab


def row(*widgets: QWidget, stretch_last: bool = False) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for i, x in enumerate(widgets):
        if x is None:
            lay.addStretch(1)
        else:
            lay.addWidget(x, 1 if (stretch_last and i == len(widgets) - 1) else 0)
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return w
