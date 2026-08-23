"""hildr's team state, answered from the GCS instead of raw store slots.

hildr's logic asks `_read(ct, SLOT_X)` / `_write(ct, SLOT_X, v)`.  This
adapter keeps those calls but maps every slot onto what the GCS already
provides, so the bot's decisions stay the same while all 16 engine slots
belong to the GCS protocol:

    heartbeats (BUILDER, MINER, BEAT0-4)  -> registry liveness
    ENEMY (enemy Core + ring_extra)       -> map.enemy_core() + STATUS CORE_FLAGS
    THREAT, GO, ECON_OK                   -> STATUS CORE_FLAGS bits (Core sends on change,
                                             and every FLAGS_REFRESH rounds for newborns)
    BUILT (sentinels placed)              -> live sentinel owners
    HARVEST                               -> OUR_HARVESTER facts in the map
    EHEAL (enemy builders beside their Core) -> STATUS ENEMY_MENDERS (sentinels report it,
                                             keeping hildr's "zero only if you see it all")
    EHP (enemy Core HP)                   -> STATUS ENEMY_CORE_HP
    ETA (attacker's steps to post)        -> STATUS ETA

Role conventions derived from slots (same snapshot, same rule for everyone):
    the attacker is the builder in slot 1; the miner is the builder in the
    lowest live builder slot above 1.
"""

from utils.GCS.Base.protocol import STATE_CODE

ATTACKER_SLOT = 1
FLAGS_REFRESH = 5            # Core re-sends CORE_FLAGS this often even if unchanged

_OUR_HARVESTER = STATE_CODE["OUR_HARVESTER"]


def _pack(pos, extra=0):
    return (pos[0] + 1) * 64 + pos[1] + extra * 65536


class TeamState:
    def __init__(self, player, slots):
        self.p = player                      # the hildr Player (has .gcs, .round)
        self.S = slots                       # dict name -> hildr slot constant
        self.flags = {"go": 0, "econ": 0, "threat": 0, "ring_extra": 0}
        self.flags_sent = None
        self.flags_round = -100
        self.eta_sent = None
        self.ehp_sent = None
        self.eheal_sent = None

    # ------------------------------------------------------------------ helpers
    @property
    def gcs(self):
        return self.p.gcs

    def _owners(self):
        return self.gcs.registry.owners if self.gcs and self.gcs.registry else {}

    def _fresh(self):
        return self.p.round + 1

    def _core_flags(self):
        v = self.gcs.status.get("CORE_FLAGS")
        if v is None:
            return self.flags if self.gcs.kind == "core" else {"go": 1, "econ": 0, "threat": 0, "ring_extra": 0}
        return {"go": v & 1, "econ": (v >> 1) & 1, "threat": (v >> 2) & 1, "ring_extra": v >> 3}

    def _builder_slots(self):
        return sorted(s for s, o in self._owners().items() if o.kind == "builder_bot")

    def _miner_slot(self):
        return next((s for s in self._builder_slots() if s != ATTACKER_SLOT), None)

    # ------------------------------------------------------------------ reads
    def read(self, ct, slot):
        S = self.S
        f = self._core_flags()
        if slot == S["BUILT"]:
            return sum(1 for o in self._owners().values() if o.kind == "sentinel")
        if slot == S["BUILDER"]:
            if self.gcs.slot == ATTACKER_SLOT:
                return 0                         # we are the attacker
            # the Core hands out the lowest free slot, so holding slot >= 2 already
            # proves slot 1 is taken; the registry confirms it once it knows
            alive = (self.gcs.slot is not None and self.gcs.slot > ATTACKER_SLOT) or \
                (ATTACKER_SLOT in self._owners() and self._owners()[ATTACKER_SLOT].kind == "builder_bot")
            return self._fresh() if alive else 0
        if slot == S["ENEMY"]:
            enemy = self.gcs.map.enemy_core()
            if enemy is None and getattr(self.p, "enemy", None) is not None:
                enemy = (self.p.enemy.x, self.p.enemy.y)
            return _pack(enemy, f["ring_extra"]) if enemy is not None else 0
        if slot == S["THREAT"]:
            return self._fresh() if f["threat"] else 0
        if S["BEAT0"] <= slot < S["BEAT0"] + S["BEATS"]:
            i = slot - S["BEAT0"]
            live = sorted(s for s, o in self._owners().items() if o.kind == "sentinel" and o.has_written)
            return self._fresh() if i < len(live) else 0
        if slot == S["HARVEST"]:
            return sum(1 for t in self.gcs.map.tiles.values()
                       if t.building and t.building.state == _OUR_HARVESTER)
        if slot == S["EHEAL"]:
            return self.gcs.status.get("ENEMY_MENDERS", 0)
        if slot == S["GO"]:
            return f["go"]
        if slot == S["EHP"]:
            return self.gcs.status.get("ENEMY_CORE_HP", 0)
        if slot == S["MINER"]:
            m = self._miner_slot()
            return self._fresh() if m is not None and m != self.gcs.slot else 0
        if slot == S["ECON_OK"]:
            return self._fresh() if f["econ"] else 0
        if slot == S["ETA"]:
            return self.gcs.status.get("ETA", 0)
        return 0

    # ------------------------------------------------------------------ writes
    def write(self, ct, slot, value):
        S = self.S
        value = max(0, int(value))
        if slot == S["THREAT"]:
            self.flags["threat"] = 1 if value else 0
        elif slot == S["GO"]:
            self.flags["go"] = 1 if value else 0
        elif slot == S["ECON_OK"]:
            self.flags["econ"] = 1 if value else 0
        elif slot == S["ENEMY"]:
            self.flags["ring_extra"] = min(63, value // 65536)
        elif slot == S["ETA"]:
            if value != self.eta_sent:
                self.eta_sent = value
                self.gcs.send_status("ETA", min(511, value))
        elif slot == S["EHP"]:
            if value != self.ehp_sent:
                self.ehp_sent = value
                self.gcs.send_status("ENEMY_CORE_HP", min(511, value))
        elif slot == S["EHEAL"]:
            if value != self.eheal_sent:
                self.eheal_sent = value
                self.gcs.send_status("ENEMY_MENDERS", min(511, value))
        # BUILT, BUILDER, MINER, BEAT*, HARVEST, EHEAL: derived on the read side

    def flush_flags(self):
        """Core: send CORE_FLAGS when they changed, or periodically for newborns."""
        if self.gcs.kind != "core":
            return
        f = self.flags
        v = f["go"] + 2 * f["econ"] + 4 * f["threat"] + 8 * f["ring_extra"]
        if v != self.flags_sent or self.p.round - self.flags_round >= FLAGS_REFRESH:
            self.flags_sent, self.flags_round = v, self.p.round
            self.gcs.send_status("CORE_FLAGS", min(511, v))
