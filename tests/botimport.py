"""Import a bot's flat top-level modules (state.py, constants.py, toolbox.py,
modes/, ...) the same way the real fcode engine does -- by putting the
bot's own directory on sys.path, not as a proper installed package.

Every warden-family bot uses the same flat module names on purpose (see
common/toolbox.py's module docstring for why: the engine only puts
main.py's own directory on sys.path, so each bot is a self-contained,
flat namespace, not a Python package). That means two bots' tests in the
same pytest session would silently share one bot's cached `state`/
`constants`/... modules if we just left the path entry and sys.modules
entries lying around -- bot_on_path() scopes both to a single import.

Usage:

    from botimport import bot_on_path
    import importlib

    WARDEN_DIR = Path(__file__).parent.parent / "bots" / "warden"

    def import_warden():
        with bot_on_path(WARDEN_DIR):
            return SimpleNamespace(
                state=importlib.import_module("state"),
                economy=importlib.import_module("modes.economy"),
            )

The returned module objects stay perfectly usable after the `with` block
exits -- only *future* bare `import` statements would fail to find them,
and nothing here does that.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def bot_on_path(bot_dir: Path) -> Iterator[None]:
    bot_dir_str = str(bot_dir)
    before_modules = set(sys.modules)
    sys.path.insert(0, bot_dir_str)
    try:
        yield
    finally:
        sys.path.remove(bot_dir_str)
        for name in set(sys.modules) - before_modules:
            del sys.modules[name]
