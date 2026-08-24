# Jotunn

`odin` at `93e46da3d` with one change, and it is a **negative result kept for
the record**: the attacker Builder never rushes the enemy Core and spends the
whole match on their economy instead -- barriers on their ore, cuts in their
belts.

The reasoning was that this is a different win condition rather than a tuned
version of the same one. A Core kill needs a Builder to out-trade turrets it
cannot afford to fight; denial needs only to arrive, since a 3 Ti barrier on an
ore tile removes that tile's income for the rest of the match and the round-1000
tiebreak is decided on titanium delivered. BLITZ is exempt, because when the two
Cores are close the match is a race and the Core kill lands first.

## Measured -- it does not work

fcode 2.3.3, 21 official maps, both seats. The run was cut short at 171 games:

| bot | score |
|---|---|
| odin (baseline, 336 games) | 0.821 |
| fenrir2 (336 games) | 0.860 |
| **jotunn** | **0.526** |

Per opponent: heimdall 0.357, ragnarok_fair 0.500, steward 0.524,
tempest_reinf 0.667 (3 games), vigil_reinf2 0.714.

A loss of ~30pp against the same baseline. Denial alone does not substitute for
the threat of a Core kill: an opponent that is never threatened at home is free
to spend everything on its own economy, and out-mines the denial faster than the
barriers remove income. Kept unshipped so the idea is not re-invented.

> Measured before the Aug 4 turret patch (fcode <= 2.3.3).

---

## Inherited notes from the parent

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`heimdall` (at `dfa9229f7`) plus the three-change combo that was measured to
0.917 on the night of Aug 3–4 but never shipped because that session was cut
off. Atlas-free and fair by construction, like its parent. Three changes,
nothing else:

1. **`REPAIR_ATTEMPT_LIMIT = 3`** — stop rebuilding a belt tile after the
   third attempt. Traced on `bridge`: the one conveyor tile routing our belt
   through the map's single fighting corridor sat inside an enemy Gunner's
   ray, `REPAIR_NETWORK` rebuilt it **22 times** (66 Ti + 22% compounding
   scale), and the bot mined 10 titanium in 1000 rounds. A hole that keeps
   reappearing is not damage — it is a tile the enemy controls, and the belt
   has to go somewhere else. With the cap, the same bridge seat mines 2,340.
2. **`AVOID_ENEMY_RAYS = False`** — the ray-dodging detour no longer pays on
   this chassis.
3. **`SIEGE_BARRIER_ENABLED = False`** — siege barriers no longer pay on this
   chassis.

Both flags are worked examples of the standing rule: *a constant is only
measured for the bot it was measured on.* Each was worth real games on an
older, atlas-carrying, guardless chassis and re-measured negative on heimdall.

## The Core-death projection (second commit)

Lucas's idea, built from the traced jackpot loss: the bot died on round 192
holding **762 banked titanium**, because the guard Builder had been killed on
round 143, the only survivor was the attacker across the map, and nothing in
the lineage replaces a dead defender while income is healthy. The Core now
projects its own death — damage rate over the last 20 rounds, dead within 60
at that rate, judged only after round 40 (an early rush is the reactive
guard's fight; spawning bodies into one is the measured −30pp refill
catastrophe) — and spawns up to two Builders under a `CORE_DYING_FLAG`. The
first runs the guard kit; the second is a dedicated mender, because in the
trace both defenders chose turret duels and the Core was healed exactly once
all game while 4 HP/1 Ti healing was affordable forever. The traced loss is
now a 1000-round tiebreak win, 5,180 mined vs 2,910.

## Line-of-sight discipline (fourth commit)

Lucas's constraint: never seat an attack turret where an enemy turret can
already shoot it, prefer seats it cannot reach even by rotating (a rotation
is a flat 10 Ti), and when a covered seat is literally the only one, take it
under duel rules — one such turret at a time, built *facing the covering
turret* so it kills the threat before rotating on to its real target, with
its Builder standing adjacent healing it through the duel (4 HP for a flat
1 Ti beats the 10 dmg/round it takes). Two scope cuts, both measured, both
load-bearing: **not under BLITZ** (the seat detours and healing titanium
lose the mutual-kill tiebreak — showdown 16/16 → 13/16 with it on) and
**attack seats only, never the guard** (the corridor tiles the belt needs
covered are exactly the tiles enemy turrets shoot down).

## Measured (local gate, deterministic)

- Official 21-map pool, both seats, 8-bot panel (casemate, gobbleglitch,
  vigil, ragnarok, valkyrie, warden, vanguard, warden_walk):
  **311/336 = 0.926, every opponent ≥ 0.81** (heimdall 304; odin lineage
  308 → 313 → 312 → 311 as the unknown-map arm climbed 134 → 140). Per-map:
  showdown, vase, sweden back to 16/16; bridge 10/16 is the one map under
  0.81 — all its losses are round-1000 tiebreaks, two by 80–130 Ti.
- 40 generated unknown maps vs vigil + ragnarok, both seats:
  **140/160 = 0.875** — the best off-pool score in the record (heimdall
  134; the pool−1/arm+3 trade is the same bet as the tabu port, made
  because the final is played on terrain nobody tuned against).
- Duel tend 15 vs 40 rounds: byte-identical on all 496 games — duels
  resolve fast; the tend bound never binds.
- Sibling matchups (heimdall, pantheon_replica_day3) byte-identical to the
  first odin: the projection never fires there.
