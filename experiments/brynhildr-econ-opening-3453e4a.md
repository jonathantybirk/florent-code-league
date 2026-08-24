# brynhildr_econ_opening@3453e4a

Queued 2026-08-24 from `x/jon`. This is a standalone fork of submission v110,
`brynhildr@e9f94e7`, with a map-aware initial economy module.

## Hypothesis

On long or economy-sensitive starts, buy one precomputed mining Builder on round
0 and start Brynhildr's original Sentinel attacker on round 1. On every unlisted
start, execute v110 unchanged from round 0. The opening uses no GCS slots and is
vendored inside the bot because ladderfarm exports only the bot directory.

The gate is keyed by `(map size, own Core position)`, allowing asymmetric maps
to use economy from only the start where it won. It enables 37 of 106 official
map/start combinations.

## Local evidence

- Full 53-map, both-seat head-to-head against v110, seed 1: **68-38**.
- Changed starts in that panel: **37-0**.
- Nine symmetric maps, both seats, seeds 1-3: **52-2**. Both nominal losses
  were tied Pinch coinflips; the other Pinch start collected 2440 vs 2430 Ti.
- Nineteen asymmetric starts, seeds 1-5: **95-0**.
- Two opening Builders were rejected at **17-20** on the same changed starts.
- A non-gated Heart run against do-nothing produced identical result JSON to
  v110, confirming the gate preserves the flagship path there.
- The underlying opening completed all declared construction on 53 maps, both
  starts, and 1-4 Builders: 424/424 configurations.

All local matches used the server's 10 ms TLE. The repository suite passed 65
tests, plus Python compilation and `git diff --check`.

## Online decision

Run three forced rounds against the same defensive/walling panel used for recent
Brynhildr candidates. Promotion remains ladderfarm's normal qualified simulated
one-round delta-Elo decision. Do not promote from this local panel alone.

If online results are worse, inspect losses by map/start first: narrow or replace
the terrain gate before changing the proven single-miner schedule. The next
orthogonal experiment is attacker timing on only the losing online starts; a
global second miner is already falsified.
