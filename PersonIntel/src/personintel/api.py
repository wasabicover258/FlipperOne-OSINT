"""Stabile Python-Schnittstelle fuer die Einbindung in eine Hauptanwendung.

Beispiel::

    from personintel.api import PersonIntel, AppPaths
    pi = PersonIntel(AppPaths(data_dir=Path("..."), config_dir=Path("...")))
    case = pi.create_case("Recherche X")

Alles, was hier exportiert wird, folgt der Versionierung des Pakets (siehe docs/FUSION.md).
"""

from . import EXCHANGE_FORMAT, RESULT_SCHEMA_VERSION, __version__  # noqa: F401
from .adapters.base import (Adapter, AdapterState, AdapterStatus, Capability, ConfigField,  # noqa: F401
                            ConfigValidation, InstallInfo, RawResult)
from .core.config import AppPaths, Limits, Settings  # noqa: F401
from .core.engine import Engine, TimelineEntry  # noqa: F401
from .core.errors import *  # noqa: F401,F403
from .core.models import (Case, Evidence, Finding, FindingStatus, Purpose, QueryKind, QueryMode,  # noqa: F401
                          QueryRecord, QueryState, ReviewState, Source, Target)
from .core.plugins import PageSpec, PluginRegistry  # noqa: F401
from .exchange.schema import export_case, import_case, validate_bundle  # noqa: F401
from .reports.export import Report, ReportOptions  # noqa: F401
from .security.authorization import ActiveConfirmation  # noqa: F401

#: Alias: die Fassade der Anwendung
PersonIntel = Engine
