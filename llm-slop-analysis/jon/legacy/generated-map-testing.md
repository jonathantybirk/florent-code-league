# Generated map testing

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

The synthetic maps under `maps/generated/` are generalisation tests, not
predictions of the competition's hand-authored map style. New profile corpora
are written into new subdirectories; the legacy corpus is never moved during a
benchmark.

## Known hard constraints

The published engine specification and official map editor establish:

- width and height are independently between 8 and 30 inclusive;
- terrain is rectangular and consists only of empty, wall, and titanium-ore
  tiles;
- the map is symmetric under 180-degree rotation, left-right reflection, or
  top-bottom reflection;
- each team has one 2x2 Core;
- the second Core is the transformed counterpart of the first; and
- Core footprints have a one-tile clear margin. The editor clears terrain in
  that margin and rejects Core footprints whose margins overlap.

The bundled maps omit the editor's newer field-5 symmetry metadata. Generated
maps include it; `fcode 2.2.0` accepts both encodings.

No published rule fixes the ore count, wall count, Core distance from an edge,
number of initially visible ores, number of legal spawn tiles, or the dominant
symmetry type.

## Explicit playability policies

The generator additionally requires:

- both Core spawn rings are connected by eight-direction Builder movement;
- at least two ore tiles are reachable from that connected component; and
- both Cores have their complete twelve-tile spawn ring in bounds.

These are conservative testing policies rather than claimed competition
guarantees. Use `validate --rules-only` to check only the known hard
constraints.

## Commands

Generate both profiled corpora:

```bash
uv run python maps/generated/generate_profiles.py all
```

The profiles are:

- `representative/`: two randomized variants of every official archetype,
  preserving the pool's dimensions, Core anchors, symmetry class, wall and ore
  counts, initially visible ore, and round-one symmetry ambiguity;
- `stress/`: broad legal fuzz maps plus adversarial ambiguity cases.

The adversarial cases are intentionally mirror-x maps where rotation and
mirror-x both survive round one and imply the same enemy-Core anchor. Rotation
is nevertheless false and predicts different unseen terrain. This is distinct
from a genuinely dual-symmetric map: if two transforms are both real
symmetries, they cannot disagree on the predicted terrain value.

Generate the checked-in deterministic corpus:

```bash
uv run python maps/generated/generate_maps.py generate \
  --count 24 --seed 20260731
```

Generate a separate exploratory corpus:

```bash
uv run python maps/generated/generate_maps.py generate \
  --count 100 --seed 42 --output /tmp/fcode-random-maps
```

Validate generated maps:

```bash
uv run python maps/generated/generate_maps.py validate maps/generated
```

Run the generator tests:

```bash
uv run python -m unittest maps/generated/test_generate_maps.py
```

Run a match on one generated map by passing its explicit path:

```bash
uv run fcode run --tle 10 bots/jon/fair/jonbot \
  bots/jon/fair/vanguard \
  maps/generated/random-20260731-000-mirror-y-8x16.map26
```

Run both player orders across the complete generated corpus:

```bash
uv run python maps/generated/run_corpus.py \
  bots/jon/fair/jonbot bots/jon/fair/vanguard
```

The root-level `fcode run --map-random` command scans only `maps/*.map26`, not
subdirectories. Consequently, checked-in generated maps do not silently enter
the normal competition-map pool.

## Intended use

Useful corpus dimensions include:

- very small and very large rectangles;
- all three legal symmetry families;
- open maps, sparse obstacles, and dense chokepoints;
- centerline ore fixed under a reflection;
- short and long Core-to-Core routes;
- scarce and abundant ore; and
- layouts unlike any of the fifteen announced maps.

Failures on these maps should be treated as evidence of brittle assumptions,
not as estimates of ladder win rate. The competition maps are expected to be
handcrafted and will have a more deliberate tactical structure.
