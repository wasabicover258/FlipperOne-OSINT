"""Mr.Holmes (Lucksi/Mr.Holmes) - Erkennung der lokalen Installation und Berichtsimport.

Mr.Holmes wird laut oeffentlicher Dokumentation ausschliesslich ueber ein interaktives Menue
(``python3 MrHolmes.py``) bedient; eine dokumentierte, nicht-interaktive CLI/API existiert nicht.
Dieser Adapter erfindet deshalb keine Automatisierung. Unterstuetzt wird:

* **Erkennung** einer lokalen Installation (Verzeichnis mit ``MrHolmes.py``; Konfiguration oder uebliche Orte).
* **Berichtsimport**: Von Mr.Holmes (oder einer anderen Quelle) erzeugte Berichtsdateien
  (.txt/.json/.html/.csv/.md) werden lokal eingelesen, mit SHA-256 als Quelle dokumentiert und
  strukturiert aufbereitet (E-Mail-Adressen, URLs, Rufnummern-aehnliche Zeichenfolgen).
  Der Import ist *passiv* (keine Netzwerkzugriffe); Inhalte bleiben unbestaetigt, bis sie geprueft sind.

Die Recherche selbst fuehrt der Nutzer in Mr.Holmes durch - ausserhalb der Recherchekontrolle von
PersonIntel; der Import ist der dokumentierte Weg, Ergebnisse quellenbasiert zu uebernehmen.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, ClassVar, Optional

from ..core.errors import AdapterError, ValidationError
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._norm import make_finding, make_source
from .base import (Adapter, AdapterState, AdapterStatus, Capability, ConfigField, ConfigValidation, InstallInfo,
                   RawResult)

ALLOWED_SUFFIXES = {".txt", ".json", ".html", ".htm", ".csv", ".md", ".log"}
MAX_IMPORT_BYTES = 5_000_000
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
_PHONE = re.compile(r"(?<![\w/])\+[1-9][\d ()\-]{7,18}\d")
_CANDIDATE_DIRS = ["~/Mr.Holmes", "~/tools/Mr.Holmes", "~/Desktop/Mr.Holmes", "~/Downloads/Mr.Holmes", "/opt/Mr.Holmes"]


class MrHolmesAdapter(Adapter):
    id = "mrholmes"
    name = "Mr.Holmes"
    category = "Recherche und Berichterstellung"
    description = "Erkennt eine lokale Mr.Holmes-Installation und übernimmt dessen Berichte quellenbasiert (Import, passiv)."
    homepage = "https://github.com/Lucksi/Mr.Holmes"
    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField("install_dir", "Mr.Holmes-Verzeichnis (optional)", help="Verzeichnis, das MrHolmes.py enthält."),
    )

    def install_hint(self) -> str:
        return ("Installation: git clone https://github.com/Lucksi/Mr.Holmes && cd Mr.Holmes && "
                "sudo bash install.sh (siehe Projekt-README). Berichtsimport funktioniert auch ohne Installation.")

    def _install_dir(self) -> Optional[Path]:
        cfg = str(self.config.get("install_dir", "") or "")
        for cand in ([cfg] if cfg else []) + _CANDIDATE_DIRS:
            p = Path(cand).expanduser()
            if (p / "MrHolmes.py").is_file():
                return p
        return None

    def detect_installation(self) -> InstallInfo:
        p = self._install_dir()
        if not p:
            return InstallInfo(False, message="Keine Mr.Holmes-Installation gefunden.")
        return InstallInfo(True, path=str(p), version="", message=f"Installation: {p} (Version nicht ermittelbar)")

    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation:
        cfg = config if config is not None else self.config
        d = str(cfg.get("install_dir", "") or "")
        if d and not (Path(d).expanduser() / "MrHolmes.py").is_file():
            return ConfigValidation(False, [f"{d} enthält keine MrHolmes.py."])
        return ConfigValidation(True)

    def get_capabilities(self) -> list[Capability]:
        return [Capability(
            QueryKind.REPORT_FILE, QueryMode.PASSIVE, "Bericht importieren",
            "Liest eine lokale Berichtsdatei ein (keine Netzwerkzugriffe). Mr.Holmes bietet keine "
            "dokumentierte Automatisierungsschnittstelle; Recherchen führen Sie dort selbst durch.")]

    def get_status(self) -> AdapterStatus:
        if not self.enabled:
            return AdapterStatus(self.id, AdapterState.DISABLED, "Modul ist deaktiviert.")
        val = self.validate_configuration()
        if not val.ok:
            return AdapterStatus(self.id, AdapterState.NOT_CONFIGURED, "; ".join(val.errors),
                                 requirement="; ".join(val.errors))
        inst = self.detect_installation()
        if inst.installed:
            return AdapterStatus(self.id, AdapterState.AVAILABLE,
                                 f"Installation erkannt ({inst.path}). Unterstützt: Berichtsimport. "
                                 "Interaktive Recherche läuft außerhalb von PersonIntel.")
        return AdapterStatus(self.id, AdapterState.NOT_INSTALLED,
                             "Keine Installation erkannt – Berichtsimport ist dennoch möglich.",
                             requirement=self.install_hint())

    def find_candidate_reports(self, limit: int = 50) -> list[str]:
        """Heuristik: Dateien in Verzeichnissen namens 'Reports' der Installation (Struktur nicht dokumentiert)."""
        base = self._install_dir()
        if not base:
            return []
        out: list[tuple[float, str]] = []
        for d in base.rglob("*"):
            if d.is_dir() and d.name.lower() == "reports":
                for f in d.rglob("*"):
                    if f.is_file() and f.suffix.lower() in ALLOWED_SUFFIXES:
                        out.append((f.stat().st_mtime, str(f)))
        return [p for _, p in sorted(out, reverse=True)[:limit]]

    # ------------------------------------------------------------------
    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query, kind_expected=QueryKind.REPORT_FILE)
        started = now_iso()
        path = Path(aq.value).expanduser()
        if not path.is_file():
            raise AdapterError(f"Datei nicht gefunden: {path}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValidationError(f"Dateityp nicht unterstützt (erlaubt: {', '.join(sorted(ALLOWED_SUFFIXES))}).")
        size = path.stat().st_size
        if size > MAX_IMPORT_BYTES:
            raise AdapterError(f"Datei zu groß ({size} Bytes; Limit {MAX_IMPORT_BYTES}).")
        data = path.read_bytes()
        text = data.decode("utf-8", "replace")
        if path.suffix.lower() in (".html", ".htm"):
            text = html.unescape(re.sub(r"(?is)<(script|style).*?</\1>", " ", text))
            text = re.sub(r"<[^>]+>", " ", text)
        json_keys: list[str] = []
        if path.suffix.lower() == ".json":
            try:
                obj = json.loads(data.decode("utf-8", "replace"))
                json_keys = sorted(obj.keys())[:50] if isinstance(obj, dict) else []
            except ValueError:
                pass
        payload = {"file_name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": size,
                   "text": text, "json_keys": json_keys}
        return self._raw(aq, started, payload)

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        p = raw.payload
        src = make_source(raw, f"Importierte Berichtsdatei „{p['file_name']}“ (SHA-256 {p['sha256'][:16]}…)",
                          kind="file")
        batch.sources.append(src)
        text: str = p.get("text", "")
        batch.findings.append(make_finding(
            raw, src, "document", f"Bericht importiert: {p['file_name']}", value=p["sha256"],
            status=FindingStatus.INFO, evidence=Evidence.UNCONFIRMED,
            data={"size": p["size"], "sha256": p["sha256"], "json_keys": p.get("json_keys", []),
                  "excerpt": " ".join(text.split())[:1500],
                  "hinweis": "Inhalt stammt aus einer externen Datei; Echtheit und Richtigkeit sind nicht geprüft."},
            tags=["import"]))
        seen: set[tuple[str, str]] = set()
        for label, rx, ftype, limit in (("E-Mail-Adresse", _EMAIL, "metadata", 100), ("URL", _URL, "link_hint", 200),
                                        ("Rufnummer (Muster)", _PHONE, "metadata", 100)):
            n = 0
            for m in rx.finditer(text):
                val = m.group(0).rstrip(".,;")
                if (label, val) in seen:
                    continue
                seen.add((label, val))
                n += 1
                if n > limit:
                    batch.notes.append(f"{label}: Limit von {limit} Einträgen erreicht.")
                    break
                batch.findings.append(make_finding(
                    raw, src, ftype, f"{label} im Bericht: {val}", value=val,
                    url=val if label == "URL" else "", status=FindingStatus.POSSIBLE, evidence=Evidence.UNCONFIRMED,
                    data={"extracted_by": "regex", "file": p["file_name"]}, tags=["import", "extracted"]))
        return batch
