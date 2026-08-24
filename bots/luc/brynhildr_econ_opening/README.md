# brynhildr_econ_opening

Fork of ladderfarm flagship `brynhildr@e9f94e7` (submission v110). It spawns one
store-free, precomputed opening miner on round 0, then starts Brynhildr's original
attacker on round 1. The opening owns neither Brynhildr's GCS slots nor its later
combat/economy policy.

`openingstrat/` is vendored inside the bot because ladderfarm and the platform
export only this bot directory. It is the same modular data-plan/runner package
used by the standalone opening harness, with no dependency on repository paths.

The opening is enabled on 37 terrain/start pairs selected by direct head-to-head
evidence. Against the unmodified flagship it won all 37 changed starts at seed 1;
the complete 53-map, both-seat panel was 68-38. Repeating the symmetric gates for
three seeds scored 52-2 (the losses were tied Pinch coinflips), and repeating the
19 asymmetric gates for five seeds scored 95-0. Two opening miners scored 17-20,
so the fork intentionally pays for exactly one before releasing the original rush.

hildr's Sentinel rush in steward's armour: `hildr@7a6d86c` (the walk, the ring, the race
arithmetic) plus the measured half of `steward_hardened_reinforced@366cd1b` (an economy that
wins timeouts, a home guard that survives sieges), rebuilt on what the ladder replays of both
actually showed.

## Where it stands

15 pool maps, both seats, seeds 1-3 (90 games an opponent), fcode 2.3.9:

| opponent | brynhildr | hildr@7a6d86c | steward@366cd1b |
|---|---|---|---|
| hildr@168b1a4 (v78, the flagship) | **75/90 (83%)** | 16/30 | 10/30 |
| steward_hardened_reinforced@366cd1b | **72/90 (80%)** | 23/30 | — |
| gefn@60ae5f1 | **72/90 (80%)** | 25/30 | 9/30 |
| hildr@7a6d86c | 69/90 (77%) | — | 7/30 |
| brokkr@05bf388 (Jon's economy bot) | 72/90 (80%) | 7/30 | 11/30 |
| v70 sentinel_rush_cluster | 75/90 (83%) | 25/30 | 11/30 |

Maps won in both seats: 10/15 against hildr78, 9/15 against steward, 10/15 against gefn.
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

## Comms (16 slots)

| slot | writer | content |
|---|---|---|
| 0 | attacker | Sentinels placed; the Core writes 0 to restart the ring |
| 1 | attacker | heartbeat `(round+1) + 65536*(eta+1 \| scouting bits)` |
| 2 | Core | enemy Core packed, `+ 65536*(ring_extra \| HOLD_REBUILD \| RING_HOLD)` |
| 3 | Core | orders `(round+1) + 65536*flags`: threat, econ, turret, gunner, quiet, miners allowed, Harvesters |
| 4-8 | ring Sentinels | heartbeats |
| 9 | Core | the turret hitting us: packed position, `+65536*(1 Sentinel \| 2+4*facing Gunner)` |
| 10-12 | ring | enemy menders, GO/HOLD/volley, enemy Core HP |
| 13-15 | home Builders | heartbeats `(round+1) + 65536*(mining \| harvesters<<1)` |

Guard Sentinels (a line that cannot reach the enemy Core) take no heartbeat slot and shoot
turrets, then Builders, then the enemy economy, then untended barriers. Gunners are never
built by this bot but run steward's module if one exists.
