"""File-based tracing, off unless BROKKR_DEBUG names a path.

The engine does not surface a bot's stdout, and the one thing worth knowing
during development -- why a Builder did nothing this round -- is invisible in
a replay. Writing to a file costs nothing when the variable is unset.
"""

import os

_PATH = os.environ.get("BROKKR_DEBUG")
ON = bool(_PATH)


def log(message: str) -> None:
    if not ON:
        return
    try:
        with open(_PATH, "a") as handle:
            handle.write(message + "\n")
    except OSError:
        pass
