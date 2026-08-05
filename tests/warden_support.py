"""Load bots/warden_'s modules for tests -- see botimport.bot_on_path for
why this needs care instead of a plain `import economy`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from botimport import bot_on_path

WARDEN_DIR = Path(__file__).resolve().parent.parent / "bots" / "warden_"


def import_warden() -> SimpleNamespace:
    with bot_on_path(WARDEN_DIR):
        return SimpleNamespace(
            constants=importlib.import_module("constants"),
            state=importlib.import_module("state"),
            policy=importlib.import_module("policy"),
            core=importlib.import_module("core"),
            toolbox=importlib.import_module("toolbox"),
            modes=importlib.import_module("modes"),
            economy=importlib.import_module("modes.economy"),
            defence=importlib.import_module("modes.defence"),
            scouting=importlib.import_module("modes.scouting"),
            offence=importlib.import_module("modes.offence"),
        )
