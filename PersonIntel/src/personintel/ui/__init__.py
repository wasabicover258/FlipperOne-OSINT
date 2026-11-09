"""Grafische Oberflaeche (PySide6).

Die Oberflaeche ist vollstaendig von :class:`personintel.core.engine.Engine` getrennt: sie liest und
schreibt ausschliesslich ueber die Engine-Fassade. Einzelne Seiten sind austauschbar bzw. per
``PluginRegistry.register_page`` erweiterbar (siehe docs/FUSION.md).
"""
