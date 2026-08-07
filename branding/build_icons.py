"""Rasterise the PromptCAD SVG icon set into the assets the app ships.

Run with FreeCAD's bundled interpreter, which already has PySide6 (for
QtSvg rendering) and Pillow (for multi-frame .ico packing):

    "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe" branding/build_icons.py

Outputs land in branding/generated/ and are consumed by branding.xml, the
launcher's embedded icon, and the installer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Must be set before QGuiApplication so this runs on a build box with no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
OUT = HERE / "generated"

MASTER = ICONS / "promptcad-mark.svg"
FLAT = ICONS / "promptcad-mark-flat.svg"
SPLASH = ICONS / "promptcad-splash.svg"

# The plated master holds detail down to about 48px; below that the
# construction lines and extrusion smear, so the flat mark takes over.
ICO_FRAMES = [
    (256, MASTER),
    (128, MASTER),
    (64, MASTER),
    (48, MASTER),
    (32, FLAT),
    (24, FLAT),
    (16, FLAT),
]


def _fail(msg: str) -> "NoReturn":  # noqa: F821
    sys.stderr.write(f"build_icons: {msg}\n")
    raise SystemExit(1)


try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QGuiApplication,
        QImage,
        QPainter,
    )
    from PySide6.QtSvg import QSvgRenderer
except ImportError as exc:  # pragma: no cover - depends on interpreter
    _fail(f"PySide6 with QtSvg is required ({exc}). Use FreeCAD's bundled python.exe.")

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    _fail(f"Pillow is required ({exc}). Use FreeCAD's bundled python.exe.")


def render_image(svg: Path, width: int, height: int | None = None) -> QImage:
    """Rasterise one SVG onto a transparent canvas."""
    if not svg.is_file():
        _fail(f"missing source SVG: {svg}")
    height = height if height is not None else width

    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        _fail(f"Qt could not parse {svg.name}")

    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(0)  # transparent

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    try:
        renderer.render(painter, QRectF(0, 0, width, height))
    finally:
        painter.end()
    return image


def render(svg: Path, width: int, height: int | None = None) -> Path:
    """Rasterise one SVG and write it as a PNG, returning the written path."""
    height = height if height is not None else width
    image = render_image(svg, width, height)
    dest = OUT / f"{svg.stem}-{width}x{height}.png"
    if not image.save(str(dest), "PNG"):
        _fail(f"could not write {dest}")
    return dest


# --- type -------------------------------------------------------------------
# Qt's offscreen platform finds no system fonts, so the splash wordmark is
# painted here with fonts loaded by path rather than left to <text> in the SVG.

WORDMARK_FONT = Path(r"C:\Windows\Fonts\segoeuib.ttf")   # Segoe UI Bold
BODY_FONT = Path(r"C:\Windows\Fonts\segoeui.ttf")        # Segoe UI Regular


def _load_font(path: Path) -> str | None:
    """Register a font file with Qt and return the family name it provides."""
    if not path.is_file():
        return None
    font_id = QFontDatabase.addApplicationFont(str(path))
    if font_id == -1:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    return families[0] if families else None


def _sized(family: str | None, pixels: int, *, bold: bool) -> QFont:
    font = QFont(family) if family else QFont()
    font.setPixelSize(pixels)
    font.setBold(bold)
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


def build_splash() -> Path:
    """Render the splash artwork, then paint the wordmark over it."""
    image = render_image(SPLASH, 640, 400)

    bold_family = _load_font(WORDMARK_FONT)
    body_family = _load_font(BODY_FONT)
    if bold_family is None or body_family is None:
        sys.stderr.write(
            "build_icons: WARNING - Segoe UI not found, splash type will fall back\n"
        )

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    try:
        # "Prompt" in white, "CAD" in the accent, set as one continuous word.
        wordmark = _sized(bold_family, 58, bold=True)
        painter.setFont(wordmark)
        metrics = QFontMetrics(wordmark)
        x, baseline = 180, 200
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(x, baseline, "Prompt")
        painter.setPen(QColor("#38BDF8"))
        painter.drawText(x + metrics.horizontalAdvance("Prompt"), baseline, "CAD")

        painter.setFont(_sized(body_family, 19, bold=False))
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(x + 2, 234, "Natural-language parametric CAD")

        # Attribution sits bottom-right, clear of FreeCAD's own progress text.
        painter.setFont(_sized(body_family, 13, bold=False))
        painter.setPen(QColor("#64748B"))
        painter.drawText(
            QRectF(300, 356, 314, 20),
            int(Qt.AlignRight | Qt.AlignVCenter),
            "Built on FreeCAD \u00b7 LGPL-2.1-or-later",
        )
    finally:
        painter.end()

    dest = OUT / "promptcad-splash.png"
    if not image.save(str(dest), "PNG"):
        _fail(f"could not write {dest}")
    return dest


def build_wizard_images() -> list[Path]:
    """Installer artwork. Inno Setup reads BMP only, and ignores alpha."""
    splash = Image.open(OUT / "promptcad-splash.png").convert("RGB")
    large_path = OUT / "wizard-large.bmp"
    splash.resize((497, 312), Image.LANCZOS).save(large_path, format="BMP")

    # The modern wizard header is light, so the mark sits on white rather
    # than on our own dark plate, which would read as a pasted-on sticker.
    header = Image.new("RGB", (138, 140), (255, 255, 255))
    mark = Image.open(render(MASTER, 112)).convert("RGBA")
    header.paste(mark, ((138 - 112) // 2, (140 - 112) // 2), mark)
    small_path = OUT / "wizard-small.bmp"
    header.save(small_path, format="BMP")

    return [large_path, small_path]


def main() -> int:
    QGuiApplication(sys.argv)  # required before any QPainter/font work
    OUT.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    # --- multi-resolution Windows icon, used by the launcher and installer ---
    frames = []
    for size, source in ICO_FRAMES:
        png = render(source, size)
        written.append(png)
        frames.append(Image.open(png).convert("RGBA"))

    ico = OUT / "PromptCAD.ico"
    # Pillow writes every supplied size as its own frame when sizes= covers them.
    frames[0].save(ico, format="ICO", sizes=[(f.width, f.height) for f in frames])
    written.append(ico)

    # --- branding.xml assets ---
    window_icon = OUT / "promptcad-window.png"
    Image.open(render(MASTER, 256)).convert("RGBA").save(window_icon)
    written.append(window_icon)

    program_logo = OUT / "promptcad-logo.png"
    Image.open(render(FLAT, 128)).convert("RGBA").save(program_logo)
    written.append(program_logo)

    written.append(build_splash())

    # --- in-app artwork, swapped into the rebranded addon by build/rebrand.py.
    # Named explicitly rather than relied on as a side effect of the logo
    # render above, because rebrand.py looks this exact filename up. ---
    written.append(render(FLAT, 128))

    # --- addon / listing icon (package.xml wants a raster icon) ---
    addon_icon = OUT / "promptcad-64.png"
    Image.open(render(MASTER, 64)).convert("RGBA").save(addon_icon)
    written.append(addon_icon)

    # --- Inno Setup wizard artwork (needs the splash PNG to exist first) ---
    written.extend(build_wizard_images())

    for path in written:
        print(f"  {path.relative_to(HERE)}  ({path.stat().st_size:,} bytes)")
    print(f"build_icons: wrote {len(written)} files to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
