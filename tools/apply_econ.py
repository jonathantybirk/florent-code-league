"""Economy fixes, as independently selectable anchored substitutions so each can be measured alone.

Every anchor is asserted unique, so this rebases onto a bot/ that moved underneath it and names
the moved anchor instead of applying in the wrong place (same pattern as tools/apply_posture.py).

usage: python tools/apply_econ.py <srcdir> <dstdir> [flags]

  --belt      our own conveyors/splitters stop being recorded as movement obstacles (G61)
  --straight  a chain is laid only on strictly core-ward steps -- no crooked links, no two-belt
              loops
  --unreach   a builder whose target is provably unreachable abandons it instead of orbiting it
  --beltstay  a builder with a chain in flight never wanders off to explore
  --explore   frontier exploration (walk to the nearest unseen tile) instead of greedy "away"
  --lab       no builder ever runs the siege -- the pure-economy measurement build

The shipped set is all five behaviour flags:
    python tools/apply_econ.py bot bots/cand/T4D --belt --straight --unreach --beltstay --explore
"""
import io
import pathlib
import shutil
import sys

SRC = pathlib.Path(sys.argv[1])
DST = pathlib.Path(sys.argv[2])
FLAGS = set(sys.argv[3:])

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
# 1. OUR OWN BELTS ARE NOT WALLS.  G61: a Builder Bot stands on conveyors and splitters.
#    `_observe` recorded EVERY building in `known_blocked`, which `_nav_field` treats as
#    impassable -- so the chain a builder lays behind it walls off the corridor it just walked,
#    and on a narrow map it walls off the whole far side of the board.
# ---------------------------------------------------------------------------
if "--belt" in FLAGS:
    sub('''                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        if et == EntityType.CORE:''',
        '''                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        # OUR OWN BELTS ARE NOT OBSTACLES. G61 measured the standing rules
                        # exhaustively: a Builder Bot walks onto conveyors and splitters and
                        # stands on them. `known_blocked` is the movement set `_nav_field`
                        # floods over, and recording a belt in it makes the chain we lay behind
                        # us a WALL across our own corridor. Measured on bridge/a: the builder
                        # that had just laid (5,3) and (6,3) was standing on (6,3), its own nav
                        # field said every tile east of x=5 was unreachable, and all six builders
                        # were in two-tile oscillations by round 15 for a final score of ZERO
                        # titanium collected. `occupied` keeps them -- that set means "a building
                        # is here", which is a different question and is what the siege planner
                        # and the ray checks need.
                        if mine and (et == EntityType.CONVEYOR or et == EntityType.SPLITTER):
                            self.known_blocked.discard(key)
                        if et == EntityType.CORE:''')

# ---------------------------------------------------------------------------
# 2. AN UNREACHABLE TARGET IS ABANDONED, NOT ORBITED.
#    `self.stuck` only counts rounds in which the STEP COMPUTATION failed. A builder walking at a
#    target it cannot reach still moves every round -- it just moves back and forth -- so `stuck`
#    stays 0 and `_abandon` never fires. `_nav_field` already answers the question exactly: it is
#    a flood FROM the target, so `field.get(our tile) is None` means no path over ground we know.
# ---------------------------------------------------------------------------
if "--unreach" in FLAGS:
    sub('''        if self.phase == "harvest" and self.target_ore is not None:
            target = Position(self.target_ore[0], self.target_ore[1])
            step = self._step_toward(ct, pos, target)''',
        '''        if self.phase == "harvest" and self.target_ore is not None:
            target = Position(self.target_ore[0], self.target_ore[1])
            if self._unreachable(ct, pos, target):
                self._abandon()
                return
            step = self._step_toward(ct, pos, target)''')

    sub('''    def _explore(self, ct, pos):''',
        '''    def _unreachable(self, ct, pos, target):
        """True when no path to `target` exists over ground we have already seen.

        `_nav_field` is a flood FROM the target over the known wall and building sets, so this is
        one dict lookup and no extra work at all. It is deliberately conservative: unobserved
        ground is treated as open by the flood, so this only fires when we have PERSONALLY seen
        the walls that seal the target off.
        """
        field = self._nav_field(ct, target)
        if field is None:
            return False
        return field.get((pos.x, pos.y)) is None

    def _explore(self, ct, pos):''')

# ---------------------------------------------------------------------------
# 3. FRONTIER EXPLORATION.
#    The old `_explore` steps toward whichever cardinal points away from the Core, with no memory
#    at all. Where the away direction is blocked on one tile and open on the neighbour, that is an
#    unbreakable two-tile cycle: measured on bridge/a, four of six builders spent rounds 11-1000
#    oscillating, discovered no further ore, and built nothing. Walk to the nearest tile we have
#    never seen instead -- same BFS machinery, and it terminates.
# ---------------------------------------------------------------------------
if "--explore" in FLAGS:
    sub('''    def _explore(self, ct, pos):
        """Spread out from the Core to find ore. Deterministic -- never the global random module (G26)."""
        core = self._nearest_core_tile(pos)
        if core is None:
            order = CARDINALS
        else:
            away = cardinal_of(pos.x - core.x, pos.y - core.y)
            order = (away,) + tuple(d for d in CARDINALS if d != away)
        offset = (self.ordinal or 0) % len(order)
        for i in range(len(order)):
            d = order[(i + offset) % len(order)]
            if self._passable(ct, pos, d):
                try:
                    ct.move(d)
                except Exception:
                    continue
                return''',
        '''    def _explore(self, ct, pos):
        """Walk toward the nearest tile we have never seen. Deterministic (G26/M02).

        The old version stepped toward whichever cardinal pointed away from the Core and had no
        memory whatsoever, so wherever the away direction is blocked on one tile and open on its
        neighbour it is an UNBREAKABLE TWO-TILE CYCLE -- and because both moves succeed,
        `self.stuck` is never touched and nothing ever notices. Measured on bridge/a against an
        inert opponent: four of the six builders oscillated from round 11 to round 1000,
        discovered not one further ore tile, and the game ended 0 titanium collected.

        A single BFS outward over the ground we know, stopping at the first unseen tile, cannot
        cycle: every step strictly decreases the distance to a frontier, and reaching one turns it
        into seen ground, which moves the frontier outward. ~w*h integer ops, and only on a
        builder that has nothing else to do.
        """
        step = self._frontier_step(ct, pos)
        if step is not None:
            try:
                ct.move(step)
                return
            except Exception:
                pass
        core = self._nearest_core_tile(pos)
        if core is None:
            order = CARDINALS
        else:
            away = cardinal_of(pos.x - core.x, pos.y - core.y)
            order = (away,) + tuple(d for d in CARDINALS if d != away)
        offset = (self.ordinal or 0) % len(order)
        for i in range(len(order)):
            d = order[(i + offset) % len(order)]
            if self._passable(ct, pos, d):
                try:
                    ct.move(d)
                except Exception:
                    continue
                return

    def _frontier_step(self, ct, pos):
        """First step of a shortest walk to the nearest tile absent from `self.seen`.

        BFS from where we stand rather than from a goal, because the goal is "any unseen tile" and
        there are many of them. Not cached: the frontier moves every round the builder does, and
        the flood stops at the FIRST unseen tile, so on an explored map it is a few hundred
        integer ops and on an unexplored one it stops almost immediately.
        """
        if not self._cpu_left(ct):
            return None
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        start = (pos.x, pos.y)
        walls, blocked, seen = self.known_walls, self.known_blocked, self.seen
        first = {}
        frontier = []
        for d in CARDINALS:
            n = pos.add(d)
            key = (n.x, n.y)
            if not (0 <= key[0] < w and 0 <= key[1] < h):
                continue
            if key in walls or key in blocked or key in first:
                continue
            if key not in seen:
                return d if self._passable(ct, pos, d) else None
            first[key] = d
            frontier.append(key)
        goal_dir = None
        while frontier and goal_dir is None:
            nxt = []
            for cx, cy in frontier:
                d0 = first[(cx, cy)]
                for nb in ((cx, cy - 1), (cx + 1, cy), (cx, cy + 1), (cx - 1, cy)):
                    if nb in first or nb == start:
                        continue
                    if not (0 <= nb[0] < w and 0 <= nb[1] < h):
                        continue
                    if nb in walls or nb in blocked:
                        continue
                    first[nb] = d0
                    if nb not in seen:
                        goal_dir = d0
                        break
                    nxt.append(nb)
                if goal_dir is not None:
                    break
            frontier = nxt
        if goal_dir is None:
            return None
        return goal_dir if self._passable(ct, pos, goal_dir) else None''')

# ---------------------------------------------------------------------------
# 4. A BUILDER WITH A CHAIN IN FLIGHT NEVER WANDERS.
#    `_walk` falls through to `_explore` for ANY phase that is not "harvest" -- including "belt".
#    So the single round in which `_belt_step` cannot find a legal sidestep beside the Core hands
#    the builder to the explorer, which walks it away from its own half-built chain WITHOUT
#    owing the belt on the tile it vacates. That is a permanent gap, and a chain with a gap
#    scores exactly zero (G02). Measured on crossfire/a: same ten harvesters at the same rounds
#    with and without frontier exploration, 14520 collected against 4960 -- the entire difference
#    is chains abandoned mid-flight, and a better explorer makes it WORSE because it wanders
#    further.
# ---------------------------------------------------------------------------
if "--beltstay" in FLAGS:
    sub('''            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return
        self._explore(ct, pos)''',
        '''            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return
        if self.phase == "belt":
            # A CHAIN IN FLIGHT IS NEVER ABANDONED FOR A WALK. Every tile this builder vacates
            # owes a conveyor (`self.owed`), and the only code that owes one is `_belt_step`.
            # Moving from here would leave a hole in the chain, and a chain with a hole delivers
            # nothing at all for the rest of the match (G02). Stand still instead: the position
            # stuck counter in `_run_builder` is already ticking, so a genuinely wedged builder
            # still gives the chain up after five rounds and goes back to prospecting.
            if self.stuck >= 5:
                self._abandon()
            return
        self._explore(ct, pos)''')

# ---------------------------------------------------------------------------
# 5. A CHAIN IS LAID ONLY ON STRICTLY CORE-WARD STEPS.
#    `_belt_step` owes a conveyor on EVERY tile it vacates, and it walks with `_step_toward`,
#    whose fallbacks are "any cardinal that rotates off the wanted one" and then "any passable
#    cardinal at all". So a builder shoved sideways by another builder lays the chain sideways,
#    and a builder that steps back the way it came lays a belt pointing at a belt pointing back at
#    it. That pair is a permanent two-tile loop: the stack bounces between them forever and the
#    harvester behind it delivers NOTHING for the rest of the match. Measured on aurora/a, belts
#    (4,15) facing SOUTH and (4,16) facing NORTH, feeding a harvester built on round 7 that
#    scored zero for 993 rounds.
#    The nav field is a flood FROM the Core, so "strictly decreasing" is exactly "closer to the
#    Core", and a trail of strictly decreasing tiles cannot revisit one -- no loop is
#    constructible. When no descending step is legal the builder WAITS rather than laying a
#    crooked link; the position stuck counter still gives the chain up after five rounds.
# ---------------------------------------------------------------------------
if "--straight" in FLAGS:
    sub('''        step = self._step_toward(ct, pos, target)
        if step is None:
            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return False
        try:
            ct.move(step)
        except Exception:
            return False
        # Owe a belt on the tile we just left, facing exactly the way we walked.''',
        '''        step = self._belt_move(ct, pos, target)
        if step is None:
            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return False
        try:
            ct.move(step)
        except Exception:
            return False
        # Owe a belt on the tile we just left, facing exactly the way we walked.''')

    sub('''    def _finish_chain(self, ct):''',
        '''    def _belt_move(self, ct, pos, target):
        """A step that STRICTLY shortens the walk to `target`, or None.

        `_step_toward` is the general-purpose stepper and its fallbacks are deliberately loose --
        rotate off the wanted direction, then take any passable cardinal at all -- because for a
        builder merely travelling, a sideways shuffle beats standing still. For a builder LAYING A
        CHAIN it is the opposite: every tile it vacates gets a conveyor pointing the way it
        walked, so a loose step is a permanently crooked link, and a step back the way it came is
        a two-belt loop that zeroes the chain for the rest of the match (G02).
        """
        field = self._nav_field(ct, target)
        if field is None:
            return None
        here = field.get((pos.x, pos.y))
        if here is None:
            return None
        best, best_d = None, here
        for d in CARDINALS:
            n = pos.add(d)
            nd = field.get((n.x, n.y))
            if nd is None or nd >= best_d:
                continue
            try:
                if not ct.can_move(d):
                    continue
            except Exception:
                continue
            best, best_d = d, nd
        return best

    def _finish_chain(self, ct):''')

# ---------------------------------------------------------------------------
# lab build: no siege at all, so `idle` survives 1000 rounds and titanium_collected is a pure
# measurement of the economy.
# ---------------------------------------------------------------------------
if "--lab" in FLAGS:
    sub('''        if siege is None or self.core_pos is None:
            return False
        if self.rush_role is None:''',
        '''        if ECON_LAB:
            self.rush_role = False
            return False
        if siege is None or self.core_pos is None:
            return False
        if self.rush_role is None:''')
    sub('''ATTACKERS = 2''', '''ATTACKERS = 2
ECON_LAB = True''')

io.open(DST / "main.py", "w", encoding="utf-8", newline="\n").write(src)
print("wrote", DST / "main.py", sorted(FLAGS))
