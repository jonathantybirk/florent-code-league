# jonbot_econ@3c3a0d4

Timing-preserving fork of `brynhildr@533601b`. It does not alter Core spawning,
the economy trigger, miner count, roles, or defensive priorities. It only makes
a miner standing on its next build tile vacate inward through the completed belt
instead of taking the first arbitrary cardinal step.

Local 10 ms evidence:

- parent mirror: 21-21 over 21 maps and both seats;
- economy/defense panel: 93-33, identical to the parent opponent-by-opponent;
- rejected static ore ownership: 90-36;
- superseded early-start v115 online: 6-19 over its first five series.

The online test is intentionally against the five opponents that exposed the
early-start regression first, followed by the remaining comparison set.

## Follow-up ablations

Replay analysis of v116's Bifrost loss to Torsko found miner authorization at
round 108, conveyors at 111/113/115/117, and Harvesters at 121/145. The initial
chain is already near the one-build/one-move limit; the larger issue is the
strategy's deliberate late authorization versus Torsko's round-1 economy.

- Building later expansions from the nearer endpoint regressed the standard
  economy/defense panel from 93-33 to 90-36.
- Reducing only the post-authorization Harvester reserve from 20 to 10 regressed
  the parent mirror from 21-21 to 18-24.

Both ablations were rejected. `tools/evaluate_mining.py` on `x/jon@7aa09bc`
now reports adaptive mining timelines without assuming a fixed opening plan.
