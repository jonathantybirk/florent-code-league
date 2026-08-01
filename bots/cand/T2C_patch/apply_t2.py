"""TASK 2 -- PASSABLE BUILDINGS.  Anchored-substitution rebaser, like tools/apply_posture.py.

THE DEFECT.  `_observe` records every building it sees into `self.occupied` and
`self.known_blocked`, and every navigator in the bot -- the rusher's `_bfs_step`, the approach
flood in `_plan_rush` / `_extend_battery`, and the economy's `_nav_field` -- treats that set as
impassable. G61 measured the standing rule exhaustively and it does not say that:

    passable to a Builder Bot : empty ground, CONVEYORS, SPLITTERS
    not passable              : walls, harvesters, barriers, turrets, Core footprints

Conveyors are exactly what an opponent lays across the ground in front of its own Core, dozens of
them, and every one of them deletes a tile our rusher is allowed to stand on. Traced on
`bridge/a` vs `jonbot`: the planner published gunner tile (20,5) facing SOUTH at round 2 -- range
1 onto the enemy Core, a perfect plan. The only tile it can be built from is (19,5), because
(20,4) is a wall, (21,5) is off the map and (20,6) is the Core. jonbot put a CONVEYOR on (19,5)
on round 1. From then on `_bfs_step` could not seed its goal ring, returned None, and the greedy
`_step_toward` fallback walked the rusher N,S,N,S between (19,3) and (19,4) -- both of which also
held enemy conveyors it was standing on quite happily -- for 987 consecutive rounds. Zero
gunners, 4766 titanium banked, a 1000-round loss on the collected tiebreak. `string/a` is the
same picture with the same opponent: 970 rounds oscillating between (8,3) and (8,4).

THE FIX.  Split remembered occupancy by whether the thing on the tile is a WALL to a walker.
`occupied` keeps every building, because a conveyor is still a ballistic stopper (a shot is
absorbed by the first building in the lane whoever owns it) and still cannot be built on.
`passable_bld` is the conveyor/splitter subset, and it is subtracted from every set that means
"cannot walk here". The type read costs nothing: `_observe` already calls `get_entity_type` on
every occupied tile it does not recognise as a Core.

SECOND DEFECT, SAME SYMPTOM, DIFFERENT CAUSE (mode C).  `_run_rush`'s build branch spends the
round and returns True whenever the rusher is orthogonally adjacent to the tile it must build on,
whether or not the build succeeded, and touches no counter on failure. The comment there records
that an unconditional 45-round give-up was tried and MEASURED WORSE, because it abandoned firing
positions that were only waiting to be paid for. Both halves are right, and together they leave a
hole: any PERMANENT refusal freezes the rusher for the rest of the match. Traced on `atoll/b` vs
`luc1`: the plan was Gunner (4,13) facing SOUTHWEST, range 1 onto the enemy Core; luc1's Builder
Bot id8 parked ON (4,13) at round 2 and never left. A bot is not a building, so
`get_tile_building_id` returns None and the occupied-tile branch above never fires; the rusher
stood at (5,13) from round 13 to round 999 calling `can_build_gunner` on a tile with a body on it,
while our treasury climbed to 4506 titanium. Zero gunners, 1000 rounds, a loss on the tiebreak.

The fix keeps the measured lesson intact by separating the two reasons a build can be refused:
the give-up counter only advances on a round where the Gunner was AFFORDABLE and the engine still
said no. "Waiting to be paid for" therefore never trips it, and "there is a body on that tile"
trips it in eight rounds.

usage:  python apply_t2.py <src_bot_dir> <dst_bot_dir> [A|C]
        A = passable buildings only.  C = A + the affordable-refusal give-up.
"""
import io
import pathlib
import shutil
import sys

src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2])
mode = (sys.argv[3] if len(sys.argv) > 3 else "C").upper()
if dst.exists():
    shutil.rmtree(dst)
dst.mkdir(parents=True)
for f in src.glob("*.py"):
    shutil.copy(f, dst / f.name)

p = dst / "main.py"
s = io.open(p, encoding="utf-8").read()


def sub(old, new, n=1, when=("A", "C")):
    global s
    if mode not in when:
        return
    assert s.count(old) == n, (s.count(old), n, old[:90])
    s = s.replace(old, new)


# --- 1. the new memory -------------------------------------------------------------------
sub("""        self.enemy_core_tiles = set()
        self.occupied = set()
        self.occ_ver = 0""",
    """        self.enemy_core_tiles = set()
        self.occupied = set()
        # The subset of `occupied` that is NOT a wall to a walker. G61 measured the standing rule
        # exhaustively: a Builder Bot may stand on a CONVEYOR or a SPLITTER -- either team's, the
        # rule is about the building type and not about who owns it -- and may not stand on a
        # wall, a harvester, a barrier, a turret or a Core footprint. Those tiles stay in
        # `occupied`, because a conveyor is still a ballistic stopper and still cannot be built
        # on; they are simply subtracted from every set that means "cannot walk here".
        self.passable_bld = set()
        self.occ_ver = 0""")

# --- 2. classify on observation, using the entity-type read that is already being made -----
sub("""            else:
                if key not in self.occupied:
                    self.occupied.add(key)
                    self.occ_ver += 1
                self.known_blocked.add(key)
                if key not in self.core_tiles and key not in self.enemy_core_tiles:""",
    """            else:
                if key not in self.occupied:
                    self.occupied.add(key)
                    self.occ_ver += 1
                self.known_blocked.add(key)
                self.passable_bld.discard(key)
                if key not in self.core_tiles and key not in self.enemy_core_tiles:""")

sub("""                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        if et == EntityType.CORE:""",
    """                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        # A conveyor or a splitter is not an obstacle -- G61 verified a builder
                        # stepping onto one and reading the building id still underneath it. This
                        # is the single most common building on the board: an opponent lays its
                        # belt across the ground in front of its own Core, and every tile of it
                        # used to delete a tile our rusher was allowed to stand on.
                        if et == EntityType.CONVEYOR or et == EntityType.SPLITTER:
                            self.passable_bld.add(key)
                            self.known_blocked.discard(key)
                        if et == EntityType.CORE:""")

sub("""            if occ is None:
                if key in self.occupied:
                    self.occupied.discard(key)
                    self.occ_ver += 1
                self.known_blocked.discard(key)""",
    """            if occ is None:
                if key in self.occupied:
                    self.occupied.discard(key)
                    self.occ_ver += 1
                self.passable_bld.discard(key)
                self.known_blocked.discard(key)""")

# --- 3. the rusher's navigation ------------------------------------------------------------
sub("""            blocked = (self.known_walls | self.core_tiles | self.enemy_core_tiles
                       | self.occupied)""",
    """            blocked = (self.known_walls | self.core_tiles | self.enemy_core_tiles
                       | (self.occupied - self.passable_bld))""")

# --- 4. the approach flood the planner ranks firing positions with ------------------------
# `buildings` stays whole where it is passed to `siege` (a conveyor stops a shot and cannot be
# built on); only the WALK field loses the passable ones.
sub("""        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        dist = self._flood(ct, (pos.x, pos.y), blocked | (buildings - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            found = siege.plan(""",
    """        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        walls_to_a_walker = buildings - self.passable_bld
        dist = self._flood(ct, (pos.x, pos.y),
                           blocked | (walls_to_a_walker - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            found = siege.plan(""")

sub("""        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        dist = self._flood(ct, (pos.x, pos.y), blocked | (buildings - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            sites = siege.battery(""",
    """        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        walls_to_a_walker = buildings - self.passable_bld
        dist = self._flood(ct, (pos.x, pos.y),
                           blocked | (walls_to_a_walker - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            sites = siege.battery(""")


# --- 5. mode C: the give-up that can tell "no money" from "there is a body on that tile" ----
if True:
    sub("""# --- Ammunition (fcode 2.3.x) ---""",
        """# Rounds the rusher will keep asking for a build the engine refuses while it CAN AFFORD IT,
# before it gives the tile up and re-derives. The affordability test is the whole point: an
# unconditional patience was measured at 29-13 against 31-11 over 42 mirrored games because it
# abandoned firing positions that were only waiting to be funded, and that is the ONE reason a
# refusal is worth waiting out. Every other reason -- an enemy Builder Bot parked on the tile
# (measured on atoll/b vs luc1: 987 consecutive rounds asking, 4506 titanium banked, no Gunner),
# the team unit cap, a building that appeared and left no id we can read -- is permanent to us and
# is worth exactly the eight rounds it takes to notice.
BUILD_PATIENCE = 8

# --- Ammunition (fcode 2.3.x) ---""", when=("C", "G"))

    sub("""        self.rush_stuck = 0
        self.rush_i = 0""",
        """        self.rush_stuck = 0
        # Rounds spent asking for a build we could afford and were refused. See BUILD_PATIENCE.
        self.build_wait = 0
        self.rush_i = 0""", when=("C", "G"))

    sub("""    def _drop_plan(self):
        self.rush_route = None""",
        """    def _drop_plan(self):
        self.build_wait = 0
        self.rush_route = None""", when=("C", "G"))

    sub("""            if ok:
                self.rush_i += 1
                self.rush_dist = None
                self.rush_stuck = 0""",
        """            if ok:
                self.rush_i += 1
                self.rush_dist = None
                self.rush_stuck = 0
                self.build_wait = 0
            else:
                self._refused(ct, bxy, kind)""", when=("C", "G"))

    sub("""    def _is_our_gunner(self, ct, entity_id):""",
        """    def _refused(self, ct, bxy, kind):
        \"\"\"The engine said no from a legal tile. Wait it out, or give the tile up.

        Two reasons, and they want opposite answers. NOT ENOUGH TITANIUM is the normal state of a
        rusher that has walked ahead of its funding, it resolves itself, and abandoning the
        position over it measured 29-13 against 31-11. ANYTHING ELSE is permanent as far as this
        builder is concerned -- an enemy Builder Bot standing on the tile is the measured case, and
        a bot is not a building, so the occupied-tile branch above cannot see it. Separating them
        is one call to `get_global_resources`.
        \"\"\"
        try:
            cost = ct.get_gunner_cost()
            if kind == "conveyor":
                cost = ct.get_conveyor_cost()
            elif kind == "harvester":
                cost = ct.get_harvester_cost()
            if ct.get_global_resources() < cost:
                self.build_wait = 0
                return
        except Exception:
            self.build_wait = 0
            return
        self.build_wait += 1
        if self.build_wait < BUILD_PATIENCE:
            return
        self.build_wait = 0
        # Same split as the unreachable-tile handler in `_rush_walk`: an appended battery turret is
        # dropped on its own, and only the load-bearing first Gunner re-opens the whole plan.
        if self.rush_route and self.rush_i >= self.rush_base_len > 0:
            self._abort_segment(bxy)
        else:
            self.rush_black.add(bxy)
            self._drop_plan()

    def _is_our_gunner(self, ct, entity_id):""", when=("C", "G"))

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched %s mode=%s  (%d bytes)" % (p, mode, len(s)))
