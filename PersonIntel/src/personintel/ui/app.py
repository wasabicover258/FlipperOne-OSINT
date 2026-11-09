"""Start der Oberflaeche: Datenverzeichnis oeffnen, ggf. Passphrase erfragen, Hauptfenster zeigen."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import __version__
from ..core.config import AppPaths
from ..core.engine import Engine
from ..core.errors import LockedError, PersonIntelError
from .context import AppContext
from .dialogs import PassphraseDialog
from .main_window import MainWindow
from .style import APP_ICON_SVG


def app_icon() -> QIcon:
    try:
        from importlib.resources import files
        path = files("personintel.ui.resources").joinpath("personintel.svg")
        with path.open("rb") as fh:
            data = fh.read()
    except Exception:
        data = APP_ICON_SVG.encode("utf-8")
    pm = QPixmap()
    if pm.loadFromData(data, "SVG"):
        return QIcon(pm)
    return QIcon()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="personintel", description="PersonIntel – journalistische Personenrecherche")
    ap.add_argument("--data-dir", help="Basisverzeichnis für Daten und Konfiguration (statt XDG)")
    ap.add_argument("--version", action="version", version=f"personintel {__version__}")
    return ap.parse_args(list(argv))


def resolve_paths(data_dir: Optional[str]) -> AppPaths:
    if data_dir:
        base = Path(data_dir).expanduser()
        paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    else:
        paths = AppPaths.default()
    paths.ensure()
    return paths


def open_engine(paths: AppPaths, *, ask_passphrase=None) -> Engine:
    """Oeffnet die Engine; bei verschluesselter Datenbank wird die Passphrase erfragt."""
    passphrase = os.environ.get("PERSONINTEL_DB_PASSPHRASE") or None
    while True:
        try:
            return Engine(paths, db_passphrase=passphrase, load_plugins=True)
        except LockedError as exc:
            if ask_passphrase is None:
                raise
            passphrase = ask_passphrase(str(exc))
            if not passphrase:
                raise


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PersonIntel")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("PersonIntel")
    app.setDesktopFileName("personintel")
    app.setWindowIcon(app_icon())

    def ask(info: str) -> str:
        dlg = PassphraseDialog("Datenbank entsperren", info)
        return dlg.passphrase if dlg.exec() == dlg.DialogCode.Accepted else ""

    paths = resolve_paths(args.data_dir)
    try:
        engine = open_engine(paths, ask_passphrase=ask)
    except (PersonIntelError, OSError) as exc:
        QMessageBox.critical(None, "PersonIntel", f"Start nicht möglich:\n{exc}")
        return 2
    ctx = AppContext(engine)
    win = MainWindow(ctx)
    win.show()
    ctx.refresh_statuses()
    try:
        return app.exec()
    finally:
        engine.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
