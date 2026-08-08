"""A construction grid that is simply always there.

An empty 3D view with nothing in it is a void: no sense of scale, no ground
plane, no way to tell a 5mm part from a 500mm one until something else is on
screen to compare it with. Every CAD program answers that with a grid.

FreeCAD's own grid belongs to Draft. It is drawn by that workbench's view
machinery and exists while that workbench is loaded, which makes it the wrong
tool here twice over: PromptCAD opens in Part Design, and loading Draft to
borrow its grid would pull in a workbench's worth of toolbars that
:mod:`.shell` then has to hide again on every activation.

So this draws its own, straight into the view's scene graph with Coin. That is
a few dozen lines, it owes nothing to which workbench is active, and it is
runtime-only - the node is attached to the *view*, so nothing about it is
written into the user's .FCStd.

Two line weights, as on a drawing sheet: a fine line at every spacing and a
heavier one every tenth, both close enough to the background to read as paper
rather than as geometry. A grid that competes with the part is worse than no
grid at all.
"""

from __future__ import annotations

from ..ui.qt import QtWidgets

# Millimetres. 200mm of grid at 10mm spacing covers the desk-sized parts
# PromptCAD is actually asked for, without the far edge of it dominating a
# zoomed-out view.
_SPACING = 10.0
_EXTENT = 200.0
_EVERY = 10

# Matched to theme/PromptCAD.yaml's grid colours. These are literals rather
# than a read of the preference because Coin wants floats in 0..1 and the
# conversion is not worth a dependency between the two.
_FINE = (0.145, 0.145, 0.169)
_BOLD = (0.208, 0.208, 0.239)

_MARK = "PromptCADGrid"
_installed = False


def _log(message: str) -> None:
    try:
        import FreeCAD

        FreeCAD.Console.PrintWarning(message + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# The node
# --------------------------------------------------------------------------- #
def _lines(coin, color, pairs):
    """One SoSeparator holding every segment of a single weight."""
    sep = coin.SoSeparator()

    material = coin.SoBaseColor()
    material.rgb.setValue(*color)
    sep.addChild(material)

    points = []
    for (x1, y1), (x2, y2) in pairs:
        points.append((x1, y1, 0.0))
        points.append((x2, y2, 0.0))

    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), points)
    sep.addChild(coords)

    lines = coin.SoLineSet()
    lines.numVertices.setValues(0, len(pairs), [2] * len(pairs))
    sep.addChild(lines)
    return sep


def _build(coin):
    """The whole grid: fine segments, then the heavier every-tenth ones."""
    fine, bold = [], []

    steps = int(_EXTENT / _SPACING)
    for step in range(-steps, steps + 1):
        offset = step * _SPACING
        bucket = bold if step % _EVERY == 0 else fine
        bucket.append(((-_EXTENT, offset), (_EXTENT, offset)))
        bucket.append(((offset, -_EXTENT), (offset, _EXTENT)))

    root = coin.SoSeparator()
    root.setName(_MARK)

    # The grid must never be pickable: clicking empty space to clear a
    # selection has to keep working, and a grid line under the cursor would
    # otherwise swallow that click.
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    root.addChild(pick)

    # Unlit, so the grid does not shade with the camera the way a solid does.
    lighting = coin.SoLightModel()
    lighting.model = coin.SoLightModel.BASE_COLOR
    root.addChild(lighting)

    root.addChild(_lines(coin, _FINE, fine))
    root.addChild(_lines(coin, _BOLD, bold))
    return root


# --------------------------------------------------------------------------- #
# Attaching
# --------------------------------------------------------------------------- #
def _has_grid(scene) -> bool:
    for index in range(scene.getNumChildren()):
        if scene.getChild(index).getName() == _MARK:
            return True
    return False


def decorate(view=None) -> None:
    """Put the grid in ``view``, or in the active view. Safe to repeat."""
    try:
        from pivy import coin
        import FreeCADGui as Gui
    except Exception:
        return

    try:
        if view is None:
            document = Gui.ActiveDocument
            if document is None:
                return
            view = document.ActiveView
        scene = view.getSceneGraph()
    except Exception:
        return

    try:
        if _has_grid(scene):
            return
        scene.addChild(_build(coin))
    except Exception as exc:
        _log(f"PromptCAD could not draw its grid: {exc}")


def _on_window_activated(*_args) -> None:
    decorate()


def install() -> None:
    """Draw the grid now, and in every 3D view opened afterwards."""
    global _installed
    if _installed:
        return

    try:
        import FreeCADGui as Gui

        window = Gui.getMainWindow()
    except Exception:
        return
    if window is None:
        return

    _installed = True
    decorate()

    # A new document means a new view with its own scene graph, and there is no
    # Python-side "view created" signal to hang this on. The MDI area's own
    # activation signal is the closest thing that is already there, and it
    # fires for exactly the case that matters - a view becoming the one the
    # user is looking at.
    area = window.findChild(QtWidgets.QMdiArea)
    if area is not None:
        try:
            area.subWindowActivated.connect(_on_window_activated)
        except Exception:
            pass
