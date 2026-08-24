# sigrun@31311f2

Successor to `sigrun@5b3fba2`. It was initially queued normally, then moved to
the front for two rounds after explicit approval to resume limited priority
testing. Both rounds are pinned to the ten teams currently nearest our #27,
1762-rated ladder position; no top-five sampling is used.

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

## Online round 1 (v130)

The first nearby-only priority round scored 10-15: DinooniD 3-2, OpenSverige
0-5, I Stone 4-1, 0033 2-3, and Besvikomat 1-4. This is below the local panel
and is not promotion evidence.

Replay inspection separates two regimes. Against OpenSverige, four losses end
in 108-255 rounds with no Harvester ever built; the 1000-round Valkyrie loss
builds only two and finishes with none connected. Those are combat/pressure
losses, not shared-trunk execution failures. Against Besvikomat, the two long
losses build eleven Harvesters each but lose 12 and 11 economy buildings,
respectively; exposed-network survival is the economy bottleneck there.

At collection time ladderfarm had promoted `jonbot_econ@19793f0` (v120) as the
active expected-Elo winner. Sigrun v130 remains a challenger pending its second
nearby-only round; it must not replace v120 from this first result.

## Online round 2 and final verdict

The second nearby-only round scored 14-11: Banminary 1-4, TRRR 3-2, Atlas 2-3,
Torsko 3-2, and Viktor5776 4-1. Across both priority rounds v130 is 24-26.
That is materially better than the first slice but not promotion evidence, so
no further priority rounds are assigned. Ladderfarm remains authoritative and
has since moved the active expected-Elo flagship to Brynhildr v104.
