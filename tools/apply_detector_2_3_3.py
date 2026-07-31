"""FFPOST2 = FFPOST with the archetype detector made HONEST ON 2.3.3.

FFPOST is a faithful rebase of a refactor written against 2.2.0, and its detector rests on two
premises the 2.3.3 engine killed:

  * old G13 "a Builder Bot cannot attack any adjacent tile"  -- REVERSED. A builder hits
    orthogonally adjacent tiles for BUILDER_BOT_ATTACK_DAMAGE=2 at 2 Ti (G59).
  * "our own turrets check the occupant's team before every shot" -- never true (G10, turrets are
    team-blind) and now it bites, because 2.3.3 turrets draw on a global ammo pool and actually
    shoot, so ours grind down our own buildings (G11).

Measured on 2.3.3 over 270 games (e10/fp_*.txt): 86.9% of every hit point we lose comes from an
enemy BUILDER, 12.7% from an enemy turret, 0.4% from our own turret shooting our own buildings.
Of the 50 games where EV_HURT would latch, 26 (52%) were latched by something that is not an
enemy turret at all. "Any HP loss proves a fed enemy turret" is refuted.

The repair is measured, not guessed. The three attack damages are pairwise distinct --
BUILDER_BOT_ATTACK_DAMAGE=2, GUNNER_DAMAGE=10, SENTINEL_DAMAGE=18 -- and a cross-tab of every hit
point we took against the source the replay independently proves (e10/quanta_*) is perfectly
diagonal: 192 hits of exactly 2 all from an adjacent enemy builder, 37 hits of exactly 10 all from
an enemy Gunner, zero off-diagonal. So the SIZE of a hit names its source.

This splits the one overloaded bit into three honestly-named ones and re-prices them. It changes
no action: the postures still hold identical parameter rows, so the posture the detector computes
is still read by nothing. Parity is re-proved separately.

usage:  python patch_detect.py <postureBuildDir> <destdir>
"""
import io
import pathlib
import shutil
import sys

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
CAND = REPO / "bots" / "cand"


def sub(s, old, new, n=1):
    assert s.count(old) == n, ("expected %d got %d for %r" % (n, s.count(old), old[:70]))
    return s.replace(old, new)


def main():
    src = CAND / sys.argv[1]          # a POSTURE build (the output of apply_posture2.py)
    dest = CAND / sys.argv[2]
    globals()["SRC"] = src
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("atlas.py", "siege.py"):
        shutil.copyfile(SRC / name, dest / name)
    s = io.open(SRC / "main.py", encoding="utf-8").read()

    # --- 1. the bits ---------------------------------------------------------------------
    s = sub(s, """EV_HURT = 1 << 3           # a unit of ours has lost hit points -- PROVES a fed enemy turret""",
            """EV_HURT = 1 << 3           # a unit of ours has lost hit points -- CONTACT, not a turret""")
    s = sub(s, """EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON)""",
            """# 2.3.3 splits the old EV_HURT three ways, because on 2.3.3 the SIZE of a hit names its
# source. The three attack damages are pairwise distinct -- BUILDER_BOT_ATTACK_DAMAGE=2,
# GUNNER_DAMAGE=10, SENTINEL_DAMAGE=18 -- and measured over 229 damage events the cross-tab
# against the proven source is perfectly diagonal. EV_HURT keeps its bit and loses its meaning:
# it now says only "somebody is in contact with us", which is still the single best discriminator
# we have (zero damage in 84 games vs jonbot and starter_fixed; damage in 47 of 90 vs vanguard) --
# it simply is not evidence of a TURRET any more.
EV_MELEE = 1 << 10         # a net loss of exactly 2 HP -- an enemy Builder Bot is beside us
EV_TURRET_HURT = 1 << 11   # a net loss of exactly 10 or 18 -- a FED ENEMY TURRET. Inherits the
                           # claim the old EV_HURT made, and unlike it, actually supports it.
EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON, EV_MELEE, EV_TURRET_HURT)

# Damage quanta, read off GameConstants. A NET round delta is matched against these, so the
# discrimination is strong evidence rather than proof: HEAL_AMOUNT is 4, so a Gunner hit plus two
# friendly heals in the same round also nets -2. That is rare and it is documented rather than
# hidden -- pretending a signal is airtight is exactly the mistake this patch is fixing.
DMG_MELEE = 2
DMG_GUNNER = 10
DMG_SENTINEL = 18""")

    # --- 2. the weights ------------------------------------------------------------------
    s = sub(s, """# Evidence weights. EV_HURT is worth double because it is the only bit here with ZERO false
# positives -- see Player._sense.
EV_WEIGHTS = ((EV_HURT, 2), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))""",
            """# Evidence weights, re-priced against measurement rather than against the 2.2.0 argument.
# EV_HURT was worth double on the claim that it had zero false positives; on 2.3.3 that claim is
# refuted (52% of its latches are not turrets) so it drops to 1 and keeps its seat only as a
# contact tell. The two bits that replace it are the ones that carry a defensible claim, and
# EV_MELEE is worth as much as EV_TURRET_HURT because melee is not the lesser threat here: it is
# 86.9% of all the damage we actually take.
EV_WEIGHTS = ((EV_HURT, 1), (EV_TURRET_HURT, 2), (EV_MELEE, 2),
              (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))""")

    # --- 3. remember last round's own HP --------------------------------------------------
    s = sub(s, """        self.core_ev = 0               # evidence only the Core can see (its own hit points)""",
            """        self.core_ev = 0               # evidence only the Core can see (its own hit points)
        self.last_hp = None            # own HP last round, so a delta can be sized""")

    # --- 4. _sense: size the hit --------------------------------------------------------
    s = sub(s, '''    def _sense(self, ct):
        """Fold this round's observations into the latched evidence word.

        EV_HURT is the bit that matters and it has ZERO false positives, which is why it is the
        only one weighted double. A Builder Bot cannot attack any adjacent tile at all -- can_fire
        is False and fire() raises against an adjacent Core, Barrier, Conveyor, Harvester and
        Builder Bot, verified byte-identically on two platforms (G13) -- and the only attack a
        builder has is the range-0 shot at its OWN tile, which damages the building under it and
        nothing else (G14). Our own turrets check the occupant's team before every shot, so no
        friendly fire either. Therefore: one hit point of damage anywhere on our side PROVES the
        enemy has a turret and is feeding it. Nothing else in this detector is that clean, and it
        is latched forever the moment it fires.

        The other bits are TELLS, not proofs, and are priced accordingly.
        """
        try:
            self.evidence = self.evidence | (ct.read_store(S_FLAGS) & EV_MASK)
        except Exception:
            pass
        if not (self.evidence & EV_HURT):
            try:
                if ct.get_hp() < ct.get_max_hp():
                    self.evidence = self.evidence | EV_HURT
            except Exception:
                pass''',
            '''    def _sense(self, ct):
        """Fold this round's observations into the latched evidence word.

        ON 2.3.3 NOTHING HERE IS A PROOF. The 2.2.0 version of this detector rested on EV_HURT
        being a zero-false-positive proof of a fed enemy turret, which followed from a Builder Bot
        being unable to damage anything adjacent (old G13) and from our own turrets not firing on
        our own team. G13 is REVERSED -- a builder hits orthogonally adjacent tiles for 2 damage
        at 2 Ti (G59) -- and turrets were always team-blind (G10), which only became visible once
        2.3.3 gave them a global ammo pool to shoot from (G11). Measured over 270 games, 86.9% of
        every hit point we lose is enemy BUILDER melee and 0.4% is our own turret shooting our own
        buildings; 52% of EV_HURT's latches are not caused by a turret at all.

        So the hit is SIZED instead of merely counted. The delta is taken against this unit's own
        HP from last round -- free, because the same get_hp() call was already being made -- and
        matched against the three distinct attack damages. Only this unit's own hit points are
        watched: polling every visible building would name the melee on our belts too, but it
        costs an API call per tile per round against a 10 ms budget (G45), and a cut belt already
        has its own bit in EV_ECON_HIT.
        """
        try:
            self.evidence = self.evidence | (ct.read_store(S_FLAGS) & EV_MASK)
        except Exception:
            pass
        try:
            hp = ct.get_hp()
            if hp < ct.get_max_hp():
                self.evidence = self.evidence | EV_HURT
            if self.last_hp is not None and hp < self.last_hp:
                self.evidence = self.evidence | self._size_hit(self.last_hp - hp)
            self.last_hp = hp
        except Exception:
            pass''')

    # --- 5. the sizing helper ------------------------------------------------------------
    s = sub(s, """    def _scan_intruder(self, ct, tile, key):""",
            '''    def _size_hit(self, lost):
        """Which evidence bit a net hit-point loss of `lost` justifies. Never both."""
        if lost == DMG_MELEE:
            return EV_MELEE
        if lost == DMG_GUNNER or lost == DMG_SENTINEL:
            return EV_TURRET_HURT
        return 0

    def _scan_intruder(self, ct, tile, key):''')

    # --- 6. the Core's own copy ----------------------------------------------------------
    s = sub(s, """            hp, mx = ct.get_hp(), ct.get_max_hp()
            # ANY damage at all on the Core proves a fed enemy turret exists, tens of rounds
            # before the 88% alarm below is willing to say so. Same argument as _sense: a Builder
            # Bot cannot attack an adjacent tile (G13) and our own turrets never fire on our own
            # team, so nothing else on the board can have done it.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT""",
            """            hp, mx = ct.get_hp(), ct.get_max_hp()
            # Damage on the Core is CONTACT, latched tens of rounds before the 88% alarm below is
            # willing to say anything. It is no longer evidence of a turret on its own -- an enemy
            # Builder Bot standing on our footprint chips it for 2 a round (G59) -- so the Core
            # sizes its own hits exactly as every other unit does.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT
            if self.last_hp is not None and hp < self.last_hp:
                self.core_ev = self.core_ev | self._size_hit(self.last_hp - hp)
            self.last_hp = hp""")

    # --- 7. the belt-loss comment -------------------------------------------------------
    s = sub(s, """                    # A belt of ours we can SEE is gone. Nothing friendly removes it -- our own
                    # turrets never fire on our own team -- so this is either their gunner or a
                    # builder standing on it with the range-0 attack (G14). The saboteur tell.""",
            """                    # A belt of ours we can SEE is gone. On 2.3.3 that is a TELL and not a
                    # proof: their gunner, their builder chewing it down 2 HP at a time (G59), or
                    # -- measured, 0.4% of the damage we take -- OUR OWN team-blind gunner
                    # shooting through it (G10/G11). Priced at one point accordingly.""")

    io.open(dest / "main.py", "w", encoding="utf-8", newline="\n").write(s)
    for token in ("EV_MELEE", "EV_TURRET_HURT", "_size_hit", "DMG_SENTINEL", "self.last_hp"):
        assert token in s, token
    assert "PROVES a fed enemy turret" not in s
    assert "verified byte-identically on two platforms (G13)" not in s
    print("detector corrected -> %s  (%d bytes)" % (dest, len(s)))


if __name__ == "__main__":
    main()
