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

## Measured (local gate, deterministic)

- Official 21-map pool, both seats, 8-bot panel (casemate, gobbleglitch,
  vigil, ragnarok, valkyrie, warden, vanguard, warden_walk):
  **308/336 = 0.917, every opponent ≥ 0.81** (heimdall: 304/336 = 0.905).
- 40 generated unknown maps vs vigil + ragnarok, both seats:
  **134/160 = 0.838** — identical to heimdall. The combo is +4 on-pool,
  neutral off-pool.
