"""Apply the POSTURE refactor to a copy of bot/.

Written as anchored substitutions rather than a patch on purpose: bot/ is being edited in
parallel, so this has to rebase. Every anchor is asserted unique, and a moved anchor names itself
in the failure message instead of silently applying in the wrong place.

usage:  python apply_posture.py <srcdir> <dstdir> [--defence]

  --defence   fill DEFENCE_OVERRIDES with the one demonstrated posture difference. Without it all
              three posture rows are identical and the build is the parity build.
"""
import io
import pathlib
import shutil
import sys

SRC = pathlib.Path(sys.argv[1])
DST = pathlib.Path(sys.argv[2])
DEFENCE = "--defence" in sys.argv
ECONOMY = "--economy" in sys.argv
SHARP = "--sharp" in sys.argv

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
# 1. Slot 3 widens from a 0/1 alarm into the Core's published STATE word.
# ---------------------------------------------------------------------------
sub('''# Slot 3 used to be a count of completed chains that nothing ever read. It is now the home alarm:
# 1 once our own Core has been hit hard enough that mining more titanium into it is worth less
# than keeping it standing (G01 -- titanium only scores while there is a Core footprint to land on).
S_ALARM = 3''',
    '''# Slot 3 used to be a count of completed chains that nothing ever read, then the home alarm.
# It is now the Core's published STATE WORD, of which the alarm is bit 0 with exactly its old
# meaning: 1 once our own Core has been hit hard enough that mining more titanium into it is
# worth less than keeping it standing (G01 -- titanium only scores while there is a Core
# footprint for the stacks to land on).
#
# There was no sixteenth slot to take. Every one of the 16 is spoken for -- N_CLAIMS was already
# cut to 5 to free slot 9 for the second attacker -- so the posture had to go somewhere that
# already existed. Slot 3 is the right somewhere: it is the ONLY slot with a single writer that
# is the Core, and the Core is the natural arbiter (it acts first every round and never moves).
# Folding the posture in beside the alarm also avoids the failure the brief warned about, of two
# independent mechanisms both deciding the base is in trouble and disagreeing.
S_STATE = 3
S_ALARM = S_STATE          # legacy name: the alarm is bit 0 of the same word
ALARM_BIT = 1
POSTURE_SHIFT = 1          # bits 1-2 carry the posture''')

# ---------------------------------------------------------------------------
# 2. Slot 11 gains the evidence bitfield above the 3-bit symmetry mask.
# ---------------------------------------------------------------------------
sub('''S_SYMMETRY = 11''',
    '''S_SYMMETRY = 11
# ...and the same slot carries the ARCHETYPE EVIDENCE in the bits above it. The symmetry mask is
# three bits wide (siege.ALL_REJECTED == 0b111) and every reader of it already masks, so the top
# 29 bits of slot 11 were dead space. The two fields share a slot because they share a protocol
# exactly: both are MONOTONE -- a rejected symmetry is never un-rejected and an archetype never
# un-happens -- so the read-or-write merge that makes the symmetry mask safe against a lost write
# makes the evidence safe for free. Same writers (Builder Bots only), same rounds, same merge.
#
# The Core READS this slot and never writes it. That matters: a writer that does not maintain the
# symmetry mask would clobber three bits of it back to their previous round's value every time it
# published, which is a real regression for one line of convenience.
S_FLAGS = S_SYMMETRY
EV_MASK = 0xFFFFFFF8

EV_HURT = 1 << 3           # a unit of ours has lost hit points -- PROVES a fed enemy turret
EV_ECON_HIT = 1 << 4       # a belt of ours has been destroyed where we could see it
EV_INTRUDER = 1 << 5       # an enemy Builder Bot seen at or inside the midline
EV_DEEP = 1 << 6           # ...and seen in the near third of the core-to-core axis
EV_FOE_TURRET = 1 << 7     # at least one enemy turret seen standing
EV_FOE_TURRET2 = 1 << 8    # at least FOE_TURRETS_MANY of them
EV_FOE_ECON = 1 << 9       # at least FOE_HARVESTERS_MANY enemy producers seen standing
EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON)''')

# ---------------------------------------------------------------------------
# 3. The posture enum, the weights, and the parameter table.
# ---------------------------------------------------------------------------
sub('''def cardinal_of(dx, dy):''',
    '''# --- Posture ------------------------------------------------------------------
# One enum, owned by the Core, published through the store, read by every unit. Store writes are
# visible next round (G20), so this is a TEN-ROUND-TIMESCALE decision and never a same-round
# tactical one -- which is exactly what it should be. A posture is a claim about the opponent's
# archetype, and archetypes do not change mid-match.
#
# RUSH is the default and RUSH is today's whole behaviour, verbatim. That is deliberate: the
# refactor has to be provably free before any of it is allowed to be clever, so the shipped build
# gives all three rows identical values and the switch is exercised without changing an action.
POSTURE_RUSH = 0
POSTURE_DEFENCE = 1
POSTURE_ECONOMY = 2
POSTURE_NAMES = ("RUSH", "DEFENCE", "ECONOMY")

# Rungs of the builder's priority ladder, as data. The ORDER is a posture parameter; the rungs
# themselves are the same code in every posture, which is the point -- three specialists can
# disagree about what to try first without any of them forking a step.
STEP_OWED = 0
# STEP_SABOTAGE is GONE on 2.3.3. It called `_sabotage`, the range-0 own-tile shot of the old
# G14, and `fire(own_position)` now raises -- so bot/ deleted the method and the rung with it.
# The rung id is left unallocated rather than renumbered, so a posture row written against the
# 2.2.0 ladder cannot silently reinterpret one rung as another.
STEP_HOLD = 2
STEP_PHASE = 3
STEP_REPAIR = 4
STEP_SEEK = 5
STEP_HEAL = 6
ORDER_TODAY = (STEP_OWED, STEP_HOLD, STEP_PHASE,
               STEP_REPAIR, STEP_SEEK, STEP_HEAL)

# Evidence weights. EV_HURT is worth double because it is the only bit here with ZERO false
# positives -- see Player._sense.
EV_WEIGHTS = ((EV_HURT, 2), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 3
# Points needed to leave the default at all, and the level it has to fall back below before the
# default is resumed. A Schmitt trigger: the gap is what stops a single flickering bit flapping
# the whole team's economy. In practice evidence is latched, so DEFENCE is a one-way door -- the
# release path exists for a future specialist that fields decaying evidence, not for today.
POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1
# Minimum rounds between two CHANGES of posture. The first change is deliberately not gated:
# there is nothing yet to oscillate against, and the bits worth acting on early are the ones that
# fire on contact. Every change after that waits. (On 2.2.0 the justification given here was that
# the early bit had zero false positives; on 2.3.3 none of them do -- see apply_detector_2_3_3.py
# -- so the reason to leave the first change ungated is only that there is nothing to flap yet.)
POSTURE_DWELL = 60
POSTURE_FIRST_DWELL = 0
# Round by which a total absence of evidence means the opponent is not contesting the middle at
# all and a greedy economy is simply correct. Late on purpose: silence before this is much more
# likely to mean we have not looked than that there is nothing to see.
ECONOMY_FROM = 150
# Census thresholds, as fractions of what a real opponent fields: `vanguard` runs ~4.9 turrets a
# game against our ~1.3, and an economy bot runs neither.
FOE_TURRETS_MANY = 2
FOE_HARVESTERS_MANY = 3
# Where "our half" ends, as hundredths of the core-to-core axis (0 = our Core, 100 = theirs).
# A fraction rather than a tile count because the pool runs from 8x15 to 30x30.
INTRUDER_HALF = 50
INTRUDER_DEEP = 30

# THE SEAM. Every constant a posture specialist might want to disagree about is looked up here
# instead of read off the module. `None` means "whatever the subsystem's own default is", so a
# row never has to duplicate a number that lives in `siege`.
_BASE_ROW = {
    "builders": BUILDERS,
    "siege_builders": SIEGE_BUILDERS,
    "attackers": ATTACKERS,
    # "forward_deposits" is GONE. It tuned how many harvesters the rusher planted next to the
    # firing position to feed the Gunner's magazine, and on 2.3.3 a Gunner has no magazine to
    # feed: ammunition is a team-wide pool filled only by convert_ammo at the Core (G52/G53), and
    # a forward Gunner kills a Core with no ore, no harvester and no conveyor anywhere on the map
    # (G57). bot/ deleted FORWARD_DEPOSITS and DEPOSIT_DRY with the doctrine, so the seam has
    # nothing left to parameterise.
    "chain_reserve": CHAIN_RESERVE,
    "alarm_reserve": ALARM_RESERVE,
    "rush_reserve": RUSH_RESERVE,
    "battery_reserve": BATTERY_RESERVE,
    "max_battery": None,            # None -> siege.MAX_BATTERY
    "fortify_from": FORTIFY_FROM,
    "fortify_keep_open": FORTIFY_KEEP_OPEN,
    "hold_on_posture": False,       # come home on the posture, not only on the Core alarm
    "fire_only": None,              # None -> a turret shoots whatever the engine offers it
    "order": ORDER_TODAY,
}

# Filled in by a specialist. Empty here, and that emptiness is the acceptance criterion: with
# nothing in these two dicts the refactored bot must measure identically to the unrefactored one,
# game for game, which is what proves the seams cost nothing.
DEFENCE_OVERRIDES = {}
ECONOMY_OVERRIDES = {}


def _row(over):
    row = dict(_BASE_ROW)
    row.update(over)
    return row


POSTURE_PARAMS = (_row({}), _row(DEFENCE_OVERRIDES), _row(ECONOMY_OVERRIDES))


def cardinal_of(dx, dy):''')

# ---------------------------------------------------------------------------
# 4. Per-unit state.
# ---------------------------------------------------------------------------
sub('''        self.errors = 0''',
    '''        # Posture. Every unit carries the team posture; only the Core decides it.
        self.posture = POSTURE_RUSH
        self.alarm = False
        self.state = 0                 # the Core's own copy of what it last published
        self.posture_round = 0
        self.switches = 0
        self.score = 0

        # Archetype evidence. Monotone and latched forever -- an archetype does not un-happen.
        self.evidence = 0
        self.core_ev = 0               # evidence only the Core can see (its own hit points)
        self.ev_round = {}             # bit -> round the TEAM first held it (Core only)
        self.foe_turrets = set()       # enemy turret tiles this unit has seen
        self.foe_harvesters = set()    # enemy producer tiles this unit has seen

        self.errors = 0''')

# ---------------------------------------------------------------------------
# 5. The Core: arbitrate, publish, and take its budget from the posture.
# ---------------------------------------------------------------------------
sub('''        hurt = False
        try:
            hurt = ct.get_hp() * 100 < ct.get_max_hp() * ALARM_PERCENT
            if hurt or ct.read_store(S_ALARM) == 1:
                ct.write_store(S_ALARM, 1)
                hurt = True
        except Exception:
            hurt = False

        cap = BUILDERS
        reserve = CHAIN_RESERVE
        if hurt:
            cap = SIEGE_BUILDERS
            reserve = ALARM_RESERVE''',
    '''        hurt = False
        try:
            hp, mx = ct.get_hp(), ct.get_max_hp()
            # ANY damage at all on the Core proves a fed enemy turret exists, tens of rounds
            # before the 88% alarm below is willing to say so. Same argument as _sense: a Builder
            # Bot cannot attack an adjacent tile (G13) and our own turrets never fire on our own
            # team, so nothing else on the board can have done it.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT
            hurt = hp * 100 < mx * ALARM_PERCENT
            if hurt or (self.state & ALARM_BIT):
                hurt = True
        except Exception:
            hurt = False
        if hurt:
            self.alarm = True

        # Arbitrate, then publish. The Core is the only writer of this slot, so the value it
        # reads back next round is the value it wrote -- which is why the alarm latch above can
        # be read out of `self.state` instead of out of the store.
        rnd = 0
        try:
            rnd = ct.get_current_round()
        except Exception:
            rnd = 0
        self._arbitrate(ct, rnd)
        self.state = (ALARM_BIT if self.alarm else 0) | (self.posture << POSTURE_SHIFT)
        try:
            ct.write_store(S_STATE, self.state)
        except Exception:
            pass

        cap = self._pv("builders")
        reserve = self._pv("chain_reserve")
        if hurt:
            cap = self._pv("siege_builders")
            reserve = self._pv("alarm_reserve")''')

sub('''        if self.spawned < ATTACKERS:''',
    '''        if self.spawned < self._pv("attackers"):''')

# ---------------------------------------------------------------------------
# 6. The posture machinery itself, spliced in ahead of the Core section.
# ---------------------------------------------------------------------------
sub('''    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct):''',
    '''    # ------------------------------------------------------------------
    # Posture -- the switch, the detector, and the seam every subsystem reads
    # ------------------------------------------------------------------

    def _pv(self, key):
        """This posture's value for a tuned parameter. THE seam.

        Every subsystem that used to read a module constant reads this instead: the spawn budget,
        the economy/attacker split, the turret policy, the builder's priority ordering. In the
        shipped build all three rows hold identical values, so the indirection is provably free --
        and the moment a specialist is written, exactly one number moves and nothing else does.
        """
        return POSTURE_PARAMS[self.posture][key]

    def _sync_state(self, ct):
        """Read the Core's published state word. One slot, one writer, everybody reads it.

        The alarm is bit 0 with exactly its old meaning, so `self.alarm` here is bit-for-bit the
        `read_store(S_ALARM) != 1` test it replaces, including on a failed read.
        """
        self.alarm = False
        try:
            raw = ct.read_store(S_STATE)
        except Exception:
            return
        self.alarm = (raw & ALARM_BIT) == ALARM_BIT
        p = (raw >> POSTURE_SHIFT) & 3
        self.posture = p if p < len(POSTURE_PARAMS) else POSTURE_RUSH

    def _sense(self, ct):
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
                pass
        n = len(self.foe_turrets)
        if n >= 1:
            self.evidence = self.evidence | EV_FOE_TURRET
        if n >= FOE_TURRETS_MANY:
            self.evidence = self.evidence | EV_FOE_TURRET2
        if len(self.foe_harvesters) >= FOE_HARVESTERS_MANY:
            self.evidence = self.evidence | EV_FOE_ECON

    def _scan_intruder(self, ct, tile, key):
        """Latch how deep into OUR half an enemy Builder Bot has been seen.

        Measured as a fraction of the core-to-core axis (0 = our Core, 100 = theirs), because a
        tile count means nothing across a pool that runs from 8x15 to 30x30. The axis comes free:
        `siege` already infers the enemy Core anchor from symmetry and every builder already
        holds it.

        A tell, not a proof -- an economy bot's builder can wander -- so it is worth one point,
        and only the near third is worth two.
        """
        bid = self._bot_at(ct, tile)
        if bid is None or not self._is_enemy(ct, bid):
            return
        ax = self.enemy_anchor[0] - self.core_pos.x
        ay = self.enemy_anchor[1] - self.core_pos.y
        norm = ax * ax + ay * ay
        if norm <= 0:
            return
        f = ((key[0] - self.core_pos.x) * ax + (key[1] - self.core_pos.y) * ay) * 100 // norm
        if f <= INTRUDER_HALF:
            self.evidence = self.evidence | EV_INTRUDER
        if f <= INTRUDER_DEEP:
            self.evidence = self.evidence | EV_DEEP

    def _arbitrate(self, ct, rnd):
        """Decide the team posture. Core only.

        A ratchet with a Schmitt trigger on top, not a controller: the evidence it reads is
        monotone, so this can only climb until something releases it, and the release exists for a
        future specialist rather than for today.

        BE HONEST ABOUT THE CLOCK. A posture decided at round R is published at R+1, read by a
        builder at R+2, and whatever it buys is standing perhaps twenty rounds after that. So the
        postures may differ in SCALE and must never differ in EXISTENCE: the minimum viable
        version of every subsystem is built unconditionally, and the posture only ever says how
        much more of it to buy. A defence that only exists once the detector has fired is a
        defence that arrives after the Core has.
        """
        try:
            self.evidence = self.evidence | (ct.read_store(S_FLAGS) & EV_MASK)
        except Exception:
            pass
        self.evidence = self.evidence | self.core_ev
        for bit in EV_BITS:
            if (self.evidence & bit) and bit not in self.ev_round:
                self.ev_round[bit] = rnd

        score = 0
        for bit, weight in EV_WEIGHTS:
            if self.evidence & bit:
                score += weight
        if self.alarm:
            score += ALARM_WEIGHT
        self.score = score

        want = self.posture
        if score >= POSTURE_CONFIDENCE:
            want = POSTURE_DEFENCE
        elif rnd >= ECONOMY_FROM and self.evidence == 0:
            # Nobody has touched us, nobody has been seen, nothing of ours has been shot. The
            # only remaining question is who banks more, and that is a tiebreak we win by
            # building chains rather than turrets (G01/G03).
            want = POSTURE_ECONOMY
        elif score <= POSTURE_RELEASE:
            want = POSTURE_RUSH
        if want == self.posture:
            return self.posture
        dwell = POSTURE_DWELL if self.switches else POSTURE_FIRST_DWELL
        if rnd - self.posture_round < dwell:
            return self.posture
        self.posture = want
        self.posture_round = rnd
        self.switches += 1
        return self.posture

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct):''')

# ---------------------------------------------------------------------------
# 7. The builder: sync the posture, sense, then run the ladder as data.
# ---------------------------------------------------------------------------
sub('''        self._load_atlas(ct)

        self._observe(ct, pos)
        self._infer_enemy_core(ct)
        self._read_ray(ct)''',
    '''        self._load_atlas(ct)

        self._sync_state(ct)
        self._observe(ct, pos)
        self._sense(ct)
        self._infer_enemy_core(ct)
        self._read_ray(ct)''')

sub('''        if self._is_rusher(ct) and self._run_rush(ct, pos):
            return

        # 1. Settle the belt we owe. Highest-value action in the game: nothing scores until the chain
        #    reaches the Core, so finishing always outranks starting (G02).
        if self._settle_owed(ct, pos):
            return
        # 2. The range-0 own-tile sabotage that used to live here is GONE on 2.3.3: `fire(own_pos)`
        #    raises and `can_fire(own_tile)` is False (G14 refuted). Its replacement -- the
        #    orthogonally adjacent 2 dmg / 2 Ti shot of G13 -- is given only to the rusher, in
        #    `_snipe`, because an economy builder that stops to shoot is a chain not built.
        # 2b. The base is under fire. Titanium only scores while there is a Core footprint for the
        #     stacks to land on (G01), so once the Core is being ground down, holding it outranks
        #     mining into it. Never interrupts a chain in flight -- an abandoned chain scores zero
        #     (G02) -- so a builder finishes what it started first.
        if self._hold_home(ct, pos):
            return
        # 3. Phase work.
        if self.phase == "harvest" and self._try_harvester(ct, pos):
            return
        if self.phase == "belt" and self._belt_step(ct, pos):
            return
        # A cut belt makes the ENTIRE chain upstream of it score zero (G02), and an enemy builder can
        # destroy a 20 HP conveyor for 20 Ti using the range-0 attack. Repairing one link costs ~3 Ti and
        # restores ~2.5 collected per round, so it outranks starting anything new.
        if self.phase == "seek" and self._repair_chain(ct, pos):
            return

        if self.phase == "seek":
            self._seek(ct, pos)
            if self.phase == "harvest" and self._try_harvester(ct, pos):
                return
        # 4. Repair anything friendly and damaged beside us.
        if self._heal(ct, pos):
            return
        # 5. Otherwise walk.
        self._walk(ct, pos)''',
    '''        if self._is_rusher(ct) and self._run_rush(ct, pos):
            return

        # 1-7. The priority ladder, in the order THIS POSTURE wants it. `ORDER_TODAY` is the
        #      ladder that used to be written out inline here, rung for rung and in the same
        #      order, and it is what all three postures currently use. Making the order data is
        #      the second seam: a DEFENCE specialist that wants healing ahead of prospecting, or
        #      an ECONOMY one that never bricks, changes a tuple instead of this function.
        for step in self._pv("order"):
            if self._step(ct, pos, step):
                return
        # 8. Otherwise walk.
        self._walk(ct, pos)

    def _step(self, ct, pos, step):
        """One rung of the builder's priority ladder. True if the round was spent.

        Every rung is the code that used to sit inline in `_run_builder`, moved verbatim.
        """
        if step == STEP_OWED:
            # Settle the belt we owe. Highest-value action in the game: nothing scores until the
            # chain reaches the Core, so finishing always outranks starting (G02).
            return self._settle_owed(ct, pos)
        if step == STEP_HOLD:
            # The base is under fire. Titanium only scores while there is a Core footprint for the
            # stacks to land on (G01), so once the Core is being ground down, holding it outranks
            # mining into it. Never interrupts a chain in flight -- an abandoned chain scores zero
            # (G02) -- so a builder finishes what it started first.
            return self._hold_home(ct, pos)
        if step == STEP_PHASE:
            if self.phase == "harvest" and self._try_harvester(ct, pos):
                return True
            if self.phase == "belt" and self._belt_step(ct, pos):
                return True
            return False
        if step == STEP_REPAIR:
            # A cut belt makes the ENTIRE chain upstream of it score zero (G02), and an enemy
            # builder can destroy a 20 HP conveyor for 20 Ti using the range-0 attack. Repairing
            # one link costs ~3 Ti and restores ~2.5 collected per round, so it outranks starting
            # anything new.
            if self.phase == "seek":
                return self._repair_chain(ct, pos)
            return False
        if step == STEP_SEEK:
            if self.phase == "seek":
                self._seek(ct, pos)
                if self.phase == "harvest" and self._try_harvester(ct, pos):
                    return True
            return False
        if step == STEP_HEAL:
            # Repair anything friendly and damaged beside us.
            return self._heal(ct, pos)
        return False''')

# ---------------------------------------------------------------------------
# 8. Economy/attacker split reads the posture.
# ---------------------------------------------------------------------------
sub('''                if claim == mine:
                    self.rush_role = True
                elif ATTACKERS < 2:''',
    '''                if claim == mine:
                    self.rush_role = True
                elif self._pv("attackers") < 2:''')

# ---------------------------------------------------------------------------
# 9. Spawn budget / turret budget / reserves read the posture.
# ---------------------------------------------------------------------------
sub('''        if self.battery_n >= siege.MAX_BATTERY:
            return False''',
    '''        # `None` in the row means "whatever siege thinks", so the table never duplicates a
        # constant that already has a home.
        cap = self._pv("max_battery")
        if cap is None:
            cap = siege.MAX_BATTERY
        if self.battery_n >= cap:
            return False''')

sub('''            if ct.get_global_resources() < ct.get_gunner_cost() + BATTERY_RESERVE:''',
    '''            if ct.get_global_resources() < ct.get_gunner_cost() + self._pv("battery_reserve"):''')

sub('''            if not self._rush_funded(ct):
                need += RUSH_RESERVE''',
    '''            if not self._rush_funded(ct):
                need += self._pv("rush_reserve")''')

# ---------------------------------------------------------------------------
# 10. The census, folded into the entity-type read _observe was already paying for.
# ---------------------------------------------------------------------------
sub('''        for tile in tiles:
            key = (tile.x, tile.y)''',
    '''        # An enemy Builder Bot inside our half is the second-cheapest archetype tell there is,
        # and unlike the census it is only worth paying for until it fires: the bit is latched
        # forever, so the scan switches itself off the moment it lands.
        scan_bots = (not (self.evidence & EV_DEEP)
                     and self.core_pos is not None and self.enemy_anchor is not None)
        for tile in tiles:
            key = (tile.x, tile.y)''')

sub('''                    try:
                        if ct.get_entity_type(occ) == EntityType.CORE:
                            if ct.get_team(occ) == ct.get_team():
                                self.core_tiles.add(key)
                            else:
                                self.enemy_core_tiles.add(key)
                                seen_at = ct.get_position(occ)
                                self.enemy_anchor = (seen_at.x, seen_at.y)
                                self.enemy_sighted = True
                    except Exception:
                        pass''',
    '''                    #
                    # The same entity-type read also runs the ENEMY CENSUS -- how many turrets and
                    # how many producers they have standing. It costs one extra get_team() on a
                    # tile we were already interrogating, and it is the only signal that
                    # distinguishes a greedy economy from an anti-rush before either has touched
                    # us.
                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        if et == EntityType.CORE:
                            if mine:
                                self.core_tiles.add(key)
                            else:
                                self.enemy_core_tiles.add(key)
                                seen_at = ct.get_position(occ)
                                self.enemy_anchor = (seen_at.x, seen_at.y)
                                self.enemy_sighted = True
                        elif not mine:
                            if et == EntityType.GUNNER or et == EntityType.SENTINEL:
                                self.foe_turrets.add(key)
                            elif et == EntityType.HARVESTER:
                                self.foe_harvesters.add(key)
                    except Exception:
                        pass
            if scan_bots:
                self._scan_intruder(ct, tile, key)''')

# ---------------------------------------------------------------------------
# 11. Symmetry and evidence share one write.
# ---------------------------------------------------------------------------
sub('''        try:
            ct.write_store(S_SYMMETRY, self.sym_mask)''',
    '''        try:
            # Slot 11 carries two monotone bitfields at once: the symmetry rejection mask in bits
            # 0-2 and the archetype evidence above it. Same writer, same round, same merge -- and
            # every reader of either field masks, so neither can see the other.
            ct.write_store(S_SYMMETRY, self.sym_mask | self.evidence)''')

# ---------------------------------------------------------------------------
# 12. A destroyed belt we can see is a raider tell.
# ---------------------------------------------------------------------------
sub('''                if self._building_at(ct, tile) is None:
                    self.repair_target = (tile, facing)
                    break''',
    '''                if self._building_at(ct, tile) is None:
                    # A belt of ours we can SEE is gone. Nothing friendly removes it -- our own
                    # turrets never fire on our own team -- so this is either their gunner or a
                    # builder standing on it with the range-0 attack (G14). The saboteur tell.
                    self.evidence = self.evidence | EV_ECON_HIT
                    self.repair_target = (tile, facing)
                    break''')

# ---------------------------------------------------------------------------
# 13. Coming home reads the posture; the fortification numbers come off the row.
# ---------------------------------------------------------------------------
sub('''        try:
            if ct.read_store(S_ALARM) != 1:
                return False
        except Exception:
            return False
        if self._heal(ct, pos):
            return True
        try:
            if ct.get_current_round() < FORTIFY_FROM:
                return False
            cost = ct.get_barrier_cost()
            if ct.get_global_resources() < cost + CHAIN_RESERVE:
                return False
        except Exception:
            return False''',
    '''        # Two ways in. The alarm is the measured one -- our own Core below ALARM_PERCENT, and
        # `self.alarm` is bit-for-bit the store read it replaces. The posture gate is the seam: a
        # DEFENCE specialist comes home on the fed-turret bit, which latches tens of rounds before
        # the Core has lost 12% of itself. RUSH leaves it off, so this is exactly today's
        # condition in the shipped build.
        if not (self.alarm or (self._pv("hold_on_posture")
                               and self.posture == POSTURE_DEFENCE)):
            return False
        if self._heal(ct, pos):
            return True
        try:
            if ct.get_current_round() < self._pv("fortify_from"):
                return False
            cost = ct.get_barrier_cost()
            if ct.get_global_resources() < cost + self._pv("chain_reserve"):
                return False
        except Exception:
            return False''')

sub('''        ring = self._core_ring(ct)
        free = [t for t in ring if self._building_at(ct, Position(t[0], t[1])) is None]
        if len(free) <= FORTIFY_KEEP_OPEN:
            return False''',
    '''        keep_open = self._pv("fortify_keep_open")
        ring = self._core_ring(ct)
        free = [t for t in ring if self._building_at(ct, Position(t[0], t[1])) is None]
        if len(free) <= keep_open:
            return False''')

sub('''        for t in free[:len(free) - FORTIFY_KEEP_OPEN]:''',
    '''        for t in free[:len(free) - keep_open]:''')

# ---------------------------------------------------------------------------
# 14. Turret policy consults the posture.
# ---------------------------------------------------------------------------
sub('''        if not self._is_enemy(ct, occupant):
            # Friendly or unknown in the ray. Firing destroys our own unit, and the engine keeps
            # offering this same target forever (G11) -- hold fire rather than shoot through it.
            return
        try:
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return''',
    '''        if not self._is_enemy(ct, occupant):
            # Friendly or unknown in the ray. Firing destroys our own unit, and the engine keeps
            # offering this same target forever (G11) -- hold fire rather than shoot through it.
            return
        if not self._may_fire(ct, occupant):
            return
        try:
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return

    def _may_fire(self, ct, occupant):
        """Posture hook on turret policy. True in every posture today.

        The seam is here because this is precisely where a DEFENCE specialist differs, and the
        2.3.3 ammunition model makes the argument STRONGER rather than weaker. Ammunition is one
        team-wide pool filled only by convert_ammo at the Core (G52), so every turret we own draws
        on the same purse: 2 Ti of it spent by a forward Gunner on the enemy conveyor that happens
        to be nearer in its lane is 2 Ti that is not there for the turret covering our own Core
        when their Builder Bot arrives. On 2.2.0 that waste was local to one magazine; now it is
        charged to the whole team.
        """
        self._sync_state(ct)
        want = self._pv("fire_only")
        if want is None:
            return True
        try:
            return ct.get_entity_type(occupant) in want
        except Exception:
            return True''')

# ---------------------------------------------------------------------------
# 15. Optional specialist rows.
# ---------------------------------------------------------------------------
if DEFENCE:
    sub('''DEFENCE_OVERRIDES = {}''',
        '''DEFENCE_OVERRIDES = {
    # ONE cheap difference, end to end: the detector latches the fed-turret bit, the Core flips to
    # DEFENCE, and two things change. The spawn cap goes to the siege cap without waiting for the
    # Core to have lost 12% of itself -- a heal is 4 HP for a flat 1 Ti and is NOT touched by the
    # global cost scale (G07), against their Gunner's 2 Ti for 10 damage, so a Builder standing on
    # the Core very nearly cancels a turret. And `hold_on_posture` makes the come-home rung
    # reachable on the same bit, which is what puts those Builders on the Core instead of out
    # prospecting.
    "builders": SIEGE_BUILDERS,
    "hold_on_posture": True,
}''')
if SHARP:
    # MEASURED RE-WEIGHTING. With the first weighting the two intruder bits alone reached the
    # confidence threshold, and they fire in 90-100% of games against every opponent that spawns
    # a Builder Bot at all -- luc1, lockin, jonbot AND vanguard -- so the detector collapsed to
    # "DEFENCE unless the enemy is inert": 23-30 of 30 games in DEFENCE against four of the five
    # panel bots. An intruder tells you somebody is walking about, not what they are.
    #
    # This makes the ZERO-FALSE-POSITIVE bit necessary and sufficient on its own, and demotes
    # everything else to corroboration that can never reach the threshold by itself
    # (1+1+1+1 = 4 < 5). Measured fire rates, over 54 mirrored games per opponent:
    #     idle 0%   starter_fixed 0%   luc1 50/0%   lockin 46/0%   jonbot 46/41%   vanguard 66/66%
    # -- i.e. it is silent against the two opponents that never land a shot on us and fires in
    # two thirds of games against the one that kills us, at a median round of 24 (known) and
    # 14 (unseen).
    sub('''EV_WEIGHTS = ((EV_HURT, 2), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 3''',
        '''EV_WEIGHTS = ((EV_HURT, 5), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 1), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 5''')
    sub('''POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1''',
        '''POSTURE_CONFIDENCE = 5
POSTURE_RELEASE = 0''')

if ECONOMY:
    sub('''ECONOMY_OVERRIDES = {}''',
        '''ECONOMY_OVERRIDES = {
    "attackers": 1,
    # "forward_deposits" removed with the doctrine (G52/G53/G57)
    "builders": BUILDERS + 1,
}''')

io.open(DST / "main.py", "w", encoding="utf-8", newline="\n").write(src)
print("wrote %s  (%d chars, defence=%s economy=%s)" % (DST / "main.py", len(src), DEFENCE, ECONOMY))
