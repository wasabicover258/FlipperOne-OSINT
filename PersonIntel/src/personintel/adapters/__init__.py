"""Die zehn voneinander unabhaengigen Connectoren."""

from .babelstreet import BabelStreetAdapter
from .base import (Adapter, AdapterState, AdapterStatus, Capability, ConfigField, ConfigValidation,  # noqa: F401
                   InstallInfo, RawResult)
from .holehe import HoleheAdapter
from .ignorant import IgnorantAdapter
from .mosint import MosintAdapter
from .mrholmes import MrHolmesAdapter
from .phoneinfoga import PhoneInfogaAdapter
from .pipl import PiplAdapter
from .shadowdragon import ShadowDragonAdapter
from .sherlock import SherlockAdapter
from .spokeo import SpokeoAdapter

#: Reihenfolge = Reihenfolge im Dashboard
BUILTIN_ADAPTERS = (
    HoleheAdapter, MosintAdapter, SherlockAdapter, PhoneInfogaAdapter, IgnorantAdapter, MrHolmesAdapter,
    PiplAdapter, SpokeoAdapter, ShadowDragonAdapter, BabelStreetAdapter,
)
