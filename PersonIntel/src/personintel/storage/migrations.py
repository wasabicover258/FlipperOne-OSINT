"""Schema-Migrationen (``PRAGMA user_version``). Nur anhaengen, nie aendern."""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE cases (
            id         TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload    TEXT NOT NULL
        );
        -- Generische Datensaetze eines Falls: target | source | finding | query | event | node | edge
        CREATE TABLE records (
            id      TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            kind    TEXT NOT NULL,
            ts      TEXT NOT NULL,
            ref     TEXT,
            payload TEXT NOT NULL
        );
        CREATE INDEX idx_records_case_kind ON records(case_id, kind, ts);
        -- Append-only, hash-verkettet; enthaelt keine Rechercheinhalte
        CREATE TABLE audit (
            seq       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            case_id   TEXT,
            action    TEXT NOT NULL,
            payload   TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash      TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE INDEX idx_audit_case ON audit(case_id);
        CREATE INDEX idx_records_ref ON records(ref);
        """,
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Wendet fehlende Migrationen an und liefert die neue Version."""
    version = current_version(conn)
    for ver, sql in MIGRATIONS:
        if ver > version:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {int(ver)}")
            conn.commit()
            version = ver
    return version
