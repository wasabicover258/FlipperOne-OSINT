"""Spokeo People Intelligence API v5 (https://docs.spokeo.com).

Dokumentiert (verifiziert gegen docs.spokeo.com): Basis ``https://api.spokeo.com/v5/``, Authentifizierung per
Header ``X-api-key``, ``GET /emails?email=``, ``GET /phones?phone=`` (10-stellige US-Nummer),
``GET /usernames?username=``. Antworten: ``{"data": {...}, "metadata": {...}}``; Fehlerantworten 400/412.
Account-Einrichtung: apisupport@spokeo.com (vertragsgebunden). Es gibt keinen dokumentierten kostenlosen
Test-/Statusendpunkt, daher bleibt der Lizenzstatus bis zur ersten erfolgreichen Abfrage "nicht verifiziert".

Datensparsamkeit: Wohnadressen, Verwandte und Geburtsdaten werden nicht uebernommen; Telefon/E-Mail
nur mit ``include_contact_details``. Rohantworten werden nicht gespeichert.
"""

from __future__ import annotations

from typing import Any

from ..core.errors import AdapterNotAvailable
from ..core.ids import now_iso
from ..core.models import Evidence, FindingStatus, NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from . import _http
from ._commercial import CommercialAdapter
from ._norm import make_finding, make_source
from .base import Capability, RawResult

DEFAULT_URL = "https://api.spokeo.com/v5"
_ENDPOINT = {QueryKind.EMAIL: ("emails", "email"), QueryKind.PHONE: ("phones", "phone"),
             QueryKind.USERNAME: ("usernames", "username")}


def _us_ten_digits(e164: str) -> str:
    digits = e164.lstrip("+")
    if digits.startswith("1") and len(digits) == 11:
        return digits[1:]
    raise AdapterNotAvailable("Spokeo Phone Search unterstützt laut Dokumentation nur 10-stellige US-Nummern (+1…).",
                              "US-Rufnummer verwenden oder anderen Anbieter wählen.")


class SpokeoAdapter(CommercialAdapter):
    id = "spokeo"
    name = "Spokeo"
    vendor = "Spokeo"
    category = "Kommerzielle Rechercheplattformen"
    description = "Spokeo People Intelligence API v5 (E-Mail, Telefon [US], Benutzername) – erfordert API-Vertrag."
    homepage = "https://docs.spokeo.com"

    def missing_requirement(self) -> str:
        return ("Spokeo-API-Zugang (Vertrag; Kontakt apisupport@spokeo.com) und API-Schlüssel "
                "im Credential-Store hinterlegen.")

    def license_text(self) -> str:
        return "durch erfolgreiche Abfrage bestätigt" if self._conn.state == "ok" else "nicht verifizierbar ohne kostenpflichtige Abfrage"

    def get_capabilities(self) -> list[Capability]:
        ok = self.has_key()
        reason = "" if ok else self.missing_requirement()
        caps = [Capability(QueryKind.EMAIL, QueryMode.ACTIVE, "Spokeo Email Search",
                           "Übermittelt die E-Mail-Adresse an Spokeo.", available=ok, reason=reason, cost_note=self.cost_note),
                Capability(QueryKind.USERNAME, QueryMode.ACTIVE, "Spokeo Username Search",
                           "Übermittelt den Benutzernamen an Spokeo.", available=ok, reason=reason,
                           cost_note=self.cost_note),
                Capability(QueryKind.PHONE, QueryMode.ACTIVE, "Spokeo Phone Search (nur US, 10-stellig)",
                           "Übermittelt die US-Rufnummer an Spokeo.", available=ok, reason=reason,
                           cost_note=self.cost_note)]
        return caps

    def _base(self) -> str:
        return _http.safe_base_url(str(self.config.get("base_url", "") or ""), DEFAULT_URL)

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        aq = self._authorize(query)
        if aq.kind not in _ENDPOINT:
            raise AdapterNotAvailable(f"Spokeo: Abfrageart {aq.kind.value} nicht unterstützt.")
        path, param = _ENDPOINT[aq.kind]
        value = _us_ten_digits(aq.value) if aq.kind is QueryKind.PHONE else aq.value
        key = self.api_key()
        started = now_iso()
        self._check_cancel(aq.query_id)
        resp = _http.request("GET", f"{self._base()}/{path}", params={param: value}, headers={"X-api-key": key},
                             timeout=45, secrets=(key,))
        self._check_cancel(aq.query_id)
        if resp.status != 200 or not isinstance(resp.json, dict):
            hint = ""
            if isinstance(resp.json, dict):
                hint = str(resp.json.get("message") or resp.json.get("error") or "")
            raise self._http_error(resp.status or 0, hint)
        self._set_conn("ok", "Zugang funktioniert (Abfrage erfolgreich).")
        return self._raw(aq, started, {"kind": aq.kind.value, "response": resp.json})

    # ------------------------------------------------------------------
    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        batch = NormalizedBatch()
        src = make_source(raw, "Spokeo People Intelligence API v5 (Antwort des Anbieters)", kind="api",
                          url="https://api.spokeo.com/v5/", active=True)
        batch.sources.append(src)
        resp = raw.payload.get("response") or {}
        data = resp.get("data") or {}
        kind = raw.payload.get("kind")
        owners = data.get("owners") or []
        for o in owners[:30]:
            self._owner(raw, src, o, kind, batch)
        for sp in (data.get("social_profiles") or [])[:100]:
            primary = bool(sp.get("is_primary_match"))
            url = sp.get("profile_url") or ""
            batch.findings.append(make_finding(
                raw, src, "profile",
                f"Soziales Profil ({sp.get('network', '?')}): {sp.get('display_name') or sp.get('username') or url}",
                value=sp.get("username", "") or "", url=url, status=FindingStatus.FOUND if primary else FindingStatus.POSSIBLE,
                evidence=Evidence.INDICATION if primary else Evidence.UNCONFIRMED,
                data={"network": sp.get("network"), "match_type": sp.get("match_type"),
                      "search_term": sp.get("search_term"), "is_primary_match": primary,
                      "hinweis": "Anbieterdatensatz – kein eigener Beleg für die Identität."},
                tags=["vendor-record"]))
        info = data.get("phone_info")
        if isinstance(info, dict) and info:
            batch.findings.append(make_finding(
                raw, src, "metadata", "Rufnummern-Informationen (Spokeo)",
                value=", ".join(f"{k}={v}" for k, v in info.items() if v not in (None, "")),
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION, data={"phone_info": info},
                tags=["vendor-record", "phone-metadata"]))
        rep = data.get("reputation")
        if isinstance(rep, dict) and rep:
            batch.findings.append(make_finding(
                raw, src, "metadata", "Reputation der Rufnummer (Spokeo)",
                value=", ".join(f"{k}={v}" for k, v in rep.items() if v not in (None, "")),
                status=FindingStatus.FOUND, evidence=Evidence.INDICATION, data={"reputation": rep},
                tags=["vendor-record"]))
        meta = resp.get("metadata") or {}
        batch.findings.append(make_finding(
            raw, src, "summary", f"Spokeo: {len(owners)} Datensätze, {len(data.get('social_profiles') or [])} Profile",
            status=FindingStatus.INFO, data={"metadata": meta,
                                             "hinweis": "Wohnadressen, Verwandte und Geburtsdaten werden nicht übernommen."}))
        if not owners and not data.get("social_profiles") and not info:
            batch.notes.append("Spokeo lieferte keinen Treffer.")
        return batch

    def _owner(self, raw: RawResult, src, o: dict[str, Any], kind: str | None, batch: NormalizedBatch) -> None:
        names = o.get("names") or []
        name = (f"{o.get('first_name', '')} {o.get('last_name', '')}".strip()
                or (names[0].get("full_name") if names and isinstance(names[0], dict) else "") or "ohne Namen")
        current = o.get("is_current_owner")
        evidence = Evidence.UNCONFIRMED if current is False else Evidence.INDICATION
        data: dict[str, Any] = {"spokeo_id": str(o.get("id", "")), "age": o.get("age"),
                                "confidence_score": o.get("confidence_score"), "is_current_owner": current,
                                "is_company": o.get("is_company"),
                                "social_networks": [sp.get("network") for sp in (o.get("social_profiles") or [])][:20],
                                "work_history": [f"{w.get('title', '')} @ {w.get('company_name', '')}".strip(" @")
                                                 for w in (o.get("work_history") or [])][:10],
                                "schools": [s.get("name") for s in (o.get("schools") or [])][:10],
                                "hinweis": "Anbieterdatensatz – kein eigener Beleg. Adressen, Verwandte, Geburtsdaten "
                                           "werden nicht übernommen."}
        phones = list(o.get("phones") or []) + [p.get("phone") for p in (o.get("additional_phones") or [])]
        emails = [e.get("email") if isinstance(e, dict) else e for e in (o.get("emails") or [])]
        if self.include_contacts():
            data["phones"] = [str(p) for p in phones if p][:20]
            data["emails"] = [e for e in emails if e][:20]
        else:
            data["contact_details_omitted"] = {"phones": len([p for p in phones if p]), "emails": len([e for e in emails if e])}
        status = FindingStatus.POSSIBLE if current is False else FindingStatus.FOUND
        batch.findings.append(make_finding(raw, src, "person_record", f"Spokeo-Datensatz: {name}",
                                           value=str(o.get("id", "")), status=status, evidence=evidence, data=data,
                                           tags=["vendor-record"]))
