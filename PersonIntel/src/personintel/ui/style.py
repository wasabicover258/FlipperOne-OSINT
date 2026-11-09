"""Farben und Stylesheet. Belegstufen und Modulstatus sind immer farblich *und* textlich erkennbar."""

from __future__ import annotations

from ..adapters.base import AdapterState
from ..core.models import Evidence, FindingStatus, QueryState, ReviewState

EVIDENCE_COLOR = {
    Evidence.CONFIRMED: "#1b7f3a",
    Evidence.INDICATION: "#b5651d",
    Evidence.UNCONFIRMED: "#6b6b6b",
}
STATE_COLOR = {
    AdapterState.AVAILABLE: "#1b7f3a",
    AdapterState.NOT_INSTALLED: "#b5651d",
    AdapterState.NOT_CONFIGURED: "#b5651d",
    AdapterState.UNVERIFIED: "#9a7d0a",
    AdapterState.UNAVAILABLE_VENDOR: "#2f5d8a",
    AdapterState.DISABLED: "#6b6b6b",
    AdapterState.ERROR: "#a62121",
}
QUERY_STATE_LABEL = {
    QueryState.QUEUED: "wartet",
    QueryState.RUNNING: "läuft",
    QueryState.DONE: "fertig",
    QueryState.FAILED: "fehlgeschlagen",
    QueryState.CANCELLED: "abgebrochen",
}
FINDING_STATUS_LABEL = {
    FindingStatus.FOUND: "Treffer",
    FindingStatus.POSSIBLE: "möglicher Treffer",
    FindingStatus.NOT_FOUND: "kein Treffer",
    FindingStatus.FAILED: "fehlgeschlagen",
    FindingStatus.INFO: "Information",
}
REVIEW_LABEL = {
    ReviewState.UNREVIEWED: "ungeprüft",
    ReviewState.REVIEWED: "geprüft",
    ReviewState.REJECTED: "verworfen",
}

STYLESHEET = """
QMainWindow, QDialog { background: #f4f5f7; }
QWidget#Sidebar { background: #22303f; }
QPushButton#NavButton {
    background: transparent; color: #cfd8e3; border: none; padding: 10px 14px;
    text-align: left; font-size: 13px;
}
QPushButton#NavButton:hover { background: #2c3e51; color: #ffffff; }
QPushButton#NavButton:checked { background: #38546f; color: #ffffff; font-weight: bold; }
QLabel#PageTitle { font-size: 19px; font-weight: bold; color: #1d2a36; }
QLabel#PageHint { color: #4b5a68; }
QLabel#CaseBanner { background: #e3e9f0; border: 1px solid #c6d0da; padding: 6px 10px; border-radius: 4px; }
QLabel#Warning { background: #fdf3e3; border: 1px solid #e6c98f; padding: 8px 10px; border-radius: 4px; color: #6b4a10; }
QGroupBox { font-weight: bold; margin-top: 10px; border: 1px solid #ccd4dd; border-radius: 5px; padding-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTableWidget { background: #ffffff; gridline-color: #e3e7ec; }
QHeaderView::section { background: #eaeef3; padding: 5px; border: none; border-right: 1px solid #dde3ea; }
QPushButton { padding: 6px 12px; }
QPushButton#Primary { background: #2f6fa8; color: white; border: none; border-radius: 4px; padding: 7px 14px; }
QPushButton#Primary:hover { background: #3a82c2; }
QPushButton#Primary:disabled { background: #a9bccd; }
QPushButton#Danger { background: #a62121; color: white; border: none; border-radius: 4px; padding: 6px 12px; }
QPushButton#Danger:hover { background: #c02a2a; }
QTextBrowser, QPlainTextEdit { background: #ffffff; }
"""

APP_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="12" fill="#22303f"/>
  <circle cx="27" cy="26" r="12" fill="none" stroke="#7fb2de" stroke-width="4"/>
  <line x1="36" y1="35" x2="50" y2="49" stroke="#7fb2de" stroke-width="5" stroke-linecap="round"/>
  <circle cx="27" cy="22" r="4" fill="#e8f1f9"/>
  <path d="M19 33c2-4 14-4 16 0" fill="none" stroke="#e8f1f9" stroke-width="3" stroke-linecap="round"/>
</svg>
"""
