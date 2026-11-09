"""Headless-Kommandozeile: Status, Faelle, Export/Import, Berichte, Audit-Pruefung.

Bewusst *ohne* Recherche-Befehle als einzelne Unterbefehle: Abfragen erfordern die dokumentierte
Zweckpruefung und bei aktiven Pruefungen eine gesonderte Bestaetigung. Ein fremdes Vorderteil, das
diese Bestaetigung beim Menschen einholt, benutzt stattdessen ``personintel-cli bridge``
(zeilenweises JSON, siehe :mod:`personintel.bridge`).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .core.config import AppPaths
from .core.engine import Engine
from .core.errors import LockedError, PersonIntelError
from .storage.repository import Repository


def _open(args) -> Engine:
    paths = AppPaths.default()
    if args.data_dir:
        base = Path(args.data_dir).expanduser()
        paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    paths.ensure()
    pw = os.environ.get("PERSONINTEL_DB_PASSPHRASE")
    try:
        return Engine(paths, db_passphrase=pw)
    except LockedError:
        if not sys.stdin.isatty():
            raise
        return Engine(paths, db_passphrase=getpass.getpass("Passphrase der Datenbank: "))


def _write(text: str, out: Optional[str]) -> None:
    if out:
        p = Path(out)
        p.write_text(text, encoding="utf-8")
        os.chmod(p, 0o600)
        print(f"Geschrieben: {p}")
    else:
        print(text)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="personintel-cli", description="PersonIntel – Kommandozeile (ohne Recherchebefehle)")
    ap.add_argument("--version", action="version", version=f"personintel {__version__}")
    ap.add_argument("--data-dir", help="Basisverzeichnis (statt XDG), enthält data/ und config/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="Betriebsstatus der zehn Module")
    s.add_argument("--json", action="store_true")
    sub.add_parser("cases", help="Fälle auflisten")
    sub.add_parser("audit-verify", help="Hash-Kette des Audit-Protokolls prüfen")
    e = sub.add_parser("export", help="Fall als JSON-Bundle exportieren")
    e.add_argument("case_id")
    e.add_argument("-o", "--output")
    i = sub.add_parser("import", help="JSON-Bundle importieren")
    i.add_argument("file")
    sub.add_parser("bridge", help="Brückenbetrieb: zeilenweises JSON über stdin/stdout (für fremde Oberflächen)")
    r = sub.add_parser("report", help="Bericht erzeugen")
    r.add_argument("case_id")
    r.add_argument("--format", choices=["md", "html", "json"], default="md")
    r.add_argument("-o", "--output")
    r.add_argument("--mask", action="store_true", help="Kennungen im Bericht maskieren")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "bridge":
        from .bridge import run_bridge
        return run_bridge(args.data_dir)
    try:
        eng = _open(args)
    except LockedError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    try:
        if args.cmd == "status":
            sts = eng.statuses()
            names = {a.id: a.name for a in eng.adapters()}
            if args.json:
                print(json.dumps([{**s.__dict__, "state": s.state.value, "name": names[s.adapter_id]} for s in sts],
                                 ensure_ascii=False, indent=2))
            else:
                for s in sts:
                    line = f"{names[s.adapter_id]:<14} {s.state.label_de:<36} {s.version or ''}"
                    print(line.rstrip())
                    if s.requirement:
                        print(f"{'':<14} Voraussetzung: {s.requirement}")
        elif args.cmd == "cases":
            for c in eng.cases():
                print(f"{c.id}  {c.created_at}  {c.name}")
        elif args.cmd == "audit-verify":
            ok, bad = eng.audit.verify()
            print("Audit-Protokoll: OK" if ok else f"Audit-Protokoll: MANIPULATION/FEHLER ab Eintrag {bad}")
            return 0 if ok else 1
        elif args.cmd == "export":
            _write(json.dumps(eng.export_case(args.case_id), ensure_ascii=False, indent=2), args.output)
        elif args.cmd == "import":
            data = json.loads(Path(args.file).read_text(encoding="utf-8"))
            case = eng.import_case(data)
            print(f"Importiert: {case.id} – {case.name}")
        elif args.cmd == "report":
            rep = eng.build_report(args.case_id, mask_identifiers=args.mask)
            text = {"md": rep.to_markdown, "html": rep.to_html, "json": rep.to_json}[args.format]()
            _write(text, args.output)
        return 0
    except (PersonIntelError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    finally:
        eng.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
