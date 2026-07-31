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
| + parasitise without owning a deposit; abandon denied tiles | **178-2 (99%)** |

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

## What still loses

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
