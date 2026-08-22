"""The Core as the team's information hub -- three facts the design depends on.

  Q1 Does the Core's code run EVERY round, or only when its action cooldown is clear?
     A hub that is skipped on cooldown rounds cannot be the heartbeat.
  Q2 Who wins a same-round write race, the Core or a builder? The Core is spawned
     first, so if the rule is "highest entity id wins" the Core loses EVERY contested
     slot -- which forces a design where Core-owned slots are never written by units.
  Q3 What does the Core see that a unit does not? CORE_VISION_RADIUS_SQ is 36 against
     20 for a builder; this confirms it in-engine rather than from the constant.

Slot 1 is Core-only, as a control: if it never shows the Core's id, the Core is not
writing at all and Q2 is moot.
"""

from fcode import Controller, EntityType

S_RACE = 0      # everyone writes their own id here
S_CTRL = 1      # Core only


class Player:
    def __init__(self):
        self.ran = 0
        self.id = None
        self.kind = None
        self.spawned = 0
        self.race = []
        self.ctrl = []
        self.rounds = []
        self.vis = None
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if self.kind == "core" and not self.done:
                self.done = True
                ct.resign("ERR:%s:%s" % (type(exc).__name__, str(exc)[:60]))

    def _run(self, ct):
        self.ran += 1
        if self.id is None:
            self.id = ct.get_id()
            self.kind = ct.get_entity_type().value
        r = ct.get_current_round()
        self.rounds.append(r)
        self.race.append(ct.read_store(S_RACE))
        ct.write_store(S_RACE, self.id)

        if self.kind != "core":
            return

        ct.write_store(S_CTRL, self.id)
        self.ctrl.append(ct.read_store(S_CTRL))
        if self.vis is None:
            self.vis = ct.get_vision_radius_sq()

        if self.spawned < 3 and ct.can_act():
            for p in ct.get_nearby_tiles(2):
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                    break

        if r >= 22 and not self.done:
            self.done = True
            # rounds the Core's code ran vs rounds elapsed -> Q1
            gaps = [b - a for a, b in zip(self.rounds, self.rounds[1:]) if b - a != 1]
            ct.resign(
                "COREID=%d VIS=%s RAN=%d RND=%d GAPS=%s SPAWNED=%d "
                "RACE=%s CTRL=%s" % (
                    self.id, self.vis, self.ran, r, gaps[:6], self.spawned,
                    self.race[-12:], self.ctrl[-4:]))
