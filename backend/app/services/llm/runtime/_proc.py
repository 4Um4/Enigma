"""
SSOT helper for invisible subprocess spawning on Windows.

CREATE_NO_WINDOW (= 0x08000000) tells Windows: do not allocate a console
for this child. STARTUPINFO with SW_HIDE further guarantees that even if
the child creates a GUI window later, it stays hidden.

IMPORTANT: DETACHED_PROCESS is intentionally NOT used here.
  Microsoft docs forbid combining DETACHED_PROCESS with CREATE_NEW_PROCESS_GROUP,
  and client.py merges this helper with CREATE_NEW_PROCESS_GROUP (needed for
  Ctrl-Break lifecycle control of the Host broker). The conflict causes Windows
  to fall back to allocating a new console — which is exactly the visible
  window we are trying to suppress. CREATE_NO_WINDOW alone is sufficient and
  safe to combine with CREATE_NEW_PROCESS_GROUP.

On Linux/macOS this is a no-op — returns empty dict.

Usage:
    from app.services.llm.runtime._proc import silent_subprocess_kwargs
    proc = subprocess.Popen(cmd, **silent_subprocess_kwargs(), stdout=..., stderr=...)
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def silent_subprocess_kwargs() -> dict[str, Any]:
    """Return subprocess kwargs that hide the child window on Windows.

    Returns:
        Empty dict on Linux/macOS.
        On Windows:
            creationflags = CREATE_NO_WINDOW  (no DETACHED_PROCESS — see module docstring)
            startupinfo   = STARTUPINFO(dwFlags=STARTF_USESHOWWINDOW, wShowWindow=SW_HIDE)
    """
    kwargs: dict[str, Any] = {}
    if sys.platform != "win32":
        return kwargs

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    kwargs["creationflags"] = CREATE_NO_WINDOW

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    kwargs["startupinfo"] = si

    return kwargs


__all__ = ["silent_subprocess_kwargs"]