"""Plugin-Registrierung fuer Adapter und UI-Seiten.

Eine Hauptanwendung kann Adapter/Seiten per Code registrieren (``registry.register_adapter``) oder
Drittpakete ueber Entry-Points der Gruppen ``personintel.adapters`` und ``personintel.ui_pages``
einbinden. Es gibt keine Abhaengigkeit von einer bestimmten Hauptanwendung.
"""

from __future__ import annotations

import importlib.metadata as md
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type

from ..adapters import BUILTIN_ADAPTERS
from ..adapters.base import Adapter
from .errors import PersonIntelError

ADAPTER_GROUP = "personintel.adapters"
UI_GROUP = "personintel.ui_pages"


@dataclass
class PageSpec:
    id: str
    title: str
    factory: Callable[..., Any]   # factory(engine) -> QWidget
    order: int = 100


class PluginRegistry:
    def __init__(self) -> None:
        self._adapter_classes: dict[str, Type[Adapter]] = {}
        self._pages: dict[str, PageSpec] = {}

    # ---- Adapter ----------------------------------------------------------
    def register_adapter(self, cls: Type[Adapter], *, replace: bool = False) -> None:
        if not (isinstance(cls, type) and issubclass(cls, Adapter)):
            raise PersonIntelError("Adapter muss von personintel.adapters.base.Adapter erben.")
        if not cls.id or not cls.name:
            raise PersonIntelError("Adapter braucht 'id' und 'name'.")
        if cls.id in self._adapter_classes and not replace:
            raise PersonIntelError(f"Adapter '{cls.id}' ist bereits registriert.")
        self._adapter_classes[cls.id] = cls

    def adapter_classes(self) -> list[Type[Adapter]]:
        return list(self._adapter_classes.values())

    def adapter_class(self, adapter_id: str) -> Optional[Type[Adapter]]:
        return self._adapter_classes.get(adapter_id)

    def load_builtin(self) -> None:
        for cls in BUILTIN_ADAPTERS:
            if cls.id not in self._adapter_classes:
                self.register_adapter(cls)

    def load_entry_points(self) -> list[str]:
        """Laedt Drittanbieter-Plugins; fehlerhafte Plugins werden gemeldet, nicht fatal."""
        problems: list[str] = []
        try:
            eps = md.entry_points()
            group = eps.select(group=ADAPTER_GROUP) if hasattr(eps, "select") else eps.get(ADAPTER_GROUP, [])
        except Exception as exc:  # pragma: no cover
            return [f"entry_points: {exc}"]
        for ep in group:
            try:
                self.register_adapter(ep.load())
            except Exception as exc:
                problems.append(f"Plugin {ep.name}: {exc}")
        try:
            group = eps.select(group=UI_GROUP) if hasattr(eps, "select") else eps.get(UI_GROUP, [])
            for ep in group:
                try:
                    spec = ep.load()
                    self.register_page(spec() if callable(spec) and not isinstance(spec, PageSpec) else spec)
                except Exception as exc:
                    problems.append(f"UI-Plugin {ep.name}: {exc}")
        except Exception:  # pragma: no cover
            pass
        return problems

    # ---- UI-Seiten ----------------------------------------------------------
    def register_page(self, spec: PageSpec, *, replace: bool = False) -> None:
        if spec.id in self._pages and not replace:
            raise PersonIntelError(f"Seite '{spec.id}' ist bereits registriert.")
        self._pages[spec.id] = spec

    def pages(self) -> list[PageSpec]:
        return sorted(self._pages.values(), key=lambda p: (p.order, p.id))
