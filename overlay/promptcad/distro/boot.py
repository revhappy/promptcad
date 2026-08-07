"""Deferred startup for the PromptCAD distribution layer.

Called from the tail of InitGui.py. At that moment the main window object
exists but its event loop does not, and anything touching toolbars or docks
before the loop starts is thrown away when FreeCAD builds its own - so this
polls for readiness first, exactly as the addon's own startup module does.
"""

from __future__ import annotations

from ..ui.qt import QtCore

# The addon's startup module arms a 500ms timer to install its toolbar. We wait
# a little longer so that toolbar exists when the shell looks for it - but the
# shell copes with its absence too, because relying on another module's timer
# would be fragile.
_INTERVAL_MS = 900
_MAX_ATTEMPTS = 40  # ~36s, then give up rather than poll for the whole session

_timer = None
_started = False
_attempts = 0


def install() -> None:
    """Arm the deferred start. Safe to call more than once."""
    global _timer
    if _timer is not None or _started:
        return
    _timer = QtCore.QTimer()
    _timer.timeout.connect(_try_start)
    _timer.start(_INTERVAL_MS)


def _log(message: str) -> None:
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(message + "\n")
    except Exception:
        pass


def _warn(message: str) -> None:
    try:
        import FreeCAD

        FreeCAD.Console.PrintWarning(message + "\n")
    except Exception:
        pass


def _main_window():
    try:
        import FreeCADGui as Gui

        return Gui.getMainWindow()
    except Exception:
        return None


def _try_start() -> None:
    global _started, _attempts

    _attempts += 1
    window = _main_window()
    ready = window is not None and window.property("eventLoop")

    if not ready:
        if _attempts >= _MAX_ATTEMPTS:
            _stop_timer()
            _warn("PromptCAD shell gave up waiting for the main window.")
        return

    _stop_timer()
    _started = True

    # Each half is independent: a model that cannot be found should not cost
    # the user their window layout, and vice versa.
    try:
        from . import models

        status = models.adopt()
        if status:
            _log(status)
    except Exception as exc:
        _warn(f"PromptCAD could not look for local models: {exc}")

    try:
        from . import panel_models

        problem = panel_models.install()
        if problem:
            _warn(problem)
    except Exception as exc:
        _warn(f"PromptCAD could not extend the model dropdown: {exc}")

    try:
        from . import shell

        shell.install()
    except Exception as exc:
        _warn(f"PromptCAD could not apply its window layout: {exc}")


def _stop_timer() -> None:
    global _timer
    if _timer is not None:
        _timer.stop()
        _timer = None
