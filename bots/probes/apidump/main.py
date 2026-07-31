"""Enumerate the REAL Controller object at runtime on the installed engine.

The Controller class surface is empty from outside the sandbox; only the live object handed to run()
carries the methods. This is how every API claim in docs/ground-truth.md was established, and it is how
we check what the 2.3.x update actually changed.

Findings come back through ct.resign(), the only channel that reaches run_game's result dict (print() is
swallowed into the replay).
"""

from fcode import Controller, EntityType


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("EXC:" + type(exc).__name__ + ":" + str(exc)[:80])
            except Exception:
                pass

    def _run(self, ct):
        if self.done:
            return
        self.done = True
        names = sorted(n for n in dir(ct) if not n.startswith("_"))
        interesting = [n for n in names
                       if any(k in n.lower() for k in ("ammo", "convert", "global", "resource"))]
        parts = ["N=%d" % len(names), "AMMO/CONVERT/GLOBAL:" + ",".join(interesting)]

        # Probe the specific methods the official docs claimed and 2.2.0 lacked.
        for probe in ("get_global_ammo", "convert_ammo", "can_convert_ammo",
                      "get_ammo_amount", "get_ammo_type"):
            parts.append(probe + "=" + ("Y" if hasattr(ct, probe) else "N"))
        ct.resign(" | ".join(parts))
