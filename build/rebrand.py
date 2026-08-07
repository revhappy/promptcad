"""Turn a GPT4FreeCAD checkout into the PromptCAD addon, without touching it.

PromptCAD and GPT4FreeCAD are separate projects. The GPT4FreeCAD repository is
upstream and stays pristine: this script copies it into the build staging area
and applies the rebrand there, so an upstream `git pull` never conflicts with
anything PromptCAD does.

Usage:
    python rebrand.py --source <GPT4FreeCAD checkout> --dest <staged Mod\\PromptCAD>

The transform is deliberately mechanical - a package rename plus a token
substitution - so it keeps working as upstream changes. Anything that needs a
real code change belongs upstream, not here.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Ordered: the CamelCase form must run before the lowercase one so that
# "GPT4FreeCAD" is not first mangled into "PromptCAD" by a case-insensitive
# pass. These are plain string replacements, applied to text files only.
SUBSTITUTIONS = [
    ("GPT4FreeCAD", "PromptCAD"),   # class names, command ids, UI strings
    ("GPT4FREECAD", "PROMPTCAD"),   # env vars / constants, if any appear
    ("gpt4freecad", "promptcad"),   # the python package and dotfile names
]

PACKAGE_RENAMES = [("gpt4freecad", "promptcad")]

# Copied verbatim; rewriting bytes in these would corrupt them.
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".pyd", ".so", ".dll",
    ".zip", ".gz", ".FCStd", ".step", ".stp", ".stl",
}

# Never copied into the payload.
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".vscode", ".idea",
                 ".ruff_cache", ".mypy_cache"}
EXCLUDED_NAMES = {".DS_Store"}

# Artwork swapped in after the copy: the upstream addon loads these two files
# by name, so replacing the files rebrands every button without patching any
# of upstream's icon-resolution code.
ICON_SWAPS = [
    ("gpticon.png", "generated/promptcad-mark-flat-128x128.png"),
    ("logo.svg", "icons/promptcad-mark-flat.svg"),
]


def _is_excluded(path: Path, source: Path) -> bool:
    rel = path.relative_to(source)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    return path.name in EXCLUDED_NAMES


def _rebrand_text(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def _rebrand_path(rel: Path) -> Path:
    """Apply the package rename to a relative path."""
    parts = list(rel.parts)
    for i, part in enumerate(parts):
        for old, new in PACKAGE_RENAMES:
            if part == old:
                parts[i] = new
            elif part.startswith(old + "."):  # e.g. gpt4freecad.egg-info
                parts[i] = new + part[len(old):]
    return Path(*parts) if parts else rel


def copy_tree(source: Path, dest: Path) -> tuple[int, int]:
    """Copy source to dest, renaming the package and rewriting text files."""
    text_count = 0
    binary_count = 0

    for path in sorted(source.rglob("*")):
        if _is_excluded(path, source):
            continue

        target = dest / _rebrand_path(path.relative_to(source))

        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() in BINARY_SUFFIXES:
            shutil.copy2(path, target)
            binary_count += 1
            continue

        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Not text after all - copy it through untouched rather than guess.
            shutil.copy2(path, target)
            binary_count += 1
            continue

        target.write_text(_rebrand_text(original), encoding="utf-8", newline="")
        text_count += 1

    return text_count, binary_count


def swap_icons(dest: Path, branding: Path) -> list[str]:
    """Replace upstream's artwork with the PromptCAD set."""
    swapped = []
    for target_name, branding_rel in ICON_SWAPS:
        replacement = branding / branding_rel
        if not replacement.is_file():
            raise SystemExit(
                f"rebrand: missing branding asset {replacement}\n"
                f"        Run branding/build_icons.py first."
            )
        shutil.copy2(replacement, dest / target_name)
        swapped.append(target_name)
    return swapped


# Appended to the staged InitGui.py. FreeCAD is already imported by the time
# this runs, and the guard means a missing overlay degrades to stock behaviour
# instead of a workbench that will not load.
BOOT_HOOK = '''

# --- PromptCAD distribution layer (appended by the PromptCAD build) ---
# Not part of the upstream addon; see promptcad/distro/__init__.py.
try:
    from promptcad.distro import boot as _promptcad_boot
    _promptcad_boot.install()
except Exception as exc:
    FreeCAD.Console.PrintError(f"PromptCAD distribution layer unavailable: {exc}\\n")
'''

BOOT_MARKER = "promptcad.distro"


def apply_overlay(dest: Path, overlay: Path) -> int:
    """Copy PromptCAD's own modules over the staged addon, verbatim.

    No substitution runs on these: they are already PromptCAD-native, and they
    mention the upstream project by name on purpose.
    """
    if not overlay.is_dir():
        raise SystemExit(f"rebrand: overlay directory not found: {overlay}")

    copied = 0
    for path in sorted(overlay.rglob("*")):
        rel = path.relative_to(overlay)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def wire_boot(dest: Path) -> bool:
    """Append the distribution layer's entry point to InitGui.py."""
    init_gui = dest / "InitGui.py"
    text = init_gui.read_text(encoding="utf-8")
    if BOOT_MARKER in text:
        return False
    init_gui.write_text(text + BOOT_HOOK, encoding="utf-8", newline="")
    return True


def verify(dest: Path) -> None:
    """Fail loudly if the rebrand left the upstream name anywhere it matters."""
    leaked = []
    for path in dest.rglob("*"):
        if path.is_dir() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for old, _ in SUBSTITUTIONS:
            if old in text:
                leaked.append(f"{path.relative_to(dest)}: {old}")
                break

    if leaked:
        sys.stderr.write("rebrand: upstream name survived in:\n")
        for entry in leaked[:20]:
            sys.stderr.write(f"  {entry}\n")
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="GPT4FreeCAD checkout (read-only)")
    parser.add_argument("--dest", required=True, type=Path,
                        help="output directory, e.g. stage\\Mod\\PromptCAD")
    parser.add_argument("--branding", required=True, type=Path,
                        help="PromptCAD branding directory")
    parser.add_argument("--overlay", type=Path,
                        help="PromptCAD overlay tree layered over the addon")
    args = parser.parse_args()

    source = args.source.resolve()
    dest = args.dest.resolve()
    branding = args.branding.resolve()

    if not (source / "InitGui.py").is_file():
        raise SystemExit(f"rebrand: {source} does not look like the addon "
                         f"(no InitGui.py)")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    text_count, binary_count = copy_tree(source, dest)
    swapped = swap_icons(dest, branding)

    # Verify before the overlay lands: this checks the *rename transform*, and
    # PromptCAD's own files legitimately name the upstream project.
    verify(dest)

    print(f"rebrand: {text_count} text files rewritten, "
          f"{binary_count} copied verbatim")
    print(f"rebrand: artwork replaced -> {', '.join(swapped)}")

    if args.overlay:
        copied = apply_overlay(dest, args.overlay.resolve())
        wired = wire_boot(dest)
        print(f"rebrand: overlay applied ({copied} files), "
              f"InitGui hook {'added' if wired else 'already present'}")

    print(f"rebrand: staged at {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
