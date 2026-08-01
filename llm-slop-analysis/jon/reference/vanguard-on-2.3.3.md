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

## Where the headroom is not

Swept and found flat: `MAX_BUILDERS` (4/6/8), `HOME_LINE_MAX` (7/14/24, literally
identical results), `FORTIFY_ROUND` (5/60/200). `ECONOMY_BUILDERS` is the one
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
