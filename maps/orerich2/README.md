# maps/orerich2 — an independent second sample at the live ore profile

Same construction as `maps/orerich` but from a different generator seed
(777001 instead of 5150), selected on the same live-terrain filter: 40-56 ore
per 1000 tiles, area 350-520, wall fraction 5-20%.

| set | maps | ore/1k | area | wall |
|---|---|---|---|---|
| live ladder | 13 | 47.0 | 439 | 11.9% |
| `maps/orerich` | 150 | 46.1 | 404 | 12.0% |
| **`maps/orerich2`** | 150 | **45.4** | 415 | 11.5% |

## Why a second sample exists

Because a result measured on one map sample is a result about that sample.
`nott` read +0.2 and +1.0 sd against `vanguard` and `undertow` on `orerich`;
on `orerich2` the same pair reads +0.6 and **-0.6** sd. Pooled over both
samples the effect on that base is +0.54 sd rather than the +0.78 sd the first
sample alone suggested.

Use both whenever a change is close enough to matter. Terrain statistics come
from `tools/mapstat.py`.
