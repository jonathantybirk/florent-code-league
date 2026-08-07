"""diag -- re-verify, against the live engine, every fact lib/ is built on.

    uv run fcode run modulah/diag starter maps/eider.map26 --tle 0

Not a competitor. It plays a few rounds, asserts the engine still behaves the
way the library assumes, prints PASS/FAIL per check and resigns with a summary.

This exists because every tuned constant in this repo was measured against a
version of the game that may no longer exist, and because two of lib/'s load-
bearing facts have uncomfortably little margin:

  * Core vision (dist_sq 36) exceeds the longest reach anything has against
    the Core (Sentinel diagonal, dist_sq 32) by only 4. If a patch lengthens
    the Sentinel ray by one diagonal step, the Core stops being able to see
    everything that can shoot it, and threat.max_burst silently starts
    under-reporting instead of failing.

  * The store's one-round write latency is what makes the t+1 economy bucket
    dead and the t+2..t+6 window correct. If writes ever became visible
    within a round, the whole schedule would be off by one.

Run it after every fcode bump, before trusting anything in lib/.
"""

from __future__ import annotations

import sys

from fcode import Controller, EntityType, GameConstants, GameError

from geometry import COMPASS, RAY_LEN, can_ray_reach, core_footprint

PROBE_SLOT = 15
SENTINEL_VALUE = 0xABCD


def _emit(ok: bool, label: str, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {label}{(' -- ' + detail) if detail else ''}", file=sys.stderr, flush=True)
    return ok


class Player:
    def __init__(self):
        self.results: list[bool] = []
        self.wrote_at = None

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()
        try:
            if r == 2:
                self._check_rays(ct)
                self._check_vision(ct)
                self._check_reach_margin(ct)
                ct.write_store(PROBE_SLOT, SENTINEL_VALUE)
                self.wrote_at = r
                self.results.append(
                    _emit(
                        ct.read_store(PROBE_SLOT) != SENTINEL_VALUE,
                        "store write is not visible in the round it was made",
                    )
                )
            elif self.wrote_at is not None and r == self.wrote_at + 1:
                self.results.append(
                    _emit(
                        ct.read_store(PROBE_SLOT) == SENTINEL_VALUE,
                        "store write is visible on the very next round",
                    )
                )
                ok = sum(self.results)
                ct.resign(message=f"diag {ok}/{len(self.results)} checks passed")
        except GameError as exc:
            _emit(False, "diag aborted", str(exc))

    # --- checks -------------------------------------------------------------

    def _check_rays(self, ct: Controller) -> None:
        """geometry.can_ray_reach must agree tile-for-tile with the engine.

        Compared against the union of get_attackable_tiles_from over all 8
        facings, which is exactly the claim can_ray_reach makes: could a
        turret here ever hit that tile, at some facing.
        """
        me = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        for kind in (EntityType.GUNNER, EntityType.SENTINEL):
            engine = set()
            for d in COMPASS:
                for t in ct.get_attackable_tiles_from(me, d, kind):
                    engine.add((t.x - me.x, t.y - me.y))
            lib = {
                (dx, dy)
                for dx in range(-8, 9)
                for dy in range(-8, 9)
                if can_ray_reach(kind, dx, dy)
                and 0 <= me.x + dx < w
                and 0 <= me.y + dy < h
            }
            self.results.append(
                _emit(
                    engine == lib,
                    f"{kind.name} ray table matches engine",
                    f"engine={len(engine)} lib={len(lib)} "
                    f"missing={sorted(engine - lib)} extra={sorted(lib - engine)}",
                )
            )

    def _check_vision(self, ct: Controller) -> None:
        """Core vision must be the UNION of radius discs over the 2x2 footprint.

        A single disc of radius_sq 36 holds 113 tiles; the union over four
        footprint tiles holds 140. If this ever reads 113, the footprint union
        has gone away and every hop-6 economy bucket becomes unreliable.
        """
        foot = core_footprint(ct)
        self.results.append(_emit(len(foot) == 4, "core footprint is 2x2", f"got {len(foot)}"))

        vis = ct.get_nearby_tiles()
        expected = set()
        for f in foot:
            for dx in range(-7, 8):
                for dy in range(-7, 8):
                    if dx * dx + dy * dy <= GameConstants.CORE_VISION_RADIUS_SQ:
                        x, y = f.x + dx, f.y + dy
                        if 0 <= x < ct.get_map_width() and 0 <= y < ct.get_map_height():
                            expected.add((x, y))
        got = {(t.x, t.y) for t in vis}
        self.results.append(
            _emit(got == expected, "vision is the union of footprint discs",
                  f"engine={len(got)} predicted={len(expected)}")
        )

        # Hop h sits at most h steps from the footprint, so hop 6 is the last
        # one guaranteed visible for any chain shape. Check the straight-line
        # worst case explicitly.
        worst = max(f.distance_squared(t) for f in foot for t in vis)
        self.results.append(
            _emit(worst >= 36, "vision reaches at least radius 6 from a footprint tile",
                  f"max dist_sq from nearest footprint tile ~ {worst}")
        )

    def _check_reach_margin(self, ct: Controller) -> None:
        """The margin that makes 'the Core sees everything that can shoot it' true."""
        me = ct.get_position()
        worst = 0
        for kind in RAY_LEN:
            for d in COMPASS:
                for t in ct.get_attackable_tiles_from(me, d, kind):
                    worst = max(worst, me.distance_squared(t))
        margin = GameConstants.CORE_VISION_RADIUS_SQ - worst
        self.results.append(
            _emit(
                margin > 0,
                "core vision still exceeds the longest turret reach",
                f"vision_sq={GameConstants.CORE_VISION_RADIUS_SQ} "
                f"worst_reach_sq={worst} margin={margin}",
            )
        )
