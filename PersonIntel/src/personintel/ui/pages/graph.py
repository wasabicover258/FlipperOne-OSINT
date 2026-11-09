"""Graph der belegten Verbindungen - Knoten und Kanten nur durch Entscheidung des Bearbeiters."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from ...core.errors import PersonIntelError
from ...core.models import Evidence
from ...graph.model import NODE_TYPES, RELATIONS, layout
from ..dialogs import LinkDialog, NodeDialog
from ..style import EVIDENCE_COLOR
from ..widgets import Page, Table, cell, evidence_item, warn_label

NODE_R = 16


class GraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(260)
        self.setBackgroundBrush(QBrush(QColor("#ffffff")))

    def draw(self, nodes: list, edges: list) -> None:
        sc = self.scene()
        sc.clear()
        if not nodes:
            t = sc.addText("Noch keine Knoten. Verbindungen entstehen ausschließlich durch manuelle Übernahme.")
            t.setDefaultTextColor(QColor("#6b6b6b"))
            return
        w, h = 900.0, 520.0
        pos = layout(nodes, edges)
        pts = {nid: QPointF(40 + x * (w - 80), 40 + y * (h - 80)) for nid, (x, y) in pos.items()}
        for e in edges:
            a, b = pts.get(e.source), pts.get(e.target)
            if a is None or b is None:
                continue
            color = QColor(EVIDENCE_COLOR[e.evidence])
            line = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
            pen = QPen(color, 2.0)
            if e.evidence is Evidence.UNCONFIRMED:
                pen.setStyle(Qt.DashLine)
            line.setPen(pen)
            line.setZValue(-1)
            sc.addItem(line)
            # Pfeilspitze
            v = b - a
            length = max((v.x() ** 2 + v.y() ** 2) ** 0.5, 1e-6)
            ux, uy = v.x() / length, v.y() / length
            tip = QPointF(b.x() - ux * NODE_R, b.y() - uy * NODE_R)
            left = QPointF(tip.x() - ux * 11 - uy * 5, tip.y() - uy * 11 + ux * 5)
            right = QPointF(tip.x() - ux * 11 + uy * 5, tip.y() - uy * 11 - ux * 5)
            head = QGraphicsPolygonItem(QPolygonF([tip, left, right]))
            head.setBrush(QBrush(color))
            head.setPen(QPen(color))
            sc.addItem(head)
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            lab = QGraphicsSimpleTextItem(f"{RELATIONS.get(e.relation, e.relation)} [{e.evidence.label_de}]")
            f = QFont()
            f.setPointSize(7)
            lab.setFont(f)
            lab.setBrush(QBrush(color))
            lab.setPos(mid.x() + 4, mid.y() - 14)
            sc.addItem(lab)
        for n in nodes:
            p = pts[n.id]
            item = QGraphicsEllipseItem(QRectF(p.x() - NODE_R, p.y() - NODE_R, NODE_R * 2, NODE_R * 2))
            item.setBrush(QBrush(QColor("#38546f")))
            item.setPen(QPen(QColor("#22303f"), 2))
            item.setToolTip(f"{n.label} ({NODE_TYPES.get(n.type, n.type)})")
            sc.addItem(item)
            text = QGraphicsSimpleTextItem(n.label)
            f = QFont()
            f.setPointSize(8)
            f.setBold(True)
            text.setFont(f)
            text.setPos(p.x() + NODE_R + 4, p.y() - 8)
            sc.addItem(text)
            sub = QGraphicsSimpleTextItem(NODE_TYPES.get(n.type, n.type))
            f2 = QFont()
            f2.setPointSize(7)
            sub.setFont(f2)
            sub.setBrush(QBrush(QColor("#6b6b6b")))
            sub.setPos(p.x() + NODE_R + 4, p.y() + 3)
            sc.addItem(sub)
        sc.setSceneRect(sc.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(sc.sceneRect(), Qt.KeepAspectRatio)


class GraphPage(Page):
    id = "graph"
    title = "Verbindungen"
    hint = ("Der Graph zeigt ausschließlich Verbindungen, die der Bearbeiter übernommen hat. Jede Verbindung nennt "
            "ihre Basisbefunde; ihre Belegstufe kann die der Befunde nicht übersteigen.")

    def build(self) -> None:
        self.body.addWidget(warn_label(
            "Gleiche Benutzernamen, Telefonnummern oder E-Mail-Adressen sind kein Beleg dafür, dass es sich um "
            "dieselbe Person handelt. Eine Gleichsetzung zweier Identitäten verlangt einen unabhängigen Beleg "
            "und eine Begründung."))
        split = QSplitter(Qt.Vertical)
        self.view = GraphView()
        split.addWidget(self.view)

        lower = QWidget()
        low = QVBoxLayout(lower)
        low.setContentsMargins(0, 0, 0, 0)
        tables = QSplitter(Qt.Horizontal)

        nbox = QGroupBox("Knoten")
        nl = QVBoxLayout(nbox)
        self.nodes = Table(["Bezeichnung", "Art", "Belege"], stretch=0)
        self.nodes.itemSelectionChanged.connect(self._node_pick)
        nl.addWidget(self.nodes)
        tables.addWidget(nbox)

        ebox = QGroupBox("Verbindungen")
        el = QVBoxLayout(ebox)
        self.edges = Table(["Von", "Beziehung", "Nach", "Belegstufe", "Begründung"], stretch=4)
        self.edges.itemSelectionChanged.connect(self._edge_pick)
        el.addWidget(self.edges)
        tables.addWidget(ebox)
        tables.setSizes([380, 620])
        low.addWidget(tables, 1)

        sbox = QGroupBox("Hinweise (keine Verbindungen, nur Vorschläge zur Prüfung)")
        sl = QVBoxLayout(sbox)
        self.suggestions = QLabel("–")
        self.suggestions.setWordWrap(True)
        sl.addWidget(self.suggestions)
        low.addWidget(sbox)

        btns = QHBoxLayout()
        self.b_node = QPushButton("Knoten hinzufügen …")
        self.b_node.setObjectName("Primary")
        self.b_node.clicked.connect(self._add_node)
        self.b_link = QPushButton("Verbindung übernehmen …")
        self.b_link.clicked.connect(self._link)
        self.b_rm_node = QPushButton("Knoten entfernen")
        self.b_rm_node.clicked.connect(self._remove_node)
        self.b_rm_edge = QPushButton("Verbindung entfernen")
        self.b_rm_edge.clicked.connect(self._remove_edge)
        for b in (self.b_node, self.b_link, self.b_rm_node, self.b_rm_edge):
            btns.addWidget(b)
        btns.addStretch(1)
        low.addLayout(btns)
        split.addWidget(lower)
        split.setSizes([320, 400])
        self.body.addWidget(split, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if not self.ctx.has_case():
            self.view.draw([], [])
            self.nodes.fill([])
            self.edges.fill([])
            self.suggestions.setText("–")
            for b in (self.b_node, self.b_link, self.b_rm_node, self.b_rm_edge):
                b.setEnabled(False)
            return
        cid = self.ctx.case_id
        nodes = self.engine.graph.nodes(cid)
        edges = self.engine.graph.edges(cid)
        findings = {f.id: f for f in self.engine.findings(cid)}
        labels = {n.id: n.label for n in nodes}
        self.view.draw(nodes, edges)
        self.nodes.fill([[cell(n.label, data=n.id), cell(NODE_TYPES.get(n.type, n.type)),
                          cell(len(n.finding_ids))] for n in nodes])
        self.edges.fill([[cell(labels.get(e.source, e.source), data=e.id),
                          cell(RELATIONS.get(e.relation, e.relation)), cell(labels.get(e.target, e.target)),
                          evidence_item(e.evidence),
                          cell(e.note or "–", tooltip="Basisbefunde: " + "; ".join(
                              findings[i].title for i in e.basis_finding_ids if i in findings))]
                         for e in edges])
        sug = self.engine.graph.suggest_links(cid)
        self.suggestions.setText("<br>".join("• " + s.description for s in sug) if sug
                                 else "Keine Hinweise.")
        self.b_node.setEnabled(True)
        self.b_link.setEnabled(len(nodes) >= 2 and bool(findings))
        self._node_pick()
        self._edge_pick()

    def _node_pick(self) -> None:
        self.b_rm_node.setEnabled(bool(self.nodes.selected_data(0)))

    def _edge_pick(self) -> None:
        self.b_rm_edge.setEnabled(bool(self.edges.selected_data(0)))

    def _add_node(self) -> None:
        findings = [f for f in self.engine.findings(self.ctx.case_id, include_rejected=False)]
        dlg = NodeDialog(findings, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        type_, label, ids = dlg.values()
        try:
            self.engine.graph.add_node(self.ctx.case_id, type_, label, ids)
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Knoten", str(exc))
            return
        self.ctx.notify("Knoten hinzugefügt.")

    def _link(self) -> None:
        nodes = self.engine.graph.nodes(self.ctx.case_id)
        findings = self.engine.findings(self.ctx.case_id, include_rejected=False)
        dlg = LinkDialog(nodes, findings, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            self.engine.graph.link(self.ctx.case_id, **dlg.values())
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Verbindung nicht übernommen", str(exc))
            return
        self.ctx.notify("Verbindung übernommen.")

    def _remove_node(self) -> None:
        nid = self.nodes.selected_data(0)
        if nid:
            self.engine.graph.remove_node(self.ctx.case_id, nid)
            self.ctx.notify("Knoten entfernt.")

    def _remove_edge(self) -> None:
        eid = self.edges.selected_data(0)
        if eid:
            self.engine.graph.remove_edge(self.ctx.case_id, eid)
            self.ctx.notify("Verbindung entfernt.")
