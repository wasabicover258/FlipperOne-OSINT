"""Kommerzielle Connectoren gegen einen lokalen HTTP-Server mit dem dokumentierten Antwortformat.

Die echten Anbieter werden nie kontaktiert: ``base_url`` zeigt auf 127.0.0.1.
"""

import json

import pytest

from personintel.adapters.base import AdapterState
from personintel.api import (AdapterNotAvailable, AuthorizationDenied, Evidence, FindingStatus, QueryState)
from conftest import confirm, make_case, run


def _setup(engine, server, adapter_id, *, key="good-key", contacts="false"):
    engine.configure_adapter(adapter_id, secrets={"api_key": key},
                             config={"base_url": server.url, "include_contact_details": contacts})
    return engine.adapter(adapter_id)


# --------------------------------------------------------------------- Status
def test_commercial_status_without_key(engine):
    st = {s.adapter_id: s for s in engine.statuses()}
    for aid in ("pipl", "spokeo"):
        assert st[aid].state is AdapterState.NOT_CONFIGURED
        assert "API-Schlüssel" in st[aid].requirement or "API-Schlüssel" in st[aid].message
        assert all(not c.available for c in engine.adapter(aid).get_capabilities())


def test_status_is_unverified_until_first_successful_call(engine, vendor_server):
    ad = _setup(engine, vendor_server, "spokeo")
    assert ad.get_status().state is AdapterState.UNVERIFIED
    case = make_case(engine)
    rec, _ = run(engine, case.id, "spokeo", "email", "erika@example.org")
    assert rec.state is QueryState.DONE, rec.message
    st = ad.get_status()
    assert st.state is AdapterState.AVAILABLE and "verbunden" in st.connection_status


def test_query_without_key_is_denied_before_any_request(engine, vendor_server):
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied):
        engine.run_query(case.id, "pipl", t.id, confirmation=confirm(t.value))
    assert vendor_server.calls == []


def test_non_https_base_url_is_refused(engine):
    engine.configure_adapter("pipl", secrets={"api_key": "k"}, config={"base_url": "http://example.org"})
    val = engine.adapter("pipl").validate_configuration()
    assert not val.ok and any("HTTPS" in e for e in val.errors)


# ----------------------------------------------------------------------- Pipl
def test_pipl_connection_test_uses_free_documented_call(engine, vendor_server):
    ad = _setup(engine, vendor_server, "pipl")
    ok, msg = ad.test_connection()
    assert ok, msg
    method, path, form, headers = vendor_server.calls[-1]
    assert method == "POST" and form["email"] == "clark.kent@example.com"
    assert ad.get_status().state is AdapterState.AVAILABLE


def test_pipl_rejects_bad_key_and_reports_it(engine, vendor_server):
    ad = _setup(engine, vendor_server, "pipl", key="bad-key")
    ok, msg = ad.test_connection()
    assert not ok and "abgelehnt" in msg
    st = ad.get_status()
    assert st.state is AdapterState.ERROR and st.license_status == "abgelehnt"


def test_pipl_query_minimizes_data(engine, vendor_server):
    _setup(engine, vendor_server, "pipl")
    case = make_case(engine)
    rec, fs = run(engine, case.id, "pipl", "email", "erika@example.org")
    assert rec.state is QueryState.DONE, rec.message
    rec_f = next(f for f in fs if f.type == "person_record" and f.title.startswith("Pipl-Treffer"))
    assert rec_f.evidence is Evidence.INDICATION and "vendor-record" in rec_f.tags
    assert rec_f.data["names"] == ["Erika Beispiel"]
    assert rec_f.data["contact_details_omitted"] == {"emails": 1, "phones": 0}
    possible = next(f for f in fs if f.title.startswith("Mögliche Person"))
    assert possible.evidence is Evidence.UNCONFIRMED and possible.status is FindingStatus.POSSIBLE
    assert any(f.type == "profile" and f.url == "https://example.org/erika" for f in fs)
    # Wohnadresse und Geburtsdatum werden nie uebernommen - auch nicht in der Datenbank
    rows = engine.repo.conn.execute("SELECT payload FROM records").fetchall()
    blob = json.dumps([f.to_dict() for f in fs]) + "".join(r["payload"] for r in rows)
    assert "Musterstr" not in blob and "1980-01-01" not in blob


def test_pipl_contact_details_only_on_explicit_opt_in(engine, vendor_server):
    _setup(engine, vendor_server, "pipl", contacts="true")
    case = make_case(engine)
    rec, fs = run(engine, case.id, "pipl", "email", "erika@example.org")
    rec_f = next(f for f in fs if f.type == "person_record" and f.title.startswith("Pipl-Treffer"))
    assert rec_f.data["emails"] == ["erika@example.org"]
    assert "Musterstr" not in json.dumps(rec_f.data)


def test_pipl_api_key_is_never_stored_with_results(engine, vendor_server):
    _setup(engine, vendor_server, "pipl")
    case = make_case(engine)
    run(engine, case.id, "pipl", "email", "erika@example.org")
    rows = engine.repo.conn.execute("SELECT payload FROM records").fetchall()
    assert not any("good-key" in r["payload"] for r in rows)
    assert not any("good-key" in json.dumps(e.detail) for e in engine.audit.entries())


# --------------------------------------------------------------------- Spokeo
def test_spokeo_email_search_normalizes_profiles(engine, vendor_server):
    _setup(engine, vendor_server, "spokeo")
    case = make_case(engine)
    rec, fs = run(engine, case.id, "spokeo", "email", "erika@example.org")
    assert rec.state is QueryState.DONE, rec.message
    method, path, params, headers = vendor_server.calls[-1]
    assert method == "GET" and path.endswith("/emails") and headers["x-api-key"] == "good-key"
    owner = next(f for f in fs if f.type == "person_record")
    assert owner.evidence is Evidence.INDICATION
    assert owner.data["contact_details_omitted"] == {"phones": 1, "emails": 1}
    prof = next(f for f in fs if f.type == "profile")
    assert prof.url == "https://example.social/@erika" and prof.status is FindingStatus.FOUND
    blob = json.dumps([f.to_dict() for f in fs])
    for forbidden in ("Musterstr", "Max Beispiel", "1980-01-01"):
        assert forbidden not in blob, forbidden


def test_spokeo_rate_limit_is_reported_and_not_retried(engine, vendor_server):
    _setup(engine, vendor_server, "spokeo")
    vendor_server.spokeo_status = 429
    case = make_case(engine)
    rec, fs = run(engine, case.id, "spokeo", "email", "erika@example.org")
    assert rec.state is QueryState.FAILED
    assert "429" in rec.message and "nicht automatisch wiederholt" in rec.message
    assert fs == []
    assert len([c for c in vendor_server.calls if c[0] == "GET"]) == 1   # kein Wiederholungsversuch


def test_spokeo_phone_is_us_only(engine, vendor_server):
    _setup(engine, vendor_server, "spokeo")
    case = make_case(engine)
    rec, _ = run(engine, case.id, "spokeo", "phone", "+49 30 123456")
    assert rec.state is QueryState.FAILED and "US-Nummern" in rec.message
    rec, fs = run(engine, case.id, "spokeo", "phone", "+1 212 555 0100")
    assert rec.state is QueryState.DONE, rec.message
    assert vendor_server.calls[-1][2]["phone"] == "2125550100"


def test_spokeo_cancel_before_request(engine, vendor_server):
    ad = _setup(engine, vendor_server, "spokeo")
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "erika@example.org")
    aq = engine.gate.authorize(engine.case(case.id), t, ad, "email", confirm(t.value))
    ad.cancel_query(aq.query_id)
    from personintel.api import QueryCancelled
    with pytest.raises(QueryCancelled):
        ad.execute_authorized_query(aq)


# ------------------------------------------------- Anbieter ohne Doku/Freigabe
@pytest.mark.parametrize("adapter_id", ["shadowdragon", "babelstreet"])
def test_vendor_contract_adapters_are_transparent_not_fake(engine, adapter_id):
    ad = engine.adapter(adapter_id)
    st = ad.get_status()
    assert st.state is AdapterState.UNAVAILABLE_VENDOR
    assert st.requirement and len(st.requirement) > 30
    assert all(not c.available and c.reason for c in ad.get_capabilities())
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied):
        engine.run_query(case.id, adapter_id, t.id, confirmation=confirm(t.value))


@pytest.mark.parametrize("adapter_id", ["shadowdragon", "babelstreet"])
def test_vendor_contract_execute_names_the_requirement(engine, adapter_id):
    ad = engine.adapter(adapter_id)
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    # Autorisierung technisch erzwingen, um den Adaptervertrag selbst zu pruefen
    from personintel.security.authorization import AuthorizedQuery, _sign
    from personintel.core.models import QueryKind, QueryMode
    from personintel.core.ids import new_id, now_iso
    aq = AuthorizedQuery(new_id("qry"), case.id, adapter_id, t.id, QueryKind.EMAIL, t.value, QueryMode.ACTIVE,
                         now_iso())
    aq = AuthorizedQuery(**{**aq.__dict__, "signature": _sign(aq._parts())})
    with pytest.raises(AdapterNotAvailable) as exc:
        ad.execute_authorized_query(aq)
    assert exc.value.requirement
