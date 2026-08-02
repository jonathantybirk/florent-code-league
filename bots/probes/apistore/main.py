"""The 16-slot communication store, measured exactly: lag, range, typing, and cross-unit sharing.

All multi-unit coordination rests on this, and each unit runs in its own sub-interpreter with no shared
globals (G20), so the store is the ONLY channel between our own units.

  S1  LAG.  Core writes slot 0 = 777 on round 2, then reads slot 0 on rounds 2, 3 and 4.
  S2  INDEX RANGE.  read_store / write_store at 15, 16, -1.
  S3  VALUE RANGE.  write 0, 1, 2**31, 2**32-1, 2**32, -1, and a float; read each back next round.
  S4  CROSS-UNIT.  Core writes slot 3 = 12345 on round 2.  The builder reads slot 3 on round 5 and
      echoes 1/2 into slot 4.  The Core reads slot 4 on round 8.  Non-zero => slots are shared by
      ALL units on the team, not per-unit.
  S5  COLLISION.  On round 10 the Core writes slot 5 = 222 and the builder writes slot 5 = 111.
      Whatever is in slot 5 on round 11 tells us the conflict rule.
  S6  Do slots start at 0?  Read every slot on round 0.

The CORE is the reporting unit (it lives all match); the builder relays through the store itself,
which is the point of the experiment.  Arena `scal`.
"""

from fcode import Controller, EntityType, GameError, Position

VALS = ((6, 0), (7, 1), (8, 2 ** 31), (9, 2 ** 32 - 1), (10, 2 ** 32), (11, -1), (12, 1.5))


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            if r == 5:
                v = ct.read_store(3)
                ct.write_store(4, 1 if v == 12345 else 2)
            if r == 10:
                ct.write_store(5, 111)
            return
        if et != EntityType.CORE or self.done:
            return

        if r == 0:
            self.n.append("S6 init=" + "".join(str(ct.read_store(i)) for i in range(16)))
            self.n.append("S2 w15=%s w16=%s wneg=%s r16=%s rneg=%s" % (
                self.act(ct, lambda: ct.write_store(15, 5)),
                self.act(ct, lambda: ct.write_store(16, 5)),
                self.act(ct, lambda: ct.write_store(-1, 5)),
                self.act(ct, lambda: ct.read_store(16)),
                self.act(ct, lambda: ct.read_store(-1))))
            if ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
            return

        if r == 1:
            self.n.append("S3w=" + "".join(
                self.act(ct, lambda i=i, v=v: ct.write_store(i, v))[0] for i, v in VALS))
            return

        if r == 2:
            self.n.append("S3r=" + ",".join(str(ct.read_store(i))[:11] for i, _ in VALS))
            ct.write_store(0, 777)
            ct.write_store(3, 12345)
            self.n.append("S1 same=%d" % ct.read_store(0))
            return

        if r == 3:
            self.n.append("S1 +1=%d" % ct.read_store(0))
            return
        if r == 4:
            self.n.append("S1 +2=%d s15=%d" % (ct.read_store(0), ct.read_store(15)))
            return
        if r == 10:
            ct.write_store(5, 222)
            return
        if r == 11:
            self.n.append("S4 echo=%d S5 collide=%d" % (ct.read_store(4), ct.read_store(5)))
            self.done = True
            ct.resign("STORE|" + "|".join(self.n))

    def act(self, ct, fn):
        """'ok' if the call returned, 'GE'/'TE'/'VE'/'OE' for the exception class it raised."""
        try:
            fn()
            return "ok"
        except GameError:
            return "GE"
        except TypeError:
            return "TE"
        except ValueError:
            return "VE"
        except OverflowError:
            return "OE"
        except IndexError:
            return "IE"
