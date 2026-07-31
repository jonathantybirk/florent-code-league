# Vanguard: engine-2.2.0 mechanics and the siege/sustain strategy

*LLM-generated.* Every claim below is either quoted from `spec.md` or was
measured against `fcode 2.2.0` with probe bots and replay decoding during this
session. Where the scraped tutorial mirror in `docs/` disagrees, the engine
won.

## Corrections to the published API docs

`docs/scraped-originals/.../robot-api.txt` describes a **newer** engine than
the one we run. Against `fcode 2.2.0`:

| Documented | Reality in 2.2.0 |
|---|---|
| `ct.get_global_ammo()` | **Does not exist** (`AttributeError`) |
| `ct.convert_ammo()` / `can_convert_ammo()` | **Do not exist** |
| "Gunners and Sentinels spend from your team's global ammunition balance" | False. Ammunition is **local to each turret** |
| `ct.can_act()` | **Does not exist** |
| Builders move cardinally only | False -- all eight directions work |

The turret API that *does* exist is `get_ammo_amount()` / `get_ammo_type()`,
both of which raise `Unit is not a turret` elsewhere. A Gunner built with no
supply sits at `ammo_amount=0` forever and never fires.

**An uncaught exception permanently destroys the unit.** A single call to a
method that does not exist inside a Core's `run()` ends the game. Every handler
must swallow its own exceptions.

## The one equation that matters

Ammunition must be physically delivered: a Harvester outputs a 10-Ti stack to
an adjacent building every 4 rounds, and Conveyors move one stack per round.
A Gunner spends 2 Ti for 10 damage and fires every other round.

> **damage/round = 5 x (titanium/round delivered into Gunners in range)**

Consequences:

- One forward Harvester = 2.5 Ti/round = **12.5 damage/round**, so a 500 HP
  Core dies 40 rounds after the first battery is fed. Matches end near round
  60, which is exactly why the opening is a pure logistics race.
- A Gunner consumes only 1 Ti/round, so **one Harvester supports 2-3 Gunners**.
  Adding Gunners past that buys nothing; adding supply buys everything.
- Sentinels are a trap: 10 ammunition for 18 damage is 1.8 damage/Ti against a
  Gunner's 5.

## Exploitable mechanics

1. **Producers do not check ownership.** The spec says "Resources may be
   outputted to a building belonging to the opposing team," and a Harvester
   "prioritises outputting in directions which were used the least recently"
   -- it round-robins into *every* adjacent building. Parking our Gunner beside
   *their* forward Harvester arms our siege for free and halves their income.
   Conveyors are narrower: they only output along their facing, so the Gunner
   must sit on exactly the tile the belt points at.

2. **Any building blocks a Gunner's ray.** So a complete ring of Barriers
   around our 2x2 Core makes point-blank Core sniping impossible -- and
   point-blank sniping is how every strong bot in `bots/lucas/` wins. Twelve
   Barriers cost 3 Ti each and only 1% cost scale each. Build the tiles nearest
   the enemy first; a half ring that covers the approach beats a full ring that
   arrives late. Wait until the Core has finished spawning: it spawns Builders
   onto that same ring.

3. **Healing beats shooting on cost.** Heal is 4 HP for 1 Ti; a Gunner
   averages 5 damage/round for 1 Ti. One Builder repairing the Core nearly
   cancels one Gunner, two cancel two -- and their titanium is gone for good
   while ours keeps the Core alive. Against Builders chipping a Barrier at 2
   damage/round, a single heal wins outright. **This was the single largest
   improvement measured: 62% to 86% win rate.**

4. **Builders have no ranged attack.** `ct.fire` only damages the building on
   the tile the Builder is standing on (2 Ti for 2 damage). An attacking
   Builder therefore cannot answer a Gunner at all.

   A defensive Gunner at home nevertheless **measured worse than nothing**
   (51-9 without it against 46-14 with it, and worse still with two). Once the
   barrier ring and the repair crew are in place the raid is already dead, and
   the Gunner is 20 Ti plus several Builder-rounds that the siege needed. Do
   not add defence to a base that is already holding.

5. **Other units are not in the remembered map.** Buildings persist in memory;
   Builder Bots do not. A remembered map therefore says a corridor is free
   while `can_move()` keeps refusing it, and the Builder paces between two
   tiles forever. Recording the tiles that currently hold a foreign bot, and
   treating them as blocked for that round only, was worth **+5 games on its
   own and took the bot from 87% to 97% in combination with the point above**.

6. **Cost scale is shared and refundable.** Scale rises with every entity built
   (Builder +20%, Gunner/Launcher +10%, Harvester +5%) and "when an entity is
   destroyed, its contribution is removed". Six Builders put a Gunner at 25 Ti
   instead of 10. Vanguard caps Builders at four and **self-destructs spent
   Launchers** to hand the 10% back.

7. **Launchers are a tempo purchase.** 20 Ti throws a Builder just over five
   tiles (`dist^2 <= 26`, measured from the Launcher) in two rounds instead of
   five walked. Worth it while the target is far; not worth it near the end.

## Map inference without reading map files

The rulebook guarantees the map is symmetric by reflection or rotation. Keep a
three-bit mask over {rot180, mirror-x, mirror-y} and reject a hypothesis when
two observed paired tiles disagree, or when its predicted enemy-Core footprint
is fully visible and empty. Once one hypothesis survives, **mirror our own
observed terrain onto the unseen half**. That is enough to plan a conveyor
route through enemy ground before ever seeing it, using only our own eyes and
a published rule -- no bundled `.map26` files. Buildings are never predicted,
only terrain.

## Methodology notes

- **Matches are deterministic**: the `--seed` flag changed nothing across
  seeds 1/2/3. A 30-game head-to-head is therefore one sample of a chaotic
  system, and a one-line change can swing it by four games without being
  better. Score changes against the pooled 180-game field
  (`scratch/ladder.py`), never a single opponent.
- Replays decode as protobuf; field 5 is an HP delta, field 12 a turret shot,
  field 4 a resource transfer, field 13 a death, field 6 the per-team titanium
  totals. That is enough for an automatic "why did I lose" report: who built
  what and when, when the first Gunner appeared, and when Core damage started.

## Measured parameter choices

Swept against `claude_challenger_1` and `_3` (60 games per value):

| Parameter | Values tried | Best |
|---|---|---|
| `MAX_BUILDERS` | 3 / 4 / 5 | 45 / 46 / 47 -- flat, kept 4 for the lower scale |
| `ECONOMY_BUILDERS` | 1 / 2 / 3 | 44 / **46** / 45 |
| `HOME_GUNNERS` | 0 / 1 / 2 | **51** / 46 / 45 |
| `MAX_HOME_HARVESTERS` | 3 / 4 / 6 | 44 / 45 / **46** |

## Scoreboard

Full field, all 15 maps, both sides, 180 games:

| Build | Record |
|---|---|
| first working siege | 105-75 (58%) |
| + barrier ring, enemy-facing first | 112-68 (62%) |
| + repair crew | 154-26 (86%) |
| + more home harvesters | 157-23 (87%) |
| + crowd-aware pathing, no home Gunner | 174-6 (97%) |
| + heal triage, emergency repair crew, long belts | 175-5 (97%) |
| + parasitise without owning a deposit; abandon denied tiles | 178-2 (99%) |
| + shoot through destructible cover, spend idle bank, flank, econ 3 | **179-1 (99.4%)** |

## Two later corrections worth keeping

- **Triage repairs by what is closest to dying, not by importance.** Healing
  the Core first looks right and is wrong: the Core has 500 HP of slack, while
  a 20 HP Conveyor on a ring tile falls in ten rounds and becomes the exact
  emplacement they shoot the Core from. Switching to lowest-HP-first turned
  the twins loss from "Core destroyed, round 241" into surviving to round 1000.
- **Idle Builders are worse than expensive Builders.** Vanguard was banking
  1370 titanium at round 400 with every Builder standing still, because no ore
  had a short enough route home. Allowing a belt three times longer once the
  bank is deep took the screening set from 65-7 to 70-2.

## The two bugs that were costing every unfinished game

Both were failures to *attack*, hiding behind a bot that looked healthy:

- **Parasitism was gated behind owning a deposit.** If both forward ores were
  already mined by the enemy, `_siege` dropped straight into harassment and
  never ran the travelling search -- even though those very Harvesters were
  the supply it wanted to shoot from. Deleting one early return was worth
  three games.
- **"Give up" counters must count intent, not failed moves.** A defender
  denies a firing position by parking a Builder on it: a Builder is not a
  building, so it cannot be shot off and cannot be walked through. Our
  attacker shuffled between the two squares beside that tile forever, and
  because it *moved* every round the patience counter kept resetting. Counting
  rounds spent wanting the tile instead makes it move one step upstream to the
  next belt tile, which feeds the same battery. On twins this turned a
  round-1000 tiebreak loss into a Core kill on round 83.

## A defensive idea that measured backwards

The Core spawns Builders onto the same ring we brick up, so a complete ring
walls in our own reinforcements and the emergency repair crew can never
appear. Leaving the ring tile furthest from the enemy open as a spawn gate is
the obvious repair -- and it is worse: on quarry it moved the Core's death
from round 240 to round 142, because a single gap is all a raider needs. A
sealed ring that cannot be reinforced beats a ring with a door. If the crew is
ever wanted mid-siege, a Builder should demolish one Barrier on demand rather
than a gate being left standing.

## Timing

The whole field plays identically with `--tle 10` as without it, so the
per-unit distance-field pathing is comfortably inside the server's 10 ms
budget on this machine.

## Adversarial self-play: the measurement that was missing

Every opponent on the branch attacks, and **none of them heals**. Since healing
is what beats them, a 98% record against that field is partly a record against
one blind spot. `bots/jon/probes/turtle` is Vanguard with the assault removed --
barrier ring, repair crew, economy, and no Gunners at all. `strat1` cannot
scratch it: zero Core damage in a full match.

Vanguard beat it only **19-11**, with a Gunner in 57% of games arriving at
round 39, and a median match length of 1000. That is the true measure of the
siege, and it was invisible against the real field. Three changes took it to
**30-0**, none of which the real field could have told us about.

The cause: `_ray_to_core` demanded an *unobstructed* line, so a bricked Core
ring made every firing position look illegal and the siege simply declined to
exist. But a Barrier is 30 HP and a Gunner hits for 10 -- the wall is three
shots, not immunity. Counting enemy buildings in the line as *cost* rather than
as a veto (and preferring clear lines when they exist) moved it to **24-6**,
ammunition delivered from 26.7 stacks to 56.8, first Gunner from round 39 to
22, and median match length from 1000 to 124 -- with no change against the real
field (178-2 either way).

One ordering trap worth remembering: the Core is itself a building and sits in
`solids`, so a blocker test written before the target test makes every ray stop
dead on the thing it was aiming at.

**Idle titanium is the most expensive thing on the board.** The Builder cap was
only lifted when the Core was *under fire*, so against a passive opponent
Vanguard banked titanium and stood still -- it fielded 4 Builders to the
turtle's 8.9 and lost the tiebreak. Lifting the cap on a deep bank as well took
the turtle match to **30-0** and doubled ammunition delivered again, 56.8
stacks to 111.3. This is the same failure the Battlecode 2025 postmortems
describe as "losing games despite having loads and loads of money".

**Once the field is saturated, freeze a copy and play yourself.** At 178-2 and
30-0 neither benchmark could resolve a further change. `bots/jon/probes/spar`
is a frozen build, and self-play against it is exactly 15-15 by construction,
so anything above 15 wins is a real improvement. That is how the last two
changes were measured:

| Change | vs frozen baseline |
|---|---|
| (calibration -- identical builds) | 15-15 |
| flanking: successive attackers take opposite sides of the Core | 18-12 |
| three of four opening Builders stay home | **19-11** |

Flanking is the one idea taken from outside: Battlecode postmortems repeatedly
note that a multi-angle assault splits the defence. Here it also defeats a
specific denial -- attackers that all pick the same best tile queue behind one
parked Builder.

## Generalisation: maps nobody tuned against

`maps/generated/` (Codex's generator) is the other half of the anti-overfitting
story. All 24 pass a from-scratch check of every rule the specification
actually states -- size 8..30, tiles in {empty, wall, ore}, terrain symmetric
under one of the three allowed transforms, two 2x2 Cores that are counterparts
under a symmetry the *terrain* also obeys, footprints clear and non-overlapping
(`scratch/validate_maps.py`; the 15 competition maps pass too).

They are **not** a representative sample, and the difference is the point:

| | competition | generated |
|---|---|---|
| median area | 484 | 308 |
| ore per 100 tiles | 2.75 | 2.53 |
| median wall % | 5.0 | 7.1 |
| median ore within 6 of own Core | 3.0 | 2.0 |
| symmetry | 10 rot, 3 mirror-y, 1 mirror-x, 1 all | 6 rot, 10 mirror-y, 8 mirror-x |

Smaller, wallier, less ore near the Cores, and the symmetry mix inverted. So
92.9% there is a stress-test score, not a ladder prediction -- but it exposed
two failures the competition maps never could:

- **The assault had no "walk to the enemy" fallback.** With no forward deposit
  and no visible enemy producer, attackers explored for a thousand rounds while
  both economies idled to a third-tiebreak draw. They now close until the Core
  is genuinely *in vision* -- a standoff measured in king moves parks a Builder
  four tiles out, seeing none of the ring it came to shoot.
- **A hard deposit cutoff gives up on maps with no ore near a Core.** Made
  tiered instead: near deposits first, a far one as a last resort, and the far
  tier suppressed entirely when the enemy already runs a producer we could
  simply stand next to. Ungated, the far tier lured attackers away from
  parasitism and cost 6 games of self-play.

## Two latent bugs that only self-play exposed

Neither changed the scoreboard much, and both would have been exploited by any
stronger opponent:

- **A state flag that latches and never clears.** The Core raised
  `SLOT_HOME_UNDER_FIRE` below 85% health but never lowered it, and every
  attacker without a battery converts to repair duty while it is set. One early
  scratch therefore disabled the entire assault for the rest of the match --
  which is exactly how a mirror match reaches round 1000 scoreless. Alarms need
  hysteresis *and* an off switch.
- **A Gunner cannot be built on the tile the Builder stands on.** Only Conveyors
  and Splitters may share a tile with a Builder, and the tile an attacker walks
  to in order to reach the Core ring is very often the tile it then wants to
  shoot from. It has to step off first -- diagonally, because their barrier
  ring routinely boxes it in on all four cardinals.

`_extend_feed`, the conveyor creep meant to bridge a distant forward Harvester
to a firing position, turned out to be **dead code**: zero conveyors built
across five maps, because `_add_gunner` always "acted" first by taking one step
toward a speculative parasite tile. Running the creep first does fire it, but
it is worth about one conveyor a match and costs self-play, so the order stands
and the creep remains the clearest piece of unfinished work.

## Building a bot to beat Vanguard

The most productive experiment of the session. Vanguard's siege needs exactly
one thing: a free tile beside a producer with a firing line to the target Core.
Two counters were built against that.

**`probes/nemesis` -- deny the firing positions.** Mine our own nearby deposits
first, brick every tile with a line to our Core (not just the twelve on the
ring), repair at 4 HP a round against their 2, post Gunners, never attack. It
does force the tiebreak -- median match length went from 101 to 256 rounds --
but it loses the tiebreak, because wardens do not mine and its own belts feed
the besieger anyway. **0-30.** Splitting Builders into miners and wardens, and
buying more of them, both helped and neither was enough. Recorded as a
negative result: pure denial cannot pay for itself here.

**`probes/nemesis2` -- Vanguard plus the defensive Gunners it had deleted.**
**16-14 against Vanguard**, and the diagnostics show it is not a defensive
effect at all:

| | nemesis2 | Vanguard |
|---|---|---|
| first Gunner | round 13, in 100% of games | round 42, in 50% |
| ammunition delivered | 89.2 stacks | 34.7 |
| Gunners built | 7.0 | 1.3 |

Every attacker is a 40 HP Builder that **cannot shoot back**, so Gunners over
the approach kill the enemy assault on arrival and *suppress their whole
siege*. Our own then lands unopposed. The earlier measurement that removed
these Gunners (51-9 without against 46-14 with) was taken against opponents
whose assault was already dying to the barrier ring -- it measured a redundancy,
not a weakness, and the conclusion did not survive an opponent built to punish
it.

The fix was ported back into Vanguard, which now beats its own previous build
16-14 with the field and the generated maps unchanged. **The lesson is about
method: a removal justified by measurement is only as good as the opponent that
measured it. Re-test deletions against something purpose-built to exploit
them.**

## The counter loop, and the harness that makes it safe

`scratch/gauntlet.py` scores a build against three groups at once, because the
roster alone stopped being informative at 99%:

- **roster** -- the seven real opponents;
- **ancestors** -- every previous Vanguard, archived under `probes/vg_v*`.
  Losing to your own last build is unambiguous in a way a saturated field
  never is;
- **counters** -- bots written specifically to beat the current build.

Three counters were built, and two of them found real defects:

| counter | idea | result | what it forced |
|---|---|---|---|
| `nemesis` | deny every firing position, never attack | 0-30 | nothing -- pure denial cannot pay for itself |
| `reaver` | cut belts beyond the repair radius | 12-18 | `_scorch`, and `REPAIR_RADIUS` 4 to 7 |
| `baiter` | plant Gunners beside producers with no line | **16-14** | relaxed Gunner placement |

**`reaver`** exploited the fact that repairs stopped at four tiles while belts
ran to twenty-one: a cut past that is severed for good. On aurora it took
Vanguard's Conveyors for 3716 damage and out-delivered it 963 stacks to 256.
Two fixes followed -- widening the radius, and **scorched earth**: destroy our
own producer rather than let it feed a Gunner planted beside it, since a
Harvester round-robins into every adjacent building regardless of owner.

**`baiter`** then attacked that very fix -- a shotless Gunner beside our
Harvester makes us burn a 20 Ti building for their 10. Tightening the trigger
to "a Gunner that can actually reach the Core" did **not** recover the match,
which was the useful part: the bait was never the edge. Baiter simply built
8.1 Gunners to our 6.8 and delivered 79.4 ammunition stacks to our 59.9,
because **a Gunner beside an enemy producer is worth building even with no
line to the Core** -- it is fed by them, it shoots what walks past, and lines
open as buildings die. Adopting that rule was the actual improvement.

Each generation beats the last: v1 23-7, v2 20-10, v3 16-14.

Two games out of 180, both Cores that eventually fall around round 240 after
the siege has stalled. Remaining ideas, in rough order of expected value:

- A forward Harvester further than about four tiles from the enemy Core cannot
  feed a Gunner directly, and the conveyor creep meant to bridge that gap
  (`_extend_feed`) still rarely fires.
- Parasitising an enemy Harvester only captures its round-robin share. Chipping
  away the rival sinks beside it should redirect the whole output into our
  Gunner; a first attempt measured exactly neutral and was dropped.

## Caveat on measurement

`common/starter` calls `random`, so 30 of the 180 games are genuinely noisy;
the rest are reproducible. Vanguard itself was made deterministic by
tie-breaking every sort and `min()` on coordinates -- the engine does not
promise an order for its `get_nearby_*` queries, and relying on one made whole
matches irreproducible.

## Mechanics probed directly (rather than reasoned about)

Three were confirmed against the engine with throwaway probe bots. Only one of
them pays, which is exactly why they are written down: "it is in the rulebook,
so it must be good" is how the Sentinel mistake happened twice.

**Launchers throw *enemy* Builders.** `ct.launch()` does not check ownership. A
Launcher planted beside an enemy Builder reported 61 legal destinations and
hurled it five tiles, for no ammunition and a one-round cooldown. Every bot in
this repository attacks by walking Builders in -- they *are* the delivery
mechanism for the whole siege -- so a Launcher on the approach deletes the
assault. **Kept.** Vanguard repels with the Launchers it already builds for its
own ferry, which costs nothing extra.

**Sentinels pierce buildings.** With a Barrier occupying the tile at +1,
`can_fire_from` reports that a Gunner cannot reach +2 or +3 and a Sentinel
reaches both. A Sentinel also covers **17 tiles to a Gunner's 3** and can fire
at empty tiles, where a Gunner needs an occupant. The earlier dismissal on
damage-per-titanium (1.8 against 5) was simply the wrong calculation -- it
ignored geometry.

*Not* kept: at 30 Ti and 10 ammunition a shot it lost 7 games against the
roster (jonbot 29-1 to 24-6) and gained nothing against the strongest opponent.
**But the strategic consequence stands: a Barrier ring does not protect a Core
from Sentinels.** Our entire defence assumes rays stop at the first building.
Nobody currently builds Sentinels; the day someone does, the ring is worthless.

**A Conveyor beside an enemy Harvester collects their titanium.** A tap planted
next to a `strat1` Harvester held `ResourceType.TITANIUM` within four rounds. It
generalises parasitism: a tap can carry their output to a Gunner placed
anywhere a line exists, instead of needing a firing position adjacent to the
Harvester itself. *Not* kept -- 12-18 with long taps and 13-17 with taps capped
at three tiles, against 14-16 without. Every tile of such a belt sits inside
their base, under their Gunners, repaired by nobody.

## An interaction bug worth more than any strategy this session

Launchers self-destruct once their ferry queue empties, to hand back the 10%
they add to the shared cost scale. That rule was written before Launchers could
repel, and it silently threw the new capability away: the Launcher standing
exactly where enemy Builders walk is the one that looks idle.

Suppressing the scrap while any enemy is in sight took the gauntlet from
435-105 to **471-99**, with the counters group going from 76.7% to 83.3%.

**When a unit gains a second role, re-check every rule written for its first
one.** No amount of strategy reasoning finds that; only the scoreboard does.

## Ideas measured neutral, recorded so they are not re-derived

- **Delayed aggression** (undertow's: hold the assault until the bank reaches
  300 Ti). Swept 120 / 200 / 300 against a frozen Vanguard and undertow: 28, 24
  and 27 wins from 60, against 27 for no delay. Our attackers already wait on
  affordability at each individual build.
- **Disabling long belts** to reduce raid surface: 10-20 and 11-19, worse both
  ways. Long belts earn their keep.

## Where Vanguard currently loses: the raid war

`undertow` (Codex) beats Vanguard on both corpora -- 19-11 on the competition
maps and 22-38 on the 30-map representative set -- so it is a real strength,
not a competition-map artefact. How it wins is the surprising part:

| | Vanguard | undertow |
|---|---|---|
| Gunners | 7.0, first round 11, in 100% of games | 2.4, round 82, in 52% |
| ammunition delivered | 41.6 stacks | 49.5 |
| Launchers | 3.6 | 7.1 |

It barely fights. It picket-spams Launchers, throws our attackers home before
the battery can be maintained, and takes the round-1000 tiebreak on titanium.
In one representative match **neither Core took a single point of damage**, our
five Gunners fired twenty shots -- all beside our *own* base -- and the game was
decided by belts: ours took 3670 damage to its 1832.

The gap is not siege power, which we have more of. Our supply is twice as easy
to cut as theirs.

Fixes tried, each measured against the strongest opponent *and* our own
previous build:

| change | vs undertow | vs vg_v7 | verdict |
|---|---|---|---|
| disable long belts | 10-20 | 11-19 | worse both ways |
| `HOME_GUNNERS` 2 -> 4 | 14-16 | **13-17** | rejected |
| `HOME_GUNNERS` 2 -> 6 | 14-16 | 13-17 | rejected |

More home Gunners genuinely help against undertow and genuinely hurt against a
strong generic opponent. **Losing to your own previous build overrules a good
head-to-head** -- tuning to one opponent is how a bot reaches the ladder
overfitted. Left at two.

Open problem: cut their supply faster than they cut ours, without spending the
titanium the tiebreak is scored on.
