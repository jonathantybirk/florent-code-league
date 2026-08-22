# Expected titanium flow

`main.py` answers one question, from the Core's point of view: **how much
titanium should I expect to receive, round by round, over the next few
rounds?**

That's `expected_titanium_schedule(ct, rounds)` — it returns a list, one
estimate per upcoming round. `expected_titanium_flow(ct)` is a convenience
wrapper around it (the old, single-number entry point, kept because
`bots/test/econ_demo` and `bots/test/luc/vidar` both already call it):
just the schedule's first 4 rounds, averaged into one per-round rate.
Everything else in the file exists to support the schedule function. It's a
pure calculation with no side effects — nothing here moves, builds, or
spends anything — so it's meant to be copied or imported into a real bot's
decision logic later, not run as-is (there's no `run()` method).

## The formula

For each round `i` from now (`i = 1, 2, 3, ...`):

```
schedule[i] = (titanium already in the pipeline, weighted, that's exactly i tiles out)
              + (10, if i rounds from now lands on a multiple of PASSIVE_TITANIUM_INTERVAL)
```

- **The pipeline term** is titanium currently sitting on a same-team
  Conveyor or Splitter within the Core's vision, weighted by the
  probability it actually completes its route (see below), and bucketed by
  exactly how many tiles — rounds — it has left to travel. A stack 3 tiles
  out contributes to `schedule[3]`, not to every round up to it.
- **The passive term** is `GameConstants.PASSIVE_TITANIUM_AMOUNT` (10),
  landing on whichever future round is next a multiple of
  `GameConstants.PASSIVE_TITANIUM_INTERVAL` (4) — every team gets this
  automatically, regardless of anything on the map.

`expected_titanium_flow` is just `sum(schedule(ct, 4)) / 4`: the same
information, collapsed from "how much arrives in each of the next 4
rounds" into "what's the average per-round rate over that same window" —
the number a bot actually wants when comparing its economy against a
build cost, if it doesn't need the round-by-round detail.

## Why this needs more than "look at nearby Conveyors"

A plain **Conveyor** is simple: it has one fixed output direction, set when
it's built, and it moves its whole held stack (10 Ti, `GameConstants.
STACK_SIZE`) one tile in that direction every round. So if a Conveyor
holding titanium is `n` tiles upstream along an unbroken Conveyor chain
leading to the Core, that stack is *guaranteed* to land in exactly `n`
rounds.

A **Splitter** breaks that guarantee. It also holds one stack and moves it
one tile per round, but it has up to *three* possible outputs (the direction
it's built facing, plus the two directions next to it) and round-robins
between them — each round it sends its stack to whichever output it used
longest ago. The `Controller` API has no method to ask a Splitter which
output is next, so from the Core's point of view, a stack sitting on a
Splitter has an unknown, un-queryable chance of heading toward the Core next
round instead of one of the others.

The rotation turned out to matter less than it first looked, though: it
doesn't cycle blindly through three fixed geometric slots regardless of
what's built on them. Verified against the real engine (see
[`bots/test/splitter_probe`](../splitter_probe/)) — a Splitter with only one
side actually leading anywhere delivered there **222 times out of 222**
dispatches over an 887-round sample, not the ~74 a blind 3-way rotation
would produce. An output with nothing to receive isn't part of the rotation
at all. So the right model isn't "always 1-in-3" — it's **1 in however many
of its outputs currently lead to a receiver** (a Conveyor, Splitter, or the
Core; see `_is_receiver`), which is usually 1 (most Splitters are built with
only the path they're routing actually connected) but drops to 1/2 or 1/3
once a second or third side is genuinely in use — a very normal thing to
build, see the
[conveyors-logistics tutorial](../../../docs/official/tutorials/conveyors-logistics/04-splitting-the-flow.txt).
That's still an expected value, not a fact about any specific stack — see
[Limitations](#limitations) below.

**Harvesters** don't get even that treatment. `get_stored_resource` — the
only way to check whether a tile is currently holding titanium — explicitly
only works on Conveyors and Splitters. A Harvester's own contents are
invisible to the API, so there's nothing to estimate; any route whose last
un-inspectable step is a Harvester is left out entirely.

## Walking the code

Reading top-down, in the order a call to `expected_titanium_schedule`
actually visits them:

### `_is_receiver(ct, pos, direction)`

Whether the tile in `direction` from `pos` is something that can actually
hold a delivered stack: a same-team Conveyor, Splitter, or the Core. Empty
ground, a wall, a building that has no titanium storage at all (a Barrier,
a turret), and a tile the Core can't currently see all come back `False`.
This is the piece that makes the Splitter weight below dynamic instead of a
hardcoded constant — it's how `_feeder_at` counts how many of a Splitter's
outputs are actually live right now.

The vision check exists because a Splitter's *other* two sides — the ones
`_feeder_at` isn't walking toward — might sit outside the Core's vision
even when the tracked side is well within it. Treating an unconfirmable
side as "not a receiver" is a deliberate choice, not the only one possible:
the alternative (assume it *is* live) would silently spread a Splitter's
weight across sides that might not even be built, which felt like the
worse failure mode to default to.

(The Barrier/turret case is the one part of this that's reasoned from the
mechanics rather than directly measured: `splitter_probe` only tested bare,
unbuilt tiles against one real Conveyor, not a Splitter with a non-receiving
*building* sitting on one of its sides. Treated the same as empty ground
here on the assumption that "has nowhere to put titanium" is what actually
governs the rotation, not "has any building at all" — plausible, but not
yet run through the real engine the way everything else in this file has
been.)

### `_core_footprint(ct)`

The Core occupies a 2×2 block of tiles, but `ct.get_tile_building_id`
works tile-by-tile. This collects every tile that belongs to the Core, by
checking which nearby tiles report the Core's own id:

```python
core_id = ct.get_id()
return [pos for pos in ct.get_nearby_tiles(dist_sq=2) if ct.get_tile_building_id(pos) == core_id]
```

`dist_sq=2` is enough to cover the whole 2×2 footprint no matter which
corner `ct.get_nearby_tiles` measures from — the two farthest tiles in a
2×2 block are a diagonal step apart, and a diagonal step has
`distance_squared == 2`.

### `_feeder_at(ct, pos, from_dir)`

The single-direction building block: "is there something in `from_dir` from
`pos` that feeds into `pos`, and if so, with what probability?"

It looks at the neighbouring tile and returns `None` unless that neighbour
is in the Core's vision, on the same team, and is a Conveyor or Splitter
whose output genuinely points back at `pos` — not just "is adjacent", but
"is actually facing the right way to deliver here":

- **Conveyor** — its one fixed facing direction must equal the direction
  back toward `pos`. If so, weight `1.0` (certain).
- **Splitter** — same idea, except a Splitter's *back* (opposite its facing
  direction) is input-only, not an output, so that one direction is
  rejected outright. Of its other three sides, `_is_receiver` counts how
  many currently lead somewhere (`pos` itself always counts as one, so this
  is never zero), and the weight is `1 / that count` — `1.0` if `pos` is
  the only side in use, `1/2` or `1/3` if one or two of the others are too.
- Anything else (empty tile, wall, Harvester, Gunner, ...) returns `None`.

### `_feeders(ct, pos, etype)`

Calls `_feeder_at` in every direction worth checking and keeps the hits.
"Worth checking" depends on what `pos` itself is:

- If `pos` is a **Splitter**, it only ever accepts input from the one tile
  directly behind it (opposite its facing direction) — so only that single
  direction is checked.
- Otherwise (`pos` is a Conveyor, or the Core itself) all four cardinal
  directions are checked, since both can be fed from any side.

This one function does double duty: it's used both to find what feeds a
Conveyor/Splitter, and — passing `EntityType.CORE` — to find what feeds the
Core's own footprint tiles in the first place. The Core isn't a Splitter, so
it automatically falls into the "check all four sides" branch, with no
special-casing needed.

### `_accumulate(ct, pos, etype, weight, hop, schedule)`

The recursive core of the whole thing. Given a tile that's already been
confirmed to feed toward the Core with some cumulative `weight` (the product
of every Splitter probability along the path so far) and is `hop` tiles —
rounds — out, it:

1. Checks whether `pos` currently holds titanium, and if so adds
   `weight * STACK_SIZE` (10 Ti scaled by however likely this stack is to
   actually complete the trip) into `schedule[hop - 1]` — the bucket for
   "arrives in exactly `hop` rounds", not a running total.
2. If `schedule` still has rounds left past this hop, recurses one hop
   further upstream for everything `_feeders` finds, each contributing its
   own `hop_weight` multiplied into the running `weight`.

```python
holding = ct.get_stored_resource(ct.get_tile_building_id(pos)) is not None
if holding:
    schedule[hop - 1] += weight * GameConstants.STACK_SIZE
if hop < len(schedule):
    for neighbor, n_etype, hop_weight in _feeders(ct, pos, etype):
        _accumulate(ct, neighbor, n_etype, weight * hop_weight, hop + 1, schedule)
```

This mutates `schedule` in place rather than returning a total — the whole
point is *which* round a contribution lands in, not just how much there is
altogether.

Two things worth noticing about this being a plain bounded recursion instead
of an explicit queue-plus-visited-set walk:

- **It can't run away.** `hop` climbs by exactly one on every step and stops
  once it reaches `len(schedule)`, so recursion depth is capped at however
  many rounds were asked for. It also can't wander further than the Core's
  vision, independent of that cap: `_feeder_at` refuses to step onto
  anything outside vision, so a request for a very large number of rounds
  doesn't turn into a search of the whole map — it's bounded by how many
  same-team Conveyor/Splitter tiles the Core can currently see, not by the
  round count.
- **It can't double-count.** Because every Conveyor and Splitter has
  exactly *one* fixed output direction, a given tile can only ever be
  discovered as a feeder of the one specific tile its output points at —
  never of two different tiles, and never in a cycle that loops back on
  itself. The "who feeds this tile" relation, walked backward from the
  Core, is guaranteed to be a tree. (Verified by hand and by a scratch test
  before relying on it — see the worked example below.)

### `expected_titanium_schedule(ct, rounds)`

Ties it together: find everything feeding the Core's footprint directly
(`_feeders(ct, tile, EntityType.CORE)` for each footprint tile), run
`_accumulate` for each of those branches into a shared `schedule`, then lay
the guaranteed passive 10 Ti onto whichever future round it's actually due:

```python
schedule = [0.0] * rounds
for tile in _core_footprint(ct):
    for neighbor, etype, weight in _feeders(ct, tile, EntityType.CORE):
        _accumulate(ct, neighbor, etype, weight, 1, schedule)

current_round = ct.get_current_round()
for i in range(rounds):
    if (current_round + i + 1) % GameConstants.PASSIVE_TITANIUM_INTERVAL == 0:
        schedule[i] += GameConstants.PASSIVE_TITANIUM_AMOUNT
return schedule
```

The passive tick has to be placed by actual game round (`current_round + i +
1`), not just by index — it's a fixed, calendar-based cadence, not something
that starts counting over from whenever this function happens to be called.
Two Cores that call this on different rounds, or the same Core calling it
twice ten rounds apart, should each get the tick lined up with the *same*
real rounds, not with "4 calls from now" in each of their own local frames.

### `expected_titanium_flow(ct)`

The single-number convenience wrapper: `sum(expected_titanium_schedule(ct,
4)) / 4`. Same information as the first 4 entries of the schedule, just
collapsed into one average.

## Worked example

A straight Conveyor chain feeding the Core from the west (arrows show the
direction titanium actually moves, i.e. each Conveyor's facing), plus a
Splitter branch feeding it from the north. The Splitter also has a second
Conveyor built on its western side, running off to a separate stockpile —
an ordinary use of a Splitter's third side, and the reason its weight below
is `1/2` rather than `1.0`: two of its three sides are genuinely in use, so
each gets half the dispatches long-run. Assume `ct.get_current_round()` is
`0` and everything drawn is in vision.

```
                    north branch          spare side, also built
                    [Conv: Ti] ──► [Splitter: Ti] ──► [stockpile route, untraced]
                     weight 1/2      weight 1/2
                                          │
                                          ▼
[dist 5: Ti] ──► [dist 4: Ti] ──► [dist 3: empty] ──► [dist 2: Ti] ──► [dist 1: Ti] ──► Core
                    weight 1        weight 1           weight 1         weight 1
```

Every tile in the picture is exactly as many hops from the Core as its
label says, on both branches (the north branch's Splitter is hop 1, its
feeder is hop 2), so each one's contribution (`weight * 10` if holding,
`0` if empty) lands in `schedule[hop - 1]`:

| hop | west chain | north branch | pipeline total this hop |
|---|---|---|---|
| 1 | dist-1, w `1`, holds → `10` | Splitter, w `1/2`, holds → `5` | `15` |
| 2 | dist-2, w `1`, holds → `10` | feeder, w `1/2`, holds → `5` | `15` |
| 3 | dist-3, w `1`, **empty** → `0` | — | `0` |
| 4 | dist-4, w `1`, holds → `10` | — | `10` |
| 5 | dist-5, w `1`, holds → `10` | — | `10` |
| 6 | *(nothing left to feed either branch)* | — | `0` |

Then the passive `+10` lands on whichever hop is a multiple of 4 rounds
from now — here just hop 4 — and the result is `expected_titanium_schedule(ct, 6)`:

```python
>>> expected_titanium_schedule(ct, 6)
[15.0, 15.0, 0.0, 20.0, 10.0, 0.0]
#                  ^^^^ hop 4: 10 (pipeline) + 10 (passive)
```

`expected_titanium_flow(ct)` is `sum([15.0, 15.0, 0.0, 20.0]) / 4 = 12.5` —
only the first 4 entries; the dist-5 Conveyor never enters the average at
all, since it's one hop past where that 4-round window cuts off.

Both of these were checked against a hand-built fake `Controller`
reproducing this exact board, including the `current_round`-dependent
placement of the passive tick (a second run starting from
`current_round = 2` instead of `0` moves the `+10` from `schedule[3]` to
`schedule[1]` and `schedule[5]`, exactly as the game-round arithmetic
above predicts) — see the note in [Limitations](#limitations) about what
that test does and doesn't prove.

## Limitations

- **The Splitter weight is an expected value, not a prediction.** Any
  *specific* stack either does or doesn't go toward the Core next round —
  there's no way to know which, so this reports the long-run average
  instead. Real-world flow will look "lumpy" compared to this smooth
  number, especially right after a delivery, when the Splitter (and
  whatever feeds it) reads empty for a stretch even on a perfectly healthy
  route.
- **Chained Splitters still compound, just not as harshly as before.** Two
  Splitters in a row, each with two live outputs, drop a stack's weight to
  `1/4`; each additional live output on either one divides it further. A
  route through several multi-output Splitters can still end up
  contributing very little to the estimate even while delivering fine —
  just less punishingly than the old flat-`1/3`-per-hop model implied.
- **Harvesters are invisible, not just excluded by choice.**
  `get_stored_resource` doesn't support them, so any route whose final hop
  into the tracked network is a Harvester contributes nothing, with no way
  to improve that short of the API exposing more.
- **`_is_receiver` treats "no titanium storage" as unreasoning as "no
  building at all."** This is the one piece of the Splitter-weight model
  that's inferred rather than directly measured — see the note under
  `_is_receiver` in [Walking the code](#walking-the-code). Everything else
  about the dynamic weight was verified against the real engine (below);
  this specific case (a Barrier or turret sitting on one of a Splitter's
  sides) wasn't.
- **The search silently stops at the edge of vision.** `_feeder_at` refuses
  to step onto anything outside the Core's vision, so a route whose next
  segment happens to sit just past that edge doesn't get excluded with an
  error or a warning — it just quietly reads as "nothing here", same as an
  empty tile or a genuine dead end. A high round count doesn't buy visibility
  the Core doesn't have; it only buys a longer schedule over whatever *is*
  visible. This also means the schedule can change from one call to the
  next purely because something entered or left vision, with no change to
  the actual belt at all.
- **Verified against a hand-written fake, and separately against the real
  engine — including the finding that changed the Splitter weight from a
  flat 1/3 to a dynamic 1/(live outputs).** The worked examples above were
  checked against a mock object implementing the documented `Controller`
  methods, confirming the arithmetic matches the rules as coded, including
  the round-by-round schedule and its `current_round`-dependent passive-tick
  placement. Separately, against the real engine:
  - [`bots/test/econ_demo`](../econ_demo/) plays a real match, lays a real
    Harvester → Conveyor → Splitter → Core route, and has the Core call
    both `expected_titanium_flow` and `expected_titanium_schedule` (with
    `SCHEDULE_ROUNDS` set past the old 4-round window, so it actually
    exercises the extra reach). On `maps/duel.map26`, `flow` reports
    `5.0000` — `(10 * 1.0 + 10) / 4`, versus `3.3333` before the
    Splitter-weight fix (see the flat-`1/3` bullet above) — and one sampled
    `schedule_now` was
    `[0.0, 10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0]`, whose first 4 entries sum
    to `10.0`, matching `flow_now = 2.5000` at that exact same round: the
    two functions agree with each other in a real match, not just in
    isolation.
  - [`bots/test/splitter_probe`](../splitter_probe/) is what found the fix
    in the first place: it builds a Splitter with only one of its three
    sides connected to anything and counts, over hundreds of real rounds,
    how often the Splitter dispatches (`get_stored_resource` reads
    occupied) against how many stacks actually reach the Core (backed out
    of the team's resource gain, less the known passive trickle). One run:
    222 dispatches, 222 arrivals — a ratio of `1.0000`, not the `~0.33` a
    blind 3-way rotation would produce. That's what motivated `_is_receiver`
    and the switch from a hardcoded `1/3` to a live count.
  - Neither has been run against the repo's own `tests/fake_controller.py`,
    which doesn't model conveyor contents or Splitter rotation and
    wouldn't exercise this logic even if used.
