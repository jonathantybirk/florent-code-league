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
visualiser) for Pantheon (#1), Erebus (#2) and CtrlAltDefeat (#4). Everything
below comes from observed game events — placements, moves, throws, shots. The
schema has a `BotOutput.stdout` field, but downloaded replays are stripped of
it: 0 stdout events across 20 ladder replays, against 101 in a local one. Their
per-unit `execTimeUs` does survive, and Pantheon runs 304-1,749 us.

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

## Siege barriers

A third change, `SIEGE_BARRIER_ENABLED`. Ragnarok already inherits Elias's
rebuild-tank (`_block_firing_lane`), but it only soaks Gunner lanes whose
terminus is **our own Core**, and only from the defence alarm. Pantheon uses
the same trick pointed the other way: of 33 barriers across twenty decoded
ladder games, **31 sit in an enemy Gunner's ray**, every one 2-5 tiles from the
*enemy* Core, and each is rebuilt on the same tile as fast as it dies -- one
tile absorbed eighteen shots over six rebuilds.

The trade is lopsided: 3 Ti and +1% scale for 30 HP eats three Gunner rounds
and six of their ammunition, and ammunition is titanium 1:1.

Two conditions, both measured:

- Only once a turret is emplaced. Soaking on the Builder's own behalf scores
  17/42 against 20/42 -- a Builder steps out of a lane for free, and rounds
  spent laying cover are rounds the battery does not exist.
- Only in a lane no friendly turret is firing through. Units act in spawn-id
  order (verified: 421 turns, no exception), so a barrier blocking both ways is
  settled by who lands the killing blow on it -- with mutual fire the
  earlier-id turret breaks its own cover and hands the later one a clear shot.
  Refusing shared lanes outright avoids the parity question and costs nothing,
  because our battery faces their Core while their defence faces our battery.

Scores 20/42 against ragnarok, i.e. **neutral in this pool** -- it fires only
11 times across 42 games whose median length is 48 rounds. It is shipped
because the regime it pays in is long sieges, and the pool underrepresents
them: the games CtrlAltDefeat won off Pantheon ran 470, 867 and 1000 rounds.

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
