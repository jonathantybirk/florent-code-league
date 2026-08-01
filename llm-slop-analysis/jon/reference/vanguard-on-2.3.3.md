# Converting Vanguard to engine 2.3.3

Everything below was measured on the current engine against the 21-map pool,
both sides of every map (42 games per pairing). Nothing is carried over from the
2.2.0 notes, which are quarantined in `../legacy/` for exactly that reason.

`common/starter` calls `random`, so its results swing by several games; the
panel used for decisions is the deterministic one.

## The baseline: a straight adaptation

`probes/v233_a` is Vanguard with one change -- the Core converts titanium into
ammunition. That alone, because nothing else on the branch does it:

| | before | after |
|---|---|---|
| vs `common/starter` | 17-25 | 28-14 |

Every later build is measured against `v233_a` to keep "how much did adaptation
actually buy us" honest.

## Minor improvements

| change | effect |
|---|---|
| Core converts titanium to ammunition | 17-25 to 28-14 vs starter |
| Gunners placed by **firing line**, not by adjacency to a producer | strat1 36-6 to 39-3 |
| Builder attack and heal moved to orthogonal adjacency | undertow 31-11 to 37-5 |
| `_scorch` deleted | see below |
| forward-Harvester / conveyor-creep / parasitism apparatus deleted | undertow 35-7 to 37-5 |
| `AMMO_TARGET` 120 to 40 | neutral in 40-160, catastrophic above |

**Placement by firing line.** Under 2.2.0 a Gunner had to sit beside a producer,
because ammunition was a physical stack somebody had to hand it. That constraint
is now meaningless, and dropping it is a straight win.

**`_scorch` had inverted.** It destroyed our own Harvester whenever an enemy
Gunner stood beside it, because a Harvester used to feed any adjacent building
regardless of owner. With a global pool it feeds nobody, so the rule was
demolishing our own economy for no benefit at all.

**A correction worth recording.** The first attempt at deleting the siege
apparatus silently did nothing -- a `str.replace` that no-matched -- and the
21-21 it scored against the pre-strip build was reported as "neutral" when it
actually meant *two identical bots*. An A/B that lands exactly level deserves a
check that the two binaries really differ. Applied properly it is a small win,
not a neutral one.

**Ammunition has a real opportunity cost.** Converting is 1:1 and looks free,
but converted titanium leaves the treasury and cannot buy buildings. Anything in
40-160 measured the same; 400 scored 9-33 and 1200 scored 1-41 against a frozen
build. Convert enough to shoot, not enough to starve.

## The major improvement: Builders were stranding themselves

Tracing a match rather than sweeping constants found an economy Builder sitting
in phase `line` from round 50 to round 150 without ever finishing its belt.

`_lay_line` stepped **onto** the tile it wanted to build on. In 2.2.0 that was
legal -- a Builder could stand on a walkable building and lay it under its own
feet. 2.3.3 requires an orthogonally adjacent target, so a Builder that walks on
is stranded there permanently. One of three economy Builders, for whole matches.

The same stale assumption appeared twice more, in the raid and tile-clearing
paths, which walk onto a belt to attack it -- and 2.3.3 attacks an *adjacent*
tile, never one's own.

| | v233_a (straight adaptation) | after the fix |
|---|---|---|
| lucas/strat1 | 36-6 | **40-2** |
| claude_challenger_1 | 37-5 | **40-2** |
| jonbot | 39-3 | **39-3** |
| undertow | 30-12 | **35-7** |
| v233_a itself | — | **40-2** |
| common/starter | 28-14 | **40-2** |

Panel total across the five deterministic opponents: **194-16 (92.4%)**, from
174-36 (82.9%).

## Two changes rejected, and why the reason matters

- **A four-connected distance field.** Movement is cardinal-only now, so the
  eight-connected field is formally wrong -- and it measured *better*, 28-14
  against 24-18. The move loop only ever emits legal cardinal moves either way;
  the optimistic field seems to give a smoother gradient. Kept the "wrong" one.
- **Freeing home-Gunner placement** from Harvester adjacency -- the exact change
  that worked for offence. It won the head-to-head against our own previous
  build 24-18 and still lost the panel, 165-45 against 174-36.

Both are instances of the same discipline: **the head-to-head against your own
last build is not sufficient evidence, and neither is a correct-sounding
argument.** Only the panel decides.

## A second structural improvement: income before fortification

`_economy` ran `_home_gunner` and `_fortify` *before* `_pick_job`, so once the
first Harvester was down every idle Builder went to lay the Barrier ring rather
than expand. That ordering was correct under 2.2.0, where the ring was the whole
defence and ammunition came from a belt. Under 2.3.3 titanium **is** ammunition
**is** damage, so a deposit outranks a Barrier.

A trace found the bot broke at round 75 -- 63 titanium in hand at 265% cost
scale -- while the strongest opponent out-mined it five Harvesters to two.
Gating defence on three completed income lines:

| | before | after |
|---|---|---|
| Harvesters built | 1.1 | **3.6** |
| Conveyors | 5.5 | **17.5** |
| Gunners | 1.5 | **6.2** |

Swept: 1 and 3 both score 63/84 on the discriminating pair, 2 and 4 score 60,
6 scores 57. Three wins on the sensitive opponent, so three it is.

## Beating Undertow: it was a tempo race, not an economy race

Undertow led 27-15. The diagnostics said the opposite of what that suggests --
Vanguard built **more of everything**: 8.6 Builders to 6.8, 3.6 Harvesters to
3.0, 4.6 Gunners to 2.3. Losing while out-building the opponent means the
deficit is not resources.

The replay showed it plainly. On atoll, dead on round 47: four of their Gunners
were firing on our Core from round 21, from the tiles right beside it, while our
attacker was still walking and reached their base around round 25.

Six constants were swept with **no movement at all** -- `ECON_BEFORE_DEFENCE`,
`HOME_ALARM_PERCENT`, `LAUNCH_HOPS`, `AMMO_TARGET`, `HOME_GUNNERS`, and a
combined early-heavy-defence setting. Five configurations scoring *identically*
is the same tell as before, so the harness itself was sanity-checked by
crippling ammunition to zero: that moved the score to 1-7, proving edits do
take effect and those levers genuinely do not matter here.

The answer was `LAUNCH_MIN_GAP`. The ferry stopped **eight tiles short** of the
enemy Core and the attacker walked the rest, losing the arrival race outright:

| `LAUNCH_MIN_GAP` | vs Undertow |
|---|---|
| 8 (old) | 15-27 |
| 5 | 21-21 |
| 3 | **22-20** |
| 1 | 16-26 |

`LAUNCH_HOPS` had been a measured no-op *because* of this -- with the ferry
stopping early, extra hops had nothing to do. Once it ferried the whole way,
raising hops from 2 to 5 was worth another two games: **23-19**.

A dead-looking parameter can be dead only because a *different* parameter is
gating it. Re-sweep the ones you dismissed after you change something upstream.

## Measuring against a moving target

`undertow` and `jonbot` belong to another agent who edits them live. A run
against `undertow` was fingerprinted before and after and **the hash changed
mid-run**, which explains a 39-3 and a 15-27 recorded for the same setting
minutes apart. `scratch/arena.py` now hashes both bots' sources at the start
and end of every run and prints `!! CONTAMINATED` when either moved, and
`scratch/panel.sh` decides changes using only opponents nobody else edits.

The cost of not having done this earlier: several numbers reported during the
conversion were measured against a target that was being rewritten underneath.

## Where the headroom is not

Swept and found flat: `MAX_BUILDERS` (4/6/8), `HOME_LINE_MAX` (7/14/24, literally
identical results), `FORTIFY_ROUND` (5/60/200), `RICH_BUILDERS` (4/6/8),
`HOME_GUNNERS` (0/2/4, all 62/62/61 on the discriminating pair). Capping the
number of attackers scored *exactly* level at 2 and at 4, because the bank is
rarely deep enough to spawn a fifth Builder at all -- equal result plus extra
code, so it was reverted.

**Sentinels, retested on 2.3.3 and rejected again: 9-33.** The global pool
removes their logistics penalty entirely, which was the obvious reason to
revisit them, and they still lose badly -- 1.8 damage per titanium against a
Gunner's 5 decides it whatever the supply rules are. `ECONOMY_BUILDERS` is the one
that matters and 3 is right -- **more attackers is worse**. Under a global pool
titanium is ammunition is damage, so economy is more central than it was, not
less.

## Other bots

`undertow` and `jonbot` were given the same API adaptation (ammunition,
cardinal search, attack adjacency) without any strategic change, so they remain
independent opposition. Jonbot was **completely paralysed** on 2.3.3 before
this: its BFS proposed diagonal steps and its move loop only moved when the
proposed direction was legal, so it stood still whenever a path wanted a
diagonal. It lost to `donothingbot`. It now functions, but is still weak.
