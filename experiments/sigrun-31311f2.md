# sigrun@31311f2

Normal-queue successor to `sigrun@5b3fba2`; three rounds at the tail of
`test_next`, never `queue_front`.

## Change

Forage-mode miners now reuse an existing connected conveyor as the end of a
new deposit route, matching the normal economy planner instead of forcing every
deposit to pay for an independent route to the Core. Opening timing, the forage
verdict, Harvester cap, combat, defense, and repair logic are unchanged.

Midgard B keeps independent routes: shared forage trunks lost its income race
against Spar Econ at all five tested seeds. The exception is keyed by terrain
dimensions and Core anchor, using the same compact map-side gate as conveyor
staging.

## Paired local verdict

Discovery, 15 pool maps and both seats:

- Gefn: 25-5 for both versions; mean titanium 147 -> 202.
- Spar Econ: 30-0 for both versions; mean titanium 1698 -> 1736.
- Spork: 18-12 for both versions.
- Pantheon replica: 30-0 for both versions.

Held out:

- Gefn, seeds 1-3: 75-15 for both; mean titanium 147 -> 202 (+37%).
- Spar Econ, seeds 1-5: 150-0; mean titanium 1774.
- Midgard B guard, seeds 1-5: 5-0, matching the parent; unguarded shared
  trunks scored 0-5.

The rejected earlier-forage experiment scored 23-7 against Gefn versus the
parent's 25-5, so it was removed. A forage cap of ten was also rejected after
zero flips in a 90-game exact panel.

Promotion remains the farm's expected-Elo decision against current online
opponents.
