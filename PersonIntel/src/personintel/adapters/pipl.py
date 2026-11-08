"""Pipl Search API (https://docs.pipl.com).

Dokumentiert (verifiziert): Endpunkt ``https://api.pipl.com/search/`` (nur HTTPS), GET oder POST
(``application/x-www-form-urlencoded``), Parameter ``key`` plus mindestens eine Kennung (``email``,
``phone``, ``username``, ``raw_name`` ...). Antwort: JSON. Laut Anbieter-Doku ist jede Abfrage mit
``email=clark.kent@example.com`` kostenlos und liefert statische Beispieldaten - sie dient hier als
**Verbindungstest** fuer den API-Schluessel, ohne Personendaten abzufragen.

Zugang erfordert einen Pipl-Vertrag/-Schluessel des Nutzers; ohne Schluessel ist der Connector
"nicht konfiguriert". Es werden keine Ergebnisse simuliert. Wohnadressen, Geburtsdaten und Bilder
werden bewusst nicht uebernommen (Datensparsamkeit); Telefon/E-Mail nur mit ``include_contact_details``.
"""

from __future__ import annotations

from typing import Any

from ..core.errors import AdapterError
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from . import _http
from ._commercial import CommercialAdapter
from ._norm import make_finding, make_source
from .base import Capability, RawResult

DEFAULT_URL = "https://api.pipl.com/search/"
_PARAM = {QueryKind.EMAIL: "email", QueryKind.PHONE: "phone", QueryKind.USERNAME: "username", QueryKind.NAME: "raw_name"}


def _disp(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for k in ("display", "address", "content", "url", "number", "name"):
            v = item.get(k)
            if isinstance(v, (str, int)) and str(v):
                return str(v)
        first, last = item.get("first"), item.get("last")
        if first or last:
            return f"{first or ''} {last or ''}".strip()
    return ""


class PiplAdapter(CommercialAdapter):
    id = "pipl"
    name = "Pipl"
    vendor = "Pipl"
    category = "Kommerzielle Rechercheplattformen"
    description = "Pipl Search API (Identity Resolution) – erfordert eigenen API-Schlüssel/Vertrag."
    homepage = "https://docs.pipl.com"

    def license_text(self) -> str:
        return "Schlüssel vom Anbieter akzeptiert (kostenloser Testaufruf)"

    def get_capabilities(self) -> list[Capability]:
        ok = self.has_key()
        reason = "" if ok else self.missing_requirement()
        desc = "Abfrage der Pipl Search API mit der registrierten Kennung (übermittelt die Kennung an Pipl)."
        return [Capability(k, QueryMode.ACTIVE, f"Pipl-Suche nach {k.label_de}", desc, available=ok, reason=reason,
                           cost_note=self.cost_note)
                for k in (QueryKind.EMAIL, QueryKind.PHONE, QueryKind.USERNAME, QueryKind.NAME)]

    def _url(self) -> str:
        return _http.safe_base_url(str(self.config.get("base_url", "") or ""), DEFAULT_URL.rstrip("/")) + "/"

    def test_connection(self) -> tuple[bool, str]:
        """Kostenloser, vom Anbieter dokumentierter Testaufruf (statische Beispieldaten)."""
        key = self.api_key()
        resp = _http.request("POST", self._url(), form={"key": key, "email": "clark.kent@example.com"},
                             timeout=30, secrets=(key,))
        if resp.status == 200:
            self._set_conn("ok", "Zugang funktioniert (kostenloser Testaufruf).")
            return True, "Schlüssel akzeptiert."
        err = self._http_error(resp.status, str((resp.json or {}).get("error", "")) if isinstance(resp.json, dict) else "")
        return False, str(err)

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query)
        param = _PARAM.get(aq.kind)
        if not param:
            from ..core.errors import AdapterNotAvailable
            raise AdapterNotAvailable(f"Pipl: Abfrageart {aq.kind.value} nicht unterstützt.")
        key = self.api_key()
        started = now_iso()
        self._check_cancel(aq.query_id)
        resp = _http.request("POST", self._url(), form={"key": key, param: aq.value}, timeout=45, secrets=(key,))
        self._check_cancel(aq.query_id)
        if resp.status != 200 or not isinstance(resp.json, dict):
            hint = str(resp.json.get("error", "")) if isinstance(resp.json, dict) else resp.text[:120]
            raise self._http_error(resp.status or 0, hint)
        self._set_conn("ok", "Zugang funktioniert.")
        d = resp.json
        meta = {k: d.get(k) for k in ("@search_id", "@persons_count", "@visible_sources", "@available_sources")}
        return self._raw(aq, started, {"person": d.get("person"), "possible_persons": d.get("possible_persons") or [],
                                       "meta": meta, "warnings": d.get("warnings") or []})

    def _person_findings(self, raw: RawResult, src, person: dict, *, evidence: Evidence, status: FindingStatus,
                         label: str, batch: NormalizedBatch) -> None:
        names = [_disp(n) for n in person.get("names", []) if _disp(n)]
        title = f"{label}: {names[0] if names else 'Person ohne Namen'}"
        data: dict[str, Any] = {"names": names[:10], "match": person.get("@match"),
                                "jobs": [_disp(j) for j in person.get("jobs", [])][:10],
                                "educations": [_disp(e) for e in person.get("educations", [])][:10],
                                "usernames": [_disp(u) for u in person.get("usernames", [])][:20],
                                "urls": [_disp(u) for u in person.get("urls", [])][:30]}
        if self.include_contacts():
            data["emails"] = [_disp(e) for e in person.get("emails", [])][:20]
            data["phones"] = [_disp(p) for p in person.get("phones", [])][:20]
        else:
            data["contact_details_omitted"] = {"emails": len(person.get("emails", [])),
                                               "phones": len(person.get("phones", []))}
        data["hinweis"] = "Anbieterdatensatz – kein eigener Beleg. Adressen, Geburtsdaten und Bilder werden nicht übernommen."
        batch.findings.append(make_finding(raw, src, "person_record", title, value="; ".join(names[:3]),
                                           status=status, evidence=evidence, data=data, tags=["vendor-record"]))
        for u in data["urls"]:
            if u.startswith(("http://", "https://")):
                batch.findings.append(make_finding(raw, src, "profile", f"Profil-URL im Pipl-Datensatz: {u}", url=u,
                                                   status=status, evidence=evidence,
                                                   data={"via": "pipl", "person": names[0] if names else ""},
                                                   tags=["vendor-record"]))

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Pipl Search API (Antwort des Anbieters)", kind="api", url="https://api.pipl.com/search/",
                          active=True)
        batch.sources.append(src)
        person = raw.payload.get("person")
        if isinstance(person, dict) and person:
            self._person_findings(raw, src, person, evidence=Evidence.INDICATION, status=FindingStatus.FOUND,
                                  label="Pipl-Treffer", batch=batch)
        for p in raw.payload.get("possible_persons", [])[:20]:
            if isinstance(p, dict):
                self._person_findings(raw, src, p, evidence=Evidence.UNCONFIRMED, status=FindingStatus.POSSIBLE,
                                      label="Mögliche Person (Pipl)", batch=batch)
        meta = raw.payload.get("meta", {})
        batch.findings.append(make_finding(
            raw, src, "summary", f"Pipl: {len(batch.findings)} Datensätze/Profile", status=FindingStatus.INFO,
            data={"meta": meta, "warnings": raw.payload.get("warnings", [])}))
        if not (person or raw.payload.get("possible_persons")):
            batch.notes.append("Pipl lieferte keinen Treffer.")
        return batch
