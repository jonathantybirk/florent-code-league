# The Vanguard oracle: what map knowledge is actually worth

`bots/jon/unfair/vanguard_oracle` is `bots/jon/fair/vanguard` plus an atlas.
The fair bot stays fair -- it has no reference to bundled terrain at all, and
that is deliberate, not an oversight.

The atlas identifies the map from `(width, height, own core anchor)`, verifies
every currently visible tile against the bundled terrain before trusting it,
and then hands over full terrain plus the enemy Core position on round 0.

## Measure the oracle against a field, never against its own twin

The first read was that map knowledge made the bot **worse**: the oracle lost
to fair Vanguard 18-24. That was wrong, and the reason matters. The two bots
are byte-identical apart from the atlas, so that match is a near-mirror and is
decided by map and side asymmetries rather than by strength. On the pooled
regression panel over the same period:

| bot | panel (of 378) |
|---|---|
| fair Vanguard | 332 |
| oracle, as inherited | 352 |
| oracle, after this work | **369** |

The head-to-head moved 18-24 -> 25-17 over the same changes, but the panel is
what the decisions were made on.

## What the atlas is worth, and what it is not

**A map-aware opening (+4).** The oracle BFSes the true cardinal walking
distance between the two Cores on round 0 and rushes when they are close
(`RUSH_ECONOMY_BUILDERS = 1` under `RUSH_DISTANCE = 18` steps), develops when
they are far. The fair bot cannot do this -- it has to commit to one opening
for all 21 maps before it has seen anything. Thresholds 0/16/20/26 scored
103/107/107/101 over 126 games; `RUSH_ECONOMY_BUILDERS` 0/1/2 scored
101/107/103.

**Nearest-seat preference (+5).** Knowing the whole map also reveals the
pristine firing seat on the *far* side of their Core, and `obstacles` outranks
`reach` in the seat sort, so the oracle would walk around the base for a
cleaner line. Since the siege is bottlenecked on walking, seats much further
off than the nearest usable one are now discarded: `SEAT_REACH_SLACK` 0/999
scored 103/98.

**Per-map ferry length (+8 out-of-sample).** `LAUNCH_HOPS` is one number for 21
maps and the per-map spread is huge. Uniform 1/2/4 scores 114/130/113 over 168
games; per-map argmax would score 144. Most of that gap is argmax noise on
8-game cells, so only the lopsided maps are overridden in `MAP_HOPS`.

## Overfitting works, but only where the per-map effect is large

Both per-map tables were tuned on four frozen probes and then validated against
five strong opponents that were **not** used for tuning:

- `MAP_HOPS` (ferry): 114 vs 106 over 210 games. Kept.
- `MAP_LINE` (supply trunk): 90 vs 91 over 168 games. **Dropped.** In-sample it
  looked worth +5 on `hive` and `sweden`, and none of it survived.

The difference is margin size. The ferry cells differ by 0/8 vs 5/8 on the same
map; the trunk cells differ by 5/8 vs 7/8. Per-map argmax on 8 games is a noise
generator, and the only defence is to validate on opponents the table has never
seen. Do not add a per-map override without that check.

## Maps that stay weak whatever is tuned

`showdown` (4-5/8), `jackpot` (4-5/8) and `bridge` (3-5/8) resist every
parameter tried. `jackpot` is a dense maze and `bridge` is a set of narrow
corridors -- both are maps where walking dominates and firing seats are
screened, which is the same bottleneck the fair bot has: instrumenting `_siege`
shows attacker rounds going 8/34/65 to walking against 1/7/11 to building.
Precomputing and pre-assigning seats from the atlas on round 0 is the obvious
oracle-only answer and is not implemented yet.

## CPU

The added round-0 BFS is inside budget: 0 divergences under `--tle 10` across
the maps checked, including the largest.
