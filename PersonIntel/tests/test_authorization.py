import dataclasses
import pytest

from personintel.api import (ActiveConfirmation, AuthorizationDenied, Purpose, QueryKind, UnauthorizedQueryError,
                             ValidationError)
from personintel.security.authorization import AuthorizedQuery
from conftest import PURPOSE_TEXT, confirm, make_case, write_tool

HOLEHE = """
import sys
if "--help" in sys.argv: print("usage: holehe [--csv] [--no-clear] [--timeout]"); sys.exit(0)
"""


def test_no_purpose_blocks_everything(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = engine.create_case("ohne Zweck")
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="Recherchezweck"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))


def test_purpose_requires_concrete_description_and_responsible_person(engine):
    case = engine.create_case("x")
    with pytest.raises(ValidationError):
        engine.set_purpose(case.id, Purpose(category="journalism", description="kurz", authorized_by="Ich"))
    with pytest.raises(ValidationError):
        engine.set_purpose(case.id, Purpose(category="journalism", description=PURPOSE_TEXT, authorized_by=" "))
    with pytest.raises(ValidationError):
        engine.set_purpose(case.id, Purpose(category="spass", description=PURPOSE_TEXT, authorized_by="Ich"))


def test_expired_purpose_is_rejected(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = make_case(engine)
    c = engine.case(case.id)
    c.purpose.expires_at = "2000-01-01T00:00:00+00:00"
    engine.repo.save_case(c)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="abgelaufen"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))


def test_active_check_needs_purpose_permission_and_separate_confirmation(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    passive = make_case(engine, active=False)
    t = engine.add_target(passive.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="keine aktiven"):
        engine.run_query(passive.id, "holehe", t.id, confirmation=confirm(t.value))

    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="Bestätigung|Bestaetigung"):
        engine.run_query(case.id, "holehe", t.id)  # keine Bestaetigung
    with pytest.raises(AuthorizationDenied, match="stimmt nicht"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm("other@example.org"))
    with pytest.raises(AuthorizationDenied, match="Nutzungsbedingungen"):
        engine.run_query(case.id, "holehe", t.id, confirmation=ActiveConfirmation(t.value, True, False))


def test_scope_is_limited_and_single_identifier_only(engine):
    case = make_case(engine)
    for bad in ("a@example.org, b@example.org", "a@example.org b@example.org", "a@example.org\nb@example.org",
                "not-an-email"):
        with pytest.raises(ValidationError):
            engine.add_target(case.id, "email", bad)
    with pytest.raises(ValidationError):
        engine.add_target(case.id, "phone", "+49 30 1234, +49 30 5678")
    for i in range(engine.settings.limits.max_targets_per_case):
        engine.add_target(case.id, "username", f"user{i}")
    with pytest.raises(AuthorizationDenied, match="Fallumfang"):
        engine.add_target(case.id, "username", "one_too_many")


def test_duplicate_target_rejected(engine):
    case = make_case(engine)
    engine.add_target(case.id, "email", "A@Example.org")
    with pytest.raises(ValidationError):
        engine.add_target(case.id, "email", "a@example.org")


def test_purpose_can_restrict_kinds(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = engine.create_case("nur Benutzernamen")
    engine.set_purpose(case.id, Purpose(category="journalism", description=PURPOSE_TEXT, authorized_by="Ich",
                                        active_checks_allowed=True, allowed_kinds=["username"]))
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="erlaubt keine"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))


def test_forged_and_tampered_authorizations_are_rejected(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    adapter = engine.adapter("holehe")
    forged = AuthorizedQuery(query_id="qry_0000000000000000", case_id=case.id, adapter_id="holehe", target_id=t.id,
                             kind=QueryKind.EMAIL, value=t.value, mode=adapter.capability(QueryKind.EMAIL).mode,
                             issued_at="2026-01-01T00:00:00+00:00", signature="deadbeef")
    with pytest.raises(UnauthorizedQueryError):
        adapter.execute_authorized_query(forged)
    with pytest.raises(UnauthorizedQueryError):
        adapter.execute_authorized_query("holehe a@example.org")  # type: ignore[arg-type]
    with pytest.raises(UnauthorizedQueryError):
        engine.jobs.submit(forged, adapter)

    real = engine.gate.authorize(case_obj := engine.case(case.id), t, adapter, QueryKind.EMAIL, confirm(t.value))
    tampered = dataclasses.replace(real, value="victim@example.org")  # Ziel nachtraeglich geaendert
    with pytest.raises(UnauthorizedQueryError):
        adapter.execute_authorized_query(tampered)


def test_authorization_is_bound_to_adapter(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    write_tool(bin_dir, "sherlock", "import sys\nsys.exit(0)\n")
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    aq = engine.gate.authorize(engine.case(case.id), t, engine.adapter("holehe"), QueryKind.EMAIL, confirm(t.value))
    with pytest.raises(UnauthorizedQueryError):
        engine.adapter("sherlock").execute_authorized_query(aq)


def test_daily_budget_and_min_interval(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    engine.settings.limits.min_active_interval_seconds = 3600.0
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    rec = engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))
    engine.wait(rec.id, 30)
    with pytest.raises(AuthorizationDenied, match="Mindestabstand"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))

    engine.settings.limits.min_active_interval_seconds = 0.0
    engine.settings.limits.max_active_queries_per_case_per_day = 1
    with pytest.raises(AuthorizationDenied, match="Tagesbudget"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))


def test_denials_and_authorizations_are_audited_without_plaintext_identifier(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    case = make_case(engine, active=False)
    t = engine.add_target(case.id, "email", "secret.person@example.org")
    with pytest.raises(AuthorizationDenied):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))
    entries = engine.audit.entries(case.id)
    assert any(e.action == "query.denied" for e in entries)
    assert "secret.person" not in repr([e.detail for e in entries])
    assert engine.audit.verify() == (True, None)


def test_unavailable_vendor_functions_are_denied(engine):
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="nicht verfuegbar"):
        engine.run_query(case.id, "shadowdragon", t.id, confirmation=confirm(t.value))
    with pytest.raises(AuthorizationDenied, match="nicht verfuegbar"):
        engine.run_query(case.id, "babelstreet", t.id, confirmation=confirm(t.value))


def test_disabled_adapter_is_denied(engine, bin_dir):
    write_tool(bin_dir, "holehe", HOLEHE)
    engine.configure_adapter("holehe", enabled=False)
    case = make_case(engine)
    t = engine.add_target(case.id, "email", "a@example.org")
    with pytest.raises(AuthorizationDenied, match="deaktiviert"):
        engine.run_query(case.id, "holehe", t.id, confirmation=confirm(t.value))
