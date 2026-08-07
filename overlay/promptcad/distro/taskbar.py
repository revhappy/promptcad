"""Tell Windows the window belongs to PromptCAD, not to FreeCAD.

PromptCAD.exe starts `bin\\freecad.exe` and exits, because a launcher that
stayed resident would just park a second process in the tree. That is the right
call for process management and the wrong one for the taskbar: the window is
owned by freecad.exe, and with no explicit identity Windows derives one from
the owning process's path. So the taskbar button groups under *FreeCAD*, "Pin
to taskbar" pins **freecad.exe** rather than PromptCAD.exe - which is why a pin
comes back wearing FreeCAD's icon and, worse, launches stock FreeCAD when
clicked.

The fix is an AppUserModelID, set from inside the process that owns the window.
That is this one: FreeCAD embeds Python, so a call made while `InitGui.py` runs
is a call made by freecad.exe itself. Windows then groups the window under that
ID and resolves it to the Start-menu shortcut carrying the same ID, so a pin is
a PromptCAD pin with PromptCAD's icon.

Two halves have to agree, and neither works alone:

* here - the running process claims the ID, and
* `installer\\PromptCAD.iss` - every shortcut declares the same ID.

Timing matters. This has to happen before the main window is shown, so it runs
straight from the InitGui hook rather than through `boot.py`'s deferred timer,
which fires nearly a second too late.
"""

from __future__ import annotations

import sys

# "CompanyName.ProductName" is the documented convention. Keep it stable: it is
# the key Windows stores pinned shortcuts and jump lists against, so changing
# it orphans every pin the user has already made.
APP_ID = "AlphaIntelLabs.PromptCAD"

_installed = False


def install() -> str:
    """Claim the AppUserModelID. Returns a message, or "" if there was nothing
    to do. Never raises - a wrong taskbar icon must not cost anyone their CAD
    program."""
    global _installed

    if _installed or not sys.platform.startswith("win"):
        return ""

    try:
        import ctypes

        # Fails with E_INVALIDARG on a malformed ID and S_OK otherwise. It is
        # only honoured before the process shows its first window, which is why
        # this is called from the top of the InitGui hook.
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(APP_ID))
    except Exception as exc:  # noqa: BLE001 - old Windows, or no shell32
        return f"PromptCAD could not set its taskbar identity: {exc}"

    _installed = True
    if result != 0:  # S_OK
        return (f"PromptCAD's taskbar identity was rejected "
                f"(HRESULT 0x{result & 0xFFFFFFFF:08X}); pinned shortcuts may "
                f"show the FreeCAD icon.")
    return ""


def current() -> str:
    """The ID this process is actually running under - for diagnostics."""
    if not sys.platform.startswith("win"):
        return ""
    try:
        import ctypes

        buffer = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
            ctypes.byref(buffer))
        return buffer.value or "" if result == 0 else ""
    except Exception:  # noqa: BLE001
        return ""
