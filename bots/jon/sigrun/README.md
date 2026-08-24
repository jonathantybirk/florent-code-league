# sigrun

A fork of `brynhildr@2f83111` -- submission **v109**, the build ladderfarm holds as
flagship. Everything below the line is brynhildr's own README, kept for lineage.
This part is only what the fork changes and the evidence for it.

## The pool is fifteen maps, and it is an exact instrument

`fcode maps list` is the competition pool and it is fifteen maps. `maps/` holds 53;
the other 38 are never drawn. That was the first thing the harness said and it
turned out to matter more than anything else measured here.

The pool also measures without noise. All fifteen maps are mirror- or rotationally
symmetric, so a build against a copy of itself, both seats, scores **exactly**
75-75 over 150 games -- measured, not assumed. Better, every start is decided by
(map, seat) alone: a five-seed run returns 5-0 or 0-5 in all thirty cells. One seed
is the whole head-to-head, and a change is worth precisely the seats it turns.

## What this fork changes

Three things, all small, all in the same pathology: the flagship loses to a
mid-game siege it has every mechanism to survive, and each mechanism is disabled
by a rule written for a different situation.

### 1. The anti-grinder rule must not outlive the Core it protects


`spar_wall` beats v109 0-3 on eleven pool starts, always by a Core kill between
rounds 98 and 221, always with titanium still in the bank -- 516 Ti on valkyrie A,
162 on glacierkeep A. Traced round by round on glacierkeep A: from round 47 the Core
takes a measured **28 HP a round** from four Gunners holding lanes, the mend squad is
sized correctly at **five** from round 80, and **not one mender is ever bought** for
the next 170 rounds while the bank climbs.

One line does it:

```python
if self.home_deaths >= 2 and threatened:
    need_menders = 0
```

Two menders die to those Gunners by round 45, and from then on the Core refuses to
buy any mender at all while anything is shooting it. Against a grinder that is right
-- bodies that die faster than they heal are the enemy's ammunition. Once the Core
itself is the thing being ground it is a suicide pact. The rule now yields when a
settled siege has the Core under `SIEGE_HP`:

```python
if (self.home_deaths >= 2 and threatened
        and not (siege_len >= SIEGE_SETTLED and hp < SIEGE_HP)):
    need_menders = 0
```

glacierkeep A against spar_wall goes from a loss on round 221 to a **win on round
814**. Across the panel it is **+12** and nothing regresses.

Three larger fixes were written first, upstream of this line -- raise the squad when
dying with a bank, size it to the measured damage instead of the `min(landing, 7)` a
barrier is assumed to take off it, let the squad outrank re-feeding the ring -- and
**all three produced byte-identical results**, because every one of them was
downstream of a gate that had already zeroed `need_menders`. Stacked on top of the
one-line fix afterwards they measured 97-23 against its 98-22, so none is carried.
The instrumenting is what found this; the guessing found nothing.

Ten of the eleven starts still lose, and four more fixes down that seam were measured
and none of them is carried. The layers are real and each is visible once the one above
it opens; they simply do not add up to a game.

* **The purse.** On valkyrie A the Core now *asks* for a second mender from round 120
  and buys nothing: `kill_hold` reserves the whole burst whenever the kill is priced as
  affordable, which against a wall it always is and never fired, so the Core dies on
  384 Ti. Freeing that reservation on the same terms as the squad: **98-22**, level.
* **The trigger.** `siege_len >= 30` arrives after valkyrie A is decided -- that Core
  falls from 493 to dead in 75 rounds. Keying "dire" on HP lost rather than rounds
  elapsed, or halving the qualifier: **98-22** both, level.
* **The sizing.** `min(landing, 7)` assumes a barrier takes the rest off a lane Gunner.
  Counting the lane Gunners once the siege is settled: **97-23**.
* **The counter-turret.** It is refused against Gunners because they re-seat, and
  spar_wall's do not -- three hold the same lanes for sixty rounds at 21 HP a round,
  which no squad out-heals, since MENDERS_MAX menders restore 20. Allowing it against a
  settled lane, breaking the `need_menders == 0` deadlock that held both purchases at
  once, and teaching `_counter_turret` to target a Gunner at all (it only ever collected
  Sentinels, so authorising the purchase bought nothing): **97-23**.

The arithmetic on those starts says menders cannot win and the turret does not arrive in
time, so the answer is probably neither -- not to be found by opening one more gate.

### 2. Close the lane rather than pay for what it does

Step 1 of `_home_builder` heals the Core whenever it is hurt and we are beside it;
step 2 lays a 3 Ti barrier in a live Gunner lane. Under sustained fire the Core is hurt
every round, so step 1 always fires and step 2 is never reached: every home Builder
stands there mending, and nobody ever walks off to close the lane.

The prices are not close. Healing is 1 Ti for 4 HP, so absorbing three lane Gunners at
21 HP a round costs 5.25 Ti a round for as long as they live. A barrier is 3 Ti, blocks
line of sight outright rather than absorbing the shot, and has 30 HP -- a 7-damage
Gunner needs five rounds to break one, so the same lane costs about 0.6 Ti a round to
keep shut. Shut beats paid for by an order of magnitude.

Only the lowest live home slot is diverted; the rest go on healing, so a Core that is
genuinely racing something down does not stop being mended. Diverting *every* Builder
is 98-22 on the screen -- then nothing gets healed -- against 99-21 for the one.

skald A against spar_wall goes from a loss on round 150 to a win on round 564. Across
the panel it is **+4, all of it in the spar_wall column** (59-31 to 63-27); the other
four columns do not move at all.

Re-measured on the merged file after `bots/jon/sigrun` picked up another agent's miner
and forage work, the same hunk is worth the same **+4**: spar_wall 62-28 without it,
**66-24** with, over fifteen pool maps in both seats at seeds 1-3. It is not made
redundant by their economy changes and they do not subsume it.

### 3. paths B opens with a miner

`openingstrat/` (vendored from `brynhildr_econ_opening`) spawns one precomputed mining
Builder on round 0 and starts brynhildr's attacker on round 1, on exactly one start.

Run on all thirty pool starts the opening turns four seats against v109 -- bifrost B,
glacierkeep A, helheim B, paths B -- and gating all four is **56-34 against v109** but
**328-122 against the panel**, below v109's own 332-118. Priced per start across the
panel the four are **-4, +0, -3 and +3**: the opening's tempo is worth its titanium
against v109's own rush and against almost nothing else. Only paths B survives being
priced against a field: +3 on the seeds it was chosen from, **+7 on held-out seeds
4-10** (49/70 against 42/70).

Selecting starts against a single opponent is fitting to that opponent, even when the
instrument has no noise in it. That is the whole lesson of the four-start build.

The catalog is cut from 3,539 lines to the one map the gate can reach, and
`_opening_enabled` requires `terrain.py` to *name* the map as well as match its size
and Core, so a foreign map sharing a start cannot get paths' plan laid on terrain that
does not describe it.

## A note on ownership

`bots/jon/sigrun` is no longer a single agent's directory: it has commits from more
than one, and a `git rebase` will merge a local hunk onto someone else's newer file
silently and cleanly. A clean rebase is **not** evidence that a benchmark still
describes the build. Every number below was re-measured on the file as it stands after
merging; keep the exact benchmarked directory around (`bots/jon/sig_<change>`) so the
diff is always available.

## Where it stands

Panel: fifteen pool maps, both seats, seeds 1-3, 450 games a build.

| build | total | v109 | brokkr | steward | spar_wall | spar_sentinel |
|---|---|---|---|---|---|---|
| v109 (the flagship) | 332-118 | 45-45 | 78-12 | 78-12 | 56-34 | 75-15 |
| + the anti-grinder exemption, + paths B | 344-106 | 51-39 | 78-12 | 78-12 | 59-31 | 78-12 |
| **sigrun** | **348-102** | **51-39** | 78-12 | 78-12 | **63-27** | **78-12** |

Head to head on the pool the fork is **0.567 against v109 in three independent seed
blocks**: 17-13 on seed 1, 51-39 across seeds 1-3 (the panel row above), and **85-65 on
held-out seeds 4-8**, which chose nothing. The flagship against a copy of itself is
exactly 75-75 over the same 150 games, so the held-out block is +20 games on a
measurement with no noise in it. Nothing here is fitted to a seed.

## Against the current frontier, not just the flagship

v109 is the build ladderfarm holds, but luc's lineage has moved several generations past
it, and those are what a promoted bot will actually be compared against. Fifteen pool
maps, both seats, seeds 1-3:

| opponent | sigrun |
|---|---|
| `brynhildr@2c7d15e` (luc's tip) | **57-33 (0.633)** |

Re-pricing the opening gate against that six-opponent field (the five-bot panel plus the
tip) rather than against v109 alone changed the answer: **glacierkeep A**, rejected on the
old panel, is **33-3 against 30-6** and is now enabled. paths B stays at 27-9 against
24-12 -- though it is *negative* against the tip alone (5-5 with, 10-0 without) and
positive against the other five. The field decides, not any single opponent; that is the
same lesson the four-start version taught, applied one level up.
| `brynhildr@2f83111` (v109, the flagship) | 51-39 (0.567) |

## What each change is worth, ablated on the merged file

Removing one hunk at a time from the build as it stands:

| change | with | without | worth |
|---|---|---|---|
| the anti-grinder exemption (vs spar_wall, 90 games) | 66-24 | 56-34 | **+10** |
| the lane-first barrier (vs spar_wall, 90 games) | 66-24 | 62-28 | **+4** |
| the paths B gate (paths, four opponents, 24 games) | 21-3 | 18-6 | **+3** |

None is dead weight and none is subsumed by the other agent's miner and forage work.
Note that removing the anti-grinder exemption returns the siege column to *exactly*
v109's 56-34: on this fixture the whole improvement over the flagship is these two.

## What was measured and thrown away

| build | total |
|---|---|
| + the four-start opening gate | 328-122 |
| + `HARVESTERS_MAX` 7, `ECON_ROUND` 30 | 331-119 |
| + the harvester cap raised only in the income war | 331-119 |
| + a home Launcher against loitering Builders | 321-129 |
| + that Launcher and the economy pair | 316-134 |

**The home Launcher is a negative result.** The bot already has the flinging half --
`_launcher` throws any adjacent enemy Builder to the far side of the map -- and its own
comment says "we never build one". A Gunner is measured off against harassers because a
squad digs 25 HP out faster than 7 damage a round kills one, and a Launcher never has
to kill anything: 20 Ti, no ammunition, cannot miss, and one throw puts a digger five
tiles from the wall it was laying. It still lost. Against brokkr, the harassment bot it
was built for, the column did not move at all (78-12 either way) -- the trigger never
fired, because a harasser steps in and out and `loiter` peaked at five of the six
consecutive rounds the Gunner rule wants. Rebuilt on cumulative visits it did fire, and
cost eight games of the mirror.

**The constants are at a local optimum.** Twenty-one perturbations against v109, 150
games each: most scored exactly 75-75 -- the constant never binds in games this short --
and the two that moved, `BURST_SLACK` and `SNIPE_BANK`, were worse in both directions.
Re-run against the four-bot panel (the right question), fourteen of them landed within
+-2 of control's 96-24. A seventeen-point structural flip search found nothing worth
more than +2 starts in the mirror, and the four-start gate is why a mirror flip is not
by itself evidence.

**Two changes believed on 53-map evidence do not survive the pool.** The
x/codex-wallguard siege guard (`brynhildr@533601b`) is 54-52 across all 53 maps and
**42-48** on the pool, bifrost 0-6. The shipped terrain-gated econ opening
(`brynhildr_econ_opening@3453e4a`, fitted against v110) is **14-16**. Together, 15-15.

## Reproducing

```sh
mkdir -p bots/rivals/bryn109
git show 2f83111:bots/luc/brynhildr/main.py    > bots/rivals/bryn109/main.py
git show 2f83111:bots/luc/brynhildr/terrain.py > bots/rivals/bryn109/terrain.py
uv run python tools/ab.py bots/jon/sigrun bots/rivals/bryn109 --seeds 1 --maps \
  auroraveil,bifrost,fimbulwinter,glacierkeep,helheim,holmgang,icefloe,jotunheim,\
longhouse,midgard,paths,skald,stavkirke,valkyrie,yggdrasil
```

`tools/flips.py` names the starts a change turns against a reference pattern from the
same rival; `tools/map_cores.py` reads the two Core positions out of a `.map26` so a
start can be named.

---

# brynhildr (the fork's parent, verbatim)


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
# Mining cadence

The Core's economy authorization and build timing are unchanged. Once mining
is authorized, a miner vacates a build tile inward through its finished belt
and stages on the inward tile while approaching the next build. This removes
step-away/step-back cycles without changing combat, repair, or spawning.

Paired seed-1 panel, 15 maps, both seats, versus Hildr, Steward, Gefn, Spar
Econ, and Spar Wall: **127-23**, versus **122-28** for `sigrun@338a1ad`.
The game-level matrix has five loss-to-win flips and no win-to-loss flips.
Antler and the two reproduced negative starts (Auroraveil A, Skald B) retain
the parent movement.

## The income-war cap

Sigrun v127's six online losses to Torsko and 0033 ended at connected-Harvester
counts 0-3, 4-11, 5-13, 2-7, 4-8, and 4-7. The opening was not the failure:
after Sigrun had explicitly abandoned the rush for `FORAGE`, the hard cap of
five still stopped its economy.

Normal play remains capped at five. Only while `ORD_FORAGE` is active, the Core
pays for up to seven Harvesters (the exact capacity of the existing order
field), and new forage chains route independently instead of adding load to a
possibly saturated trunk. All pre-verdict build timing is unchanged.

Discovery panel: **128-22** versus `ca5008a`'s **127-23**, one gain and no
losses. Held-out Spar Econ seeds 2-5: **120-0** versus **116-4**; Midgard B is a
loss-to-win flip at every seed.
