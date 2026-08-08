"""Derive the PromptCAD theme into a staged application tree.

FreeCAD 1.x splits a theme in two. The stylesheet (``FreeCAD.qss``) is written
against ``@Token`` names and carries no colours of its own; a YAML file under
``Gui/Stylesheets/parameters`` answers those tokens. Anything the stylesheet
cannot reach - the 3D view background, the colour a new solid is drawn in, the
selection highlight - is an ordinary preference. So a theme here is one palette
file plus one FCParameters document, and this script puts both in place.

The FCParameters document is derived from FreeCAD's own dark pack rather than
written out in full. That pack sets a few hundred values, most of them syntax
colours for the Python editor and per-workbench defaults that simply need to be
*a* dark theme's values; forking all of it into this repository would mean
maintaining FreeCAD's choices forever and silently drifting from them at every
upgrade. Reading it at build time and overriding the forty or so entries that
carry PromptCAD's identity keeps the diff to the part we actually decided.

The result is written where the launcher looks for it. ``PromptCAD.cs`` seeds a
brand-new profile by copying a pack file over as the initial ``user.cfg``, so
the theme is present in the very first frame the user sees rather than being
applied afterwards while they watch the window repaint.
"""

from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# The pack we derive from. FreeCAD ships it; we do not vendor a copy.
_BASE_PACK = Path("data/Gui/PreferencePacks/FreeCAD Dark/FreeCAD Dark.cfg")

_DEST_PACK = Path("data/Gui/PreferencePacks/PromptCAD/PromptCAD.cfg")
_DEST_YAML = Path("data/Gui/Stylesheets/parameters/PromptCAD.yaml")


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
def packed(hex_rgb: str, alpha: int = 0xFF) -> int:
    """``#rrggbb`` as the 0xRRGGBBAA integer FreeCAD stores colours in.

    Verified against the pack we derive from: FreeCAD Dark's 3D background is
    522133503, which is 0x1F1F1FFF - the #1f1f1f its own documentation quotes.
    """
    value = hex_rgb.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_rgb!r}")
    return (int(value, 16) << 8) | (alpha & 0xFF)


# The palette, kept in step with theme/PromptCAD.yaml and with the app mock on
# alphaintellabs.com/promptcad. Where a colour appears in both files it is
# because the stylesheet and the 3D view are painted by different machinery,
# not because one of them is a stray copy.
_VIEW_BG = "#0E0E10"
_VIEW_GLOW = "#191920"
_SKY = "#38BDF8"
_SKY_DEEP = "#0EA5E9"
_AMBER = "#F59E0B"

# The solid. Steel rather than a colour: on a neutral ground the part should
# read as a machined object, and FreeCAD's stock warm grey reads as unfinished.
_SHAPE_FACE = "#4C5464"
_SHAPE_EDGE = "#A9B2C4"

# The construction grid. Close enough to the ground to read as paper rather
# than as geometry - a grid that competes with the part is worse than no grid.
_GRID_LINE = "#2A2A31"
_GRID_EVERY = 10


# --------------------------------------------------------------------------- #
# FCParameters editing
# --------------------------------------------------------------------------- #
def _group(root: ET.Element, path: tuple[str, ...]) -> ET.Element:
    """Find - or create - the nested ``FCParamGroup`` at ``path``."""
    node = root
    for name in path:
        found = None
        for child in node.findall("FCParamGroup"):
            if child.get("Name") == name:
                found = child
                break
        if found is None:
            found = ET.SubElement(node, "FCParamGroup", {"Name": name})
        node = found
    return node


def _set(group: ET.Element, tag: str, name: str, value: str) -> None:
    """Set one typed entry, replacing any existing entry of the same name.

    FCBool and FCUInt carry their value in a ``Value`` attribute; FCText carries
    it as element text. Getting that backwards produces a file FreeCAD parses
    without complaint and then ignores, so the two shapes are kept apart here
    rather than at every call site.
    """
    for child in list(group):
        if child.tag == tag and child.get("Name") == name:
            group.remove(child)

    if tag == "FCText":
        node = ET.SubElement(group, tag, {"Name": name})
        node.text = value
    else:
        ET.SubElement(group, tag, {"Name": name, "Value": value})


def build_pack(base: Path, dest: Path) -> None:
    """Write the PromptCAD pack, derived from ``base``."""
    tree = ET.parse(base)
    root = tree.getroot()
    prefs = ("Root", "BaseApp", "Preferences")

    # -- Stylesheet -------------------------------------------------------- #
    # "Theme" is what selects the parameters YAML: FreeCAD looks for
    # parameters/<Theme>.yaml. StyleSheet stays FreeCAD's own, because the
    # tokens in it are exactly what our palette answers.
    main = _group(root, prefs + ("MainWindow",))
    _set(main, "FCText", "Theme", "PromptCAD")
    _set(main, "FCText", "StyleSheet", "FreeCAD.qss")
    _set(main, "FCText", "QtStyle", "FreeCAD")
    _set(main, "FCText", "OverlayActiveStyleSheet", "Freecad Overlay.qss")

    # -- FreeCAD's own setup wizard ---------------------------------------- #
    # It runs when General/FirstTime is unset, and its first page is a theme
    # picker. Since this pack *is* the profile a new user starts on, leaving
    # the flag alone means PromptCAD's first frame is a dialog inviting the
    # user to pick a FreeCAD theme, and whatever they pick overrides the one
    # they just installed. The choices it offers all remain in Preferences.
    general = _group(root, prefs + ("General",))
    _set(general, "FCBool", "FirstTime", "0")

    # -- Accent ------------------------------------------------------------ #
    # @AccentColor resolves through this, so a user who picks a different
    # accent in Preferences recolours the theme rather than breaking it.
    themes = _group(root, prefs + ("Themes",))
    _set(themes, "FCUInt", "ThemeAccentColor1", str(packed(_SKY)))
    _set(themes, "FCUInt", "ThemeAccentColor2", str(packed(_SKY_DEEP)))
    _set(themes, "FCUInt", "ThemeAccentColor3", str(packed(_AMBER)))

    # -- The 3D view ------------------------------------------------------- #
    # A flat background is the safe choice and the wrong one: the mock's
    # viewport has a soft lift behind the part, and without it a dark view
    # reads as a hole in the window. FreeCAD's radial gradient does that with
    # BackgroundColor2 at the centre and BackgroundColor3 at the edge.
    view = _group(root, prefs + ("View",))
    _set(view, "FCBool", "Simple", "0")
    _set(view, "FCBool", "Gradient", "1")
    _set(view, "FCBool", "RadialGradient", "1")
    _set(view, "FCBool", "UseBackgroundColorMid", "0")
    _set(view, "FCUInt", "BackgroundColor", str(packed(_VIEW_BG)))
    _set(view, "FCUInt", "BackgroundColor2", str(packed(_VIEW_GLOW)))
    _set(view, "FCUInt", "BackgroundColor3", str(packed(_VIEW_BG)))

    _set(view, "FCUInt", "DefaultShapeColor", str(packed(_SHAPE_FACE)))
    _set(view, "FCUInt", "DefaultShapeLineColor", str(packed(_SHAPE_EDGE)))
    _set(view, "FCUInt", "HighlightColor", str(packed("#7DD3FC")))
    _set(view, "FCUInt", "SelectionColor", str(packed(_SKY)))
    _set(view, "FCUInt", "BoundingBoxColor", str(packed(_SHAPE_EDGE)))

    # -- The grid ---------------------------------------------------------- #
    # An empty 3D view with no grid is a void: nothing says which way the
    # ground plane lies or how big anything is until the first solid appears.
    # The grid is FreeCAD's, from Draft, and "alwaysShowGrid" is what lifts it
    # out of Draft's own edit mode and into the view the user always has.
    draft = _group(root, prefs + ("Mod", "Draft"))
    _set(draft, "FCBool", "grid", "1")
    _set(draft, "FCBool", "alwaysShowGrid", "1")
    _set(draft, "FCBool", "gridBorder", "0")
    _set(draft, "FCBool", "gridShowHuman", "0")
    _set(draft, "FCInt", "gridEvery", str(_GRID_EVERY))
    _set(draft, "FCInt", "gridSize", "200")
    _set(draft, "FCFloat", "gridSpacing", "10.0")
    _set(draft, "FCInt", "gridTransparency", "60")
    _set(draft, "FCUInt", "gridColor", str(packed(_GRID_LINE)))

    dest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest, encoding="UTF-8", xml_declaration=True)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Stage the PromptCAD theme.")
    parser.add_argument("--stage", type=Path, required=True,
                        help="the staged application tree")
    parser.add_argument("--palette", type=Path, required=True,
                        help="theme/PromptCAD.yaml")
    args = parser.parse_args()

    stage = args.stage.resolve()
    base = stage / _BASE_PACK
    if not base.is_file():
        raise SystemExit(f"theme: FreeCAD's dark pack is not staged: {base}")
    if not args.palette.is_file():
        raise SystemExit(f"theme: palette not found: {args.palette}")

    yaml_dest = stage / _DEST_YAML
    yaml_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.palette, yaml_dest)

    build_pack(base, stage / _DEST_PACK)

    print(f"theme: palette -> {_DEST_YAML}")
    print(f"theme: pack    -> {_DEST_PACK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
