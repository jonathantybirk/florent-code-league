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
placement, move, throw, shot, HP delta, ammo conversion, **and `botOutput`,
which carries the other team's stdout**. Our own `PLAN_FAILED` lines come back
out of a replay this way, which is by far the fastest way to debug an opening.

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
