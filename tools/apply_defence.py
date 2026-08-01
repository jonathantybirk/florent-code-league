"""Fill the DEFENCE posture row, and give it something to spend the round on.

Written as ANCHORED SUBSTITUTIONS, not a diff, for the same reason `apply_posture.py` was: three
other agents are editing `bot/` right now, so this has to rebase onto a tree that moved. Every
anchor is asserted unique and a moved anchor names itself in the failure message instead of
applying somewhere it should not. (`apply_posture.py` itself no longer applies to `bot/` -- the
posture refactor it describes has already landed there. This one starts from that landed state.)

The SHIPPING build is

    python tools/apply_defence.py bot bots/cand/DEF2 --keep=2

Every other flag below is an experiment that was run and is recorded here with its number, so the
next person does not pay for it twice.

usage:  python tools/apply_defence.py <srcdir> <dstdir> [--off | --on]
                                      [--keep=N] [--home] [--late]
                                      [--holdfrom=N] [--cap=N] [--counter]

  --off        force the trigger OFF -- POSTURE_CONFIDENCE unreachable, so the posture can never
               leave RUSH. This build MUST measure at parity with <srcdir>; it is the proof that
               the defence costs nothing in the games where it is not wanted.
  --on         force the trigger ON  -- DEFENCE from round 0 in every game, whatever the evidence.
               The proof that the row actually changes behaviour, and the price of paying for it
               unconditionally.
  --keep=N     ring tiles left unbricked under DEFENCE (FORTIFY_KEEP_OPEN is 5). SHIPPED AT 2:
               five of the six new maps put a Core flush against a border, so the in-bounds ring
               is shorter than five tiles and the fortifier could never start at all. Measured on
               jackpot (Core at literal (0,0)): 0 barriers at keep=5, 2 at keep=2, and the hit
               points their turrets put into our Core fell 640 -> 510 and 820 -> 610.
  --home       MEASURED WORSE, NOT SHIPPED. Adds EV_HOME_THREAT: the Core latches an enemy on foot
               within HOME_WATCH_D2 of its own footprint, which fires ten to fifteen rounds before
               anything hits us. It does exactly what it claims -- barriers 3.1 -> 4.4 a game and
               the median round our Core dies 56 -> 70 -- and it LOSES GAMES, 4-12 against 6-10 on
               the same sixteen. Coming home earlier is coming off the economy earlier, and we win
               only by killing.
  --late       no effect, measured byte-identical. Moves STEP_HOLD below STEP_PHASE to let a
               builder finish the trip to its ore. It cannot: the walk to ore happens in `_walk`,
               BELOW the whole ladder, so the come-home rung pre-empts it wherever HOLD sits.
  --holdfrom=N MEASURED WORSE, NOT SHIPPED. Only builders with spawn ordinal >= N hold the base,
               to stop the whole economy turning round at once. With --home, 4-12.
  --cap=N      MEASURED WORSE, NOT SHIPPED. Spawn cap under DEFENCE. Every builder is +20
               percentage points of PERMANENT global cost scale (G07), which is charged to the
               Gunner and the ammunition we win with.
  --counter    let a builder holding the base shoot an ORTHOGONALLY ADJACENT enemy building
               (2 dmg / 2 Ti, G13-reversed/G59) at a defensive titanium floor. NOT MEASURED.

WHAT THE ROW DOES, and why it is these three things and not something else.

Measured, `bots/cand/DBASE` vs `bots/rivals/undertow`, 16 known games, replay-attributed:
    onCORE 478 HP/game   absorb 54 HP/game   melee 0 HP/game   ourBAR 0.44   foeBAR 1.81
That is: 90% of every hit point their turrets deal lands on our Core, none of the damage we take
from this opponent is builder melee at all, and our own Core barrier ring gets built less than
once every two games. Their nearest turret sits a mean 2.6 Manhattan tiles from our footprint --
in other words there IS a tile between it and the Core on nearly every map, and that tile is one
of ours.

  1. `barrier_reserve`. The ring is not missing, it is UNFUNDED. `_hold_home` will not lay a
     3 Ti Barrier unless the bank holds barrier_cost + CHAIN_RESERVE = ~52 Ti, and in exactly the
     games where the Core is being shot the bank sits at 0-50. DEFENCE drops the reserve on THIS
     ONE purchase to zero. A separate key rather than reusing `chain_reserve`, because
     `chain_reserve` is also the Core's spawn gate and moving that would change something else.
  2. `brick_first`. `_hold_home` heals before it bricks, and `_heal` succeeds every round the Core
     is damaged and a builder is beside it -- so the first builder home heal-tanks forever and the
     ring is never reached. Healing loses that exchange on arithmetic: 4 HP per 1 Ti against a
     Gunner's 10 damage per 2 Ti. REBUILDING beats both -- a fresh 30 HP Barrier costs ~4 Ti, or
     7.5 HP per titanium -- so under DEFENCE the barrier is tried first and the heal becomes the
     fallback for the rounds when there is nothing to build.
  3. `hold_on_posture`. Come home on the detector instead of waiting for the Core to have lost
     12% of itself.

WHAT IS DELIBERATELY NOT HERE. Barrier denial of THEIR firing tiles measured LOW_VALUE and the
structural reason has not changed: everything orthogonally adjacent to our Core is our own 12-tile
spawn ring, so denial can only begin at distance 2 and a range-1 shot from inside the ring is
undeniable. This row does not deny their positions; it puts a wall in the lane of the ones they
have already taken, which is the exchange their own ring already wins against us (their Core
absorbs 69% of our fire, ours 6%).

THE TRIGGER is the damage quantum, not "we lost hit points". That signal is refuted -- 86.9% of
the HP we lose across the whole panel is enemy builder melee -- so this patch also lands the
corrected detector of `tools/apply_detector_2_3_3.py` (GUNNER_DAMAGE 10, SENTINEL_DAMAGE 18 and
BUILDER_BOT_ATTACK_DAMAGE 2 are pairwise distinct and cross-tab perfectly diagonal against
replay-proven sources) and re-prices the weights so that ONLY a proven turret hit, or the Core's
own 88% alarm, can reach the confidence threshold on its own.
"""
import io
import pathlib
import shutil
import sys

SRC = pathlib.Path(sys.argv[1])
DST = pathlib.Path(sys.argv[2])
FORCE_OFF = "--off" in sys.argv
FORCE_ON = "--on" in sys.argv
COUNTER = "--counter" in sys.argv
HOME = "--home" in sys.argv
LATE = "--late" in sys.argv
KEEP = None
HOLDFROM = None
CAP = None
for _a in sys.argv:
    if _a.startswith("--keep="):
        KEEP = int(_a.split("=", 1)[1])
    if _a.startswith("--holdfrom="):
        HOLDFROM = int(_a.split("=", 1)[1])
    if _a.startswith("--cap="):
        CAP = int(_a.split("=", 1)[1])
assert not (FORCE_OFF and FORCE_ON), "--off and --on are mutually exclusive"

if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True)
for name in ("atlas.py", "siege.py"):
    shutil.copyfile(SRC / name, DST / name)

src = io.open(SRC / "main.py", encoding="utf-8").read()


def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, "anchor not unique (%d): %r" % (n, old[:90])
    src = src.replace(old, new)


# ---------------------------------------------------------------------------
# 1. The detector: size the hit instead of merely counting it.
# ---------------------------------------------------------------------------
sub('''EV_HURT = 1 << 3           # a unit of ours has lost hit points -- PROVES a fed enemy turret''',
    '''EV_HURT = 1 << 3           # a unit of ours has lost hit points -- CONTACT, not a turret''')

sub('''EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON)''',
    '''# The old EV_HURT claimed that any hit point lost PROVED a fed enemy turret. It rested on the
# 2.2.0 pair "a Builder Bot cannot damage an adjacent tile" (old G13) and "our own turrets do not
# fire on our own team" -- the first is REVERSED on 2.3.3 (a builder hits orthogonally adjacent
# tiles for 2 damage at 2 Ti, G59) and the second was never true (turrets are team-blind, G10, and
# now have a global pool to shoot from, G11). Measured over 270 games: 86.9% of every hit point we
# lose is enemy BUILDER melee and 0.4% is our own turret shooting our own buildings, so 52% of
# EV_HURT's latches were caused by something that is not a turret.
#
# What replaces it is the DAMAGE QUANTUM. The three attack damages are pairwise distinct and a
# cross-tab of 229 damage events against the source the replay independently proves is perfectly
# diagonal, so the SIZE of a hit names its source. EV_HURT keeps its bit and loses its claim: it
# now says only "somebody is in contact with us".
EV_MELEE = 1 << 10         # a net loss of exactly 2 HP -- an enemy Builder Bot is beside us
EV_TURRET_HURT = 1 << 11   # a net loss of exactly 10 or 18 -- a FED ENEMY TURRET
# ...and the bit that beats both of them ON THE CLOCK. Being hit is a late signal: measured
# against `undertow` over 16 known games, their first turret exists at round 30 and lands its
# first shot at 31, our Core is dead by 60, and a posture decided at 31 is published at 32, read
# by a builder at 33 and standing as a Barrier some ten rounds after that. Half the defence
# arrives after the Core has. What is EARLY is the enemy BUILDER that walks in to build the
# turret, and the Core can see it for nothing: the Core acts first every round, never moves, and
# one `get_nearby_entities` around its own footprint answers "is somebody setting up on top of
# us" directly, instead of inferring it from our own hit points afterwards.
EV_HOME_THREAT = 1 << 12   # an enemy Builder Bot or turret standing NEXT TO OUR OWN CORE
EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON, EV_MELEE, EV_TURRET_HURT,
           EV_HOME_THREAT)
# Squared radius, measured from the Core's ANCHOR (its top-left footprint tile, G33), inside
# which an enemy on his feet is treated as a siege being set up rather than a wanderer. A Gunner
# reaches three tiles along its facing (attack r^2 = 13), so anything that can already shoot the
# footprint is inside r^2 = 16 of the anchor; the extra ring of slack is the walk-in.
HOME_WATCH_D2 = 25

# Read off GameConstants. A NET round delta is matched against these, so this is strong evidence
# and not proof: HEAL_AMOUNT is 4, so a Gunner hit plus two friendly heals in the same round also
# nets -2, and five builders chewing the same tile also net -10. Documented rather than hidden --
# pretending a signal is airtight is the mistake this replaces.
DMG_MELEE = 2
DMG_GUNNER = 10
DMG_SENTINEL = 18''')

sub('''# Evidence weights. EV_HURT is worth double because it is the only bit here with ZERO false
# positives -- see Player._sense.
EV_WEIGHTS = ((EV_HURT, 2), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 3''',
    '''# Evidence weights, priced so that DEFENCE is reachable by exactly two routes and no other:
# a hit of turret size landed on one of our units, or the Core's own 88% alarm. Everything else
# a hit of turret size landed on one of our units, an enemy standing on our own doorstep, or the
# Core's own 88% alarm. Everything else is corroboration and CANNOT reach the threshold however
# much of it accumulates: every remaining bit at once is 2+1+1+1+1+1 = 7 against a threshold of 8.
# That matters because the cheap bits are not cheap in the way they look: EV_INTRUDER and EV_DEEP
# fire in 90-100% of games against every opponent that spawns a Builder Bot at all, so a threshold
# they can reach between them is not a detector, it is "DEFENCE unless the enemy is inert".
EV_WEIGHTS = ((EV_TURRET_HURT, 8), (EV_HOME_THREAT, 8), (EV_MELEE, 2), (EV_HURT, 1),
              (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 1), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 8''')

if FORCE_OFF:
    # THE GATE, WELDED SHUT. Nothing can score 10**9, so `want` never becomes DEFENCE and the
    # non-empty row below is unreachable. This build exists to be measured against its parent:
    # if it is not identical, game for game, then the defence is costing something in the games
    # where it never fires and no result from the ON build can be trusted.
    sub('''POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1''',
        '''POSTURE_CONFIDENCE = 10 ** 9
POSTURE_RELEASE = 1''')
elif FORCE_ON:
    # THE GATE, WELDED OPEN. Zero is reachable by an empty evidence word, so the Core arbitrates
    # DEFENCE on round 0 of every game against every opponent.
    sub('''POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1''',
        '''POSTURE_CONFIDENCE = 0
POSTURE_RELEASE = -1''')
else:
    sub('''POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1''',
        '''POSTURE_CONFIDENCE = 8
POSTURE_RELEASE = 1''')

# ---------------------------------------------------------------------------
# 2. Two new seam keys. Both hold today's value in the base row, so a build with an empty
#    DEFENCE_OVERRIDES is still the parity build.
# ---------------------------------------------------------------------------
sub('''    "hold_on_posture": False,       # come home on the posture, not only on the Core alarm''',
    '''    "hold_on_posture": False,       # come home on the posture, not only on the Core alarm
    # Titanium held back before a Core-ring Barrier is laid. Its own key rather than
    # `chain_reserve`, which it used to share: `chain_reserve` is ALSO the Core's spawn gate, and
    # a specialist that wants cheap barriers does not thereby want the Core spending its last
    # titanium on builders.
    "barrier_reserve": CHAIN_RESERVE,
    # Lay the Barrier BEFORE trying to heal, instead of after. Healing is 4 HP per 1 Ti; a fresh
    # 30 HP Barrier is ~4 Ti, or 7.5 HP per titanium, and unlike a heal it also stops the ray.
    "brick_first": False,
    # Titanium floor under the builder's own 2 dmg / 2 Ti orthogonal shot while it is holding the
    # base. `None` -> SNIPE_FLOOR, which is 90 and is never met during a siege.
    "hold_snipe_floor": None,
    # WHICH builders are allowed to hold the base, by spawn ordinal. `None` -> all of them, which
    # is today's behaviour and is the expensive half of a defence: the come-home rung outranks
    # everything except a belt in flight, and the walk to ore happens in `_walk` BELOW the whole
    # ladder, so a builder that has claimed an ore tile twenty tiles away turns round and walks
    # back the moment the posture flips. An integer here reserves the job for the late cohort --
    # the builders the emergency spawn cap puts on the Core ring, who are standing on the ring
    # already -- and leaves the chains that are already running alone.
    "hold_from_ordinal": None,''')

# ---------------------------------------------------------------------------
# 3. Per-unit state for the quantum detector.
# ---------------------------------------------------------------------------
sub('''        self.core_ev = 0               # evidence only the Core can see (its own hit points)''',
    '''        self.core_ev = 0               # evidence only the Core can see (its own hit points)
        self.last_hp = None            # own HP last round, so a delta can be SIZED''')

# ---------------------------------------------------------------------------
# 4. _sense: size the hit.
# ---------------------------------------------------------------------------
sub('''    def _sense(self, ct):
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

        NOTHING HERE IS A PROOF ON 2.3.3. The hit is SIZED rather than merely counted: the delta
        is taken against this unit's own hit points last round -- free, because the same get_hp()
        call was already being made -- and matched against the three distinct attack damages.
        Only this unit's own hit points are watched; polling every visible building would name the
        melee on our belts too, but it costs an API call per tile per round against a 10 ms budget
        (G45), and a cut belt already has its own bit in EV_ECON_HIT.
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

sub('''    def _scan_intruder(self, ct, tile, key):''',
    '''    def _size_hit(self, lost):
        """Which evidence bit a NET hit-point loss of `lost` justifies. Never both."""
        if lost == DMG_MELEE:
            return EV_MELEE
        if lost == DMG_GUNNER or lost == DMG_SENTINEL:
            return EV_TURRET_HURT
        return 0

    def _scan_intruder(self, ct, tile, key):''')

sub('''            hp, mx = ct.get_hp(), ct.get_max_hp()
            # ANY damage at all on the Core proves a fed enemy turret exists, tens of rounds
            # before the 88% alarm below is willing to say so. Same argument as _sense: a Builder
            # Bot cannot attack an adjacent tile (G13) and our own turrets never fire on our own
            # team, so nothing else on the board can have done it.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT''',
    '''            hp, mx = ct.get_hp(), ct.get_max_hp()
            # Damage on the Core is CONTACT and nothing more -- an enemy Builder Bot standing on
            # our footprint chips it 2 at a time (G59). The Core sizes its own hits exactly as
            # every other unit does, and it is the unit this matters most on: measured against
            # `undertow`, 90% of every hit point their turrets deal lands here.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT
            if self.last_hp is not None and hp < self.last_hp:
                self.core_ev = self.core_ev | self._size_hit(self.last_hp - hp)
            self.last_hp = hp''')

if HOME:
    sub('''        self._top_up_ammo(ct)''',
        '''        self._top_up_ammo(ct)
        self._watch_home(ct)''')
    sub('''    def _top_up_ammo(self, ct):''',
        '''    def _watch_home(self, ct):
        """Latch an enemy standing on our own doorstep. Core only, and only until it fires.

        This is the EARLY half of the detector and the reason the posture can arrive in time to
        matter. Every other bit here is downstream of damage we have already taken; this one fires
        when their Builder Bot walks in, which is measured at ten to fifteen rounds before the
        Gunner it is carrying exists and twenty before the Core notices its own hit points.

        Cheap by construction: the Core is the only caller, it never moves so the radius never has
        to be recomputed, and the scan switches itself off permanently the moment it lands --
        `get_nearby_entities` is one call and the loop breaks on the first enemy on foot.

        A TURRET counts wherever it is inside the radius, because a turret near our Core has no
        other purpose. A BUILDER counts too, and that is the deliberately loose half: an economy
        opponent's builder can wander through. It is bounded by the radius rather than by
        intention -- HOME_WATCH_D2 is five tiles, against EV_DEEP's thirty per cent of a
        core-to-core axis that runs to twenty-five tiles on the bigger maps.
        """
        if self.core_ev & EV_HOME_THREAT:
            return
        try:
            mine = ct.get_team()
        except Exception:
            return
        try:
            ids = ct.get_nearby_entities(HOME_WATCH_D2)
        except Exception:
            # `dist_sq must not exceed the vision radius` -- fall back to whatever it is.
            try:
                ids = ct.get_nearby_entities()
            except Exception:
                return
        for eid in ids:
            try:
                if ct.get_team(eid) == mine:
                    continue
                et = ct.get_entity_type(eid)
            except Exception:
                continue
            if (et == EntityType.BUILDER_BOT or et == EntityType.GUNNER
                    or et == EntityType.SENTINEL):
                self.core_ev = self.core_ev | EV_HOME_THREAT
                return

    def _top_up_ammo(self, ct):''')

# ---------------------------------------------------------------------------
# 5. `_hold_home`: fund the ring, and build it before healing it.
# ---------------------------------------------------------------------------
sub('''        """Heal and brick while the Core is under sustained fire. True if the round was spent.

        Two things, in that order. Healing first because it is the cheapest damage-per-titanium
        in the game and needs no build site: 4 HP for a flat 1 Ti, against a Gunner's 2 Ti for 10
        damage on a turret that averages 5 damage a round. Bricking second because a Barrier on
        the tile their turret needs costs 3 Ti and takes 6 Ti of shooting to clear -- and a
        Gunner's ray stops at the FIRST building, so one wall shuts a whole lane.''',
    '''        """Heal and brick while the Core is under sustained fire. True if the round was spent.

        Two things, and WHICH ONE FIRST IS A POSTURE PARAMETER. Bricking is the better half and
        it used to be the unreachable half: a Barrier on the tile their turret needs costs 3 Ti,
        takes 6 Ti of shooting to clear, and a Gunner's ray stops at the FIRST building, so one
        wall shuts a whole lane -- 30 hit points of cover for about 4 titanium. Healing is 4 HP
        for a flat 1 Ti and needs no build site, which reads well until it is put beside the
        Gunner it is supposed to be answering: 10 damage for 2 Ti, every round. Under DEFENCE the
        Barrier goes first and the heal is what is left for a round with nothing to build; in
        every other posture the order is the historical one, heal first.''')

sub('''        if self._heal(ct, pos):
            return True
        try:
            if ct.get_current_round() < self._pv("fortify_from"):
                return False
            cost = ct.get_barrier_cost()
            if ct.get_global_resources() < cost + self._pv("chain_reserve"):
                return False
        except Exception:
            return False''',
    '''        # ORDER IS THE WHOLE POINT. `_heal` succeeds every round the Core is damaged and a
        # builder is beside it, so healing first means the first builder home heal-tanks for the
        # rest of the match and the ring below is never reached -- measured, 0.44 barriers a game
        # against their 1.81. And it loses the exchange it is tanking: 4 HP for 1 Ti against a
        # Gunner's 10 damage for 2 Ti. Rebuilding beats both, at 30 HP for ~4 Ti, and a Barrier
        # also stops the ray where a healed Core does not. So under DEFENCE the heal becomes the
        # FALLBACK for rounds with nothing to build; in every other posture `brick_first` is
        # False and these three lines are the two they replace, verbatim.
        first = self._pv("hold_from_ordinal")
        if first is not None and (self.ordinal is None or self.ordinal < first):
            return False
        brick_first = self._pv("brick_first")
        if not brick_first and self._heal(ct, pos):
            return True
        try:
            if ct.get_current_round() < self._pv("fortify_from"):
                return self._hold_fallback(ct, pos, brick_first)
            cost = ct.get_barrier_cost()
            # A SEPARATE RESERVE. This gate used to read `chain_reserve`, which is 45, so a
            # Barrier needed ~52 Ti banked -- and in the games where the Core is actually under
            # fire the bank sits at 0-50. That single number is why the ring does not exist.
            if ct.get_global_resources() < cost + self._pv("barrier_reserve"):
                return self._hold_fallback(ct, pos, brick_first)
        except Exception:
            return self._hold_fallback(ct, pos, brick_first)''')

sub('''        if len(free) <= keep_open:
            return False''',
    '''        if len(free) <= keep_open:
            return self._hold_fallback(ct, pos, brick_first)''')

sub('''            try:
                ct.move(step)
                return True
            except Exception:
                continue
        return False

    def _snipe(self, ct, pos):''',
    '''            try:
                ct.move(step)
                return True
            except Exception:
                continue
        return self._hold_fallback(ct, pos, brick_first)

    def _hold_fallback(self, ct, pos, brick_first):
        """What a base-holding builder does on a round it cannot lay a Barrier.

        False in every posture where `brick_first` is False, which is what makes this whole branch
        invisible outside DEFENCE: the callers all replace a literal `return False`.
        """
        if not brick_first:
            return False
        if self._hold_snipe(ct, pos):
            return True
        return self._heal(ct, pos)

    def _hold_snipe(self, ct, pos):
        """Chew the enemy building next to us. 2 damage for 2 Ti, orthogonal only (G59).

        Costed honestly: a 40 HP Gunner is 20 rounds and 40 titanium for ONE builder, which is a
        bad trade against a turret that deals 10 a round while it is being chewed -- but the four
        orthogonal neighbours of a tile can be occupied by four builders at once, and the four of
        them together take it down in five rounds for the same 40 Ti. It is off unless the row
        turns it on, and it never outranks laying a Barrier, which is strictly better value per
        titanium (30 HP of wall for ~4 Ti).
        """
        floor = self._pv("hold_snipe_floor")
        if floor is None:
            return False
        if not self._can_act(ct):
            return False
        try:
            if ct.get_global_resources() < floor:
                return False
        except Exception:
            return False
        for d in CARDINALS:
            t = pos.add(d)
            if not self._in_bounds(ct, t):
                continue
            eid = self._building_at(ct, t)
            if not self._is_enemy(ct, eid):
                continue
            if (t.x, t.y) in self.enemy_core_tiles:
                continue
            try:
                if ct.can_fire(t):
                    ct.fire(t)
                    return True
            except Exception:
                continue
        return False

    def _snipe(self, ct, pos):''')

# ---------------------------------------------------------------------------
# 6. The row itself.
# ---------------------------------------------------------------------------
ROW = ['    "hold_on_posture": True,',
       '    "barrier_reserve": 0,',
       '    "brick_first": True,']
if KEEP is not None:
    # Ring tiles left unbricked. FORTIFY_KEEP_OPEN is 5, and on the 21-map pool that is not a
    # margin, it is a switch: five of the six new maps put a Core footprint flush against a border
    # (G64a), so the in-bounds ring is SHORTER than five tiles and the fortifier can never start.
    # Measured on jackpot, whose Core anchors at literal (0,0): the in-bounds ring is 5 tiles and
    # zero barriers were laid in either orientation while 640 and 820 hit points went into the
    # Core. The four DIAGONAL ring tiles cannot terminate a chain anyway (G02 wants an orthogonal
    # neighbour of the footprint), so the number that has to stay open is smaller than it looks.
    ROW.append('    "fortify_keep_open": %d,' % KEEP)
if LATE:
    # THE LADDER ORDER IS A POSTURE PARAMETER, and this is the one place it earns its keep.
    # STEP_HOLD sits ahead of STEP_PHASE in every posture today, so the moment DEFENCE latches
    # EVERY builder that is not mid-belt drops what it is doing and walks home -- including the
    # ones already standing on the ore they claimed. That is what a defence costs, and it is
    # charged in exactly the rounds the rush needs funding: measured against `undertow`, an
    # earlier trigger bought 40 more rounds of Core (median kill 422 vs 474) and LOST two games,
    # because we only ever win by killing. Moving HOLD one rung down lets a builder finish the
    # chain it is on and defends with whoever is idle.
    ROW.append('    "order": (STEP_OWED, STEP_PHASE, STEP_HOLD,')
    ROW.append('              STEP_REPAIR, STEP_SEEK, STEP_HEAL),')
if HOLDFROM is not None:
    ROW.append('    "hold_from_ordinal": %d,' % HOLDFROM)
if CAP is not None:
    ROW.append('    "builders": %d,' % CAP)
if COUNTER:
    ROW.append('    "hold_snipe_floor": 8,')
sub('''DEFENCE_OVERRIDES = {}''',
    '''DEFENCE_OVERRIDES = {
    # Three numbers and no new subsystem. The ring already existed, was already sited on the side
    # the enemy walks in from, and already rebuilt itself when a tile came free; it was funded out
    # of a reserve it could never meet and queued behind a heal that never yielded.
%s
}''' % "\n".join(ROW))

io.open(DST / "main.py", "w", encoding="utf-8", newline="\n").write(src)
for token in ("EV_TURRET_HURT", "_size_hit", "_hold_fallback", "barrier_reserve", "brick_first"):
    assert token in src, token
assert "PROVES a fed enemy turret" not in src
print("wrote %s  (%d chars, off=%s on=%s counter=%s)"
      % (DST / "main.py", len(src), FORCE_OFF, FORCE_ON, COUNTER))
