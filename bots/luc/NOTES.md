# Dev notes

Scratchpad for the next session. Not shipped doctrine — ideas to measure, not trust.

## 2026-08-04 — turret fights

When pushing turrets into a fight (field Gunners, lane pressure, anything
offensive rather than the Core seal), score candidate sites with two priorities
ahead of raw coverage:

1. **Stay out of enemy rays**, ideally also far from their current rotation.

## 2026-08-03 — reading the ladder's replays

`.replay26` is protobuf. The full schema is embedded as a JSON blob in the
bundled visualiser (`fcode/data/visualiser/assets/main-DFlSC1w7.js`, search
`nested:{battlecode:`) — extract it and the whole match decodes: every
placement, move, throw, shot, HP delta and ammo conversion.

**Downloaded replays carry no stdout.** The `BotOutput` message survives, but
only its `id` and `execTimeUs` fields: across 20 ladder replays, 0 stdout
events and 0 `tled` flags. Locally (`fcode run`) stdout *is* recorded, which is
how our own `PLAN_FAILED` lines come back out of a replay — the fastest way
there is to debug an opening. Do not expect to read anyone else's prints; the
schema has the field but the server strips it.

What downloaded replays *do* give away is `execTimeUs` per unit per round —
the opponent's real CPU time. Pantheon samples at 304-1,749 us, so the top of
the ladder is nowhere near the 10 ms limit.

Pull replays with `fcode match replay <match-id>`; `fcode match list --team
<id>` finds top-vs-top games (widen with `COLUMNS=250` to get full IDs).

### What the top three actually do

- **Pantheon (#1)** plays one fixed opening on every map: Builder round 0,
  Launcher round 1 on the enemy-facing side at radius 2, one throw per round on
  rounds 2-5, Launcher razed round 6. Two throws carry raiders at the enemy
  Core, two carry economy Builders to distant ore. Throws cross walls, so it
  ignores chokepoints — on `pinch` it throws over a two-tile wall band and kills
  the Core on round 24.
- **Erebus (#2)**, one rating point behind, builds **no Launcher at all** and
  takes two of five off CtrlAltDefeat on the round-1000 titanium tiebreak.
  There is more than one viable top strategy.
- **The rush is answered by surviving it.** All three games CtrlAltDefeat won
  against Pantheon ran long (1000, 867, 470). The pattern across 20 decoded
  games: whoever has turrets around their own Core before the enemy's forward
  turrets land, lives; a tie goes to the attacker.

### We are already ahead on delivery

Ragnarok's attacker chains Launcher hops and puts a Gunner beside the enemy
Core on **round 12** of aurora, against Pantheon's 32 and CtrlAltDefeat's 43.
The obvious "copy the leader" move is a downgrade — measured 18/42 against
23/42. Do not spend more time porting Pantheon's opening; the gap to close is
elsewhere.

### The atlas silently disables the relay off-pool

`_opening_ferry` began `if p.atlas is None: return False`. The atlas only
recognises the published pool, so on a generated map, the held-out set, or the
final, the entire relay switched itself off and the attacker walked. This is
most of why `ragnarok_fair` sits five places below `ragnarok`. Fixed in
`valkyrie` by gating on *knowing* the Core (atlas or actually seen).

Ferrying at the symmetry **guess** was also tried and is worse — 17/42 against
21/42 atlas-free. The old gate was right to refuse a guess and wrong only about
what counts as knowing.

### The cluster is the instrument, and it is cheap

`git push` to x/luc schedules the bot on DTU HPC automatically: 3,900-odd
matches against the whole rated field, collected in about three minutes, plus a
compliance stage. Do not grind the 252-game panel locally -- it put this laptop
at load 24 for a worse answer. Read results with
`git show origin/x/tournament:tournament/runs/<run>/matches.csv`.

Cluster numbers for valkyrie@d181312 (3,038 matches, 94 opponents): **90.3%
overall**, and the losses are almost all one family --

    vigil@e267eeb              2/10
    vigil@e22eda8              4/10
    ragnarok_fair@79582fc     17/42
    ragnarok@79582fc          21/42
    vigil@18b749d              8/14

The ragnarok line does not beat the vigil line. That is the rock-paper-scissors
the ratings already record: the Nash core is {vigil@e267eeb 0.50,
ragnarok@79582fc 0.25, ragnarok_fair@79582fc 0.25}. Beating both at once means
collapsing that core, which is exactly the hard part -- and note the local gate
disagrees with the cluster's small sample (locally valkyrie takes 24/42 off
vigil@e267eeb, the cluster had 2/10 on a partial run), so wait for a full run
before believing either.

### Measured failures worth not repeating

- **Pad-first spawn order** (Launcher-ring Builder first, Pantheon-style):
  -25 games in 252. Pushes the miner from spawn index 0 to 2; first Harvester
  round 7 -> 9, delivered titanium 696 -> 470.
- **Reserving the first Harvester's cost against ammo conversion**: 24/42 ->
  15/42 against vigil@e267eeb. The bug it fixes is real -- on bridge ragnarok
  loses both seats and mines *zero* titanium, because combat opens on round 4,
  the COMBAT_AMMO_FLOOR override converts down to EMERGENCY_RESERVE every round
  after, and a scale factor of 2.4x puts a 47 Ti Harvester out of reach forever
  -- but turrets that cannot fire cost more than the Harvester is worth. The
  bridge economy failure is still unsolved and still worth solving another way.
- **`except Exception` around ammo conversion hides fatal typos.** A missing
  import made `_keep_ammunition` raise NameError every round; the bot kept
  playing with 0 ammunition and scored 1/42 without ever crashing. Always grep
  a fresh replay for `PLAN_FAILED .* reason=NameError` before trusting a run.

### Still open

- The `vigil` lineage overruns 10 ms in real matches (~0.3 TLE unit-rounds per
  game at `--tle 10`); the `ragnarok` lineage measures 0 on the same scan. Any
  further work belongs on ragnarok's chassis, and vigil's timing is worth a
  look before that lineage is used again.
- Nothing in `valkyrie` beat ragnarok by more than noise on 42 games. 42 games
  cannot resolve these differences — the 3,780-game tournament is the only
  instrument here that can.
- Untested idea from the Pantheon replays worth its own experiment: they throw
  **economy** Builders to ore that is fifteen rounds' walk away. We only ever
  ferry attackers.
