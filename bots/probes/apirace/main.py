"""Turn order between the two TEAMS: simultaneous, or sequential -- and if sequential, who goes first?

Within a team the docs are explicit (units run in spawn order, Core first, and one unit's changes are
visible to the next).  Between teams nothing is documented at all.  A stable first-mover advantage
would be exploitable, and would also explain any A/B asymmetry in match results.

The race, on arena `close` (14x11, Core A anchor (1,5), Core B anchor (8,5)):

  Both teams walk a builder to a stance orthogonally adjacent to the SAME contested tile (5,5).
  Team A stands at (4,5); Team B stands at (6,5).  On rounds 40, 42, 44 and 46 both call
  build_barrier((5,5)).  Exactly one can win it; on the odd round in between, whoever owns it
  destroys it (destroy is free and costs no action cooldown), so the next race starts clean.

Two readings per race round:
  pre   what is on the contested tile at OUR turn, BEFORE we act:  '-' empty, 'us' ours, 'TH' theirs.
        'TH' means the other team's action for THIS round was already applied when we ran -- they act
        before us.
  bld   'Y' our build succeeded, 'n' it raised.

Four race rounds in one game answer STABLE vs ALTERNATING.

SPAWN_ROUND exists to separate two hypotheses that the default pairing cannot tell apart: "Team A's
units all act first" versus "all units act in ascending entity id, regardless of team".  Running
apiracel (spawns late, so its builder has the HIGHER id) as Team A against apirace as Team B puts a
low-id Team B builder against a high-id Team A builder.  If Team B then wins the tile, ordering is by
global entity id; if Team A still wins, ordering is by team.

Variants: `apiraceq` = identical, silent, spawns round 0.  `apiracel` = identical, silent, spawns
round 10.  Only one resign_message survives a game, so exactly one of the pair may report.
"""

from fcode import Controller, Direction, EntityType, GameError, Position, Team

REPORT = True
SPAWN_ROUND = 0
TILE = Position(5, 5)
ROUNDS = (40, 42, 44, 46)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.stance = None
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        mine = ct.get_team()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and r >= SPAWN_ROUND:
                q = Position(3, 5) if mine == Team.A else Position(7, 5)
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        if self.stance is None:
            self.stance = Position(4, 5) if mine == Team.A else Position(6, 5)
        pos = ct.get_position()

        if pos != self.stance:
            d = pos.cardinal_direction_to(self.stance)
            if ct.can_move(d):
                ct.move(d)
            return

        if r in ROUNDS:
            bid = ct.get_tile_building_id(TILE)
            pre = "-" if bid is None else self.owner(ct, bid, mine)
            try:
                ct.build_barrier(TILE)
                won = "Y"
            except GameError:
                won = "n"
            self.n.append("r%d %s%s" % (r, pre, won))
            return

        if r - 1 in ROUNDS:
            bid = ct.get_tile_building_id(TILE)
            if bid is not None and self.owner(ct, bid, mine) == "us":
                try:
                    ct.destroy(TILE)
                except GameError:
                    pass
            return

        if r == ROUNDS[-1] + 2:
            self.done = True
            if REPORT:
                ct.resign("RACE|side=%s|id=%d|%s" % (
                    str(mine)[-1], ct.get_id(), "|".join(self.n)))

    def owner(self, ct, bid, mine):
        try:
            return "us" if ct.get_team(bid) == mine else "TH"
        except GameError:
            return "?"
