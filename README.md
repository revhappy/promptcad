# PromptCAD

A branded, single-installer distribution of FreeCAD with the natural-language
CAD workbench built in.

PromptCAD is **a bundle, not a fork**. It ships FreeCAD byte-for-byte as
upstream released it and adds its own files alongside: a launcher, a branding
config, artwork, and a rebranded copy of the workbench. No FreeCAD binary is
patched or recompiled.

That choice is deliberate. A hard fork of FreeCAD means inheriting a very
large C++ codebase, a three-platform build toolchain and a permanent rebase
against an actively developed upstream. Bundling gets the same product with
none of that, and it keeps the LGPL obligations simple: we redistribute
FreeCAD verbatim, so the "corresponding source" is just upstream's source.

## Relationship to GPT4FreeCAD

[GPT4FreeCAD](https://github.com/revhappy/GPT4FreeCAD) is a **separate,
upstream project**. This repository never modifies it.

`build/rebrand.py` copies the GPT4FreeCAD checkout into the build staging area
and applies the rebrand *there* — a package rename, a token substitution, and
an artwork swap. Upstream stays pristine, so `git pull` in GPT4FreeCAD never
conflicts with anything here, and a feature landing upstream reaches PromptCAD
on the next build with no merge.

Anything that needs a real code change belongs upstream, not in the transform.

## How the rebrand works

| Surface | Mechanism |
|---|---|
| Window title, splash, window icon, About box | `branding/branding.xml` — a config file FreeCAD itself reads and supports |
| Taskbar / Start menu / process name | `PromptCAD.exe`, a small launcher that starts the bundled `freecad.exe` |
| Workbench, toolbar, menus, dialogs | `build/rebrand.py` renaming the staged addon copy |
| Installer, shortcuts, Add/Remove Programs | `installer/PromptCAD.iss` |
| Settings isolation | `<ExeName>` relocates the whole user profile to `%APPDATA%\PromptCAD\` |
| Prompt-first window, model discovery | `overlay/` — extra modules layered into the staged addon |

## The distribution layer

`overlay/promptcad/distro/` holds behaviour that belongs to *this product*
rather than to the addon. The build copies it into the staged addon and appends
a short hook to the staged `InitGui.py`; upstream never learns it exists.

- **`models.py`** — finds `.gguf` files in Downloads, the install's `models\`
  folder, the user profile, LM Studio and the Machine SDK cache, then adopts
  one. Matching is by loose pattern, not exact filename, because NVIDIA ships
  `NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf` inside a repo called
  `NVIDIA-Nemotron-3-Nano-4B-GGUF` and re-quantisers rename freely.
- **`panel_models.py`** — wraps the panel's `_populate_models` and
  `_on_model_changed` so every discovered model appears in the panel's own
  dropdown. Upstream lists a single entry, the one path recorded in Settings.
- **`shell.py`** — the minimal toolbar layout and the `All tools` toggle
  (Ctrl+Shift+T), re-applied on workbench activation because FreeCAD rebuilds
  the toolbar area every time.
- **`taskbar.py`** — claims an AppUserModelID so Windows files the window under
  PromptCAD. Runs synchronously from the InitGui hook, not through `boot.py`,
  because Windows only honours the ID before the process shows its first
  window.
- **`boot.py`** — polls for the main window's event loop, then starts the
  above. Each part is independently guarded.

The launcher is part of this layer too. Besides starting `bin\freecad.exe` with
the working directory set for branding, it seeds a **brand-new** profile with
the bundled `FreeCAD Dark` preference pack, by writing it as the initial
`user.cfg`. Preference packs are ordinary `FCParameters` documents — the same
shape as `user.cfg` — so a pack file simply *is* a valid starting profile.

That matters more than a colour preference. Stock FreeCAD with no theme set
applies no stylesheet at all: it takes whatever palette Windows hands Qt and
leaves tab bars, scroll bars and combo boxes drawn as raw Qt chrome, which is
why an unseeded PromptCAD looked subtly unlike FreeCAD rather than obviously
unlike it (measured: 694 characters of stylesheet against 70,183). Seeding
before the process starts also means no visible repaint, which applying a theme
from the addon at startup would cause.

Only ever for a profile that does not exist yet — once there is a `user.cfg` it
belongs to the user, who may have chosen the light theme deliberately. To bring
an *existing* profile over, merge the pack into it rather than replacing it.

Deleting `bin\branding.xml` returns the app to stock FreeCAD appearance, which
is a useful thing to know when debugging.

## Models

**No weights ship with PromptCAD** — the installer is already around 700MB —
but you do not have to configure anything either. Download a `.gguf` in a
browser and start the app: discovery looks in the install's `models\` folder,
your Downloads, `%APPDATA%\PromptCAD\<version>\models`, an LM Studio library
and `%USERPROFILE%\.machine\models`, adopts the first thing it recognises, and
says so in the Report view.

### Local — GGUF

| Model | Quant | Size | Needs | Licence | Download |
|---|---|---|---|---|---|
| **NVIDIA Nemotron 3 Nano 4B** — the default | Q4_K_M | 2.84 GB | 8 GB RAM | NVIDIA Open Model | [`.gguf`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF/resolve/main/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf?download=true) · [repo](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF) |
| Google Gemma 4 12B | Q4_K_M | 7.66 GB | 16 GB RAM or a GPU | Gemma Terms of Use | [`.gguf`](https://huggingface.co/bartowski/gemma-4-12B-it-GGUF/resolve/main/gemma-4-12B-it-Q4_K_M.gguf?download=true) · [repo](https://huggingface.co/bartowski/gemma-4-12B-it-GGUF) |

Nemotron 3 Nano is what PromptCAD's prompts are tuned against and it runs on a
laptop CPU. Gemma 4 12B is noticeably stronger on multi-step geometry at
roughly three times the download.

Two things worth knowing before you go looking for these files:

- **The filename is not the repository name.** NVIDIA ships
  `NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf` — no hyphen after "Nemotron" — inside
  a repository called `NVIDIA-Nemotron-3-Nano-4B-GGUF`, and re-quantisers
  rename freely. Discovery matches on a loose pattern for exactly that reason.
- **A partly downloaded file is skipped on purpose.** Size is checked first,
  because a truncated `.gguf` fails deep inside the inference engine with an
  error that makes no sense.

### Cloud — open weights, too big to hold

| Model | Publisher | Size | Licence |
|---|---|---|---|
| [GLM-5.2](https://huggingface.co/zai-org/GLM-5.2) | Z.ai / Zhipu AI | 744B MoE | MIT |
| [Inkling](https://thinkingmachines.ai/model-card/inkling/) | Thinking Machines Lab | 975B total / 41B active | see model card |
| [Inkling-Small](https://thinkingmachines.ai/news/inkling-small/) | Thinking Machines Lab | 276B total / 12B active | see model card |

Open weights, but past what a workstation will hold — Z.ai puts GLM-5.2's floor
at eight H100s, and Inkling-Small is still ~140GB quantised. Reach these
through an API provider rather than downloading them.

PromptCAD also works with **no local model at all**: add a key for Anthropic,
OpenAI, Google or OpenRouter in Settings. Local models are for working offline
and keeping your geometry on your own machine.

`overlay/promptcad/distro/models.json` is the manifest behind all of the above.
It is served from `alphaintellabs.com/promptcad/models.json` and bundled as a
fallback, so the list can change without an app release — **edit that file
rather than this table**, and keep the two in step.

## Layout

```
branding/
  branding.xml          FreeCAD's branding hooks
  icons/*.svg           hand-drawn source artwork
  build_icons.py        SVG -> PNG / ICO / BMP, via FreeCAD's bundled Python
  generated/            build output (not committed)
launcher/
  PromptCAD.cs          the launcher shim
  build_launcher.ps1    compiles it with the in-box csc.exe
build/
  build.ps1             the whole pipeline
  rebrand.py            GPT4FreeCAD -> PromptCAD source transform
installer/
  PromptCAD.iss         Inno Setup script
legal/
  NOTICE.txt            attribution, shown as the installer's licence page
  SOURCE-OFFER.txt      the written offer the LGPL requires
dist/                   build output (not committed)
```

## Building

Needs a FreeCAD install (the payload and the build's Python/Qt), a
GPT4FreeCAD checkout, and Inno Setup for the installer step.

```powershell
# everything
.\build\build.ps1

# iterate on branding or the addon without re-copying 2GB of FreeCAD
.\build\build.ps1 -SkipPayload -NoInstaller

# non-default locations
.\build\build.ps1 -FreeCAD "C:\Program Files\FreeCAD 1.1" -Addon "..\GPT4FreeCAD"

# release build: smaller installer, roughly 3x the compile time
.\build\build.ps1 -MaxCompression
```

The mirror step copies only stock FreeCAD. Any other workbench under the
source `Mod\` triggers a warning naming it, and `-ExcludeMod <name>` leaves it
out — a developer's own copy of the upstream addon must not ship, or the
bundle installs a second unbranded workbench beside PromptCAD.

Inno Setup, if you don't have it:

```powershell
winget install --id JRSoftware.InnoSetup
```

The staged tree at `dist\stage` is a complete, runnable application — launch
`dist\stage\PromptCAD.exe` to test without building an installer at all. Use
that for day-to-day iteration: compressing 2GB solid takes 10–20 minutes even
at `lzma2/normal`, so the installer step is worth running only when you
actually need an installer.

## Design notes

The mark is a prompt chevron rendered as a CAD solid: `> _` floating over an
isometric cube. Two variants, because one asset cannot do both jobs —
`promptcad-mark.svg` carries the plate and the cube for 48px and up, and
`promptcad-mark-flat.svg` drops both so the glyph survives at 16px in a
toolbar. A flat dark `>_` on navy was rejected at the sketch stage for reading
as the PowerShell icon; the cube is what makes it read as CAD first.

## Licensing

PromptCAD's own code and artwork are MIT. The bundled FreeCAD is
LGPL-2.1-or-later and unmodified. See `legal/NOTICE.txt` for the full picture
and `legal/SOURCE-OFFER.txt` for the source offer.

FreeCAD is a trademark of the FreeCAD Project Association. PromptCAD is not
affiliated with or endorsed by them, and the name is used only to identify the
upstream software this is built on.

## Known limits

- **Windows only.** The launcher and installer are Windows-specific. macOS
  (`.app` bundle + `.dmg`) and Linux (AppImage) would each need their own
  packaging; the branding config and the rebrand transform are portable.
- **Installer size.** The payload is ~2GB, compressing to roughly 700MB. A
  download-on-install variant would be much smaller but needs hosting.
- **Code signing.** Unsigned, so SmartScreen will warn on first run. An OV/EV
  certificate and a `SignTool` line in the `.iss` are the fix.
- **Profile version is pinned.** `BuildVersionMajor`/`Minor` in
  `branding.xml` decide the user data folder (`%APPDATA%\PromptCAD\v1-0\`).
  Changing them migrates users to an empty profile, so they are pinned and
  deliberately not tied to the product version.

## Three things that will bite you

**The taskbar files windows by process, not by launcher.** `PromptCAD.exe`
starts `bin\freecad.exe` and exits, so the window belongs to freecad.exe — and
with no explicit identity Windows derives one from that process's path. The
taskbar button therefore grouped under FreeCAD, and "Pin to taskbar" pinned
**freecad.exe**: a pin wearing FreeCAD's icon that launched stock FreeCAD when
clicked. The fix is an AppUserModelID declared in two places that must agree,
and neither works alone — `overlay\promptcad\distro\taskbar.py` claims it on
the running process, and `installer\PromptCAD.iss` stamps the same string on
every shortcut. Keep the ID stable forever: it is the key Windows stores pins
and jump lists against, so changing it orphans every pin a user has made.



**Branding image paths resolve against the install root**, not against
`branding.xml`'s own directory and not against the working directory. With
bare filenames sitting next to `branding.xml` in `bin\`, FreeCAD finds
nothing and silently falls back to its own red "F" icon — no warning, no log
line, and the window title is still correct, so it looks like it worked.
Hence the `bin/` prefix on every image path.

**Not every `.gguf` is a model.** Scanning for `*.gguf` on a machine that has
LM Studio finds `mmproj-*` multimodal projectors, `mtp-*` drafter heads and
`*-imatrix` quantisation matrices — they live in the same repositories as the
real weights and download alongside them. Loading one fails deep inside
llama.cpp with nothing useful to say. `models._is_sidecar` filters them; on
this machine that cut a real scan from 13 hits to 8. Speculative-decoding
drafters are deliberately *not* filtered, since those are real usable models.

**Versioning is independent.** PromptCAD's version lives in `VERSION` and
flows to the installer, `PromptCAD.exe`'s version resource, and Add/Remove
Programs. It is *not* the GPT4FreeCAD addon version — this is a distribution,
not a re-release of the addon, and inheriting `2.8.0` put that number in the
installer while the app's own title bar said `1.0.1`.
