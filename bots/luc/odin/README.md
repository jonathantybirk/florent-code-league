# Odin

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

## Measured (local gate, deterministic)

- Official 21-map pool, both seats, 8-bot panel (casemate, gobbleglitch,
  vigil, ragnarok, valkyrie, warden, vanguard, warden_walk):
  **313/336 = 0.932, every opponent ≥ 0.81** (heimdall 304, repair-cap-only
  odin 308). Per-map minimum: bridge 12/16; every other map ≥ 0.81.
- 40 generated unknown maps vs vigil + ragnarok, both seats:
  **135/160 = 0.844** (heimdall and first odin: 134).
- Sibling matchups (heimdall, pantheon_replica_day3) byte-identical to the
  first odin: the projection never fires there.
