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

Cluster numbers for valkyrie@d181312 over the **complete** 3,906-match run
against 94 opponents: **89.7% overall**. Per-matchup, on full 42-game samples:

    ragnarok_fair@79582fc     17/42  40%   <- the only real losing matchup
    ragnarok@79582fc          21/42  50%
    vigil@e22eda8             23/42  55%
    vigil@e267eeb             24/42  57%
    vigil@18b749d             24/42  57%

**Do not read a partial run.** At 10 games the same matchup showed 2/10 against
vigil@e267eeb and I concluded the ragnarok line loses to the vigil line. It
does not -- the full sample is 57%, and it agrees exactly with the local gate.
A run is partial until `matches.csv` reaches the planned count; check it.

The genuinely interesting result is the last line of that table inverted:
**ragnarok_fair beats valkyrie 25/42 while ragnarok itself only draws 21/42.**
The atlas-free twin of the same bot is the stronger opponent, which says the
offline map oracle is not paying for itself against this bot and may be
actively costing it. Worth chasing, and it matters doubly if the final is
played on a map the atlas has never seen.

The opening headcount is settled, in ragnarok's favour. A fourth Builder is a
regression in *both* directions -- valkyrie_atk2 (second attacker) 83.6% and
valkyrie_econ2 (second miner) 83.4%, against valkyrie's 89.7%, and 12/42 and
1/4 respectively head-to-head. The +20% scale per Builder really does outweigh
either a second battery or a second belt. Pantheon opens with four anyway; that
is a difference in what the rest of the bot does, not a lever to copy.

vigil's own tip was a regression and is now fixed (c71a543fc): commit 64e40cba4
("Place the ring on the real threat boundary, and turn it on") flipped
RING_COVER_SHELL to True and left the paragraph arguing against it standing.
With it on, vigil loses **15/42** to vigil@e267eeb, its own previous commit;
with it off the same comparison is 21/42 and every one of the 21 maps splits
1-1 -- an exact mirror, so the shell was the whole regression.

### The one lever that has moved anything: stop buying Launchers

Every Launcher is +10% on every price the team pays for the rest of the game,
and the bill lands on the only two things that win: Gunners and Harvesters.
Both changes that moved the map metric are this same observation applied twice.

Found by chasing an anomaly rather than by tuning: `ragnarok_fair` beats
`valkyrie` 25/42 where `ragnarok` itself only draws 21/42. The fair twin is the
same bot with the atlas removed, and `_opening_ferry` is gated on the atlas, so
it *cannot ferry* -- it is forced to walk, and that handicap is why it wins. On
aurora the chaining bot ends with 6 Launchers, 1 Harvester and 4 Gunners; the
walking bot ends with 3, 2 and 7.

Both caps are non-monotonic, so neither "chain" nor "walk" was the right answer
(worst-target map rate, 21 maps x both seats vs the two Nash-core agents):

    MAX_RELAY_LAUNCHERS   0:14%   1:29%   2:24%   uncapped:5%
    RING_MAX_SITES        1:24%   2:33%   3:29%   8 (all):29%

5% -> 33% overall. The first relay hop clears the Builder out of its own half
while the map is empty and is worth 20 Ti; hops after it are not. Two ring
sites are the throw pad plus one approach; below that the screen covers
nothing, above it the sites are bought with the turrets that kill Cores.

Things checked at the same time and left alone, all on the same metric against
33% for the shipped build: the siege Sentinel earns its +20% (off is 29%),
FORTIFY's field Gunners earn theirs (off is 24%), and the attack-Gunner cap
does not bind above seven (5 -> 7 is +1 game; 7 and 10 are identical). So the
scale-discipline vein is mined out at the two Launcher caps -- every other
spender in the bot is already paying for itself.

The caps also bought CPU headroom, which was not the point but matters: fewer
Launchers means fewer launcher hazards to path around, and the worst Builder
turn drops from 4,198 us to 2,994 us. Worth having, because the cluster's
compliance stage measured valkyrie at 5,944 us where this laptop said 3,993 --
cluster hardware is materially slower and the 10 ms limit is enforced there.

### Cluster verdicts, full samples only

    valkyrie@d181312   89.7%  (3906)
    warden             89.0%  (4029)   repair + write-off ported from vigil
    vigil, shell off   88.7%  (4032)   was losing 15/42 to its own last commit

warden draws valkyrie 21/42 -- an exact split. **The vigil port is neutral.**
The capability gap is real (ragnarok genuinely cannot mend a belt and never
calls self_destruct) but it does not pay in this field, where the median game
is short and belts are rarely shot. At 2,407 of 4,029 matches it read 90.5% and
looked like a win; that was the partial-run trap for the second time in one
session, and the only reason it was not reported as a result is that the
hedge was made explicit.

The vigil fix is confirmed the other way: 21/42 against vigil@e267eeb on the
cluster, exactly the mirror the 84-game local gate predicted. So the local gate
is a trustworthy *screen* when an effect is real -- it just cannot see small
ones, which is how it called the 25-game pad-first regression noise.

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
