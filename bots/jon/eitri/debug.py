"""File tracing, off unless EITRI_DEBUG names a path.

A replay shows a Builder standing still; it cannot show what the Builder was
trying to do. Every opening bug so far has been of that shape.
"""

import os

_PATH = os.environ.get("EITRI_DEBUG")
ON = bool(_PATH)


def log(message: str) -> None:
    if not ON:
        return
    try:
        with open(_PATH, "a") as handle:
            handle.write(message + "\n")
    except OSError:
        pass
