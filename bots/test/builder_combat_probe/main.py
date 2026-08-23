"""Empirical probe: can a Builder Bot's Attack ever reduce an ENEMY Builder
Bot's HP -- either directly, or as collateral when the target tile also
carries a building the enemy Builder Bot happens to be standing on?

docs/official/docs/game-rules-builder-bot.txt's Attack section says a
Builder Bot "can attack the building on any orthogonally adjacent tile" --
building, not unit -- and tests/fake_controller.py's can_fire() for a
BUILDER_BOT attacker only ever checks `building_at(target) is not None`,
never builder_at(target). Neither source describes any way to damage an
enemy Builder Bot directly. But docs/official/docs/robot-api.txt's heal()
is explicitly documented as a *dual* hit: "if a friendly Builder Bot is
standing on a friendly building on the target tile, both are healed in the
same call." If Attack mirrors that (a building hit also damaging whatever
Builder Bot is standing on it, friend or foe), that would be a real,
undocumented way to hurt an enemy Builder Bot -- and would explain a claim
that an allied Builder Bot can meaningfully speed up killing an enemy one,
which neither doc source otherwise supports. This settles it against the
real engine instead of guessing, the same way bots/test/splitter_probe
settled the Splitter rotation question and bots/test/vision_probe settled
vision-gating.

Two conditions are measured, back to back, against the same enemy Builder
Bot:

  Phase 1 (bare ground): the TARGET stands on empty ground, adjacent to
  the ATTACKER. get_tile_building_id(target_pos) is None here -- this is
  the plain case the docs describe, expected to leave can_fire() False and
  HP unchanged.

  Phase 2 (on a building): once Phase 1 has been observed for a few
  rounds, the TARGET builds a Conveyor on a tile away from the ATTACKER
  and steps onto it (Conveyor/Splitter tiles are Builder-Bot-passable --
  see the Passable list in game-rules-builder-bot.txt) and stands there.
  The ATTACKER re-approaches and keeps firing at that same tile, which now
  has both a building and the TARGET on it. If TARGET's HP ever drops here
  while Phase 1 showed no drop, Attack has the same dual-hit behavior as
  heal(); if it doesn't, Attack only ever damages the building.

Two bots, not one self-branching probe: TARGET (bots/test/builder_combat_
probe run as team B here) is intentionally passive -- it never fights back
and never flees -- so HP changes can be attributed to ATTACKER's Attack
calls alone, not confounded by combat or evasion. ATTACKER is the "real"
probe; TARGET's whole job is to sit still and, once, relocate onto a
Conveyor on cue.

Run as (different bots per side, unlike the same-bot-both-sides pattern in
vision_probe/splitter_probe):

    uv run fcode run bots/test/builder_combat_probe bots/test/builder_combat_probe/target <map> --seed N

ATTACKER's Core resigns with the full result once both phases have been
observed (or GIVE_UP_ROUND is hit, or the target is destroyed -- unlikely
given Attack's 2 damage/hit vs. 40 HP, but handled).
"""

from __future__ import annotations

import random

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

PHASE1_ROUNDS_BEFORE_TRANSITION = 5  # adjacent rounds to observe bare-ground before TARGET relocates
PHASE2_ROUNDS_BEFORE_REPORT = 5  # adjacent rounds to observe on-building before resigning
GIVE_UP_ROUND = 700  # generous -- exploration across a 30x30 map plus two observation phases


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def _try(fn):
    try:
        return fn(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _adjacent_direction(pos: Position, target: Position) -> Direction | None:
    for d in CARDINALS:
        if pos.add(d) == target:
            return d
    return None


def _step_toward(ct: Controller, pos: Position, target: Position) -> None:
    """One cardinal step toward target, with a wall-avoiding fallback --
    same shape as common/toolbox.py's try_move_toward, reimplemented here
    so this probe stays a single self-contained file."""
    primary = pos.cardinal_direction_to(target)
    options = [primary] if primary != Direction.CENTRE else []
    options += [d for d in CARDINALS if d != primary]
    for d in options:
        if ct.can_move(d):
            ct.move(d)
            return


class Player:
    """ATTACKER (run this directory directly as one side of the match)."""

    def __init__(self):
        self.search_target: Position | None = None
        self.enemy_id: int | None = None
        self.phase1_rounds = 0
        self.phase1_can_fire_true = 0
        self.phase1_hp_drop_observed = False
        self.phase1_hp_start: int | None = None
        self.phase1_hp_last: int | None = None
        self.phase2_rounds = 0
        self.phase2_can_fire_true = 0
        self.phase2_hp_drop_observed = False
        self.phase2_hp_start: int | None = None
        self.phase2_hp_last: int | None = None
        self.transitioned = False
        self.reported = False
        self.last_fire_error: str | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        if ct.get_unit_count() < 2:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break
        if not self.reported and ct.get_current_round() >= GIVE_UP_ROUND:
            self._report(ct, timed_out=True)

    def _run_builder(self, ct: Controller) -> None:
        if self.reported:
            return

        pos = ct.get_position()
        if self.search_target is None:
            # Mirror own start through the map centre -- a reasonable
            # heuristic for "toward the enemy side" without knowing where
            # the enemy Core actually is yet.
            w, h = ct.get_map_width(), ct.get_map_height()
            self.search_target = Position(w - 1 - pos.x, h - 1 - pos.y)

        if self.enemy_id is None:
            self._scan_for_enemy(ct)

        if self.enemy_id is None:
            self._step_toward_or_explore(ct, pos, self.search_target)
            return

        enemy_pos, err = _try(lambda: ct.get_position(self.enemy_id))
        if err is not None:
            # Lost the target entirely (shouldn't happen -- TARGET never
            # moves out of range once adjacent -- but never trust that).
            self.enemy_id = None
            return

        facing = _adjacent_direction(pos, enemy_pos)
        if facing is None:
            self._step_toward_or_explore(ct, pos, enemy_pos)
            return

        self._probe_round(ct, enemy_pos)

    def _scan_for_enemy(self, ct: Controller) -> None:
        my_team = ct.get_team()
        for uid in ct.get_nearby_entities():
            if ct.get_team(uid) != my_team and ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
                self.enemy_id = uid
                return

    def _step_toward_or_explore(self, ct: Controller, pos: Position, target: Position) -> None:
        if pos == target:
            open_dirs = [d for d in CARDINALS if ct.can_move(d)]
            if open_dirs:
                ct.move(random.choice(open_dirs))
            return
        _step_toward(ct, pos, target)

    def _probe_round(self, ct: Controller, enemy_pos: Position) -> None:
        hp_before, hp_err = _try(lambda: ct.get_hp(self.enemy_id))
        building_id, _ = _try(lambda: ct.get_tile_building_id(enemy_pos))
        can_fire = ct.can_fire(enemy_pos)

        if can_fire:
            _, fire_err = _try(lambda: ct.fire(enemy_pos))
            self.last_fire_error = fire_err
        else:
            self.last_fire_error = None

        hp_after, _ = _try(lambda: ct.get_hp(self.enemy_id))

        on_building = building_id is not None
        if not self.transitioned and on_building:
            # TARGET relocated onto its Conveyor -- Phase 1 is over even
            # if we haven't hit PHASE1_ROUNDS_BEFORE_TRANSITION yet.
            self.transitioned = True

        if not self.transitioned:
            self.phase1_rounds += 1
            if self.phase1_hp_start is None:
                self.phase1_hp_start = hp_before
            if can_fire:
                self.phase1_can_fire_true += 1
            if hp_after is not None and self.phase1_hp_last is not None and hp_after < self.phase1_hp_last:
                self.phase1_hp_drop_observed = True
            self.phase1_hp_last = hp_after if hp_after is not None else self.phase1_hp_last
            if self.phase1_rounds >= PHASE1_ROUNDS_BEFORE_TRANSITION:
                self.transitioned = True
        else:
            self.phase2_rounds += 1
            if self.phase2_hp_start is None:
                self.phase2_hp_start = hp_before
            if can_fire:
                self.phase2_can_fire_true += 1
            if hp_after is not None and self.phase2_hp_last is not None and hp_after < self.phase2_hp_last:
                self.phase2_hp_drop_observed = True
            self.phase2_hp_last = hp_after if hp_after is not None else self.phase2_hp_last
            if self.phase2_rounds >= PHASE2_ROUNDS_BEFORE_REPORT:
                self._report(ct, timed_out=False)

    def _report(self, ct: Controller, *, timed_out: bool) -> None:
        ct.resign(
            message=(
                f"{'TIMED_OUT ' if timed_out else ''}"
                f"round={ct.get_current_round()} "
                f"PHASE1(bare ground): rounds={self.phase1_rounds} "
                f"can_fire_true={self.phase1_can_fire_true} "
                f"hp_start={self.phase1_hp_start} hp_end={self.phase1_hp_last} "
                f"hp_drop_observed={self.phase1_hp_drop_observed} | "
                f"PHASE2(on building): rounds={self.phase2_rounds} "
                f"can_fire_true={self.phase2_can_fire_true} "
                f"hp_start={self.phase2_hp_start} hp_end={self.phase2_hp_last} "
                f"hp_drop_observed={self.phase2_hp_drop_observed} | "
                f"last_fire_error={self.last_fire_error} "
                f"enemy_found={self.enemy_id is not None}"
            )
        )
        self.reported = True
