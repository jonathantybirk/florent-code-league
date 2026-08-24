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


def intent(brain, ct, role: str, action: str, why: str = "") -> None:
    """Record what this unit decided to do, and why.

    A replay shows what happened; it cannot show what a Builder was trying to
    do and failed at. Almost every bug found so far was of that shape -- a
    mender standing on a Core corner *intending* to heal, a Builder holding
    position *intending* to build a conveyor it could not afford, an attacker
    standing on the tile it meant to build on. All three look identical in a
    replay: a Builder that does nothing.
    """
    if not ON:
        return
    log(f"r{brain.round:>4} {role:<7} {ct.get_id():>4} at{brain.me} "
        f"{action}" + (f"  <- {why}" if why else ""))
