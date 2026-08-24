# jonbot_brynhildr_cadence@bbf0c77

Exact fork of the repeatedly selected expected-Elo flagship
`brynhildr@e4c3dff` (v104). One priority round is pinned to nearby Besvikomat,
I Stone, 0033, Banminary, and TRRR; no top-five opponents are used.

## Change

Only the generic miner executor changes. After laying an outward conveyor it
stages through the completed inward network, allowing alternating build/move
actions without changing when the Core buys a miner. Combat, defense, purchase
timing, target selection, and all other v104 behavior are the parent
implementation.

Antler and Holmgang A retain parent movement. The latter gate is paired evidence,
not action scripting: ungated cadence flips Holmgang A from 10-0 to 0-10 while
flipping Longhouse B from 0-10 to 10-0. Keeping parent movement on Holmgang
preserves the gain without the regression.

## Local verdict

- Spar Econ, 15 pool maps, both seats, seeds 1-3: 84-6 versus the exact v104
  parent's equivalent 81-9; three Longhouse-B loss-to-win flips, no loss flips.
- Sensitive-map audit, Helheim/Holmgang/Longhouse, both seats, seeds 1-10:
  40-20 versus 30-30.
- Exact v104 direct mirror, 15 maps, both seats, seeds 1-3: 48-42.
- Off-pool regression gate on Quarry, String, and Yulerune, both seats and
  seeds 1-5: 19-11 versus the exact parent's 10-20. Every map improved and no
  map-level regression appeared, so no topology-specific exclusions were added.

## Online verdict

The first nearby-opponent round (submission v132) finished **16-9**:

- Besvikomat 1-4
- I Stone 4-1
- 0033 4-1
- Banminary 3-2
- TRRR 4-1

This is encouraging but not promotion evidence yet: the build has faced only
five of the ten closest opponents, below ladderfarm's 7/10 qualification gate.
It is now a normal coverage bot, not a forced-front entry, so future rounds fill
the missing nearby-opponent coverage when the regular selector chooses it.

The bot is vendored under `bots/jon/` so later shared Brynhildr changes cannot
silently alter this exact experimental base. Promotion remains ladderfarm's
qualified expected-Elo decision.
