"""Mosint (alpkeskin/mosint v3) - E-Mail-Analyse aus zulaessigen Quellen.

Verifizierte CLI: ``mosint <email> [-c|--config FILE] [-o|--output FILE.json] [-s|--silent]``.
Mosint **benoetigt eine Konfigurationsdatei** (Standard ``$HOME/.mosint.yaml``; Vorlage
``example-config.yaml`` im Mosint-Repository) - API-Schluessel darin sind optional.

Datenschutz-Regel (Auftrag): *keine Sammlung oder Offenlegung geleakter Passwoerter/Zugangsdaten.*
Das JSON-Schema von Mosint ist nicht formal dokumentiert; deshalb wird die Ausgabe generisch
ausgewertet:
* Schluessel, die nach Passwort/Hash/Token/Geheimnis aussehen, werden verworfen.
* In Leak-/Breach-Abschnitten werden ausschliesslich Quellen-/Seitennamen und Daten
  (Allowlist-Schluessel) uebernommen - niemals freie Zeichenketten aus Listen.
* Rohdaten werden nicht gespeichert.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..core.errors import AdapterError, QueryCancelled
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._local import LocalToolAdapter
from ._norm import make_finding, make_source, strip_secret_keys
from ._process import clean_env
from .base import Capability, ConfigField, ConfigValidation, RawResult

_LEAK_SECTION = re.compile(r"(leak|breach|pwn|dump|paste|hibp|intelx|haveibeenpwned)", re.I)
_LEAK_ALLOWED_KEYS = {"name", "title", "source", "sources", "site", "website", "domain", "date", "breachdate",
                      "breach_date", "added", "addeddate", "count", "total", "pwncount"}
_SKIP_META = {"banner", "version"}


def _leak_summary(obj: Any, depth: int = 0) -> Any:
    """Reduziert Leak-Abschnitte auf Quellennamen/Daten; verwirft jede andere Zeichenkette."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in _LEAK_ALLOWED_KEYS and isinstance(v, (str, int, float, bool)):
                out[k] = v
            elif isinstance(v, (dict, list)):
                sub = _leak_summary(v, depth + 1)
                if sub not in (None, {}, []):
                    out[k] = sub
        return out
    if isinstance(obj, list):
        items = [x for x in (_leak_summary(i, depth + 1) for i in obj if isinstance(i, (dict, list))) if x not in (None, {}, [])]
        return items
    return None


class MosintAdapter(LocalToolAdapter):
    id = "mosint"
    name = "Mosint"
    category = "E-Mail-Recherche"
    description = "Automatisierte E-Mail-Analyse (Validierung, verwandte Domains, Leak-Hinweise ohne Passwörter)."
    homepage = "https://github.com/alpkeskin/mosint"
    executable_name = "mosint"
    version_argv = ("--version",)
    install_text = ("Installation: go install -v github.com/alpkeskin/mosint/v3/cmd/mosint@latest; "
                    "danach ~/.mosint.yaml nach der Vorlage example-config.yaml anlegen.")
    config_fields = LocalToolAdapter.config_fields + (
        ConfigField("config_path", "Mosint-Konfigurationsdatei",
                    help="Standard: ~/.mosint.yaml (Pflicht, damit Mosint startet)."),
    )

    def _config_file(self) -> Path:
        return Path(str(self.config.get("config_path") or "~/.mosint.yaml")).expanduser()

    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation:
        base = super().validate_configuration(config)
        cfg = config if config is not None else self.config
        path = Path(str(cfg.get("config_path") or "~/.mosint.yaml")).expanduser()
        if not path.is_file():
            base.errors.append(f"Mosint-Konfigurationsdatei fehlt: {path} (Vorlage: example-config.yaml im Mosint-Repository).")
            base.ok = False
        return base

    def get_capabilities(self) -> list[Capability]:
        ok = bool(self.exe()) and self.validate_configuration().ok
        reason = ""
        if not self.exe():
            reason = self.install_hint()
        elif not ok:
            reason = "; ".join(self.validate_configuration().errors)
        return [Capability(
            QueryKind.EMAIL, QueryMode.ACTIVE, "E-Mail-Analyse",
            "Mosint kontaktiert Drittdienste (z. B. Verifizierung, DNS, Suchmaschinen, konfigurierte APIs). "
            "Passwörter/Zugangsdaten aus Leaks werden verworfen.", available=ok, reason=reason)]

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.EMAIL)
        exe = self.require_exe()
        val = self.validate_configuration()
        if not val.ok:
            from ..core.errors import AdapterNotAvailable
            raise AdapterNotAvailable("Mosint ist nicht konfiguriert.", "; ".join(val.errors))
        started = now_iso()
        with tempfile.TemporaryDirectory(prefix="pi-mosint-") as tmp:
            out = Path(tmp) / "mosint.json"
            argv = [exe, aq.value, "--config", str(self._config_file()), "--output", str(out), "--silent"]
            res = self.runner.run(aq.query_id, argv, cwd=tmp, timeout=self.timeout(), env=clean_env())
            if res.cancelled:
                raise QueryCancelled("Abfrage abgebrochen.")
            if res.timed_out:
                raise AdapterError("Mosint: Zeitlimit überschritten.")
            if not out.is_file():
                raise AdapterError(f"Mosint lieferte keine JSON-Ausgabe (Code {res.returncode}): "
                                   f"{(res.stderr or res.stdout).strip()[:300]}")
            try:
                data = json.loads(out.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise AdapterError(f"Mosint-Ausgabe ist kein gültiges JSON: {exc}") from exc
        # Sofort bereinigen - unbereinigte Daten verlassen diese Funktion nicht.
        return self._raw(aq, started, {"data": self._sanitize(data)}, version=self.tool_version(exe))

    @staticmethod
    def _sanitize(data: Any) -> Any:
        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for k, v in data.items():
                if _LEAK_SECTION.search(str(k)):
                    out[k] = _leak_summary(v)
                else:
                    out[k] = strip_secret_keys(v)
            return strip_secret_keys(out)
        return strip_secret_keys(data)

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Mosint-Lauf (E-Mail-Analyse, bereinigt)", active=True)
        batch.sources.append(src)
        data = raw.payload.get("data")
        if not isinstance(data, dict):
            batch.notes.append("Mosint lieferte kein auswertbares Objekt.")
            return batch
        for key, val in data.items():
            if str(key).lower() in _SKIP_META or val in (None, "", [], {}):
                continue
            if _LEAK_SECTION.search(str(key)):
                names = self._collect_names(val)
                batch.findings.append(make_finding(
                    raw, src, "breach_hint", f"Datenleck-Hinweis ({key}): {len(names) or 'Treffer'} Quelle(n)",
                    value=", ".join(names[:20]), status=FindingStatus.FOUND, evidence=Evidence.INDICATION,
                    data={"section": key, "sources": names[:100],
                          "hinweis": "Nur Quellennamen/Daten; keine Passwörter oder Zugangsdaten."},
                    tags=["breach-hint"]))
                continue
            if isinstance(val, (str, int, float, bool)):
                batch.findings.append(make_finding(raw, src, "metadata", f"{key}: {val}", value=str(val),
                                                   status=FindingStatus.INFO, data={"field": key}))
            elif isinstance(val, list):
                for item in val[:200]:
                    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)[:300]
                    batch.findings.append(make_finding(
                        raw, src, "metadata", f"{key}: {text}", value=text, status=FindingStatus.FOUND,
                        evidence=Evidence.UNCONFIRMED, data={"field": key}))
            elif isinstance(val, dict):
                batch.findings.append(make_finding(
                    raw, src, "metadata", f"{key}", value=json.dumps(val, ensure_ascii=False)[:500],
                    status=FindingStatus.INFO, data={"field": key, "content": val}))
        if not batch.findings:
            batch.notes.append("Mosint lieferte keine Ergebnisse.")
        return batch

    @staticmethod
    def _collect_names(val: Any) -> list[str]:
        names: list[str] = []

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    if str(k).lower() in {"name", "title", "source", "site", "website", "domain"} and isinstance(v, str):
                        names.append(v)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for i in o:
                    walk(i)

        walk(val)
        return sorted(set(names))
