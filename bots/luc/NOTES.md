# Dev notes

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger — *except* the mjolnir section immediately
> following, which is the first in this file measured on 2.3.4 and is marked as
> such. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Scratchpad for the next session. Not shipped doctrine — ideas to measure, not trust.

## 2026-08-04 (2.3.4) — mjolnir: what actually kills our Core, and the ratio the patch inverted

**Everything in this section is measured on fcode 2.3.4.** It is the first
section in this file that is.

`odin@38e1456` scores **0.926 on the 336-game panel under 2.3.3 and 0.720 under
2.3.4** — same bot, same opponents, same maps. Six re-tuning variants over the
ammunition thresholds, guard cap, attacker cap and siege barrier landed between
234 and 248 against a 242 baseline: the whole spread is inside the panel's ~2pp
noise floor. This is not a tuning problem.

### The titanium table that decides 2.3.4

| action | effect | HP per Ti |
|---|---|---|
| Barrier, as a wall to be shot | 30 HP for 3 Ti | **10.0** |
| Builder heal | 4 HP for 1 Ti | **4.0** |
| Sentinel fire | 18 damage for 10 Ti | 1.8 |
| Gunner fire | 7 damage for 4 Ti | 1.75 |
| Builder attack | 2 damage for 2 Ti | 1.0 |

### What kills our Core (32 lost Cores, damage classified by event size)

    gunner        20755 HP  97.6%   in 32/32 games
    sentinel        504 HP   2.4%   in  5/32 games
    builder-fire      0 HP   0.0%   in  0/32 games

Enemy Builders never touch our Core. They emplace a Gunner near it — 114 within
four tiles, median life 34 rounds — and shoot. 79% of lost Cores die before
round 200.

A Gunner's ray "stops at the first targetable tile", and every compass ray that
reaches a 2×2 Core must cross its Chebyshev-1 ring. That ring is **twelve
tiles**. Any building on all twelve and no Gunner on the map has a firing line
into the Core. 36 Ti and +12% scale. It is not `_run_core_seal`, which walls
the whole threat disc and never finishes.

### The Sentinel ratio inverted and nobody noticed

`_build_siege_sentinel` has always run *last*, and its docstring gives the
reason: a Gunner "pays 2.78x more per point of damage". That was 10 damage per
2 ammunition against 18 per 10. 2.3.4 makes it:

    damage per ammunition   Gunner 7/4 = 1.75    Sentinel 18/10 = 1.80
    damage per round        Gunner 7             Sentinel 9
    attack radius squared   Gunner 13            Sentinel 32
    HP                      Gunner 25            Sentinel 40
    blocked by terrain      yes                  never

Over 50 games this bot built **0.0 Sentinels and 5.8 Gunners** and dealt 100%
of its damage to enemy Cores with Gunners. Promoting the Sentinel is +9 games.
The range gap is the only strictly asymmetric advantage on the board: a seat
beyond r²=13 hits their Core and nothing they own answers it.

### CORRECTION: all of the below is a pool-only gain

Re-measured on 40 generated maps against the same eight opponents, every change
in this section is negative and plain odin is the better bot on unseen ground:

| build | official pool | 40 generated maps |
|---|---|---|
| odin `38e1456` | 242 (0.720) | **445/640 — 0.695** |
| mjolnir, wall ON | **265 (0.789)** | 416/640 — 0.650 |
| mjolnir, wall OFF | 245 (0.729) | 409/640 — 0.639 |
| odin + Sentinel promotion only | 245 (0.729) | 408/640 — 0.637 |

Isolated: the wall is +20 pool / −45 generated. The Sentinel promotion is +3
pool / −37 generated — the "+9" below only exists in the presence of the wall.
The harvester cap is +4 with the wall and exactly 0 without it, because the wall
is what pushes games to round 1000 where extra Harvesters pay.

What survives: the wall counters an *atlas*, not a field. `steward` reads a
published-map oracle, so on the pool it emplaces on perfect firing lines from
round 0 without scouting, and walling every ray takes that away — odin gets
15/42 against it, mjolnir-with-wall 34/42. On generated maps, where the atlas is
inert, wall-off is best (58/80 against steward, to odin's 47/80). Steward is
nonetheless *last* of the four against the eight-bot panel (209/336): a counter
to our old flagship, not the field's best.

Three separate non-transitivities in one session — mjolnir beats the panel but
loses to odin 10/42; steward beats odin but is last on the panel; wall-off loses
the pool and wins the steward matchup. Neither head-to-head nor a single panel
ranks these bots. Only the 4,956-game Nash instrument does.

**The process failure worth remembering:** eleven variants were measured
pool-only before anything was checked on generated maps. The pool is 21 maps.
This file already carried the rule.

### Shipped (bots/luc/mjolnir)

    odin 38e1456 baseline       242/336  0.720   core losses 70
    + twelve-tile wall          250/336  0.744               68
    + harvester cap 4 -> 6      254/336  0.756               64
    + Sentinel siege promoted   264/336  0.786               51

### Measured and rejected — do not re-try without reading why

| idea | total | why |
|---|---|---|
| cut every Gunner budget | 205 | Core losses 68 → 113. Gunners still stop their attackers; the wall supplements them, it does not replace them. |
| dedicated 4th "waller" Builder + mender doorway | 213 | +20% scale and one deliberately open ray cost far more than the maintenance bought |
| split `_guard_home`, wall before the denial turret only | 236 | |
| `AMMO_TARGET` 120→240, floor 80→160 | 229 | converting more titanium starves building |
| two economy Builders out of three | 141 | **bad experiment** — leaves no attacker at all; tests "no offence" |
| wall the enemy Core's spawn ring | n/a | mechanism dead: every bot on this panel spawns its Builders on rounds 0–2 and never again. Code shipped OFF, one line to enable against an opponent that reinforces. |

### Two null-vs-negative traps, both of which cost a wrong conclusion

1. "The wall must not outrank the guard, 236 vs 246" was committed as a
   measured result. The wall it tested **never got built** — it sorted targets
   by distance to the enemy Core, walked to the far side, and circled the ring
   standing on the tiles it meant to fill, because every ring tile is a cardinal
   step from its two ring neighbours and against a map edge there is no shell
   outside to build from. With the cycle-walk fix the comparison reverses:
   **wall-first 250, guard-first 242.**
2. The waller variant was smoke-tested on three hand-picked maps and looked
   spectacular — Core never damaged on two of them, jackpot surviving to round
   1000 instead of dying at 74. On the full panel it scored **213**.

A null result and a negative result are indistinguishable in a table. Check the
mechanism fired before believing the number, every time.

### Still open

- The ring degrades: on jackpot it closes at round 25 with five tiles and is
  down to three by round 100. Traced cause — our conveyor on a ring tile dies
  on round 35 and the enemy builds a **Gunner on that exact tile** on round 36,
  point-blank against the Core and on ground we can no longer build on. A
  conveyor blocks a ray but is walkable and only 20 HP, so it is the ring's
  weak link by construction. Demolishing a ring squatter with Builder fire (25
  HP, thirteen hits, 26 Ti, no scale tax) is measured on the panel as `y_demo`.
- `_run_bulwark`'s memory expiry compared against `SLOT_CORE_DAMAGED`, which
  holds an escalation *level* (0/1/2) and not a round — so it fired at most
  twice a match and a Builder never returned to a wall it had walked away from.
  Fixed to expire on rounds; measured as `y_rc15`.
- vanguard is the one opponent the wall makes worse: 30/42 → 25/42, and the
  losses are Core deaths at rounds 74–129 in games the baseline won at 140–280.

## 2026-08-04 (late) — denial turrets: a firing ray is a wall you can buy

Shipped to odin at `b3fa36695` (0.932 -> 0.938) and to heimdall at `14570253a`.
Lucas's observation: enemy bots route *around* our firing lines rather than walk
down them, so a Gunner's ray is not only a weapon, it is a wall that costs 10 Ti
and never has to fire. `_denial_gunner_site` spends the guard's spare allowance
on one turret whose ray covers the Core-threat disc, scored by *uncovered* tiles
added so a turret is bought only when it denies ground no existing one does.

**The first numbers here were wrong and are corrected below — see the cache
trap at the end of this section.** Clean A/B, both sides under names that had
never been used, so nothing could be served from cache:

                   pool          generated      pantheon   vigil_reinf
    odin      311/336 0.926   140/160 0.875   32/42 0.76   29/42 0.69
    +both     315/336 0.938   139/160 0.869   34/42 0.81   32/42 0.76

+4 on the pool, +5 across the two hardest opponents, -1 on unknown maps.
warden_walk 0.81 -> 0.88 and Pantheon crosses 0.80. Traced on quarry against
the day3 replica: 14 turrets, 69 rounds and a loss becomes 10 turrets, 59
rounds and a win -- fewer guns, sooner, because the ray does the work of a wall.

I first reported this as +2 pool and **+7 on unknown maps**. Both were inflated
by a stale baseline: `sweep.py` cached results in `results/<botname><tag>/` and
replayed them whenever the *name* matched, regardless of what the bot behind
the name had become. The odin cells were eight hours old and predated the tabu
and line-of-sight commits, so the old build was scored as worse than it is.
Fixed by keying the cache on a hash of the bot's source.

### The flank does not transfer, in either direction

`FLANK_MIN_TURRETS = 4` is **+1 alone on heimdall and -1 alone on odin**, and on
odin only pays in combination with denial. odin's `_build_basic_gunner` was
rewritten around cover tiers and the duel rule, so the term slots below the tier
and above distance rather than where it sits in heimdall. Third instance this
session of the same rule: a constant is measured for the bot it was measured on.

### Rotation: the frozen turret is the cheaper failure

From a replay where one of our Gunners sat at full health with three enemy
Gunners on true compass rays and never turned. The cause is affordability, not
aiming: rotation costs 10 Ti and `ROTATE_TITANIUM_RESERVE = 40` refuses to spend
below a bank of 40 — probed at `rotate_allowed=False` on 294 rounds with the
bank at 2 and 16. Lowering it loses, monotonically:

    10 -> 303   15 -> 304   20 -> 309   25 -> 309   40 -> 313   60 -> 314
    80 -> 312   never rotate -> 282

Chasing with 10 Ti rotations costs more than the missed shots, but forbidding
rotation entirely costs 31 games, so the mechanic matters and only the gate is
generous. Plateau 40-60; leave it alone.

### The rotation policy is settled: rotate greedily, and do not get clever

Four ways of being smarter about turning, all measured on odin, all worse in
strict proportion to how often they decline to rotate:

    rotate greedily at whatever is nearest (shipped)   315/336
    aim one round ahead, but always rotate             311/336
    rotate only when the projection says it hits       301/336
    hold the facing within r^2 36 of our own Core      284/336
    never rotate at all                                282/336

The accounting error is valuing a rotation only by the shot it lands. Turning
toward an enemy re-aims the ray over the ground they occupy, which deters the
approach and catches them when they cross it later; the rotations that "miss"
are what keep the turret relevant to where the fight is. A turret that only
turns when sure of a kill spends most of the game pointed at nothing. Same
lesson the denial turret teaches from the other side: **the ray works by
covering ground, not by scoring hits.**

Hold-the-lane is worth its own line because the reasoning is seductive and
wrong. A denial turret is bought to hold a lane, so abandoning it to chase an
intruder looks like self-harm -- but a frozen turret is trivially walked around
(24 of the 44 tiles in its range are blind to any single facing), and it loses
31 games on the pool, 15 on unknown maps, and 5 against Pantheon. Deterrence
comes from *where the turret is placed*, not from what it refuses to do next.

### Measured and rejected here, with numbers

- **Lead a rotating turret onto where the target will be** (one round of linear
  extrapolation, present tile as fallback). Diagnosis was right -- we aimed at
  where the target had been, permanently one round late against anything that
  moves -- and it does not pay: pool 307/336 against 311, generated level,
  ladder 396/462 against 397, and **0 difference against both the day3 replica
  and the real Pantheon** (identical 2-3, same turn counts). Rotations cost
  10 Ti each and leading buys more of them.
- **Anticipate motion when *siting* a new turret** (prefer a seat whose ray the
  enemy walks along rather than across). 310/336 against 311. The reason is
  structural: `_aligned_gunner_site` only considers the 8 tiles adjacent to the
  Builder, and probing shows usually **exactly one legal site**, with
  `along_values=[1]` -- no candidate ever had the enemy walking down its ray.
  A better preference order cannot help when there is nothing to choose between.
  The lever is the guard's *position*, not its aim.

### Gunner geometry, worth knowing before designing anything here

Within r^2 <= 13 there are 44 tiles; only **20 are on one of the 8 compass rays**
and **24 are unreachable from that tile by any facing**. At Chebyshev distance 1
all 8 neighbours are hittable, at distance 2 it is 8 of 16, at distance 3 only
4 of 20. A unit standing off-axis is immune to that turret however it rotates.

## 2026-08-04 — FOR WHOEVER OWNS odin: a pacing bug, and a flank idea that never fired

Written by a parallel session working on `heimdall`. I am deliberately **not**
touching `bots/luc/odin/`, because two agents editing one bot directory clobber
each other. This is the handoff instead.

**odin paces.** `benchmarks/pathology.py` over bridge+longship, odin as team a:
**110 paced / 3324 Builder-rounds = 3.3%**. Healthy is 0–2%. With the fix below
it is **21 / 5132 = 0.4%**.

The cause is in `_move_while_stuck`, and its own comment already describes it:
it picks the neighbour nearest the target, "and that choice reverses the moment
the Builder steps", so a Builder with an unreachable goal oscillates forever.
It is a greedy step with **no memory of where it has been**.

The fix is one sort term — prefer a neighbour we have not just stood on:

```python
    recent = p.recent_tiles[-TABU_WINDOW:] if TABU_WINDOW else []
    ...
            candidates.append((
                recent.count(tuple(position)),   # <- the whole change
                tuple(position) in p.seen,
                position.distance_squared(target),
                position.x, position.y, direction,
            ))
```

plus `TABU_WINDOW = 4` in `constants.py` and its import. `p.recent_tiles` already
exists — the confinement check maintains it — so nothing new is tracked.

Measured on **heimdall's** chassis, 21 official maps both seats, 8 opponents:

    TABU_WINDOW  0 (control)   304/336  0.905
                 4             308/336  0.917   <- lifts warden 0.86 -> 0.90
                 8             306/336  0.911
                16             303/336  0.902

Falls off either side of 4, which is the shape a real effect has. It composes:
heimdall shipped it together with the repair cap at 311/336 (`4c0d92eb2`).

### …and on odin it is a wash on the pool, a small gain on unknown maps

Both arms, with odin's own baseline re-measured here under identical
conditions rather than quoted (it reproduces 135/160 exactly):

    odin                    313/336  0.932      135/160  0.844
    odin + TABU_WINDOW 4    312/336  0.929      137/160  0.856

Pool -1 (the only column that moves is valkyrie 0.98 -> 0.95), generated
**+2**. Net +1 across both arms, and the gain is on the arm made of terrain
nobody has tuned against — which is the arm the final tournament looks like.

That is a judgement call and it belongs to odin's owner, not to me. What is
*not* a judgement call is the underlying observation: the pacing **symptom**
transfers between chassis (3.3% -> 0.4% on both) while the **value** of fixing
it does not. heimdall gains 4 games on the pool from this; odin loses 1.
Pacing is wasted Builder-rounds, and what a wasted round costs depends on what
that Builder would otherwise have done — and odin's Core-death projection
gives it a different Builder budget under pressure.

An earlier version of this section called it a flat rejection. That was
written from the pool arm while the generated arm was still running, and was
wrong; recorded here because issuing a verdict on one arm when a second is in
flight is exactly the partial-run trap this file warns about elsewhere.

### Also measured on this chassis, and rejected — do not re-run these

- **Flank a massed turret wall** — NOT REJECTED, **NEVER TESTED**. Worth
  reading before anyone tries it again, because the scores look like a
  rejection and are not one. Seat on the far side of their Core when they have
  massed turrets, since a Gunner has a fixed facing and rotating costs a flat
  10 Ti. Scores: pool 310/336 against 311, ladder 394/462 against 397. But an
  instrumented build says the rule **never fires at all**: across quarry,
  string, vase, bridge, jackpot, longship and twins it had an opinion on
  **0 turns**, and a win/loss diff over 21 maps x 2 seats x 3 opponents found
  **0 cells changed in either direction**.

  The reason is a hard number. Probing every seat decision for how many enemy
  turrets are visible at that moment:

        quarry    52 decisions with 0 turrets, 13 with 1, 6 with 2
        jackpot   32 decisions, all with 0
        longship   4 decisions, all with 0

  The maximum ever seen is **2**, so a threshold of 3 can never trigger, and
  the 1-game differences above come from elsewhere. The attacker simply is not
  standing there at the moment a wall exists — it seats early, is capped at
  `attack_gunners_built < 5`, and by the time a defender has massed turrets it
  has stopped choosing seats or is dead.

  So the open question is not "does flanking pay" but **"why is our attacker
  never present when the wall goes up"**. The right version of this idea is
  probably not a seat sort key at all: it is choosing which *side to approach
  from* before walking, or keeping the attacker alive long enough to re-seat.
  `<scratchpad>/variants/z_probe2` is the instrumented build that produced the
  table above.
- **Rotation-aware flank** (also avoid tiles a turret could reach *after*
  turning; `_ray_direction` returning None is the exact test for off-axis tiles
  that rotation can never reach). Scored **identically** to the plain flank,
  310/336 with the same per-opponent column — unsurprising given neither one
  ever fires. It did cost CPU: worst turn went from under 4 ms to over 4 ms
  when computed per candidate seat. Precomputing a rotation-cover map the way
  `_enemy_turret_cover` does brings it back to 5 ms. The mechanism is right and
  is worth keeping in mind if the trigger problem above is ever solved.
- **Step out of the ray when shot** (`_dodge_fire`). The symptom is real —
  `benchmarks/underfire.py`, added in `4c0d92eb2`, counts Builders that died
  without moving through the whole burst that killed them, and we do it on
  21–29% of Builder deaths against opponents' 11–24%. The cure loses: 132/160
  on generated maps against 135, and −7 games across the four hardest ladder
  matchups.
- **Stop sieging while our own Core is under attack.** 276/336 and 290/336 at
  0 and 2 remaining siege Gunners, against 304. Easing off their Core removes
  the counter-pressure that keeps them home.

### The local 8-bot panel is not the ladder, and the gap is large

The cluster run `auto-d3474c585dde` rates `heimdall@daf0de0` at **0.845 over
4,284 matches**, with **37 opponent builds below 0.80**. The panel in
`sweep.py` pins **one commit per opponent name**; the ladder runs six different
`vigil` builds, two `valkyrie`, two `warden_walk` — and the rate varies up to
10 points across builds *of the same bot*. Scoring against one of them is a
sample of size one.

Worst real matchups, none of which are in the default panel:
`ragnarok_fair@79582fc` 0.595, `vigil_reinforcements@60d5afa` 0.619,
`steward@e55aab5` 0.643, `tempest_ferry@26b5aa1` 0.643, and the whole
`tempest_*` family around 0.67–0.71.

`<scratchpad>/ladderpanel.py` scores against extracted real builds instead;
the extraction is `git archive <commit> <path>` per bot, driven off
`bot_a_commit`/`bot_b_commit` in the run's `matches.csv`. Worth rebuilding as
a committed tool — the panel being wrong is what hid the Core-death
projection's value (it looked like a 3-game regression on the 8-bot panel and
is **+5** on the ladder gate).

## 2026-08-04 — odin: the repair cap shipped, and the Core learns it is dying

### odin v1 (45aa24a90): heimdall plus the unshipped 0.917 combo

The r_cap3combo build from the Aug 3–4 night session (repair cap 3 +
`AVOID_ENEMY_RAYS` off + siege barriers off) was still sitting in that
session's scratchpad, measured 308/336 on the pool and never shipped. Its
"outstanding" generated-map arm turned out to already be in the results cache:
134/160, byte-identical to heimdall. Shipped as `bots/luc/odin` after a
determinism smoke test reproduced the cached cells exactly. First cluster
read (partial run, auto-ac724e1e86fd): 0.914 over 3,564 matches, 104
opponents; every sub-0.75 matchup is our own family (heimdall 0.52,
pantheon_replica_day3 0.60–0.62) — sibling wars, not external weakness.

### odin v2 (5ed86d3cb): the Core-death projection, Lucas's idea, landed

The jackpot diagnosis "split production between attack and defence" cashed
out concretely: our guard Builder died r143, the sole survivor was the
attacker across the map, and the Core bled 10/round from r157 to r192 with
**762 titanium banked**. Income healthy → the watchdog respawn never fires;
nothing replaces a dead defender. The dying-rich failure, one level up.

The fix is the same conditional-respawn shape as the income watchdog: the
Core projects forward from its own HP curve (damage over last 20 rounds,
dead within 60 at that rate, nothing judged before round 40) and spawns up
to two Builders under a new `CORE_DYING_FLAG` (bit 3 of SLOT_CORE_DAMAGED).
The first runs `_guard_home`; the second **only heals** — in the traced game
both defenders picked turret duels and the Core was healed exactly once all
game, while 4 HP for a flat 1 Ti out-pays everything at any scale. The
traced loss became a 1000-round tiebreak win, 5,180 vs 2,910 mined.

Panel: 313/336 = 0.932 (heimdall 304, odin v1 308), every opponent ≥ 0.81,
jackpot 9/16 → 13/16, generated arm 135/160. Pre-registered before the run
(jackpot ≥ +2 cells, no opponent −2, pool ≥ 308, arm ≥ 134) and every clause
passed. Sibling matchups byte-identical — the projection never fires there.

### The grace round is the whole mechanic

Without a grace round the flag fired on **round 14** of a longship rush,
bought two Builders at +20% each into a small bank, and the opening died of
the scale bill (longship 13/16 → 11/16) — the unconditional-refill lesson
recurring precisely. Grace 0/40/80 measured: 312 / **313** / 312, and only
grace 40 keeps both longship 13 and jackpot 13. An early rush belongs to the
reactive guard; the projection exists for the mid-game where the guard is
dead and the bank is rich.

### A latent bug worth knowing: the heartbeat undercounts riders

In the longship misfire the Core read `live=1` with all three opening
Builders alive. A Builder in Launcher transit gets no turn, misses a
heartbeat write, and the reinforcement gate (`live >= MAX_LIVE_BUILDERS`)
stops holding. The projection's grace round hides the consequence for v2,
but the income-dead respawn path reads the same counter and could
double-spawn during a ferry. Not fixed; worth a look before anything else
leans on `live`.

### Handoff answered: odin takes the tabu step (pool −1, generated +2)

To the parallel session that wrote the section above: read, and taken, with
thanks — the pacing trace and the both-arms measurement made the call easy.
odin ships `TABU_WINDOW = 4` because the final is unseen terrain and the gain
sits on the generated arm (137/160 = 0.856, the best off-pool number in the
record) while the pool cost is one game inside a column that stays ≥ 0.81
everywhere (valkyrie 41 → 40, reproduced exactly here as a port check). The
flank trigger question ("why is the attacker never present when the wall goes
up") is noted as odin's next open thread alongside the sibling war.

### Lucas's line-of-sight theory, measured: right about the attack, wrong about the guard, fatal under BLITZ

The theory — we keep seating turrets inside enemy turrets' lines of sight —
shipped in odin v4 (19630293c) after three full-panel ablations:

- **Full package** (tiers everywhere + duel-heal): pool 308, arm 138. The
  losses were localized and diagnostic: showdown 16/16 → 13/16 with two
  losses on the *mutual-kill stored-titanium tiebreak* at rounds 28–33
  (under BLITZ, seat detours and healing titanium are tiebreak poison), and
  bridge 12 → 10 (the guard moved off the corridor tiles the belt needs).
- **BLITZ exempt + guard reverted**: pool 311, arm **140/160 = 0.875**, the
  best off-pool number in the record. Shipped.
- **Duel tend 15 vs 40**: byte-identical on all 496 games. Duels resolve
  fast; the bound never binds. Left at 40.

The duel mechanic works as specced: the tier-2 turret is built facing the
covering turret (first on the ray both ways, so it fires from round one and
its own rotation logic swings it onto the Core once the duel is won), and
its Builder stands adjacent healing 4 HP for a flat 1 Ti against the
10/round it takes. What did NOT survive contact: applying the preference to
the home guard (the corridor tiles worth covering are exactly the covered
ones — defence wants contested tiles, attack wants safe ones), and applying
any of it to a race (BLITZ was already the doctrine with no ring Builder;
it is also the doctrine where this whole family of ideas is a tax).

Bridge's remaining deficit (10/16) is now the attack-side tier detour on
the one map whose only approach is one corridor; still single-map surgery,
still left for the cluster instrument.

### Bridge is the last sub-0.81 map, and its cells are razor-thin

sentry_g40 bridge 12/16; all four losses are round-1000 titanium tiebreaks:
two lost by 80 and 130 Ti out of 2,400–7,300, and two seat-b zero-economy
games (0 and 430 mined — one of them lost 0 to **90**). The zero-economy
pair is the repair cap's failure mode where the corridor is the only route:
the cap stops paying for the contested tile and the belt has nowhere else to
go. Fixing that is single-map surgery on 16-game cells; left for the
4,000-game cluster instrument. Everything else ≥ 0.81 per map.

### The gap was never the attack, it was when the defence wakes up

`_defend_core` triggers on `SLOT_CORE_DAMAGED`, which the Core raises at
`hp <= max_hp - 50` — five Gunner rounds *after* the enemy turret is already
emplaced. Answering then costs a turret duel. Answering on **sighting** costs
four shots at a Builder, and the difference is enormous because of how thin the
attack is: the whole enemy attack is one Builder, and their Core will not spawn
a replacement while any of their Builders still answers the heartbeat.

`_guard_home` in `heimdall`: the ring Builder — the one already standing at our
Core — puts an aligned Gunner on any enemy within r²=36 of the footprint,
before the ring and before the seal. 21 official maps, both seats, against
valkyrie/vigil/ragnarok/vanguard, 168 games a row:

    warden_walk (control)          118/168  0.702
    + guard r^2 64                 142/168  0.845
    + guard r^2 36                 145/168  0.863
    + guard r^2 36, cap 2          147/168  0.875   <- shipped
    + guard on every Builder       137/168  0.815

Against valkyrie alone it is 26/42 → 39/42. The mechanism is visible in the
metrics, not just the score: opponent Builders alive at round 100 fall from
2.65 to 2.27, and our own Gunners built rise from 5 to 7.

Tuning, same panel: radius 16/25/36/49 → 146/145/147/140; cap 1/2/3/4/6 →
139/147/145/146/145; chase 2/4 → 143/147. Radius and cap are flat over a wide
middle and fall off at the edges, which is what a real effect looks like.
r²=49 is where it starts paying turrets for scouts that were never going to
emplace.

Only the ring Builder guards. Letting all three do it is 137: the economy
Builder abandons the belt and the miner stops walking to ore.

### Correction: "ferrying on the symmetry guess is worse" does not hold off-atlas

The pool-era measurement (17/42 against 21/42, `FERRY_ON_INFERENCE` off) was
made on bots that *carry* an atlas. With one, `sighted` is set on round 0 and
the relay always runs, so the flag only ever governed the few games where the
lookup missed. On a bot with no atlas at all it governs **every** game: a unit
does not physically see the enemy Core until it has walked most of the way
there, and the relay it would then ask for is pointless. The flag was quietly
throwing away the whole 20pp the relay is worth (`MAX_RELAY_LAUNCHERS = 0`
scores 0.506 against 0.702).

Redone on the atlas-free chassis, 168 games against valkyrie/vigil/ragnarok/
vanguard: **119 off, 128 on**. It is now on in `heimdall`.

This is the general shape of the atlas problem and worth remembering: a flag
measured on a bot that has the oracle is not measured for a bot that does not.

### What fairness actually costs, separated from the guard

Same panel, 168 games a row, so the four rows are directly comparable:

    warden_walk         atlas, no guard    118/168  0.702
    ww_fair             fair,  no guard     96/168  0.571
    heimdall (v1)       fair,  guard       119/168  0.708
    heimdall + ferry    fair,  guard       128/168  0.762
    gd_r36_c2           atlas, guard       147/168  0.875

So on the **published pool**, against opponents that all carry the atlas, the
oracle is worth about 13pp without the guard and 11pp with it. The guard is
worth 17pp with the atlas and 14pp without. They are close to additive and
neither explains the other.

That 11-13pp is the price of fairness *on maps the atlas knows*. It is zero on
maps it does not, and the measurement is unusually clean. 24 generated
symmetric maps, both seats, against vigil and ragnarok:

    heimdall     (fair,  guard)   65/96  0.677
    warden_walk  (atlas, no guard) 46/96  0.479
    valkyrie     (atlas, no guard) 46/96  0.479
    ww_fair      (fair,  no guard) 46/96  0.479

Three controls landing on exactly 0.479 is the result: off the pool the atlas
is inert, so an atlas bot and its atlas-free twin play the identical game.
Whatever the oracle is worth on the ladder, it is worth nothing in the final,
and the guard is worth twenty points there.

A second, independent set of 30 maps (`--seed 4242`) reproduces the size of it
exactly: heimdall 74/120 (0.617) against the same control's 50/120 (0.417).
Twenty points on both sets, from different seeds.

### Measured and rejected — do not re-run these

- **Core shell.** Barriers on all twelve tiles touching the 2×2 Core. The
  mechanic is real and verified in the API docs — a Gunner's ray "stops at the
  first targetable tile", so a solid ring one tile out blocks every seat inside
  r²=13, and a Builder cannot reach the footprint to fire by hand either. It
  still loses: 78/126 → 67/126. It cannot be finished before round ~20, our
  Core takes its first damage on round 13, and the barriers come out of the
  ring Builder's mining (harvesters 2 → 1). Sealing the tiles they shoot *from*
  is the wrong side of the problem.
- **Piercing Gunner seats.** `_build_basic_gunner` demands `can_fire_from`, a
  line clear *this round*. That is too strict — a Gunner clears its own line,
  and only a WALL is permanent — and the failure is real: traced on aurora, the
  attacker stood beside a Core screened by the enemy's own conveyor line,
  found no legal seat, and wandered for 25 rounds with 40 Ti and 80 ammo in the
  bank. Fixing it does not pay: 0.702 → 0.673/0.690/0.679/0.679 at 0/1/2/4
  blockers allowed. The rounds spent chewing belt are worth less than the seat.
- ~~**The Launcher knobs are finished.** On a six-bot panel,
  `MAX_RELAY_LAUNCHERS` 0/1/2 → 0.552/0.706/0.683 and `RING_MAX_SITES` 0/1/2/3
  → 0.611/0.667/0.706/0.698. Both already sit on their maximum.~~
  **This was the most expensive wrong sentence in these notes.** Both knobs
  moved on the full eight-bot panel: relay 1 → 2 (+5 games) and ring 2 → 1
  (+9 more on the pool, +12 on the generated set). Together they took heimdall
  from 0.878 to **0.905** on the pool and 0.762 to **0.838** on unknown maps —
  the largest single gain of the session, sitting behind a note saying not to
  look.

  Three things made it wrong, and all three are general:
  1. **A narrower panel.** Six bots, and the two that were missing are the ones
     the ring change moves most.
  2. **An older chassis.** It predates the guard, `FERRY_ON_INFERENCE`, and the
     income watchdog. `_run_launcher_ring` blocks economy work while the ring
     Builder walks, and that Builder is now also the guard — so the ring's cost
     went up when the guard shipped, and nobody re-measured it.
  3. **The two knobs interact and were read one at a time.** A Launcher is +10%
     on every later price, so the second ring site raises the price of both
     relay Launchers. Neither reading stayed valid once the other changed.

  The general rule: **a constant is only measured for the bot it was measured
  on.** Every stale constant found this session had an honest comment next to it
  describing a real measurement taken on a bot that no longer exists. Re-measure
  on the current chassis and the full panel before believing any of them —
  including the ones in this file.
- **Replacing Builders the enemy killed is a large regression here.** The Core
  gates respawning on `has_live_builder`, which only proves *one* Builder is
  alive; widening the heartbeat slot to a round stamp plus one bit per Builder
  lets the Core count them and refill to three. It looks obviously right — the
  guard kills attackers, so both sides lose bodies — and it is not: on the same
  168-game panel, guard + refill scores **85/168 (0.506)** against the guard's
  147, and refilling to a ceiling of eight is worse still at 70/168. Every
  replacement is +20% on every price the team pays for the rest of the game,
  and an attrition war fought by respawning is lost on cost while being won on
  bodies. **Resolved** — see "the bastion lineage" below. The disagreement with
  `steward` was not a disagreement: refill is chassis-dependent, harmless where
  Builders rarely die and ruinous next to a guard that makes them die.

### The bastion lineage, settled

`warden` → `steward` (+ Builder refill) → `bastion` (+ a *static* home guard:
the second ring site becomes a Gunner facing the likely approach). It was
dropped mid-session without a verdict — never rated, since all three sat
deferred behind the evaluator queue. So it is worth one clean number. Standard
panel, 21 official maps, both seats, valkyrie/vigil/ragnarok/vanguard:

    warden        107/168  0.637   <- the correct control for steward
    steward       109/168  0.649   warden + refill          +2, noise
    bastion       110/168  0.655   steward + static guard   +1, noise
    warden_walk   118/168  0.702   Launcher caps
    heimdall      136/168  0.810   atlas-free + reactive guard

Three conclusions, all of them corrections:

1. **Refill is neutral on this chassis, not a regression.** 107 → 109. It is
   catastrophic only alongside the reactive guard (147 → 85), because that
   guard is what makes both sides lose bodies. Real interaction, not a
   contradiction.
2. **A static guard is worth nothing: +1 game.** The reactive guard is worth
   **+29** over the same control. Pre-placing a turret facing where the enemy
   probably comes from is not the same mechanic as answering the intruder you
   can actually see, and only the second one pays.
3. **"steward is off the trade-off frontier" was a narrow-panel artefact.** It
   was measured on three hand-picked opponents (prospect / ragnarok_fair /
   vigil@60d5afa), scored 84/126 against warden's 79, and the four-bot panel
   reverses the sign to noise. Two opponents chosen as poles of a trade-off are
   a probe, not a panel; do not draw a conclusion from one.

So bastion is correctly dead — not because it regresses, but because it is flat
where the chassis it was abandoned for is 26 games better.

### Everything else tried on the heimdall chassis, against 128/168

### Everything else tried on the heimdall chassis, against 128/168

Same panel, same 168 games, all built on the shipped atlas-free bot:

    BLITZ keeps a guard (2 attackers, not 3)   134/168  0.798   <- shipped
    guard leashed to ore within 8 of the Core  130/168  0.774
    counter-battery at the enemy Core          129/168  0.768
    RELAY_STOP_DISTANCE 7 -> 4                 127/168  0.756
    guard cap 3 instead of 2                   127/168  0.756
    ferry only on a *sole* surviving symmetry  121/168  0.720
    FORTIFY with two economy Builders          110/168  0.655

Only the first is a real effect. The BLITZ hole is worth understanding: that
doctrine was the one with no ring Builder, so it had no guard at all, on
exactly the maps where the enemy attacker arrives soonest.

The ferry row is worth reading twice: waiting until the symmetry inference has
only one surviving candidate before ferrying is *worse* than ferrying at the
farthest guess immediately (121 against 128). Being right early beats being
certain late, and a wrong guess self-corrects the moment terrain contradicts it.

The last row is the interesting negative. The FORTIFY role split was measured
at 2-12 long before a working defence existed, and the obvious hypothesis was
that a bot which cannot be killed should take the closed maps to the round-1000
economy tiebreak. It is still wrong, by more than the original margin.

### Counter-battery: a +11-game result that did not replicate

Worth writing down as a worked example of the trap this file keeps warning
about. `_engage_with_turret` is capped at zero field Gunners under RUSH, so
the attacker never answers the defender shooting its battery. Letting it build
two, but only within 6 tiles of the *enemy* Core (where a defender cannot walk
away from the turret, which is the measured reason field Gunners fail on open
ground), looked like a real find:

    30 fresh generated maps, vs vigil and ragnarok
      heimdall            74/120  0.617
      + counter-battery   85/120  0.708      <- +11 games, all of it ragnarok

Then it was replayed on the other, independent generated set and on the pool:

    24 generated maps (set 1)   65/96 -> 66/96    +1
    21 official maps            128/168 -> 129/168 +1

Then, because two sets disagreeing is not an answer, a third set of 40 fresh
maps was drawn and the prediction written down first: *counter-battery gains
against ragnarok and is level against vigil.* It failed.

    40 generated maps (set 3)   99/160 -> 101/160  +2 (ragnarok 55 -> 56)

Full ledger: +1, +11, +2 on three unknown sets and +1 on the pool -- 15 games
in 544, all of it one set. Not shipped. The mechanism is still sound and may
be worth revisiting with a sample that can resolve it, but "it worked on the
set I found it on" is not a measurement, and a pre-registered prediction is
the cheapest way to find that out.

Same story, smaller: leashing the guard's ore claims to within 8 tiles of the
Core (130/168 pool, 75/120 set 2, both +1 or +2) and rebuilding guard turrets
that have been shot off (76/120 set 2, +2). All inside noise.

### The guard's cap was the next real thing, and it replicated

Tracing a loss beat guessing again. On `runestone` the guard fired on rounds 10
and 12, spent its cap of two, and then watched valkyrie put two more Gunners on
tiles none of our turrets could reach. A Gunner has eight rays; a turret placed
to hit a Builder standing somewhere else usually cannot engage what replaces
it, and `_defend_core`'s own escalation needs `180` damage before it will allow
a second answer.

`_guard_allowance` = `MAX_GUARD_GUNNERS` + one per live enemy turret inside the
guard radius. Pre-registered before the replication ran ("beats 74/120 on set 2
by roughly +5pp"):

    30 generated maps (set 2)   74/120 -> 82/120   +6.6pp
    40 generated maps (set 3)   99/160 -> 108/160  +5.6pp
    21 official maps           134/168 -> 135/168  +0.6pp

Pooled over both unknown sets: 173/280 -> 190/280, +17 games. Shipped.

Tried at the same time and *not* shipped: falling back to healing the Core when
the guard has no firing solution (heal is 4 HP for a flat 1 Ti and needs no
alignment, so it looked like the natural partner). Pool 135/168, set 3 101/160
-- +1 and +2. A wash.

### A real bug: the published enemy-Core guess flip-flopped every round

`_update_enemy_core_inference` ends with each Builder writing *its own*
favourite surviving candidate to `SLOT_ENEMY_CORE`. Builders reject candidates
from their own vision, so two of them with different rejection sets overwrite
that slot with different answers on alternate rounds, indefinitely.

Instrumented on longship, heimdall vs warden_walk:

    RUSH  5 at (10, 9) target (24, 8)
    RUSH  6 at (11, 9) target (24, 10)
    RUSH  7 at (11,10) target (24, 8)
    ...
    RUSH 19 at (19, 7) target (24, 8)
    RUSH 20 at (19, 8) target (24,10)      <- pacing, not travelling
    ... to round 34

The attacker's BFS target reversed every round, so from round 19 it walked back
and forth between two tiles for fifteen rounds. warden_walk, which has the
atlas and knows the answer on round 0, emplaced at our Core on round 14; its
own Core took zero damage all game.

Fix: an inference another Builder has already published stands until *this*
Builder disproves it. Same trace afterwards locks on at round 5 and sights the
real Core at round 16. Worth +4/336 on the pool and +1/160 on generated maps --
inside noise both times, which is worth stating plainly: this shipped because a
target that changes every round is a defect, not because the score moved.

Worth checking the same class elsewhere. `SLOT_SYMMETRY_REJECT_START +
min(builder_index, 1)` gives three Builders two slots, so Builders 1 and 2
clobber each other's rejection masks -- benign only because each writes the
team OR it read, so bits re-propagate.

### A 918-round livelock that costs nothing, and the tool that found it

`benchmarks/pathology.py` counts Builder rounds spent stepping back onto the
tile just left. On the shipped bot across the pool it reports:

    bridge 31.3%   twins 27.6%   string 21.6%   runestone 14.3%   strait 13.3%

bridge, traced: the economy Builder spent **918 of 1000 rounds** alternating
between (10, 6) and (11, 6). The cause is in `_explore`'s fallback. Once every
stride point is explored it walks to the farthest of the four corners *from the
current position* -- and the two farthest corners are symmetric about the
Builder, so stepping toward one makes the other farther and it flips back next
round. A patrol of two tiles, forever.

Two fixes, both obviously more correct than the livelock, both measured on the
8-bot pool panel and 40 generated maps:

    shipped (livelock present)   270/336  0.804   110/160  0.688
    latch the chosen corner      268/336  0.798   110/160  0.688
    go home when idle            264/336  0.786   110/160  0.688

All three land on *exactly* 110/160 on the generated maps, which is the
cleanest possible statement of the result: off the pool the idle Builder's
behaviour makes no difference whatsoever.

The **attacker** livelocks the same way and it is not the idle case, so this
looked like the one that would pay. On generated `r18`, which we lost, the
attacker spent 81 of 193 rounds alternating between (22, 8) and (22, 7): it
reaches the enemy Core, `_build_basic_gunner` finds no legal seat, the breaker
and the Sentinel both decline, and the fallthrough is `_explore` -- which walks
*away* from the only target that matters and then paces. Replacing that
fallthrough with `_harass`, so it stays in their half shooting the belt and is
still standing there when a seat frees up, flips r18 from a loss at round 193
to a win at round 413 and takes its pacing from 30.7% to 0.9%.

    shipped                      270/336  0.804   110/160  0.688
    attacker harasses instead    268/336  0.798   111/160  0.694

Also neutral: -2 and +1 over 496 games. It does redistribute -- valkyrie and
warden each +1, vigil -3 -- but the total does not move.

### Posting the idle Builder as a picket -- the best of the five, still not enough

Suggested rather than derived, and the reasoning is better than "stop pacing":
the whole defence triggers on *sighting*, sighting needs vision, a Builder sees
r^2 20, and Builders block movement. So an idle body posted between the two
Cores buys the guard warning *and* plugs a tile. `_picket_post` picks the
enemy-facing, narrowest known tile 4-7 from our own Core, walks there once and
stands still.

    shipped                     270/336  0.804   110/160  0.688
    picket, 4-7 out             264/336  0.786   112/160  0.700
    picket, 6-10 out              --             112/160  0.700

It is the only one of the five idle behaviours that is **positive on unknown
maps**, and on bridge it is transformative: 9,480 titanium collected against 70
and the round-1000 tiebreak won, where the shipped build loses that map and
"go home" managed 7,240. It still costs six games on the pool.

"Stand *beside* the lane, not *in* it" was the obvious refinement -- our own
attacker and our own belt have to use the chokepoint, and a body in it blocks
them exactly as well as it blocks theirs. Three ways of asking, on the four
pool opponents (shipped 131/168) and the 40 generated maps (shipped 110/160):

    picket, narrowest tile           125/168   112/160
    prefer open tiles (tie-break)    125/168     --
    same, distance bucketed          126/168   112/160
    exclude our own _bfs_path,
      require adjacency to it        126/168   112/160

The first two tie-breaks never fired: the rank's leading term is the distance
to the enemy Core, which is unique per tile, and bucketing it does not help
because in open ground every candidate has four openings. Only the last one
actually moves the chosen tile, and it is worth **+1 game in 168**. The
hypothesis is right in direction and far too small to matter.

Two things the first pass did *not* test, and should have. The post was aimed
at the **inferred enemy Core** -- a symmetry guess -- not at where enemies were
actually seen, and it was **static**, not a patrol.

`_remember_threats` records every enemy unit seen within 12 of our own Core and
`_threat_bearing` aims the post along the mean *direction* of those sightings.
The direction, not the centroid: sightings are recorded near our Core by
construction, so their mean sits almost on top of it and the first version of
this collapsed to standing at home (bridge against vigil: 7,240 titanium
collected, exactly the "go home" number). Projecting the bearing back out past
the picket band fixes it (9,480, level with the shipped build's 9,490). `_picket_route` then spreads three posts >= 4 apart across
that sector and walks them in a cycle.

    shipped (paces)                     131/168  0.780   110/160  0.688
    picket at the inferred Core         125/168  0.744   112/160  0.700
    picket at the observed bearing      126/168  0.750   111/160  0.694
    patrol of three posts, observed     128/168  0.762   111/160  0.694

Aiming at evidence rather than at the symmetry guess is worth **+1 game in
168**. Patrolling rather than standing is worth **+2**. Both point the right
way; neither is close to the 6 games the whole family gives up on the pool, and
on generated maps all four sit inside one game of each other.

So the answer is not about how the post is chosen or whether the body moves.
The picket family costs about six games on the pool and gains about two on
generated maps, and every refinement of it lands inside noise.

**Five livelock and idle-behaviour fixes across two different Builders, and
only the picket is positive anywhere.** Take that
as the finding rather than as four failures: a Builder pacing is a Builder that
has run out of things worth doing, and giving it a tidier way to do nothing is
still nothing. The place to look for wins is what puts it in that state -- a
saturated economy with no reachable ore, or an enemy Core with no legal seat --
not the pacing itself.

**Neither is worth shipping.** Which is the finding: a Builder that has no ore
left to claim and no ground left to see has nothing valuable to do either way,
so the wasted rounds are a symptom rather than a cost. Pacing near the middle
of the map at least keeps vision there; walking home gives that up, which is
probably why it is the worst of the three.

The exception is real and worth remembering: on bridge alone, latching turns a
1000-round titanium *loss* into a win on round 400, and going home turns it
into 7,240 titanium collected against 70. Whatever the aggregate says, a
saturated economy on a corridor map is a case where those rounds do matter.

Revisit with the cluster's 4,000-game samples, where six games is not noise.
The detector is committed either way -- it is cheap, it found both of this
session's livelocks, and a healthy Builder sits at 0-2%.

### The ferry was throwing the wrong Builders, and never gave up

Five of the eighteen losses to `warden_walk` show **zero titanium collected**:
sweden in both seats, vase, sprint, and (against valkyrie) bridge. Not a small
economy -- none at all. Traced on sweden, and it is two separate defects in the
Launcher relay.

**The miner asks to be thrown.** `_move_cardinal_adjacent` calls `_step` with
`allow_launcher` defaulting on, so *any* Builder that fails to path once will
buy or request a throw. On sweden the economy Builder asked to be thrown **two
tiles** -- (2, 2) to (4, 2), (2, 1) to (3, 0) -- and the throws landed it off
the conveyor run it was laying, so it re-planned, walked back, and asked again.
It finished with fifteen conveyors, **zero Harvesters** and zero titanium, on a
map where the same chassis with an atlas has two Harvesters by round 19. Gating
the relay on `p.is_attacker` -- the ferry exists to carry one Builder across
the map, everyone else works on ground it can walk -- takes sweden seat a from
0 to 4,820 titanium and flips seat b and vase seat b from losses to wins.

**Nobody gives up on an impossible throw.** A Launcher can only throw to a
bot-passable tile within r^2 26 in the requested direction. Where that
direction is wall -- sweden's band -- there is no legal landing, the request is
silently ignored, and `_opening_ferry` re-armed its four-round timer on *every*
round, so it never expired. The attacker stood beside its own Launcher asking
to be thrown on every round from 30 to 999 and never attacked at all: 969
requests in one game. Counting consecutive unserviced rounds and walking after
four takes that to 19.

    shipped                        270/336  0.804   110/160  0.688
    + ferry for the attacker only  272/336  0.810   110/160  0.688
    + give up on a dead request    271/336  0.807   110/160  0.688

Both shipped. The score moves by one or two games -- these are 42-game cells --
but a Builder that lays fifteen conveyors and no Harvester, and an attacker
frozen for 970 rounds, are defects whether or not this panel can see them.
`warden_walk`, the worst matchup, goes 24/42 to 26/42.

**Still open: vase seat a.** With both fixes it still collects zero, and there
the belt *looks* right -- Harvester on (1, 7) at round 14, conveyors (1, 2)
through (1, 6), and the mirror-image opponent delivers 2,450 from the identical
shape. Something about that line does not carry. Next session starts there.

### vase seat a: a third zero-economy bug, diagnosed and NOT fixed

With both ferry fixes in, vase seat a still collects **zero** titanium over
1000 rounds against warden_walk's 2,450. Two distinct faults, both confirmed
from the replay and both resistant to the obvious repair:

**The belt loses its last tile and never gets it back.** The conveyor at
(1, 2) -- the one feeding the Core -- dies on round 7. The rest of the line
(1, 3)-(1, 6) and the Harvester on (1, 7) survive all 1000 rounds, so the ore
is mined into a dead end. warden_walk loses (9, 5) twice on the same map and
rebuilds it both times. Ours does not, because `_broken_network_tiles` skips
any tile not currently `is_in_vision`, a Builder sees r^2 20, and the miner
never goes back within sight of the Core.

**The miner is trapped in a pocket.** From round 20 it sits at (0, 8) --
row 8 is `.#.......#.`, a one-wide dead end -- and never moves again. `_explore`
picks a stride point it cannot reach, `_step` fails through to
`_move_while_stuck`, which chooses the neighbour nearest the target; that
choice reverses the moment it steps, so it oscillates. Worse, it calls
`_mark_progress("moved while blocked")` every round, so `p.last_progress_round`
is always fresh, `_report_stall` never fires and `_write_off` never retires it.

Three attempted fixes, all measured on vase both seats and all failing:

    walk the belt when idle              still 0 -- the miner is never idle,
                                         it explores forever
    walk the belt every 50 rounds        still 0 -- `_explore` is reached but
                                         the miner is stuck before it matters
    explore only reachable stride points still 0 in seat a, and seat b went
                                         from a win to a loss

**Solved, and it needed four links, not one.** The root cause is not the miner
at all: an enemy Gunner shoots the tile feeding our Core on round 7, and
`p.network_plan` -- the only record that a conveyor belonged there -- is
*per-Builder*. The miner that laid it has walked away and cannot see the hole;
every other Builder, including every replacement the Core spawns, has no record
of it. The line can never be mended by anyone.

What works is a chain, and each link alone does nothing:

1. **See the hole without remembering it.** A Conveyor delivers to the tile it
   faces; if that tile is empty the line ends in mid-air. That is inferable
   from vision by any Builder standing near it, no shared memory needed.
2. **Notice the economy is dead at all.** The Core cannot see the belt but it
   can see that titanium has stopped arriving -- sum the positive round-to-round
   changes in the team balance over 60 rounds and compare against the passive
   rate of 2.5/round. `income_dead` fires correctly on vase at round 120.
   Published as bit 2 of `SLOT_CORE_DAMAGED`; there was no free slot left.
3. **Replace the body**, but *only* when income is dead and we are under the
   opening headcount. Unconditional refilling measured -30pp; this fires
   almost never.
4. **Make the replacement a miner.** Roles are derived from spawn order, so
   everything past the opening is an attacker -- the Builder spawned to restart
   a dead economy walked off to fight and the economy stayed dead. This was the
   link that made the other three pay.

vase seat a goes from **0 to 2,230** titanium collected. Cost: exactly nothing
on the pool (154/210, identical per-opponent to the build without it) and one
game in 160 on generated maps. Shipped on that basis -- a game with no economy
at all is an automatic loss whenever it happens, and the panel simply does not
contain many of them.

Credit where due: the income watchdog was Lucas's suggestion, and it is the
right instrument precisely because it does not depend on any Builder's vision.

### The atlas was never the problem, and our own ferry was

I spent several rounds asserting that the four sub-80% matchups were hard
because those bots carry the atlas on the maps it covers. **That is wrong**, and
one control settles it. `ragnarok_fair` is `ragnarok` with the atlas removed:

    heimdall vs ragnarok       (atlas)     30/42  0.714
    heimdall vs ragnarok_fair  (no atlas)  28/42  0.667

The atlas-free twin is *harder*. Which this file already knew -- the 2026-08-03
entry records `ragnarok_fair` beating `valkyrie` where `ragnarok` only draws,
because the atlas gates `_opening_ferry`, so the fair twin **cannot ferry and is
forced to walk**, and the walking bot ends with more Gunners and Harvesters
where the chaining one ends with more Launchers.

heimdall ferried. Turning `FERRY_ON_INFERENCE` off:

                     8-bot pool        40 generated maps
      ferry on      271/336  0.807     109/160  0.681
      ferry off     282/336  0.839     115/160  0.719

    warden_walk  26/42 -> 32/42      warden    32/42 -> 34/42
    ragnarok     30/42 -> 33/42      valkyrie  32/42 -> 33/42

The gain lands exactly on the matchups that were weakest. Every opponent on the
panel is now at 0.76 or better, against 0.62 at the bottom before.

**The lesson is one this file states elsewhere and I did not apply to myself.**
`FERRY_ON_INFERENCE` has now been measured three times on three chassis and the
answer changed twice:

    atlas-carrying ancestors        17/42 on vs 21/42 off    -> OFF
    this bot, before the guard     128/168 on vs 119/168 off -> ON
    this bot, as it now stands     282/336 off vs 271/336 on -> OFF

I turned it on early, then changed the bot underneath it five times -- guard,
escalating allowance, sticky guess, attacker-only ferry, give-up -- and never
re-measured it. **Re-test the flags you flipped after any change that alters
what the bot spends on.**

### The local gate is deterministic -- there is no measurement noise

A variant was built whose edit silently failed to apply, so it was a byte-copy
of the shipped bot. It scored **exactly** 98/126 with identical per-opponent
splits. The engine is deterministic given (bot, opponent, map, seat, seed), and
`benchmarks/run_one` fixes the seed, so a 42-game cell has *zero* variance from
the harness.

That changes how to read every table in this file. A one- or two-game
difference is **not sampling noise** -- it is a real behavioural difference on
specific maps. What it is not is evidence of *generalisation*: 42 games is 21
maps in two seats, so a two-game edge can be one map behaving differently, and
that will not necessarily transfer to the cluster's field or to the final.

So "inside noise" was the wrong phrase throughout the earlier entries. The
right one is "too few maps to say whether it generalises". The remedy is the
same -- more maps, ideally the cluster -- but the reasoning is different, and a
consistent +2 across several independent map sets is worth more than the phrase
"noise" suggested.

### Every constant that was tuned before the ferry came off had flipped

Once `FERRY_ON_INFERENCE` went off, four more constants -- every one of them
set on an earlier version of this same bot -- turned out to have the wrong
value. Full 8-bot pool, 336 games, and 40 generated maps:

    ferry on, r^2 36, chase 4, cap 2, relay 1   271/336  0.807   109/160
    + ferry off                                 282/336  0.839   115/160
    + guard radius 36 -> 64                     288/336  0.857   117/160
    + guard chase 4 -> 6                        294/336  0.875   121/160
    + guard cap 2 -> 4                          290/336  0.863   120/160
    + relay cap 1 -> 2                          295/336  0.878   122/160

The reasons are all the same reason: with no ferry both sides *walk*, so
enemy attackers are in sight for longer before they emplace (wider radius,
longer chase pay), and the relay now only fires once a Core has actually been
seen, which is late and close, where a second hop is worth more than the walk
it replaces.

Guard cap 4 is the one that costs total: cap 2 is 294/336 against cap 4's 290,
but leaves `warden_walk` at 0.76 where cap 4 puts it at 0.83. It is in because
the goal is the worst matchup, not the mean. If that ever changes, change this
back first.

**Final: 295/336 = 0.878, every opponent at 0.81 or better** -- casemate 1.00,
vanguard 0.93, valkyrie 0.88, vigil/ragnarok/gobbleglitch 0.86, warden_walk
0.83, warden 0.81. On generated maps 122/160 = 0.762.

Two traps worth naming, both of which caught me:

- **Tuning against the weak matchup overfits it.** `MAX_GUARD_GUNNERS = 4`
  looked like +2 measured against warden_walk and gobbleglitch alone; on the
  full panel that build was 283/336 against 288. Only the eight-opponent check
  distinguished the version that generalised from the one that did not.
- **A flag is measured for the bot it was measured on.** This file said that
  about the atlas and I did not apply it to myself for most of a session.

### Three washes, and the point at which to stop

Traced a `heimdall` loss on a generated map (`random3/r10`, 30x10, RUSH): vigil
put three turrets on our Core on rounds 12, 14 and 15, and our first guard
Gunner went up on round 22. Ten rounds late. The obvious culprit is price --
`_keep_ammunition` converts the bank down to `EMERGENCY_RESERVE` (10 Ti) every
round the ammunition floor is unmet, and a scaled Gunner is ~20, so the guard
can be priced out of the turret that ammunition exists to feed.

Never converting below one Gunner's price:

    40 generated maps   99/160 -> 102/160   +3
    21 official maps   134/168 -> 131/168   -3

Net zero. So the price is not what made the guard late in that game, and the
fix does not ship despite being the tidier code. Same shape for turning
`FERRY_ON_INFERENCE` off on generated maps (+3 there, -9 on the pool) and for
the guard leash (+1, +2).

Three independent ideas all landing at plus-or-minus three games in 160 is the
signal that this chassis is out of reach of a 168-game gate. The next real step
needs either the cluster's 4,000-game samples or a different mechanism, not
another knob.

### Two latent bugs worth knowing about

- `warden_walk` (and everything built from it) calls
  `_keeps_route_open(p, choice[1], ...)` in `_build_basic_gunner`. `choice[1]`
  stopped being the spot when the `AVOID_ENEMY_RAYS` key was prepended to the
  tuple, so it has been passing an int; `spot not in baseline` is then always
  true and the self-blocking guard has been dead. Restoring it is worth 0
  games (117/168 against 118), so it is a correctness fix, not a lever.
- `_build_siege_sentinel` picks a seat without checking it can pay for the
  turret. On aurora the attacker walked fifteen rounds to a Sentinel seat with
  30 Ti against a 76 Ti scaled cost and then stood on it for the rest of the
  game. Adding the affordability check is also ~0 games (145/168 against 145).

### Where the map-adaptive hypothesis actually lands

Honest answer: **the geometry does not predict the levers, and only one map in
the pool has terrain worth adapting to.** Manhattan detour ratio (true walking
distance from Core ring to Core ring, over |dx|+|dy|) across the 21 maps:

    sweden 3.08 | runestone 1.17 | pinch 1.08 | bridge 1.05 | everything else <= 1.0

So the Launcher relay is not buying a way *around* walls — there are almost no
walls to go around. It buys raw tiles on open ground, which is a tempo/scale
trade, not a map question. Per-map win rates for relay 0/1/2 and ring 0/1/2/3
were also read off the cluster's 194-game-per-map cells: no ordering with walk
distance, area, corner-ness or detour survives.

Two things *are* map effects and both are worth the next session:

1. The farthest-symmetry guess for the enemy Core is **wrong on exactly the two
   maps where the Cores share an edge** — sweden (guess cheb 23, truth 13) and
   vase (14 vs 9) — and sweden is warden's worst map in the whole pool at
   0.737. Ranking surviving candidates by travel distance instead of Chebyshev
   does not fix it at round 0 (both candidates are far when the map is unknown)
   but should fix it a few rounds in. Untested.
2. The guard makes games *long* (median 47 → 57 turns) and pushes the remaining
   losses into round-1000 titanium tiebreaks, which cluster on closed maps —
   4 of our 12 losses to vigil are 1000-turn economy decisions on bridge,
   skerry and sweden. That is the map effect that is left: on a map where
   neither Core can be reached, the game is an economy game. The FORTIFY role
   split was measured at 2-12 *before* a working defence existed and deserves
   re-testing now.

### Why the generated maps are harder than the pool, in exactly one respect

The farthest-symmetry guess is right **28/42 (0.67)** on the official pool and
**60/184 (0.33)** on the generated maps. That is not the bot behaving worse; it
is one number showing up twice. Of the three candidates, the farthest is always
the 180-degree rotation wherever they differ, so "farthest-first accuracy" *is*
"the share of maps built by rotation":

    official pool     rotation 14, x-mirror 3, y-mirror 4     -> 0.67
    generated (94)    rotation 32, x-mirror 31, y-mirror 31   -> 0.33

The pool's designers prefer rotation two to one. `generate_maps.py` draws the
three symmetries uniformly on purpose, so it is a faithful test of everything
except this convention, where it is deliberately pessimistic. The final is
presumably drawn by the same people as the pool, so the convention probably
holds there and the generated-map scores understate the bot by whatever the
guess is worth.

Which is: on the pool, ferrying at the guess is +9 games in 168. On 40
generated maps it is **-3 in 160** — ferry-off scores 102/160 against
ferry-on's 99/160. Both are inside noise on their own, but they point opposite
ways and the mechanism explains why. `FERRY_ON_INFERENCE` stays **on**, betting
on the convention; if that bet looks wrong later, turning it off costs 9 games
on the pool and buys 3 on uniform terrain.

A margin rule was tried and is impossible: for a Core at (cx, cy) the rotation
candidate's Chebyshev distance always ties the larger of the two reflections,
so the margin is 0 on 184 of 188 map-sides and carries no signal.

What does *not* depend on the guess is the outcome. Splitting all 376 generated
games by whether the guess was right: 0.664 when right, 0.617 when wrong. The
symmetry test strikes a wrong candidate quickly enough that the bot recovers.

### `tools/generate_maps.py`

Draws random symmetric maps to `maps/random/` from the rules the pool obeys
(8×8–30×30, two Cores, connected), in equal parts 180° rotation, x-mirror and
y-mirror. Round-trips `aurora` byte-identically, so the encoder is right. Use
it for anything that claims to be about unknown terrain — a test set of only
rotations would score a bot that always guesses rotation as though it were
correct.

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

**Both rows above were later overturned on heimdall** (see "The Launcher knobs
are finished", struck through further up). On the current chassis and the full
eight-bot panel the optima are the other way round: relay **2**, ring **1**,
worth +14 games on the pool and +12 on unknown maps. The reasoning in this
section is still right -- Launchers are a scale bill and the bill lands on
Gunners and Harvesters -- but *which* Launcher to cut moved when the guard
shipped, because the ring Builder is now also the guard and every round it
spends walking the ring is a round it is not defending the Core. Keep the
principle; re-measure the numbers.

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

### The goal is both mElo and *sole* Nash support, and they pull apart

Specialising is easy; dominating is not. warden_walk earned Nash support at 0.5
by capping Launchers, and paid for it with the lowest mElo of the top seven.
Broken down per opponent the blanket cap is two effects added:

    gains                    losses
    ragnarok_fair  +14pp     vigil@60d5afa      -24pp
    valkyrie       +12pp     vanguard_oracle    -19pp
    ragnarok       +10pp     casemate_oracle    -12pp

It beats Launcher-heavy bots, which overspend on scale once we stop, and loses
to bots that wall us out, where the chain is the only way through. It sells
40/42 matchups to buy 21/42 ones -- exactly the trade that earns Nash support
and costs mElo.

**The trade is a frontier, and the "am I stuck" signal does not break it.**
aegis caps only the routine ferry and leaves the stuck-recovery Launcher
uncapped, on the theory that being walled out is distinguishable from routine
chaining. Measured, it just slides along the same line:

    build                       vs prospect   vs ragnarok_fair   total
    warden                         30              18             48
    aegis (conditional cap)        27              20             47
    aegis, stuck threshold 5       26              23             49
    warden_walk (blanket cap)      26              24             50
    steward (replace losses)       31              21             52

### What is off the frontier: unspent titanium

steward is the first change that improves both columns instead of trading them,
and it is not a strategy change at all. `core.py` gates respawning on
`has_live_builder`, and that heartbeat proves only that *one* Builder is alive,
so a team that loses two of three never replaces them:

    T15  Ti=154  builders=3
    T45  Ti=139  builders=1
    T90  Ti=298  builders=1     dies T103 holding 358 titanium

Beaten, on sweden, by an opponent that mined nothing at all. The bank is the
trigger, because a live headcount is not available -- comms writes are
invisible to other units until the next round, so a bitmask never accumulates,
while a working team spends income as it arrives and therefore never banks
much. After the fix the same game runs to 138 and mines 360 against 150.

That failure mode is now closed: across 38 gate losses, **zero** end holding
100 titanium or more. The remaining losses are genuine.

The lesson to carry: look for resources the bot fails to convert before looking
for tactics it fails to execute. Trades between matchups are usually a
frontier; waste is usually free.

### The Launcher caps made a new Nash pillar, not a better bot

Full ledger, auto-f11bf027e3d4: 98 bots, 285,183 matches.

    rank  bot                    melo    win rate   nash prob
    1     vigil@18b749d          457.0   0.8731     0
    2     vigil@e22eda8          456.0   0.8832     0.500001
    3     vigil@e267eeb          452.0   0.8824     0
    4     warden@3318ffd         451.5   0.8851     0
    5     ragnarok@79582fc       451.1   0.8839     0
    6     valkyrie@d181312       450.0   0.8834     0
    7     warden_walk@3318ffd    435.1   0.8698     0.499999   (rank_delta +6)
    13    ragnarok_fair@79582fc  347.0   0.7899     0          (rank_delta -5)

**The Nash support is now {vigil@e22eda8, warden_walk} at 50/50.** The capped
build displaced ragnarok *and* ragnarok_fair from the core outright.

Read that carefully, because it is not the win it first looks like.
warden_walk has the *lowest* mElo and the *lowest* win rate of the six bots
above it. It is not a better bot on average; it is a strategically distinct one
-- it beats things the others cannot, which is exactly what earns Nash support
and exactly what mElo discounts. Capping Launchers did not collapse the cycle,
it added a pillar to it.

For "beat everything on 70% of maps" the bot to build on is **warden**, which
carries the highest raw win rate in the entire field (0.8851) at rank 4 --
though warden, ragnarok and valkyrie sit within 0.2 points of each other over
4,074 games apiece, which is inside the noise. The honest summary is that the
ragnarok line has four bots statistically tied at the top and one specialist
that is half of the equilibrium.

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

### Measuring CPU without a timeout flag

The engine never reports a timeout. `fcode run --tle N` silently *drops* an
over-budget turn, so a bot that is too slow plays worse rather than erroring —
which is exactly the failure mode that would be invisible in a score table.
`benchmarks/tle.py` probes it by tightening `--tle` until outcomes move.

Two things to know when reading it. `--tle` binds both bots, so a divergence
does not say whose turn was slow; run `--attribute`, which uses mirror matches,
to pin it on one bot. And heimdall is identical to unlimited play down to 4 ms,
while the cross-panel diverges at 6 ms — that 6 ms is an *opponent's* turn, and
the `vigil` lineage's known overrun (below) is the likely source.

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
