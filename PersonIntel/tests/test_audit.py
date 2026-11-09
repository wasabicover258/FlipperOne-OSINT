"""Audit-Protokoll: Hash-Kette, Manipulationserkennung, keine Klartext-Kennungen."""

from personintel.security.audit import GENESIS
from conftest import make_case


def test_chain_links_entries_and_detects_tampering(engine):
    case = make_case(engine)
    for i in range(3):
        engine.audit.record("test.action", case_id=case.id, detail={"i": i})
    entries = engine.audit.entries()
    assert entries[0].prev_hash == GENESIS
    for a, b in zip(entries, entries[1:]):
        assert b.prev_hash == a.hash
    assert engine.audit.verify() == (True, None)

    victim = entries[-1].seq
    engine.repo.conn.execute("UPDATE audit SET action='geschoent' WHERE seq=?", (victim,))
    engine.repo.conn.commit()
    ok, bad = engine.audit.verify()
    assert ok is False and bad == victim


def test_deleting_an_entry_breaks_the_chain(engine):
    case = make_case(engine)
    engine.audit.record("a", case_id=case.id)
    engine.audit.record("b", case_id=case.id)
    engine.audit.record("c", case_id=case.id)
    seqs = [e.seq for e in engine.audit.entries()]
    engine.repo.conn.execute("DELETE FROM audit WHERE seq=?", (seqs[-2],))
    engine.repo.conn.commit()
    ok, _ = engine.audit.verify()
    assert ok is False
    engine.audit.rechain()
    assert engine.audit.verify() == (True, None)


def test_secrets_and_identifiers_never_enter_the_log(engine):
    case = make_case(engine)
    engine.audit.record("x", case_id=case.id,
                        detail={"api_key": "SECRET", "auth_token": "SECRET2", "passphrase": "SECRET3", "ok": "sichtbar"})
    body = engine.audit.entries(case.id)[-1].detail
    assert body["ok"] == "sichtbar"
    assert not any("SECRET" in str(v) for v in body.values())


def test_target_ref_is_stable_pseudonym(engine):
    a = engine.audit.target_ref("Person@Example.org")
    b = engine.audit.target_ref("person@example.org")
    c = engine.audit.target_ref("andere@example.org")
    assert a == b and a != c and len(a) == 16
    assert "example.org" not in a
