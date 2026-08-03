# Valkyrie

`ragnarok` with the opening reordered around ladder evidence. Two changes, both
switchable, neither yet distinguishable from noise on 42 local games — this is
a tournament candidate, not a measured improvement.

## What changed

**`PAD_FIRST_ORDER`** — spawn the Launcher-ring Builder first instead of last.

Ragnarok already calls the ring "a throw pad for the ferry" but spawns its
builder third, so the pad is up around round 6 while the attacker, spawned on
round 1, has already given up and started building its own Launcher to escape
from. Pad first means the pad exists before the attacker needs it. The Core's
spawn placement in `core.py` follows the same order, or a Builder spawns at the
wrong end of the map for the job it picks up.

**Ferry gate** — `_opening_ferry` refused to run whenever `p.atlas is None`.
Off the published pool that is *always*, so on a generated map, the held-out
evaluation set, or whatever the final is played on, the entire relay disabled
itself and the attacker walked. It now runs whenever the enemy Core is known,
which means the atlas *or* a unit having physically seen it.

## Where the ladder evidence came from

Decoded from `.replay26` protobuf (schema recovered from the bundled
visualiser) for Pantheon (#1), Erebus (#2) and CtrlAltDefeat (#4).

- Pantheon plays one fixed opening on every map: Builder round 0, Launcher
  round 1 on the enemy-facing side at radius 2, one throw per round on rounds
  2-5 (two raiders at the enemy Core, two economy Builders out to distant ore),
  Launcher razed round 6. It bypasses chokepoints entirely — on `pinch` it
  throws over a two-tile wall band for a round-24 Core kill.
- Erebus, one rating point behind, builds **no Launcher at all** and wins two
  of five against CtrlAltDefeat on the round-1000 titanium tiebreak.
- The three games CtrlAltDefeat took off Pantheon all ran long (1000, 867,
  470). The rush is answered by surviving it, not by out-rushing it.

**Our relay chain is already faster than any of them.** Ragnarok's attacker
chains Launcher hops and puts a Gunner beside the enemy Core on round 12 of
aurora, against Pantheon's round 32 and CtrlAltDefeat's round 43. Copying
Pantheon's cheaper single-throw opening was tried and is worse: 18/42 against
23/42 for keeping the chain.

## Measured and rejected

| tried | result |
|---|---|
| replace the relay chain with one catapult throw, Pantheon-style | 18/42 vs 23/42 — keep the chain |
| cap the ring at the one enemy-facing pad (`RING_MAX_SITES = 1`) | 18/42 vs 20/42 — the screen earns its keep |
| ferry toward the symmetry inference's guess (`FERRY_ON_INFERENCE`) | 17/42 vs 21/42 atlas-free — a wrong throw is not cheap |
| rebuild the same opening on the `vigil` lineage instead | 12/42 vs ragnarok; vigil also TLEs, ragnarok does not |

## Turn limit

`uv run python -m benchmarks.timing --bot bots/luc/valkyrie --maps all` reports
0 turns over 10 ms, worst 3,993 µs. Independently, 42 real matches against
ragnarok at `--tle 10` produced **0 TLE unit-rounds and 0 tracebacks** (the
`vigil` lineage produces roughly 0.3 TLE unit-rounds per game on the same
scan).
