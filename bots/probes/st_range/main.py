"""EXACTLY how many bits does one store slot carry, on the engine that is installed right now?

The whole embedding budget is this one number. The docs say "any non-negative integer"; the bots in
this repo assume u32. Those are not the same claim, and the difference is unbounded-vs-32-bits.

  W  WRITE ACCEPTANCE.  Write a ladder of magnitudes into distinct slots; record the exception CLASS
     for each (a bot that only catches GameError dies on an OverflowError).
  R  READ BACK.  Next round, read each slot and report the value VERBATIM. A silent truncation or
     wrap shows up here as a value that differs from what was written.
  B  BISECTION.  Binary-search the largest accepted value between 2**31 and 2**128 so the ceiling is
     located exactly rather than bracketed.
  T  TYPES.  float / bool / str / negative -- what the engine coerces vs rejects.

Core-only, reports by resigning.
"""

from fcode import Controller, EntityType

LADDER = [
    (0, 0),
    (1, 1),
    (2, 2 ** 16 - 1),
    (3, 2 ** 31),
    (4, 2 ** 32 - 1),
    (5, 2 ** 32),
    (6, 2 ** 53),
    (7, 2 ** 63 - 1),
    (8, 2 ** 64 - 1),
    (9, 2 ** 64),
    (10, 10 ** 30),
]
TYPES = [(11, -1), (12, 1.5), (13, True), (14, "x")]


def cls(fn):
    try:
        fn()
        return "ok"
    except Exception as exc:
        n = type(exc).__name__
        return {"GameError": "GE", "OverflowError": "OE", "TypeError": "TE",
                "ValueError": "VE", "IndexError": "IE"}.get(n, n[:5])


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.hi = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE or self.done:
            return
        r = ct.get_current_round()

        if r == 0:
            self.n.append("W=" + ",".join(
                "%d:%s" % (i, cls(lambda i=i, v=v: ct.write_store(i, v))) for i, v in LADDER))
            self.n.append("T=" + ",".join(
                "%d:%s" % (i, cls(lambda i=i, v=v: ct.write_store(i, v))) for i, v in TYPES))
            return

        if r == 1:
            out = []
            for i, v in LADDER + TYPES:
                try:
                    got = ct.read_store(i)
                    out.append("%d:%s%s" % (i, str(got)[:22], "" if got == v else "!=W"))
                except Exception as exc:
                    out.append("%d:R-%s" % (i, type(exc).__name__[:5]))
            self.n.append("R=" + ",".join(out))
            # B: bisect the write ceiling.
            lo, hi = 0, 2 ** 128
            for _ in range(140):
                if hi - lo <= 1:
                    break
                mid = (lo + hi) // 2
                try:
                    ct.write_store(0, mid)
                    lo = mid
                except Exception:
                    hi = mid
            self.hi = lo
            self.n.append("BISECT max=%d  == 2**%d-1? %s  bits=%d" % (
                lo, lo.bit_length(), lo == 2 ** lo.bit_length() - 1, lo.bit_length()))
            ct.write_store(0, lo)
            return

        if r == 2:
            try:
                back = ct.read_store(0)
            except Exception as exc:
                back = "R-" + type(exc).__name__
            self.n.append("BISECT readback=%s intact=%s" % (str(back)[:24], back == self.hi))
            self.done = True
            ct.resign(" | ".join(self.n))
