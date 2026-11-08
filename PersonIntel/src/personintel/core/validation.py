"""Strikte Eingabevalidierung: genau *eine* Kennung pro Abfrage.

Das ist Teil der Recherchekontrolle: Listen, Platzhalter und Massenabfragen
werden bereits hier abgewiesen.
"""

from __future__ import annotations

import re

from .errors import ValidationError
from .models import QueryKind

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")
_PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")

MAX_NAME_LEN = 100


def normalize_phone(value: str) -> str:
    """Normalisiert auf E.164-aehnliche Form ``+<Laendervorwahl><Nummer>``."""
    v = re.sub(r"[ \-().\/]", "", (value or "").strip())
    if not _PHONE_RE.match(v):
        raise ValidationError(
            "Telefonnummer muss mit Laendervorwahl angegeben werden (z. B. +4989123456).")
    try:
        import phonenumbers

        parsed = phonenumbers.parse(v, None)
        if not phonenumbers.is_possible_number(parsed):
            raise ValidationError("Telefonnummer ist laut libphonenumber nicht moeglich.")
    except ValidationError:
        raise
    except Exception:  # phonenumbers fehlt / Parse-Fehler: Regex-Pruefung genuegt dann
        pass
    return v


def normalize_target(kind: QueryKind | str, value: str) -> str:
    kind = QueryKind(kind)
    v = (value or "").strip()
    if not v:
        raise ValidationError("Leere Kennung.")
    if any(c in v for c in "\n\r\t"):
        raise ValidationError("Nur eine Kennung pro Abfrage erlaubt (keine Listen).")
    if kind is QueryKind.EMAIL:
        if not _EMAIL_RE.match(v):
            raise ValidationError("Keine einzelne, gueltige E-Mail-Adresse.")
        return v.lower()
    if kind is QueryKind.USERNAME:
        if "{" in v or "?" in v or "*" in v:
            raise ValidationError("Platzhalter/Mustersuchen sind nicht erlaubt.")
        if not _USERNAME_RE.match(v):
            raise ValidationError("Benutzername: nur Buchstaben, Ziffern, '.', '_' und '-' (max. 64).")
        return v
    if kind is QueryKind.PHONE:
        return normalize_phone(v)
    if kind is QueryKind.NAME:
        if len(v) < 2 or len(v) > MAX_NAME_LEN or not all(c.isalpha() or c in " .'-" for c in v):
            raise ValidationError("Name: 2-100 Zeichen, nur Buchstaben, Leerzeichen, '.', ''' und '-'.")
        return " ".join(v.split())
    if kind is QueryKind.REPORT_FILE:
        return v
    raise ValidationError(f"Unbekannte Kennungsart: {kind}")
