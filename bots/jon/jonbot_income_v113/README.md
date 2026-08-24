# brynhildr

# jonbot_income_v113

Timing-preserving mining-movement fork of ladderfarm's selected expected-Elo
leader, `brynhildr@1e69d09` (submission v113). Core economy authorization,
spawning, combat, defence, and every decision about *when* to build are
unchanged. Only an authorized miner's chain movement differs.

hildr's Sentinel rush in steward's armour: `hildr@7a6d86c` (the walk, the ring, the race
arithmetic) plus the measured half of `steward_hardened_reinforced@366cd1b` (an economy that
wins timeouts, a home guard that survives sieges), rebuilt on what the ladder replays of both
actually showed.

## Where it stands

15 pool maps, both seats, seeds 1-3 (90 games an opponent), fcode 2.3.9:

| opponent | brynhildr | hildr@7a6d86c | steward@366cd1b |
|---|---|---|---|
| hildr@168b1a4 (v78, the flagship) | **80/90 (89%)** | 16/30 | 10/30 |
| steward_hardened_reinforced@366cd1b | **76/90 (84%)** | 23/30 | — |
| gefn@60ae5f1 | **75/90 (83%)** | 25/30 | 9/30 |
| hildr@7a6d86c | 69/90 (77%) | — | 7/30 |
| brokkr@05bf388 (Jon's economy bot) | 72/90 (80%) | 7/30 | 11/30 |
| v70 sentinel_rush_cluster | 75/90 (83%) | 25/30 | 11/30 |

Maps won in both seats: 11/15 against hildr78, 9/15 against steward, 10/15 against gefn.
(Goal rows re-measured on the planned-ring build, seeds 1-2 of 60: hildr78 54/60, steward
52/60, gefn 50/60; spar_wall 38/60, spar_sentinel 50/60, brokkr 49/60.)
Off the pool (sweden, bridge, quarry, duel, showdown, vault) it runs without the bundled
terrain and without crashing; 7/12 against steward and brokkr. Worst unit-turn on a 30x30
map: 2.7 ms against the 10 ms limit (about 4.3 ms at the ladder's 1.6x).

## On the ladder

`231e69a` (v99), 34 unrated series at an average opponent of 1754: 15-19, 80-90 games,
estimate 1686 +-105 -- level with hildr@7a6d86c's 1707, below v78's 1856. It converted the
timeouts (TRRR 4-1 where hildr was 8-22 in games, I Stone 2-3 where hildr was 1-9) and swept
Banminary, Ouroboros, Coreflood and jmc, but lost 80 of 90 games to a Core kill in rounds
100-500 -- the mid-game siege this bot's local panel never plays:

* DinooniD: five Harvesters laid, income frozen at 110 from round 60 -- the belt's two tiles
  nearest the Core were shot out beyond the miner's sight and never repaired. Miners now
  patrol any belt tile unseen for forty rounds.
* farming_200s: seventy-six quiet rounds, two Builders bought, no Harvester -- the second
  miner took the first one's Harvester money. The second miner follows the first Harvester.
  Its second Builder dug a barrier their Builder mended, 2 Ti a hit against their 1. Nothing
  tended is dug.
* Torsko: 22 Sentinels rebuilt into the same two spots its guard covered, 880 Ti, while the
  ring reserve kept the miner unaffordable. A Sentinel dead within fifteen rounds poisons its
  spot; three such losses pause rebuilding for eighty rounds and free the reserve.
* Big O, team lazy, Lorem Ipsum: one enemy Sentinel parked beside the Core, every point of
  income spent on 1 Ti heals for as long as 500 rounds. A parked Sentinel within five tiles,
  untended, is dug out (20 hits, 40 Ti, off a ray it cannot turn); otherwise the squad saves
  for the counter-turret instead of healing while the Core can take it.

## What the replays of hildr@7a6d86c showed

Every loss to TRRR, I Stone and farming_200s on the ladder was a round-1000 timeout on
titanium collected; every loss to gsxWins was a Core kill at home.

* holmgang vs TRRR: hildr ended with 1,845 Ti banked, four idle Builders and **zero
  Harvesters** against 10,405. TRRR walled all eight tiles around the Core with barriers; the
  belt planner needs a free Core-adjacent tile and nobody shot the wall. The ring was dug out
  by round 136 and never rebuilt, because the ring only restarted when the attack Builder was
  *dead* -- a live one tended nothing for 700 rounds.
* paths vs farming_200s: the ring stood all game and the Core sat on 15 Ti for 800 rounds --
  the 20-ammo snipe float was re-fired every time passive income refilled it, so the stall
  economy's miner was never affordable.
* skald vs gsxWins: two enemy Sentinels at 18 HP a round against menders that could not be
  paid (4.5 Ti a round of mending on 2.5 of income), and no turret of ours ever answered them.

## What is different, and why each piece is there

Everything was added against a replay and kept only if the panel moved. The file comments
name the game each rule came from.

**The economy is a purchase with a time.** The attacker scouts on its walk: a Harvester or
belt of theirs (or three Builders) and nobody's attacker in sight means an economy opponent,
and the miner is bought behind the attacker at 1.2x scale instead of the 2.2x the ring
leaves. Against a rusher the miner waits for HOLD -- bought at round 11 before their Builder
was even in sight, it was exactly the four shots that left v70's Core at 14 HP. Miners join
existing belts, repair holes, recount Harvesters that died, and shoot their way out of a
barrier box.

**Titanium goes to the kill first.** A miner, a mender beyond the finish-line rule, or a
counter-turret is a HOLD purchase; while the ring is shooting and the kill is funded -- or
nearly funded, within 60% -- every point is a shot. 36 Ti held for a miner left steward's
Core at 4 HP; a 78 Ti turret bought 8 Ti short of the funding threshold let it recover from
260 to 416; a 66 Ti replacement for a lost Sentinel left gefn's at 18. A lost Sentinel is
not replaced while the standing ring can finish.

**The finish.** hildr keeps 5 Ti for the stored-titanium tiebreak; a mirror is a coin flip
at 5 against 5. This bot keeps 8, converts only what the finish needs plus one spare shot
(their HP reading lags a round, so it is an upper bound), stops a mender spending the floor
on 4-HP heals in the last 120 HP, and drops the floor altogether when ours will outlive
theirs by the one shot it holds. When their ring will kill us no later than ours kills them,
one mender (4 HP a round for 1 Ti) moves our death back further than its price moves theirs;
hildr had this projection and never called it.

**The plan is ring timing, not an HP projection.** Our measured interval between placements
is the prior for theirs (two samples of theirs said 4 rounds a turret, ours said 1, the
truth was 1.7 for both). A dead heat races. The HP projection saw their menders and called a
race we won by ten rounds unwinnable: a rusher that mends is a rusher that went broke. Behind
on the bad side of a map against a real ring, the mend plan holds our ring, buys a squad that
outlasts their 29 shots, seats a counter-Sentinel, and releases the ring once home is quiet.

**Home guard, from steward, in hildr's priority order.** A Gunner lane onto the Core gets a
3 Ti barrier -- and the Builder saves for it instead of healing, because four Gunners at
28 HP a round ate the whole income in 1 Ti heals on longhouse and the barrier that ends a
lane for good was never bought. Home Builders see r^2 20 and the Gunners shooting the Core
routinely sit outside it, so the Core publishes an unsoaked lane. A Gunner touching the
footprint is dug out (13 hits, 26 Ti, and it faces the Core, not the digger). A counter-turret
answers a Sentinel only: steward re-seated a Gunner seven times off our turret's ray on helheim
and killed six 70 Ti Sentinels with 30 Ti Gunners. Menders are sized to what barriers cannot
stop, one against Gunners before the race is called, and the damage ledger counts our own
heals as damage -- two menders restoring 8 against a Sentinel's 9 read as 1 HP a round and
sized the squad at two while the Core bled out with 115 Ti banked. A turret that covers the
Core but has not fired in ten rounds is sized at what lands: brokkr parked a silent Sentinel
and the Core bought three menders against it while the miner starved. Home Builders route
around Gunner lanes and guard Sentinels, and stand in a ring Sentinel's ray without fear: it
shoots the Core, through them.

**The ring defends itself.** The attacker re-plants any Sentinel it sees destroyed, on a spot
no known enemy turret covers while there is a choice, never stands beside an enemy Launcher
(steward's pad flung it twice), and lays a barrier in a Gunner's lane onto a ring Sentinel --
steward's guard seats one on a ray to each Sentinel and dug 26 of ours out on paths. Idle, it
barriers enemy-half ore within six steps and comes back to the ring.

**Measured and off.** An anti-Builder Gunner at home (brokkr's harassment squad digs one out
faster than it kills one: nine went up and came down on holmgang); the opening miner
unconditionally (brokkr 28/30 and every rush matchup lost); a mend plan against Gunners (the
hold never releases and they out-mine us); threat-aware routing that feared Sentinel rays
(the menders walked instead of healing and the mirror went 25 to 18).

## The planned ring, and the burst that can be sustained (the Big O sweep)

Big O swept `229b821` 0-5 and the replays showed both halves of the same disease.  The
attacker dropped its first Sentinel on the first spot it touched -- on a Core webbed with
conveyors the rest of the ring was a march between scattered spots, tens of rounds the
menders used.  And the burst was priced against the menders that happened to be standing
there, so a Core caught empty was fired on with a budget three walked-back Builders undid
(while an over-measured heal ring at a defended Core priced the kill at 500 ammo and starved
our own menders to death reserving for it -- game 2 died in 56 rounds to one parked Sentinel
with 98 Ti banked).

Three rules, all gated to PATIENT MODE -- the attacker has scouted their economy and seen no
rush signs (`econ_seen and not rush_seen`, hildr's own opening-miner discriminator).  Against
a rusher every one of them switches off and the tempo game is byte-for-byte hildr's: a
dead-heat mirror is decided by two rounds, and every variant that taxed the opening lost
paths A and B on the spot.

* The ring is planned as a cluster: `_next_stand` weighs free spots within two steps of the
  stand (CLUSTER_BONUS) beside the adjacent ones, the opening stand is committed rather than
  re-derived each round (the danger field breathes with vision -- an uncommitted goal
  dithered between two stands while no ring went down), and a first Sentinel only goes down
  on arrival where the neighbourhood holds three ring spots.
* The kill is priced against the heal ring they can raise, not the one that is home:
  `max(eheal, HEAL_ASSUMED=12)` until the burst is running -- the builders walk back, or new
  ones are spawned, the round the ring opens up.
* A mender is never starved by a phantom burst: while damage lands, the hold has already
  declared a stall, and the kill is not close, the `kill_ammo - ammo` reservation yields to
  the mender purchase.

## The income war (the verdict)

Our store against their heal ring prices the kill exactly: `kill_ammo = 10*ehp/18 *
full/(full-eheal)`, eheal measured as four a mender seen beside their Core, cross-checked
against the HP ledger. When a sixty-round window of holding closes none of the funding gap
and takes nothing off their Core -- the snipe volleys spending income exactly as fast as it
arrives (paths: 27 Ti short for seven hundred rounds), or the ring dead in a rebuild
grinder -- the verdict is that this rush will never land, and the game is declared an income
war (`ORD_FORAGE`):

* the attacker stops feeding the ring and cuts the conveyors feeding their base -- 2 Ti a
  bite, ten bites a belt tile, from a tile no known turret covers -- and lays a 3 Ti barrier
  on the stump so the line stays cut; Harvesters when no belt is known; long-leash ore
  denial as the scout. The walk to a cut is planned once and followed: the danger field
  breathes with vision (a Launcher halo seen from one tile, unseen from the next), and
  replanning every round shuffled two tiles forever. A target that never gets nearer is
  barred for 120 rounds and the next tried.
* the home half buys every miner the cap allows at once -- the verdict already said held
  titanium buys no kill.
* nothing is converted to ammunition while the home is unthreatened: banking is the point.
  The volley treadmill (convert 20, snipe, repeat) is what burned seven hundred rounds of
  income on paths.
* ehp and the mender count freeze at the last look; the war ends when the bank covers a
  re-armed FULL ring's kill at the frozen numbers -- burst, Sentinel rebuilds, and 30 Ti of
  slack -- or their Core is seen low. Then `hold_total` resets and the ordinary race
  machinery takes it from there.

Measured (seed 1): spar_wall on paths, seat A -- verdict at round 100, bank 33 to 342 while
six Harvesters went down, re-entry near round 530, Core kill at 564 in a game the treadmill
had drawn out to a lost timeout. spar_wall overall 15/30 before, 56/90 across
seeds 1-3 after; the goal trio rose to 80/76/75 of 90.

## The wall watch (the OpenSverige sweep)

OpenSverige swept v109 0-5 (match `01777bc1`), and all five games had one shape.  A Builder
and a Launcher leapfrog to our Core and are parked beside it by round 8; barriers go up on the
ring tiles -- seven of the eight by round 33 in game 1 -- while our bank still holds 450 Ti
and our attacker is walking; two Sentinels arrive at rounds 44-49, after the rush has spent
the bank (their four home menders healed the rush back from 54-236 HP every game); one mender
spawns onto the last free tile and heals 4 a round against 9, and the Core dies on round 112
with the second mender 2 Ti short.  The Core did nothing about the walls because nothing was
shooting it yet: `threatened` is what buys menders, and by the time it was true there was no
tile left to mend from.

Lucas's reading of it: when walls start going up, spawn Builders onto the tiles beside the Core
so they are standing there, able to heal, when the attack comes.  That is the wall watch
(`WALL_WATCH`, Core `_wall_watch`):

- **The trigger** is an enemy barrier on a ring tile, or two within Chebyshev 2 of the
  footprint, or an enemy Launcher within 3 of it with a Builder loitering (OpenSverige's pad
  lands a round or two before the first barrier, so this fires first).  The watch stays on for
  `WALL_MEMORY` (40) rounds after the last sighting.
- **The squad**: `want_menders` rises to `WALL_SQUAD` (3) -- 12 HP a round out-heals the two
  Sentinels that follow -- but never above the tiles it can use: ring tiles that are not wall,
  not built on, not under an enemy barrier, and not beside an enemy Launcher (it flings
  Builders of either team; the Core's spawn and the menders' post selection skip those
  `grab_zone` tiles too).  One more than the usable count is allowed, to dig.
- **The money** comes from the bank now, behind the mend float only: neither the burst
  reserve (`kill_hold`) nor the ring's reserve stands in front of the squad.  A kill that has
  to be fired while their Sentinels shoot a Core no mender can reach was never going to be
  paid for; and on 0033's 12x12 (match `5afa8b97` game 3) the rebuild reserve for four
  Sentinels at post-rush prices -- 330 Ti, after 0033's Builders had dug the ring out -- sat
  in front of a 60 Ti mender while one Sentinel took the Core from 500 to 0 with 130-206 Ti
  in the bank.  The same rebuild reserve now yields to a mender whenever the Core is being
  shot in a stalled game, as the burst reserve already did after Big O.
- **The squad holds, the rest mine.**  While the waller (a loitering Builder or a Launcher)
  stands at our ring, the Core names how many ring tiles are to be held (`ORD_HOLD_SHIFT`,
  bits 14-15 of the orders word) and the first that many of our Builders on the ring, in tile
  order, do not leave to mine; every other home Builder mines as before.  The first cut was a
  mining ban while the waller was present, and it starved the income race: against a stub
  whose three wallers never leave, v109 mined six Harvesters and killed at round 183, the ban
  bought nothing and timed out.
- **The pad Gunner** (`PAD_GUNNER`): once the squad stands, one 10 Ti Gunner is seated on a ray
  to their Launcher pad -- 30 HP that cannot step off the line, five shots -- or, when no seat
  on the pad's line fits, on the raider's line; and the Gunner unit turns after the raider (a
  rotation is 10 Ti).  That looked like a titanium sink -- seven turns in fifteen rounds on
  auroraveil -- and a build that would not turn was tried: against the OpenSverige mimic it
  killed no raiders where the turning one killed one to five a game, and lost five more of
  thirty.  A dead raider is the siege ended: no more Sentinels, the waller gone, the holders
  released to mine.  It stays.
- **Holders that yield.**  A holder steps off its ring tile when the raider stands beside it
  (`_to_post` counts Builder-adjacency as danger) and the raider walls the tile.  That looked
  wrong too -- a Builder cannot hurt a Builder -- and a build whose holders yield only to
  turret lanes and the pad's grab zone was measured: 28 of 60 against 40 of 60 for the one
  that steps off, on identical seeds.  Why the yielding holder does better is not settled
  (the tile it gives up costs the raider a barrier and a walk, and the mender it frees finds
  another tile or a dig); the measured behaviour stays.

It is dormant against everyone who does not wall: the trio and spar_wall panels are identical
to the build before it, game for game (hildr78 27/30, steward 26/30, gefn 25/30, spar_wall
19/30 -- spar_wall is a Gunner-mass siege, not a walling).  Against a stub that walls the ring
and then seats two Sentinels (`wallstub2`: midgard, skald, paths, auroraveil, both seats),
v109 survived every game but stalled -- three of eight went to round 1000, its first mender
bought at round 42-84 after the first shot had landed, min Core HP 76-160 -- while this build
killed in all eight, the squad standing from round 10-21, min Core HP 152-336.  With diggers
added to the stub (`wallstub3`, its wallers shoot our Sentinels out -- 0033's habit), v109 took
both auroraveil seats to round 1000 and lost one on titanium stored; this build killed in all
six games (skald 250/303, paths 167/43, auroraveil 400/303).

Against the OpenSverige mimic itself (`spar_open`: Launcher leapfrog, pad at two tiles, the
ring walled by round ~35, Sentinels from round 35-75, four home healers; all fifteen maps,
both seats), v109 won 6 of 30 -- its first mender bought at round 31-96, after the walls,
and usually after the first shot -- and the wall-watch build 19 of 30 before the holder fix.

## Comms (16 slots)

| slot | writer | content |
|---|---|---|
| 0 | attacker | Sentinels placed; the Core writes 0 to restart the ring |
| 1 | attacker | heartbeat `(round+1) + 65536*(eta+1 \| scouting bits)` |
| 2 | Core | enemy Core packed, `+ 65536*(ring_extra \| HOLD_REBUILD \| RING_HOLD)` |
| 3 | Core | orders `(round+1) + 65536*flags`: threat, econ, turret, gunner, quiet, miners allowed, Harvesters, save, race, forage |
| 4-8 | ring Sentinels | heartbeats |
| 9 | Core | the turret hitting us: packed position, `+65536*(1 Sentinel \| 2+4*facing Gunner)` |
| 10-12 | ring | enemy menders, GO/HOLD/volley, enemy Core HP |
| 13-15 | home Builders | heartbeats `(round+1) + 65536*(mining \| harvesters<<1)` |

Guard Sentinels (a line that cannot reach the enemy Core) take no heartbeat slot and shoot
turrets, then Builders, then the enemy economy, then untended barriers. Gunners are never
built by this bot but run steward's module if one exists.

## The income war, second look (I Stone, match `f05df8b3`)

I Stone took v109 3-2, and the two 1000-round losses (fimbulwinter game 1, stavkirke game 4)
were both lost on titanium collected.  The replays' `distributeResources` events say where every
stack went, and they showed four things, none of them the arithmetic:

- **The harasser cut the wrong tiles.**  On stavkirke their trunk was row 17, five conveyors
  carrying four Harvesters' stacks into the Core; ours bit the trunk six times, walked off to
  peek, came back and killed (6,18), (7,18), (8,18) -- thirty bites, three tiles nothing ever
  flowed through -- and never chewed again after round 200.  Targets were chosen by walking
  distance alone.
- **It chewed tiles a mender stood beside.**  On fimbulwinter every trunk tile it bit was healed
  back the same round -- (17,15) seven times over, (17,14), (18,15), (17,13), (18,10): 180
  rounds, nothing cut.  2 a bite never beats 4 a heal.
- **It healed a 3 Ti barrier for 210 rounds.**  Round 215 on stavkirke it denied the ore at
  (17,17); one of their Builders started chewing the barrier; ours stood there mending it every
  round until 424 while their network grew to 126 tiles.
- **A flung newborn built a home that was not there.**  I Stone parks a Launcher on our spawn
  tiles.  The miner spawned at (4,2) and had its first turn at (9,4) with the Core out of sight;
  `_orient` fell back to "the Core is where I am", and it laid six Harvesters and seventy
  conveyors toward (9,5).  Not one stack reached the Core all game.

What changed:

- **Loads, not distance** (`_belt_loads`, `_belt_trail`): the attacker remembers every enemy
  conveyor's facing (`enemy_belt_dir`) and traces each known enemy Harvester's output along the
  facings to their Core.  Every tile on a trail that arrives -- or leaves what this Builder has
  looked at in the last `LOOK_STALE` rounds, which may well continue -- carries that Harvester's
  load.  A tile with load 0 is never bitten (a dead end, the far side of our own stump, gefn's
  harvester-less conveyors); each Harvester feeding through a tile is worth `LOAD_STEPS` of
  walking; a tile their Builder stands beside ranks last.  Harvesters stay in the pool at their
  8-step tax.
- **The mender check**: the lowest HP seen on the target is tracked; `CHEW_IDLE` bites without a
  new low bans the tile for sixty rounds and the next one is taken.
- **The tend cap**: a barrier under chew is healed `TEND_CAP` rounds and then left for 150.
  Ring Sentinels are not capped.
- **The peek waits** while a chew is in progress (target adjacent): a conveyor at 8 HP is back to
  20 in three rounds of its mender's attention.
- **The frontier walk** (`_explore_belts`): when nothing known is cuttable -- covered, tended,
  banned, or all severed -- walk to the nearest uncovered stand beside a known belt or Harvester
  whose neighbour has not been looked at lately, where the next stretch is.
- **Home by mirror** (`_mirror_core`): a Builder that cannot see the Core on its first turn takes
  the enemy Core the Core reports in slot 2 and mirrors it -- the pool's symmetries are
  tabulated, an unknown map takes the mirror its own guess agrees with.  Checked against all
  thirty tabulated cores.

Local (seed 1, both seats, 15 maps): hildr78 27/30, steward 25/30, gefn 26/30, spar_sentinel
25/30, spar_wall 18/30 -- v108's numbers or a game better.  Against steward on bifrost the
harasser now cuts the two fed tiles, kills the Harvester and stops; the old build went on to chew
sixty bites of severed belt.

- **The diversion repair** (`_repair_belt`, `lost_belts`).  I Stone did not leave holes on
  stavkirke: from round 343 its Builders chewed our conveyors out and **re-laid their own on the
  same tiles, facing their Core**, so a repair that only looks for empty tiles saw nothing while
  our six Harvesters fed them 16 Ti a round for the last 400 rounds.  Now a foreign conveyor on a
  belt tile of ours facing the way ours did is left alone -- it carries our stacks the same way;
  one facing elsewhere, or one parked beside a Harvester of ours, is chewed out (ten bites, with
  the harasser's no-new-low check against a mender) and the line tile relaid, the side tile
  barriered so it is not laid again.  A tile in that state is no longer a belt a new chain may
  join -- `_plan_chain` could have ended a chain into their line.  Against a hijacker stub
  (eight menders on its ring so the ring cannot finish, three Builders chewing every conveyor of
  ours they see and re-laying theirs facing home): titanium collected stavkirke 30 -> 790,
  helheim 260 -> 1,010, jotunheim 50 -> 370, every game shorter.

Still open, Core side: in that game our three home Builders held ring tiles r330-430 with no
turret in sight and 3,500 Ti in the bank -- `HARVESTERS_MAX`/`MINERS_MAX` pinned us at six
Harvesters against their ten, so the tiebreak was lost with the bank unspent.
