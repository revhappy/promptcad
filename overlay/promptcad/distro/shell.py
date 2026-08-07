"""The prompt-first shell: PromptCAD's window, not FreeCAD's.

Stock FreeCAD opens with eight or nine toolbars and something like eighty
icons. That is the right default for a CAD program you drive with a mouse, and
the wrong one for a CAD program you drive by describing what you want - the
prompt ends up as a narrow strip beside a wall of buttons it does not need.

So PromptCAD starts minimal: its own toolbar plus File, the prompt panel given
real width, and everything else hidden behind one button. Nothing is removed -
"All tools" restores the full FreeCAD chrome, and the choice is remembered.

This lives in the PromptCAD distribution layer rather than in the addon
because it is a decision about *this product's* window. The addon is also
expected to work as a well-behaved guest inside someone's existing FreeCAD,
where rearranging their toolbars would be obnoxious.
"""

from __future__ import annotations

import os

from ..ui.qt import QAction, QtCore, QtGui, QtWidgets

_PARAMS = "User parameter:BaseApp/Preferences/Mod/PromptCAD"
_KEY = "shell_minimal"

_ACTION_NAME = "PromptCAD_ToggleToolsAction"
_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "icons", "promptcad-tools.svg")

# Kept visible in minimal mode. Our own toolbar has to stay - it carries the
# button that turns the others back on, and stranding the user with no way out
# would be a trap. File earns its place because new/open/save are not
# discoverable from a prompt.
_KEEP_VISIBLE = {"PromptCADGlobalToolbar", "File"}

_PANEL_DOCK = "PromptCADDock"
_MIN_PANEL_WIDTH = 420
_PANEL_FRACTION = 0.34

# Hiding toolbars is only half the job. FreeCAD lays the survivors out on the
# rows they were docked to, so File and the PromptCAD bar sat on two separate
# rows holding six icons between them - two full rows of chrome for almost
# nothing. Pulling them onto one row and shrinking the icons reclaims the rest
# of the vertical space, which is the point of minimal mode.
_MINIMAL_ICON_PX = 18
_original_icon_size = None


# --------------------------------------------------------------------------- #
# Preference
# --------------------------------------------------------------------------- #
def _params():
    try:
        import FreeCAD as App

        return App.ParamGet(_PARAMS)
    except Exception:
        return None


def is_minimal() -> bool:
    """Minimal is the default: this is what makes PromptCAD not look like FreeCAD."""
    params = _params()
    if params is None:
        return True
    return params.GetBool(_KEY, True)


def set_minimal(value: bool) -> None:
    params = _params()
    if params is not None:
        params.SetBool(_KEY, bool(value))


# --------------------------------------------------------------------------- #
# Applying the layout
# --------------------------------------------------------------------------- #
def _main_window():
    try:
        import FreeCADGui as Gui

        return Gui.getMainWindow()
    except Exception:
        return None


def apply(minimal: bool | None = None, widen: bool = False) -> None:
    """Show or hide FreeCAD's toolbars to match the current mode."""
    mw = _main_window()
    if mw is None:
        return
    minimal = is_minimal() if minimal is None else minimal

    for toolbar in mw.findChildren(QtWidgets.QToolBar):
        name = toolbar.objectName()
        if not name:
            continue
        if minimal and name not in _KEEP_VISIBLE:
            toolbar.setVisible(False)
        elif not minimal:
            toolbar.setVisible(True)

    _ensure_toggle_action(mw)
    _compact_toolbar_area(mw, minimal)

    if widen and minimal:
        _widen_panel(mw)


def _compact_toolbar_area(mw, minimal: bool) -> None:
    """Collapse the surviving toolbars onto a single, shorter row."""
    global _original_icon_size

    try:
        if minimal:
            if _original_icon_size is None:
                _original_icon_size = mw.iconSize()
            mw.setIconSize(QtCore.QSize(_MINIMAL_ICON_PX, _MINIMAL_ICON_PX))

            # Remove the break before EVERY top-area toolbar, not just the ones
            # we keep. A break sitting before a hidden toolbar still splits the
            # row, so clearing only the survivors' breaks leaves them stranded
            # on separate rows - which is exactly what the first attempt did.
            # Hidden toolbars occupy no space, so this is safe.
            for toolbar in mw.findChildren(QtWidgets.QToolBar):
                if toolbar.objectName():
                    mw.removeToolBarBreak(toolbar)
        elif _original_icon_size is not None:
            mw.setIconSize(_original_icon_size)
            # Breaks are deliberately not restored: Qt exposes no way to read
            # which toolbars originally had one, and FreeCAD re-lays out the
            # whole area on the next workbench activation anyway.
    except Exception:
        # Purely cosmetic - never let it cost the user their toolbars.
        pass


def _widen_panel(mw) -> None:
    """Give the prompt a share of the window worth typing into.

    Only on the first application - after that the user's own drag wins, and
    re-imposing a width on every workbench switch would fight them.
    """
    dock = mw.findChild(QtWidgets.QDockWidget, _PANEL_DOCK)
    if dock is None:
        return
    try:
        target = max(_MIN_PANEL_WIDTH, int(mw.width() * _PANEL_FRACTION))
        mw.resizeDocks([dock], [target], QtCore.Qt.Horizontal)
    except Exception:
        # resizeDocks is best-effort; a failure here is cosmetic.
        pass


# --------------------------------------------------------------------------- #
# The toggle
# --------------------------------------------------------------------------- #
def toggle() -> None:
    """Flip between the minimal shell and full FreeCAD."""
    now_minimal = not is_minimal()
    set_minimal(now_minimal)
    apply(now_minimal, widen=now_minimal)
    _sync_action_state()


def _ensure_toggle_action(mw) -> None:
    """Put the toggle on PromptCAD's toolbar, creating that bar if needed."""
    existing = mw.findChild(QAction, _ACTION_NAME)
    if existing is not None:
        _sync_action_state(existing)
        return

    toolbar = mw.findChild(QtWidgets.QToolBar, "PromptCADGlobalToolbar")
    if toolbar is None:
        # The user turned the addon's global toolbar off, or it has not been
        # installed yet. Own a small one so the escape hatch always exists.
        toolbar = QtWidgets.QToolBar("PromptCAD shell", mw)
        toolbar.setObjectName("PromptCADShellToolbar")
        mw.addToolBar(QtCore.Qt.TopToolBarArea, toolbar)
        _KEEP_VISIBLE.add("PromptCADShellToolbar")
        toolbar.setVisible(True)

    icon = QtGui.QIcon(_ICON) if os.path.exists(_ICON) else QtGui.QIcon()
    action = QAction(icon, "All tools", mw)
    action.setObjectName(_ACTION_NAME)
    action.setCheckable(True)
    action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+T"))
    action.triggered.connect(lambda *_a: toggle())
    toolbar.addAction(action)
    _sync_action_state(action)


def _sync_action_state(action=None) -> None:
    """Keep the button's checked state and tooltip honest."""
    if action is None:
        mw = _main_window()
        if mw is None:
            return
        action = mw.findChild(QAction, _ACTION_NAME)
    if action is None:
        return
    minimal = is_minimal()
    action.setChecked(not minimal)
    action.setToolTip(
        "Show every FreeCAD toolbar (Ctrl+Shift+T)" if minimal
        else "Back to the minimal PromptCAD layout (Ctrl+Shift+T)")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def install() -> None:
    """Apply the shell now and re-apply whenever the workbench changes.

    FreeCAD rebuilds the toolbar area on every workbench activation, which
    restores everything it thinks should be visible - so a one-shot hide does
    not survive the first workbench switch.
    """
    mw = _main_window()
    if mw is None:
        return

    apply(widen=True)

    try:
        mw.workbenchActivated.connect(_on_workbench_activated)
    except AttributeError:
        pass

    # The signal alone is not enough. FreeCAD restores toolbar visibility from
    # its own saved state during startup, and that can land *after* we have
    # hidden things - with no further activation signal to react to, so a
    # one-shot hide silently comes undone. Measured on a cold start: the
    # layout was applied, the panel was widened, and every toolbar was visible
    # again by the time the window settled. So re-assert a few times across
    # the startup window and then stop.
    for delay in (1200, 3000, 6000):
        QtCore.QTimer.singleShot(delay, _reassert)


def _reassert() -> None:
    """Re-apply the layout during startup, but never fight the user.

    Only runs while minimal mode is on: if the user has since pressed
    "All tools", these pending timers must not claw the toolbars back.
    """
    if is_minimal():
        apply(True)


def _on_workbench_activated(*_args) -> None:
    apply()
    # FreeCAD's own toolbar setup can run after this slot, so claim the layout
    # once more at the end of the current event cycle.
    QtCore.QTimer.singleShot(0, lambda: apply())
