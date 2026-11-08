"""Startet die grafische Oberflaeche (``python -m personintel`` bzw. ``personintel``)."""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from . import __version__


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        print(f"personintel {__version__}")
        return 0
    try:
        from .ui.app import run
    except ImportError as exc:
        print("Die grafische Oberfläche benötigt PySide6: pip install 'personintel[ui]'\n"
              f"({exc})", file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
