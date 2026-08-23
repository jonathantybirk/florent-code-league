# Per-path expected vs. actual titanium flow

`main.py` answers a diagnostic question, from the Core's point of view:
**for each conveyor/splitter tile that feeds the Core, how much titanium
*should* be crossing it, and how much actually is?** Comparing the two per
tile — rather than one number for the whole economy — is what lets a future
feature point at *which* stretch of belt broke instead of just "income is
down."

It's a pure data model with no side effects — nothing here moves, builds, or
spends anything — meant to be wired into a real bot's `run()` later. There's
no `run()` method here, and `self.map`/`self.harvester_positions` are never
populated from `ct` or from builder reports; both are assumed already
filled in by whatever surrounding code owns vision/reporting. See
[Limitations](#limitations) for the full list of what this file doesn't do
yet.

## The model

Two dataclasses, forming a tree rooted at the Core:

- **`Path`** — one node per conveyor/splitter tile that can reach the Core.
  `next` points one hop closer to the Core (`None` once the next hop *is*
  the Core). `harvesters` lists every `Harvester` whose delivery passes
  through this exact tile — so a tile on a shared trunk accumulates all of
  its upstream harvesters, and `expected_flow` is a property computed from
  that list.
- **`Harvester`** — `position`, `connected`, and `entry_path` (the first
  `Path` node its output reaches). `path` is a property that walks the
  chain from `entry_path` to the Core, rebuilt on demand rather than stored
  twice.

`Player.paths: dict[tuple[int, int], Path]` is keyed by tile, so "what's
the expected/actual flow at this specific tile the Core can currently see"
is an O(1) lookup, not a search.

## `self.map` assumptions

`self.map` is meant to be a locally-maintained cache of what this team's
units have observed, **not** a live view of the engine — `_contruct_map`
only allocates an empty grid; nothing in this file populates it from `ct`
or from builder reports (see [Limitations](#limitations)). Everything
downstream (`_build_paths`, `_find_entry`, `_observe_flow`) is built
entirely on the following assumptions about that cache, none of which are
currently enforced or validated by the code:

1. **Shape**: row-major `list[list]`, indexed `self.map[y][x]` — y (row)
   first, x (column) second. Matches `Position`'s `x`/`y` convention
   (compass: x east, y south), just transposed for indexing.
2. **Cell contents**: each cell is either `None` or a duck-typed "entity
   object" exposing `.type` (an `EntityType`) and, for `CONVEYOR`/
   `SPLITTER` only, `.direction` (a `Direction`). This is **not** `fcode`'s
   real entity, and not `tests/fake_controller.Entity` either — that one
   uses `.etype`, not `.type`, and also carries `.pos`/`.team`/`.hp`/etc.
   Whatever populates `self.map` must produce objects with exactly
   `.type`/`.direction` or every method here breaks. No other attribute is
   ever read.
3. **`None` means "unknown," not "confirmed empty"** — and the code cannot
   tell the difference. A conveyor that exists but was never observed (or
   was observed once and has since gone stale) looks identical to
   genuinely empty ground: both are `None`, both are treated as a dead end.
   This matters a lot given `bots/test/vision_probe`'s finding (see the
   project's `CLAUDE.md`) that the real engine raises `GameError` for
   anything outside current vision — a tile leaving vision doesn't
   downgrade to "stale but present," it just becomes unqueryable, and
   whatever `self.map` recorded from before is the *only* memory of it.
   There is currently no staleness/last-seen tracking at all.
4. **No team field, so no team filtering** — `self.map` is implicitly
   assumed to contain *only friendly* entities. If an enemy conveyor/
   splitter ever ended up recorded here, `_build_paths` would happily treat
   it as a valid link in the reachability tree, silently merging enemy and
   friendly conveyor networks. Nothing here guards against that; it has to
   be enforced by whatever populates the map.
5. **A harvester's own tile is expected to be `None`** in the map —
   `_find_entry` only ever looks at a harvester's four cardinal
   *neighbors*, never `self.map` at the harvester's own coordinates. A
   harvester is treated purely as a source, never as something that itself
   receives.
6. **The Core's 2×2 footprint must be populated on all 4 tiles
   independently** — `_build_paths` scans the whole map for any cell with
   `.type == CORE` to seed its search. Confirmed empirically
   (`vision_probe`) that the real engine returns the *same* building id for
   all four footprint tiles, so a populating routine that discovers the
   Core via one tile should mark all four it can see, not just an anchor
   corner — otherwise reachability into a partially-recorded footprint can
   silently fail depending on which corner a route approaches from.
7. **Entities are assumed current, with no notion of "when observed."** If
   a conveyor is destroyed after being recorded, nothing invalidates that
   map entry. Same caveat as point 3, worth calling out separately since
   it's a staleness problem, not just an unknown-vs-empty ambiguity.
8. **Splitters are modeled as if all 3 outputs are simultaneously live**
   for reachability purposes (`_out_dirs` returns all three non-back
   directions unconditionally) — a modeling choice, not a map-fidelity
   issue (see the Splitter bullet under [Limitations](#limitations)), but
   worth noting here too: the map doesn't need to (and doesn't) track a
   Splitter's live rotation state for this logic to run. Only
   `_observe_flow` separately reads `get_stored_resource_id` for its own
   purpose, and that goes through `ct` live, not through `self.map`.

## Why per-tile, not per-harvester

An earlier version of this tracked one flow number per harvester. That
doesn't isolate anything: two harvesters merging into a shared trunk look
identical to a healthy trunk carrying one harvester's worth of flow twice —
the merge point itself is invisible. Keying by tile instead means every
point along the network — including a trunk segment nowhere near any single
harvester — carries its own expected/actual pair, so a break shows up as a
mismatch starting at a specific tile, with everything upstream of it still
reading healthy and everything downstream reading starved.

## The formulas

**Expected**, on `Path`:

```python
stacks_per_round = len(self.harvesters) / GameConstants.PASSIVE_TITANIUM_INTERVAL
return stacks_per_round * GameConstants.PASSIVE_TITANIUM_AMOUNT
```

Every connected harvester delivers one `PASSIVE_TITANIUM_AMOUNT` stack every
`PASSIVE_TITANIUM_INTERVAL` rounds on average (see
[`docs/official/docs/game-rules-harvester.txt`](../../../docs/official/docs/game-rules-harvester.txt)),
so N harvesters through the same tile sum to `N * 10 / 4` Ti/round. These
are the real `GameConstants` fields — there's no dedicated harvester-rate
constant in `fcode`, and this is the same pair
[`bots/test/econ`](../econ/README.md) draws on for the identical 10-Ti-every-
4-rounds figure, even though that mechanic (the team's passive income) and
this one (harvester output) are independent in the rules.

**Actual**, updated by `_observe_flow` and stored as `Path.actual_flow`: an
exponential moving average (`_FLOW_EMA_ALPHA = 0.2`) over one sample per
round — `PASSIVE_TITANIUM_AMOUNT` if a *new* stack was detected passing
through this round, `0` otherwise. See `_observe_flow` below for what
"detected" means and why a single round's snapshot isn't enough on its own.

## Walking the code

### `_accepts_from(entity, travel_dir)` / `_out_dirs(entity)`

The two rules everything else is built from, straight from
[`docs/official/docs/game-rules-conveyors.txt`](../../../docs/official/docs/game-rules-conveyors.txt):

- A **Conveyor** accepts a delivery from any side except the one it outputs
  to, and has exactly one output direction (its facing).
- A **Splitter** accepts only from directly behind (opposite its facing),
  and can output to any of the other three cardinal sides (facing + the two
  adjacent) — treated here as if all three are simultaneously live, since
  the question this file answers is reachability, not which specific output
  a Splitter uses on a given round. `_out_dirs` returns all three; nothing
  here models the round-robin itself. (Contrast with `bots/test/econ`,
  which *does* model it — see the note under
  [Limitations](#limitations).)
- The **Core** accepts from anywhere.

`_DELTA`/`_OPPOSITE` at module scope precompute `Direction.delta()`/
`.opposite()` for the four cardinals: the real `fcode.Direction` rebuilds a
dict literal on every single call to either method rather than caching one,
which is cheap in isolation but adds up across the thousands of calls
`_build_paths` makes on a full map scan (measured ~2.5x speedup from this
one change — see [Performance](#performance)).

### `_build_paths(ct)`

A single reverse BFS from every Core tile (there can be up to four, since
the Core is a 2×2 footprint), walking predecessor edges — the mirror of
`_accepts_from`/`_out_dirs`. For each already-confirmed-reachable tile, it
checks each cardinal neighbour as a candidate predecessor: does the
neighbour's own facing actually produce an edge into this tile
(`_out_dirs`), *and* does this tile accept an arrival from that direction
(`_accepts_from`)? If both hold, the neighbour is reachable too, chained
toward the Core via `next`.

Building the whole tree once, rather than searching outward from each
harvester independently, is what turns per-harvester connectivity into an
O(width × height) computation total instead of O(harvesters × width ×
height) — seven-figure-tile-touch counts don't scale with how many
harvesters you've built. `_find_entry` (below) is then just a 4-neighbour
check per harvester against the tree that's already there.

A tile that also existed in the previous `self.paths` keeps its
`actual_flow`/last-seen-id state — a fresh `Path` object is still created
every call (`next`/`harvesters` depend on the current network shape and
can legitimately change), but flow history shouldn't reset to zero just
because the network got rescanned this round.

### `_find_entry(ct, position, paths)`

Whether a harvester at `position` has a viable route, and the first `Path`
node that route passes through. Checks its four cardinal neighbours against
`_accepts_from` and the tree `_build_paths` already produced — `True, None`
if the very next tile is the Core itself (zero conveyors in between),
`False, None` if nothing connects.

### `_update_harvesters(ct)`

Ties it together: build the tree, then for each harvester in
`self.harvester_positions`, find its entry point and walk `entry_path.next`
all the way to the Core, appending the `Harvester` to every `Path` node
along the way. That walk is what makes a shared trunk tile's `harvesters`
list — and therefore its `expected_flow` — reflect every harvester feeding
it, not just the nearest one.

### `_observe_flow(ct)`

The actual-flow half, called once per round from the Core's own `run()`
(raises `ValueError` from any other unit — same guard convention as
`bots/test/econ`'s `expected_titanium_schedule`), after `_update_harvesters`
so a fresh `self.paths` exists to update.

`get_stored_resource_id` — not `get_stored_resource` — is the load-bearing
call: a Conveyor/Splitter holds exactly one stack at a time, so a *changed*
id since last observed means a fresh stack actually passed through this
round; an *unchanged* id means the previous stack is still sitting there
(backpressure), not a new delivery. Treating "holds something" as "a
delivery happened" would count a stalled stack as continuous throughput.
One sample per round — `PASSIVE_TITANIUM_AMOUNT` on a detected arrival, `0`
otherwise — folds into the EMA, since a single round's snapshot can't tell
you a rate on its own.

Walks `ct.get_nearby_tiles()` (bounded by the Core's vision radius) rather
than every entry in `self.paths`, since most of `self.paths` would just
fail a vision check anyway on any map bigger than what's currently visible.
Tiles outside vision this round are left untouched — there's nothing to
observe, and no observation is recorded either way.

## Worked example

```
harvester_b (9,8)
     │ south
     ▼
[Splitter@(9,9), facing SOUTH] ──┐
                                 │ south                    Core footprint
                                 ▼                           (10,10)-(11,11)
[Conv@(7,10),E] ──east──► [Conv@(8,10),E] ──east──► [Conv@(9,10),E] ──east──► Core
     ▲
     │ east
harvester_a (6,10)
```

`harvester_a`'s route: `entry_path = (7,10)`, chained `(8,10) → (9,10) →
None` (Core). `harvester_b`'s route: `entry_path = (9,9)`, chained `(9,10)
→ None` — it never touches `(7,10)`/`(8,10)`, those belong only to
`harvester_a`'s branch.

`(9,10)` is the genuine merge point — both routes pass through it right
before the Core, so `paths[(9,10)].harvesters == [harvester_a, harvester_b]`
and `expected_flow == 2 * 10 / 4 == 5.0`. `paths[(7,10)].harvesters ==
[harvester_a]` only — it's upstream of the merge, so it only ever sees
`harvester_a`'s traffic. This exact scenario (plus a third, fully
disconnected harvester) is what
[`tests/test_econ2.py`](../../../tests/test_econ2.py) builds and asserts
against.

## Performance

The map is capped at 30×30 (900 tiles). `_build_paths`/`_update_harvesters`
were benchmarked against the repo's real `fcode` types (via
`tests/fake_controller.py`, not a standalone reimplementation) on the
worst case — a single conveyor chain covering nearly every tile of the
map: **~2.4 ms**, comfortably inside the 10 ms/round/unit budget (see
[`docs/official/docs/game-rules-overview.txt`](../../../docs/official/docs/game-rules-overview.txt#L49-L51)).
That number dropped from ~5.9 ms after caching `Direction.delta()`/
`.opposite()` (see `_DELTA`/`_OPPOSITE` above) — the real `fcode.Direction`
rebuilds a dict per call, which a from-scratch reimplementation used for
earlier estimates didn't capture.

`_observe_flow`'s own logic profiles at roughly 36 microseconds per call
against the fake harness — negligible. A raw wall-clock number for the full
call isn't trustworthy from this harness, though: `fake_controller.py`'s
`get_tile_building_id` does a linear scan over every entity in the world
(it's explicitly documented as a minimal stand-in, not built for
performance testing), which dominates any timing taken through it and has
nothing to do with this file's own code. The real engine's equivalent is a
core, constantly-used API and almost certainly not a linear scan, but that
can't be confirmed from here.

## Limitations

- **Splitter branching isn't discounted.** `_out_dirs` treats all three of
  a Splitter's outputs as simultaneously live for reachability purposes. If
  only one of three actually leads toward the Core and the other two are
  dead ends, `expected_flow` still counts full throughput toward the Core,
  when in reality only 1-in-3 of the Splitter's round-robin dispatches
  would go the right way. `bots/test/econ` models this dilution
  (`1 / live outputs`, verified against the real engine); this file
  doesn't, and comparing `expected_flow` against `actual_flow` on any
  branching layout will read as a false anomaly until it does.
- **A single tile has a physical throughput ceiling this model ignores.** A
  Conveyor/Splitter holds exactly one stack at a time, so a tile can never
  carry more than one delivery per round (10 Ti/round) no matter how many
  harvesters feed it. A trunk tile with, say, 8 harvesters upstream
  computes `expected_flow = 20.0`, double what the tile itself could ever
  physically carry — `actual_flow` will legitimately plateau at 10.0 there
  even with nothing broken.
- **`self.map` and `self.harvester_positions` are never populated.**
  `_contruct_map` allocates an empty grid; nothing here fills it in from
  `ct` or from builder reports, and nothing appends to
  `harvester_positions`. Both are assumed to already be correct by the time
  `_update_harvesters`/`_observe_flow` are called — see
  [`self.map` assumptions](#selfmap-assumptions) for exactly what "correct"
  means here.
- **Not wired into a `run()`.** Nothing here calls `_update_harvesters` or
  `_observe_flow` on a schedule; there's no unit that would trigger them
  each round.
- **The comparison itself doesn't exist yet.** `expected_flow` and
  `actual_flow` are both computed and available per `Path`, but nothing
  reads both and raises a flag when they diverge — that's the intended
  next step, not something this file does.

## Testing

[`tests/test_econ2.py`](../../../tests/test_econ2.py) exercises this
through the repo's `fake_controller.World`/`botimport` harness (real
`fcode` types, no full engine) — connectivity and path order on a straight
chain, a Splitter branch merging at the correct tile (not upstream of it),
a disconnected harvester, per-tile harvester aggregation both at and above
a merge, direct Core adjacency, the `_observe_flow` Core-only guard, id-delta
arrival detection (new stack vs. a stalled one vs. a second genuine
arrival), vision gating, and flow state surviving a `_build_paths` rebuild.
`_build_paths`/`_find_entry` were additionally cross-checked during
development against an independent forward-BFS reachability oracle across
several thousand randomized maps (not committed — a throwaway script, not a
regression test), turning up zero mismatches and zero invalid reconstructed
paths.
