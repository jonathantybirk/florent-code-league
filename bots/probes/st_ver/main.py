"""Re-verify the 16-slot communication store on fcode 2.3.6, plus the facts a claim protocol needs.

Everything the old `apistore` probe measured on 2.3.3, re-measured, and four new questions:

  V1  Slot count / init.  Read every index 0..19; record which raise and what the live ones hold.
  V2  Index range.  read/write at 0, 15, 16, 20, -1, a float index, a bool index.  Exception CLASS
      matters: on 2.3.3 a negative index raised OverflowError, which is NOT a GameError, so a bot
      that only catches GameError dies.
  V3  Value range.  0, 1, 2**31, 2**32-1, 2**32, -1, 1.5, True, "x" -- write then read back.
  V4  Write lag.  Core writes slot 0 = 777 on round 2 and reads slot 0 on rounds 2, 3, 4.
  V5  Cross-unit sharing.  Core writes 12345 into slot 3; a BUILDER and a GUNNER each read it and
      echo a verdict back through their own slot.  Turrets included on purpose -- the question is
      whether the store is team-wide or unit-local.
  V6  Same-round collision, THREE writers (Core id 1, builder A, builder B) into slot 5 in round 10.
  V7  Same-round DOUBLE WRITE by one unit: Core writes slot 6 twice (1 then 2) in round 12;
      builder A writes slot 7 twice (31 then 32) in round 14.
  V8  DEATH-ROUND WRITE.  Builder B writes slot 9 = 999 and self_destructs in the SAME round.
      If the write still lands, a heartbeat can be trusted right up to the round the unit dies --
      which is exactly the case a claim protocol has to reason about.
  V9  Can a unit interrogate an id it cannot see?  The Core calls get_hp / get_entity_type on
      builder B's id after B is dead, and on builder A's id (alive, but possibly out of vision).
      If a dead id raises and a live-but-unseen id also raises, "is the claimant alive?" cannot be
      answered by id lookup and MUST be answered by a heartbeat in the store.

The CORE is the reporter: it lives all match and resigns with the transcript.  Arena `scal`.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

# --- slot budget for this probe ------------------------------------------------
S_LAG = 0        # V4
S_RELAY = 3      # V5  Core -> everyone
S_ECHO_B = 4     # V5  builder A verdict
S_COLLIDE = 5    # V6
S_DBL_CORE = 6   # V7
S_DBL_BLD = 7    # V7
S_ECHO_G = 8     # V5  gunner verdict
S_DEATH = 9      # V8
S_ID_A = 10
S_ID_B = 11
S_ID_G = 12

VALS = ((6, 0), (7, 1), (8, 2 ** 31), (9, 2 ** 32 - 1), (10, 2 ** 32),
        (11, -1), (12, 1.5), (13, True), (14, "x"))
RELAY = 12345


def cls(fn):
    """'ok' if the call returned, else a two-letter tag for the exception CLASS."""
    try:
        fn()
        return "ok"
    except GameError:
        return "GE"
    except OverflowError:
        return "OE"
    except TypeError:
        return "TE"
    except ValueError:
        return "VE"
    except IndexError:
        return "IE"
    except Exception as exc:
        return type(exc).__name__[:4]


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.spawns = 0
        self.role = None          # builders: "A" or "B"
        self.built = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:40])

    # ------------------------------------------------------------------ dispatch
    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et == EntityType.GUNNER:
            self._gunner(ct)

    # ------------------------------------------------------------------ the core
    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()

        if r == 0:
            live, dead = [], []
            for i in range(20):
                try:
                    live.append(ct.read_store(i))
                except Exception as exc:
                    dead.append("%d:%s" % (i, type(exc).__name__[:2]))
            self.n.append("V1 n=%d init=%s bad=%s" % (
                len(live), "all0" if set(live) == {0} else str(live), ",".join(dead)))
            self.n.append("V2 w15=%s w16=%s w20=%s w-1=%s wflt=%s wbool=%s r16=%s r-1=%s rbig=%s" % (
                cls(lambda: ct.write_store(15, 5)),
                cls(lambda: ct.write_store(16, 5)),
                cls(lambda: ct.write_store(20, 5)),
                cls(lambda: ct.write_store(-1, 5)),
                cls(lambda: ct.write_store(1.0, 5)),
                cls(lambda: ct.write_store(True, 5)),
                cls(lambda: ct.read_store(16)),
                cls(lambda: ct.read_store(-1)),
                cls(lambda: ct.read_store(2 ** 40))))
            self._spawn(ct)
            return

        if r == 1:
            self.n.append("V3w=" + ",".join(
                cls(lambda i=i, v=v: ct.write_store(i, v)) for i, v in VALS))
            self._spawn(ct)
            return

        if r == 2:
            self.n.append("V3r=" + ",".join(str(ct.read_store(i))[:10] for i, _ in VALS))
            ct.write_store(S_LAG, 777)
            ct.write_store(S_RELAY, RELAY)
            self.n.append("V4 r0=%d" % ct.read_store(S_LAG))
            return

        if r == 3:
            self.n.append("V4 r+1=%d" % ct.read_store(S_LAG))
            return
        if r == 4:
            self.n.append("V4 r+2=%d s15=%d" % (ct.read_store(S_LAG), ct.read_store(15)))
            return

        if r == 10:
            ct.write_store(S_COLLIDE, 200)          # core is id 1, the LOWEST id on the team
            return
        if r == 11:
            self.n.append("V6 collide=%d (core200 A111 B122)" % ct.read_store(S_COLLIDE))
            return
        if r == 12:
            ct.write_store(S_DBL_CORE, 1)
            ct.write_store(S_DBL_CORE, 2)
            return
        if r == 13:
            self.n.append("V7 core1then2=%d" % ct.read_store(S_DBL_CORE))
            return

        if r == 18:
            ida = ct.read_store(S_ID_A)
            idb = ct.read_store(S_ID_B)
            idg = ct.read_store(S_ID_G)
            self.n.append("V5 bld=%d gun=%d" % (ct.read_store(S_ECHO_B), ct.read_store(S_ECHO_G)))
            self.n.append("V7 bld31then32=%d" % ct.read_store(S_DBL_BLD))
            self.n.append("V8 dyingwrite=%d/999" % ct.read_store(S_DEATH))
            self.n.append("V9 A=%d B=%d G=%d hpA=%s hpB=%s tB=%s pB=%s hpG=%s u=%d" % (
                ida, idb, idg,
                self._probe_id(ct, ida), self._probe_id(ct, idb),
                cls(lambda: ct.get_entity_type(idb)), cls(lambda: ct.get_position(idb)),
                self._probe_id(ct, idg), ct.get_unit_count()))
            return

        if r == 20:
            self.done = True
            ct.resign("STVER|" + "|".join(self.n))

    def _probe_id(self, ct, uid):
        if uid == 0:
            return "n/a"
        try:
            return str(ct.get_hp(uid))
        except Exception as exc:
            return type(exc).__name__[:4]

    def _spawn(self, ct):
        p = ct.get_position()
        for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1), (0, 2), (1, 2)):
            q = Position(p.x + dx, p.y + dy)
            try:
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    self.spawns += 1
                    return
            except Exception:
                continue

    # --------------------------------------------------------------- builder bot
    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()
        if r < 3:
            return          # keep slots 6..14 clean for the V3 value read on round 2

        # Identity: first builder to run takes seat A, the next takes seat B.
        if self.role is None:
            if ct.read_store(S_ID_A) == 0:
                ct.write_store(S_ID_A, mine)
                self.role = "A?"
            elif ct.read_store(S_ID_B) == 0:
                ct.write_store(S_ID_B, mine)
                self.role = "B?"
            return
        if self.role == "A?":
            # A claim that lost the collision falls back and re-claims the next free seat.
            self.role = "A" if ct.read_store(S_ID_A) == mine else None
            if self.role is None:
                return
        elif self.role == "B?":
            self.role = "B" if ct.read_store(S_ID_B) == mine else None
            if self.role is None:
                return

        if self.role == "A":
            if r == 5:
                ct.write_store(S_ECHO_B, 1 if ct.read_store(S_RELAY) == RELAY else 2)
                return
            if r in (6, 7) and not self.built:
                self._build_gunner(ct)
                return
            if r == 10:
                ct.write_store(S_COLLIDE, 111)
                return
            if r == 14:
                ct.write_store(S_DBL_BLD, 31)
                ct.write_store(S_DBL_BLD, 32)
                return
            return

        if self.role == "B":
            if r == 10:
                ct.write_store(S_COLLIDE, 122)      # highest id of the three writers
                return
            if r == 16:
                # V8: buffer a write, then die in the same round.
                ct.write_store(S_DEATH, 999)
                ct.self_destruct()
                return

    def _build_gunner(self, ct):
        p = ct.get_position()
        for d in (Direction.EAST, Direction.SOUTH, Direction.NORTH, Direction.WEST):
            q = p.add(d)
            try:
                if ct.can_build_gunner(q, Direction.EAST):
                    ct.build_gunner(q, Direction.EAST)
                    self.built = True
                    return
            except Exception:
                continue

    # -------------------------------------------------------------------- gunner
    def _gunner(self, ct):
        if self.done:
            return
        try:
            v = ct.read_store(S_RELAY)
            ct.write_store(S_ECHO_G, 1 if v == RELAY else 2)
            ct.write_store(S_ID_G, ct.get_id())
            self.done = True
        except Exception:
            pass
