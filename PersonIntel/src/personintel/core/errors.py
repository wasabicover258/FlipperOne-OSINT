"""Fehlerklassen. Alle Fehler erben von PersonIntelError."""

from __future__ import annotations


class PersonIntelError(Exception):
    """Basisklasse."""


class ValidationError(PersonIntelError):
    """Eingabe ist ungueltig (z. B. keine einzelne, wohlgeformte Kennung)."""


class AuthorizationDenied(PersonIntelError):
    """Die Zweck-/Berechtigungspruefung hat eine Abfrage abgelehnt."""


class UnauthorizedQueryError(PersonIntelError):
    """Ein Adapter wurde ohne gueltige Autorisierung aufgerufen."""


class AdapterError(PersonIntelError):
    """Abfrage ist fehlgeschlagen (transparent an den Nutzer weitergeben)."""


class AdapterNotAvailable(AdapterError):
    """Funktion ist nicht verfuegbar; ``requirement`` nennt die konkrete Voraussetzung."""

    def __init__(self, message: str, requirement: str = ""):
        super().__init__(message)
        self.requirement = requirement


class QueryCancelled(AdapterError):
    """Abfrage wurde vom Nutzer abgebrochen."""


class StorageError(PersonIntelError):
    """Fehler in der Persistenzschicht."""


class LockedError(StorageError):
    """Datenbank/Credential-Store ist verschluesselt und noch gesperrt."""


class ExchangeError(PersonIntelError):
    """Import/Export-Fehler (Format, Version, ID-Konflikte)."""


class CredentialError(PersonIntelError):
    """Fehler beim Zugriff auf Zugangsdaten."""
