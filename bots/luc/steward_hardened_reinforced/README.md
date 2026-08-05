# Steward, hardened

`steward_reinforced` as it stood at `a8dc58a3f`, with the defensive half of the
2.3.4 balance patch applied to it. Measured on fcode 2.3.6 against five
opponents over the 21 official maps in both seats — 42 games a cell, 210 a row.

|                              | vidar | vigil | tyr   | mjolnir | prospect | **mean** | **worst** |
|------------------------------|-------|-------|-------|---------|----------|----------|-----------|
| steward_reinforced (as taken)| 0.310 | 0.476 | 0.548 | 0.548   | 0.476    | 0.471    | 0.310     |
| **this bot**                 | 0.476 | 0.595 | 0.714 | 0.690   | 0.571    | **0.610**| **0.476** |

**+13.9pp of mean and +16.6pp of the worst matchup**, and every one of the five
improved. The panel is deliberately the hard end of the ladder: `vidar` is rank
1 of 139, and `tyr`/`mjolnir` are its ancestors.

## What the diagnosis was

Not the tiebreak. `steward_reinforced` loses 90% of its games to a **Core kill**,
and when it loses the median game is round 113. It was not being out-mined at
round 1000; it was dying before round 1000 existed. In the twelve losses to
vidar traced at the start, our Core ended on 0 and theirs on 215–500, while we
held four to six Gunners. This bot was never short of turrets.

## The three changes that paid

**The Builder posted at the Core mends it on any damage** (`+8pp`). The gate it
replaces was `alarm >= 2` — the Core below 300 of 500 HP — *and* FORTIFY maps
only. So the one Builder standing on the Core watched it lose two fifths of its
life before acting, and on a RUSH map never acted at all: it walked off to lay
its Launcher ring while the Core died behind it. Healing needs no sight of the
shooter, which is the point — a Builder sees r²=20 and a Sentinel shoots from
r²=32, so the turret killing our Core is routinely invisible to the Builder
standing on it. At 4 HP for a flat 1 Ti, unaffected by cost scale, it is the
most titanium-efficient act in the game.

**Home defence buys Sentinels, not Gunners** (`+5pp`). The Aug 4 patch inverted
the turret table and this lineage never noticed. The load-bearing row is cost
scale: both turrets now levy the same permanent +20% on every later price, and
that tax — not titanium — is what caps how many turrets a game can hold. Once
the count is fixed by the tax, 10 Ti more a seat buys 1.71x the damage, 1.6x the
HP, 2.46x the range and a line terrain cannot block. 2.3.3's +10% Gunner against
a +20% Sentinel is exactly what made Gunner spam correct. Applied to the two
home-guard paths only; field and denial turrets keep the Gunner, where reach
buys nothing and rotation is worth more.

**The turn budget for optional searches, 4000 µs → 2500** (`+2.9pp mean,
+9.5pp worst`). Found while chasing a timing regression, and it is the largest
single gain against `vidar` in the whole session: 0.381 → 0.476. The bot's own
note had it right all along — "an optional search that might not fit is worth
strictly less than the ordinary action it would displace" — the number was just
set too generously to act on it.

## One repair, inherited

`launcher.py` used `LAUNCH_RANGE_SQ` without importing it. `_launch_enemy_away`
is the **first call every Launcher makes every round**, so every Launcher died
to an uncaught `NameError` the first time an enemy came within radius 2 — `run()`
catches `GameError`, and a `NameError` is not one. Present in the snapshot this
bot was taken from; fixed here only, worth +1.4pp, and worth checking against
whatever `steward_reinforced` has become since.

## Measured and rejected

**Late economic expansion: -9pp.** Vidar's largest economic mechanic — spawn
Builders for income after round 200, because the median 2.3.4 game reaches the
round-1000 tiebreak on titanium collected. It does not transfer, for a reason
visible in the diagnosis above: only 33% of this bot's games reach round 200 at
all, and it is losing the ones that do not. Off.

**The attacker's turrets are this chassis's win condition.** Vidar ships a
deliberately *parked* attacker on the finding that a Builder which never builds
never raises the cost scale, worth 9.9pp there. Swept here, `ATTACK_TURRET_CAP`
5 → 2 is a wash (0.590/0.400 against 0.570/0.450) and 5 → **0 collapses the bot
to 0.240**. This is the clearest chassis-dependence result of the session: the
same mechanic is +9.9pp on one bot and -35pp on another. Left at 5.

**A second mender on a critical Core: exactly neutral.** 0.590/0.400 with and
without, on 100 games. The arithmetic is sound — one mender cancels two thirds
of a Gunner, two out-heal it outright — but nothing here can see it. Kept as
`SECOND_MENDER_ON_CRITICAL`, off.

**Sentinels shooting the supply line: neutral.** `get_nearby_entities` returns
units, so conveyors, harvesters and barriers are invisible to it and every
Sentinel in this lineage held its fire with an enemy Harvester on its line. Kept
on anyway, because a turret declining a legal target is a defect whether or not
a 100-game panel can price it — but it is not a gain and should not be cited as
one. Vidar measured the same mechanic at the same nothing (0.676 against 0.679).

## A correction to the record

**Communication-store writes are buffered to the next round.** The engine's own
documentation is explicit — *"Writes are buffered: a `write_store()` call becomes
visible to all units at the start of the next round"* — so a per-round bitmask
**cannot** accumulate: every Builder in a round reads the same snapshot, ORs its
bit onto that same stale value, and only the last writer's word survives.

`steward`'s note is right and `vidar/builder.py:318` is wrong, and it is not a
harmless comment. Vidar's `_publish_heartbeat` builds a headcount that way and
therefore reads **1 live Builder no matter how many are alive**, which means
`ECON_MAX_LIVE_BUILDERS = 7` never binds. Ported here verbatim it spawned up to
**79 Builders in a single game**, each one +20% on every subsequent price. The
expansion is capped on total spawns here instead — and since vidar is rank 1
with that cap broken, the finding is worth taking back to vidar rather than
treating as this bot's problem.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms** across 29,013 Builder
turns, worst 9,771 µs on jackpot. The 2500 µs search budget is what buys that
margin; at 4000 the same build put four turns over the limit. Note this is a
local measurement and the ladder runs on different hardware.

## Where it stands

Beats four of the five, and `vidar` — rank 1 of 139 — is now 0.476 rather than
0.310. The goal it was built for is a win against 80% of the field, and a
five-bot panel cannot certify that; the CI ladder is the only instrument that
can, which is what pushing this triggers.
