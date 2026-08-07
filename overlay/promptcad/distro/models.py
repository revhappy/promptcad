"""Find local .gguf models and adopt one without the user configuring anything.

PromptCAD ships no weights - the installer would be 3.3GB and could not be
hosted on GitHub Releases. Instead the website hands out direct Hugging Face
links, and this module notices the file afterwards: the download lands in
Downloads, PromptCAD picks it up on the next start and points the local
backend at it.

It also finds models the user already has. Anyone running LM Studio has
several gigabytes of perfectly good GGUFs sitting on disk, and asking them to
download another copy would be rude.

Deliberately stdlib-only and FreeCAD-optional: the scan and selection logic
can be exercised headlessly, which is the only way any of this gets tested.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

MANIFEST_NAME = "models.json"

# A .gguf still being written is worse than no model at all: the backend will
# load it, fail deep inside llama.cpp, and the error will make no sense. These
# are the suffixes browsers and download managers park on partial files.
PARTIAL_SUFFIXES = (".part", ".crdownload", ".download", ".tmp", ".!ut")

# Anything smaller than this is a stub, a config file someone renamed, or a
# download that has barely started.
MIN_PLAUSIBLE_BYTES = 100 * 1024 * 1024

# .gguf files that are not language models. They sit in the same repositories
# as the real weights and get downloaded alongside them, so a naive "*.gguf"
# sweep finds them and will happily try to load one - which fails deep inside
# llama.cpp with nothing useful to say.
#
#   mmproj-*    multimodal vision/audio projectors (Gemma, Qwen-VL, ...)
#   mtp-*       multi-token-prediction drafter heads
#   *imatrix*   importance matrices used when quantising
#
# Speculative-decoding drafters are deliberately NOT excluded: they are real,
# small models and perfectly usable on their own.
def _is_sidecar(name: str) -> bool:
    lowered = name.lower()
    if lowered.startswith("mmproj") or "mmproj-" in lowered:
        return True
    if lowered.startswith("mtp-") or "-mtp-" in lowered:
        return True
    return "imatrix" in lowered


@dataclass
class Found:
    """A .gguf on disk, and what we know about it."""

    path: Path
    size: int
    mtime: float
    model_id: Optional[str] = None      # manifest id, when recognised
    name: Optional[str] = None          # friendly name, when recognised
    recommended: bool = False
    complete: bool = True

    @property
    def label(self) -> str:
        return self.name or self.path.stem

    @property
    def size_label(self) -> str:
        return f"{self.size / (1024 ** 3):.2f} GB"


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def load_manifest(path: Optional[Path] = None) -> dict:
    """Read the bundled model manifest. Never raises - a broken manifest just
    means models are unrecognised, not that discovery stops working."""
    candidate = path or (Path(__file__).resolve().parent / MANIFEST_NAME)
    try:
        with open(candidate, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"local": [], "cloud": []}
    if not isinstance(data, dict):
        return {"local": [], "cloud": []}
    data.setdefault("local", [])
    data.setdefault("cloud", [])
    return data


def _match_manifest(filename: str, manifest: dict) -> Optional[dict]:
    """Recognise a file by substring, not by exact name.

    Exact filenames are a trap: NVIDIA publishes
    'NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf' inside a repository called
    'NVIDIA-Nemotron-3-Nano-4B-GGUF', and re-quantisers rename freely. So the
    manifest carries loose patterns and unrecognised GGUFs are still usable.
    """
    lowered = filename.lower()
    for entry in manifest.get("local", []):
        for pattern in entry.get("match", []):
            if pattern.lower() in lowered:
                return entry
    return None


# --------------------------------------------------------------------------- #
# Where to look
# --------------------------------------------------------------------------- #
def _freecad_dirs() -> list[Path]:
    """The install's own models dir and the user profile's, if FreeCAD is up."""
    found: list[Path] = []
    try:
        import FreeCAD  # noqa: PLC0415 - optional by design

        for getter in ("getUserAppDataDir", "getResourceDir"):
            try:
                base = getattr(FreeCAD, getter)()
            except Exception:
                continue
            if base:
                found.append(Path(base) / "models")
        home = FreeCAD.ConfigGet("AppHomePath")
        if home:
            found.append(Path(home) / "models")
    except Exception:
        pass
    return found


def search_paths(extra: Optional[Iterable[os.PathLike]] = None) -> list[Path]:
    """Directories worth scanning, most specific first, de-duplicated."""
    home = Path(os.path.expanduser("~"))
    candidates: list[Path] = []

    for value in (os.environ.get("PROMPTCAD_MODEL_DIR"),
                  os.environ.get("MACHINE_MODEL_DIR")):
        if value:
            candidates.append(Path(value))

    candidates.extend(_freecad_dirs())
    candidates.extend([
        home / ".machine" / "models",       # Machine Activation SDK
        home / "Downloads",                 # where a browser download lands
        home / ".lmstudio" / "models",      # LM Studio (current layout)
        home / ".cache" / "lm-studio" / "models",   # LM Studio (older)
        home / "models",
    ])

    if extra:
        candidates.extend(Path(item) for item in extra)

    seen: set[str] = set()
    ordered: list[Path] = []
    for path in candidates:
        try:
            key = os.path.normcase(str(path.resolve()))
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def _is_partial(path: Path) -> bool:
    """True when this looks like a download still in flight."""
    if path.name.lower().endswith(PARTIAL_SUFFIXES):
        return True
    # Chrome/Firefox keep the partial file beside the final name.
    for suffix in PARTIAL_SUFFIXES:
        if path.with_name(path.name + suffix).exists():
            return True
    return False


def _walk(root: Path, max_depth: int) -> Iterable[Path]:
    """Yield *.gguf under root, depth-limited.

    Downloads folders can be enormous, so this never recurses far and never
    follows symlinks - it is looking for multi-gigabyte files, which are not
    buried deep.
    """
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.name.lower().endswith(".gguf"):
                    yield Path(entry.path)
            except OSError:
                continue


def scan(paths: Optional[Iterable[os.PathLike]] = None,
         max_depth: int = 2,
         manifest: Optional[dict] = None) -> list[Found]:
    """Find candidate models. Incomplete downloads are returned but flagged."""
    manifest = manifest if manifest is not None else load_manifest()
    roots = [Path(p) for p in paths] if paths is not None else search_paths()

    results: list[Found] = []
    seen: set[str] = set()

    for root in roots:
        if not root.is_dir():
            continue
        for path in _walk(root, max_depth):
            if _is_sidecar(path.name):
                continue
            try:
                key = os.path.normcase(str(path.resolve()))
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)

            try:
                stat = path.stat()
            except OSError:
                continue

            entry = _match_manifest(path.name, manifest)
            expected = (entry or {}).get("size_bytes") or 0
            complete = not _is_partial(path) and stat.st_size >= MIN_PLAUSIBLE_BYTES
            if complete and expected:
                # Allow slack: quantisers differ slightly from published sizes.
                complete = stat.st_size >= expected * 0.80

            results.append(Found(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime,
                model_id=(entry or {}).get("id"),
                name=(entry or {}).get("name"),
                recommended=bool((entry or {}).get("recommended")),
                complete=complete,
            ))

    return results


_cache: tuple[float, list[Found]] | None = None
_CACHE_TTL = 15.0


def scan_cached(ttl: float = _CACHE_TTL, refresh: bool = False) -> list[Found]:
    """scan() with a short memo, for callers on the UI path.

    The dropdown repopulates on every provider change; re-walking Downloads
    each time is wasteful when the answer cannot plausibly have changed. The
    TTL is short enough that a model finishing its download shows up on the
    next glance at the menu.
    """
    global _cache
    import time

    now = time.monotonic()
    if not refresh and _cache is not None and (now - _cache[0]) < ttl:
        return _cache[1]
    found = scan()
    _cache = (now, found)
    return found


def choose(found: Iterable[Found]) -> Optional[Found]:
    """Pick the model to adopt: recommended, then recognised, then newest."""
    usable = [item for item in found if item.complete]
    if not usable:
        return None
    return sorted(
        usable,
        key=lambda item: (
            0 if item.recommended else (1 if item.model_id else 2),
            -item.mtime,
        ),
    )[0]


# --------------------------------------------------------------------------- #
# Adoption
# --------------------------------------------------------------------------- #
def adopt(force: bool = False) -> Optional[str]:
    """Point the local backend at a discovered model.

    Returns a one-line status for the report view, or None when nothing
    changed. A path the user set by hand is left alone unless it has stopped
    existing - someone who chose a model deliberately should not have that
    quietly swapped out from under them.
    """
    try:
        from ..config import get_config
    except Exception:
        return None

    config = get_config()
    current = config.machine_model_path()

    if current and not force:
        if os.path.isfile(current):
            return None
        # Configured model has gone: fall through and look for a replacement.

    pick = choose(scan())
    if pick is None:
        return None
    if current and os.path.normcase(current) == os.path.normcase(str(pick.path)):
        return None

    config.set_machine_model_path(str(pick.path))
    return f"PromptCAD found a local model: {pick.label} ({pick.size_label}) at {pick.path}"
