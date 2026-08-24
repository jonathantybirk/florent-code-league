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
