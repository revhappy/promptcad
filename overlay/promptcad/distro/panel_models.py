"""Put every local model in the panel's own dropdown.

Upstream shows a single entry for the local provider - the basename of the one
.gguf recorded in Settings - because the addon has no notion of a model
library. That means switching models is a trip into a settings dialog and a
file browser, which is the wrong shape for something you change while you are
working.

This replaces that one entry with every complete .gguf discovery found, so the
front dropdown *is* the model list. Choosing one writes the path straight to
the config, exactly as the Settings file picker would have.

Implemented by wrapping two methods on the panel class rather than editing it,
because the addon stays byte-identical upstream. Both wrappers delegate to the
original for every provider except the local one, and both are wrapped in
enough defensiveness that an upstream signature change degrades to stock
behaviour instead of a broken panel.
"""

from __future__ import annotations

from typing import Optional

from . import models

_BROWSE = "__promptcad_get_more__"
_MODELS_URL = "https://alphaintellabs.com/promptcad"
_FLAG = "_promptcad_model_list_installed"


def _placeholder() -> str:
    """Upstream's 'nothing chosen yet' label, if we can read it."""
    try:
        from ..ui import panel as panel_module

        return getattr(panel_module, "_NO_LOCAL_MODEL", "(choose a model…)")
    except Exception:
        return "(choose a model…)"


# --------------------------------------------------------------------------- #
# Replacements
# --------------------------------------------------------------------------- #
def _populate_models(self) -> None:
    """List every discovered local model; defer to upstream for cloud providers."""
    try:
        provider_id = self.provider_combo.currentData()
    except Exception:
        provider_id = None

    if provider_id != "machine":
        self._promptcad_populate_original()
        return

    try:
        from ..ui.qt import QtCore

        combo = self.model_combo
        current = self.cfg.machine_model_path()

        found = [item for item in models.scan_cached() if item.complete]
        # Recommended first, then recognised, then whatever else is on disk -
        # the same ordering the automatic pick uses, so the top entry is the
        # one PromptCAD would have chosen anyway.
        found.sort(key=lambda item: (
            0 if item.recommended else (1 if item.model_id else 2),
            item.label.lower(),
        ))

        combo.blockSignals(True)
        combo.clear()

        if not found:
            combo.addItem(_placeholder(), "")
        for item in found:
            combo.addItem(f"{item.label}  ·  {item.size_label}", str(item.path))
            combo.setItemData(combo.count() - 1, str(item.path),
                              QtCore.Qt.ToolTipRole)

        combo.insertSeparator(combo.count())
        combo.addItem("Get more models…", _BROWSE)

        index = combo.findData(current) if current else -1
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)

        if found:
            combo.setToolTip(
                f"{len(found)} local model(s) found. "
                "Downloads, this app's models folder and LM Studio are all searched.")
        else:
            combo.setToolTip(
                "No .gguf found. Choose 'Get more models…', or drop one in the "
                "app's models folder.")
        combo.blockSignals(False)
    except Exception:
        # Never leave the panel with an empty model box.
        try:
            self._promptcad_populate_original()
        except Exception:
            pass


def _on_model_changed(self, text) -> None:
    """Persist the chosen .gguf path instead of ignoring local selections."""
    try:
        provider_id = self.provider_combo.currentData()
    except Exception:
        provider_id = None

    if provider_id != "machine":
        self._promptcad_on_model_original(text)
        return

    if getattr(self, "_loading", False):
        return

    try:
        data = self.model_combo.currentData()
    except Exception:
        return

    if data == _BROWSE:
        _open_models_page(self)
        return
    if data:
        self.cfg.set_machine_model_path(data)


def _open_models_page(panel) -> None:
    """Open the download page, then put the dropdown back where it was.

    'Get more models…' is an action wearing a menu item's clothes, so it must
    not be left sitting there looking like the current selection.
    """
    try:
        from ..ui.qt import QtCore, QtGui

        QtGui.QDesktopServices.openUrl(QtCore.QUrl(_MODELS_URL))
    except Exception:
        pass

    try:
        combo = panel.model_combo
        current = panel.cfg.machine_model_path()
        combo.blockSignals(True)
        index = combo.findData(current) if current else 0
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #
def install() -> Optional[str]:
    """Wrap the panel class, and refresh any panel that is already open."""
    try:
        from ..ui import panel as panel_module
    except Exception as exc:
        return f"PromptCAD could not extend the model dropdown: {exc}"

    cls = getattr(panel_module, "GPTPanel", None)
    if cls is None:
        return "PromptCAD could not find the panel class to extend."
    if getattr(cls, _FLAG, False):
        return None

    if not (hasattr(cls, "_populate_models") and hasattr(cls, "_on_model_changed")):
        return "PromptCAD left the model dropdown alone: upstream panel has changed."

    cls._promptcad_populate_original = cls._populate_models
    cls._promptcad_on_model_original = cls._on_model_changed
    cls._populate_models = _populate_models
    cls._on_model_changed = _on_model_changed
    setattr(cls, _FLAG, True)

    _refresh_open_panel(cls)
    return None


def _refresh_open_panel(cls) -> None:
    """The addon may have opened the panel before we got here."""
    try:
        import FreeCADGui as Gui

        from ..ui.qt import QtWidgets

        window = Gui.getMainWindow()
        if window is None:
            return
        dock = window.findChild(QtWidgets.QDockWidget, "PromptCADDock")
        if dock is None:
            return
        widget = dock.widget()
        if isinstance(widget, cls):
            widget._populate_models()
    except Exception:
        pass
