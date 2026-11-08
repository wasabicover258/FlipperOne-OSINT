"""PersonIntel - eigenstaendiges OSINT-Modul fuer journalistische Personenrecherche.

Die stabile Paketschnittstelle fuer eine spaetere Integration ist
:mod:`personintel.api` (siehe docs/FUSION.md). Alles, was dort nicht
re-exportiert wird, gilt als intern.
"""

__version__ = "0.1.0"

#: Version des Austausch-/Ergebnisformats (JSON). Major-Aenderungen sind inkompatibel.
RESULT_SCHEMA_VERSION = "1.0"
EXCHANGE_FORMAT = "personintel.case"
