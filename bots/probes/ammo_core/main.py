"""Probe the 2.3.3 global-ammo model from the Core.

Questions:
  A1 starting ammo balance and starting titanium
  A2 is convert_ammo Core-only? (builder / gunner attempts must fail)
  A3 conversion rate (1:1?) and which balance moves
  A4 once per team per turn?
  A5 does converting consume the Core's action cooldown (can it still spawn the same turn)?
  A6 is the ammo usable the same turn?
  A7 edge cases: amount 0, negative, more than the treasury
  A8 get_scale_percent() units -- 1.0 or 100.0?

Results are exfiltrated through ct.resign(), the only channel reaching run_game's result dict (G29).
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def err(exc):
    return type(exc).__name__ + "(" + str(exc)[:60] + ")"


class Player:
    def __init__(self):
        self.n = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOPEXC:" + err(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            # A2: non-Core attempts.
            if len(self.n) < 60 and not self.done:
                try:
                    self.n.append("BB can_convert(5)=%s" % ct.can_convert_ammo(5))
                except Exception as exc:
                    self.n.append("BB can_convert RAISES " + err(exc))
                try:
                    ct.convert_ammo(5)
                    self.n.append("BB convert_ammo(5) SUCCEEDED ammo=%d" % ct.get_global_ammo())
                except Exception as exc:
                    self.n.append("BB convert_ammo RAISES " + err(exc))
                self.done = True
            return

        if et != EntityType.CORE:
            return

        if r == 0:
            self.n.append("A1 round0 ammo=%d ti=%d scale=%s" % (
                ct.get_global_ammo(), ct.get_global_resources(), ct.get_scale_percent()))
            self.n.append("A1 cooldown_before=%d can_act=%s" % (
                ct.get_action_cooldown(), ct.can_act()))
            self.n.append("A3 can_convert(10)=%s" % ct.can_convert_ammo(10))
            try:
                rv = ct.convert_ammo(10)
                self.n.append("A3 convert(10) ok rv=%r ammo=%d ti=%d" % (
                    rv, ct.get_global_ammo(), ct.get_global_resources()))
            except Exception as exc:
                self.n.append("A3 convert(10) RAISES " + err(exc))
            self.n.append("A5 cooldown_after=%d can_act=%s" % (
                ct.get_action_cooldown(), ct.can_act()))
            # A4: second conversion in the same turn
            self.n.append("A4 can_convert(1)again=%s" % ct.can_convert_ammo(1))
            try:
                ct.convert_ammo(1)
                self.n.append("A4 SECOND convert SUCCEEDED ammo=%d" % ct.get_global_ammo())
            except Exception as exc:
                self.n.append("A4 second convert RAISES " + err(exc))
            # A5: can the Core still spawn this turn?
            spawned = False
            for d in Direction:
                if d == Direction.CENTRE:
                    continue
                p = ct.get_position().add(d)
                try:
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        spawned = True
                        break
                except Exception:
                    continue
            self.n.append("A5 spawn_same_turn_as_convert=%s ti=%d" % (
                spawned, ct.get_global_resources()))
            return

        if r == 1:
            self.n.append("A6 r1 ammo=%d ti=%d" % (
                ct.get_global_ammo(), ct.get_global_resources()))
            # A7 edge: zero
            self.n.append("A7 can_convert(0)=%s" % ct.can_convert_ammo(0))
            try:
                ct.convert_ammo(0)
                self.n.append("A7 convert(0) ok ammo=%d" % ct.get_global_ammo())
            except Exception as exc:
                self.n.append("A7 convert(0) RAISES " + err(exc))
            return

        if r == 2:
            # A7 edge: negative
            try:
                self.n.append("A7 can_convert(-5)=%s" % ct.can_convert_ammo(-5))
            except Exception as exc:
                self.n.append("A7 can_convert(-5) RAISES " + err(exc))
            try:
                ct.convert_ammo(-5)
                self.n.append("A7 convert(-5) ok ammo=%d ti=%d" % (
                    ct.get_global_ammo(), ct.get_global_resources()))
            except Exception as exc:
                self.n.append("A7 convert(-5) RAISES " + err(exc))
            return

        if r == 3:
            ti = ct.get_global_resources()
            self.n.append("A7 ti=%d can_convert(ti)=%s can_convert(ti+1)=%s" % (
                ti, ct.can_convert_ammo(ti), ct.can_convert_ammo(ti + 1)))
            try:
                ct.convert_ammo(ti + 1)
                self.n.append("A7 overspend SUCCEEDED ammo=%d ti=%d" % (
                    ct.get_global_ammo(), ct.get_global_resources()))
            except Exception as exc:
                self.n.append("A7 overspend RAISES " + err(exc))
            return

        if r == 4:
            # A3 exact rate on a big amount
            a0, t0 = ct.get_global_ammo(), ct.get_global_resources()
            try:
                ct.convert_ammo(37)
                self.n.append("A3 rate: d_ammo=%d d_ti=%d" % (
                    ct.get_global_ammo() - a0, ct.get_global_resources() - t0))
            except Exception as exc:
                self.n.append("A3 rate RAISES " + err(exc))
            return

        if r >= 6:
            ct.resign(" | ".join(self.n[:40]))
