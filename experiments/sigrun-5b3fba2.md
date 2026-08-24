# sigrun@5b3fba2

Normal-queue successor to `sigrun@ca5008a`; three rounds at the tail of
`test_next`, never `queue_front`.

## Online evidence behind the change

Sigrun v127's six losses across its Torsko and 0033 rounds ended with connected
Harvester counts 0-3, 4-11, 5-13, 2-7, 4-8, and 4-7. The representative Paths
loss lasted 680 rounds and ended 5-13. Sigrun had already declared the rush
unfundable and entered forage mode, but `HARVESTERS_MAX = 5` still stopped the
home economy while the opponent continued expanding.

Replay command:

```bash
uv run fcode watch /tmp/sigrun-online/2949fc91-240d-4844-a7ff-91f768062886_game_5.replay26
```

## Change

Normal play is unchanged and remains capped at five Harvesters. Only after the
existing `ORD_FORAGE` income-war verdict, the Core funds up to seven—the exact
maximum already representable in its three-bit Harvester-count field. New
At this revision, forage chains route independently rather than joining a
potentially saturated four-Harvester trunk. This was later refined by
`sigrun@31311f2`, with a paired terrain-side guard for the one layout where
sharing regressed. Opening timing, rush spending, defense, and the cadence from
`ca5008a` are unchanged.

## Local verdict

Discovery panel (five opponents, 15 maps, both seats, seed 1): 128-22 versus
`ca5008a` at 127-23; one loss-to-win flip, no regressions.

Held-out Spar Econ seeds 2-5, 15 maps and both seats: 120-0 versus 116-4. The
same Midgard-B start flips from loss to win at every held-out seed. Fully
disjoint routing and a non-forage fifth-line capacity rule were separately
tested and rejected; both introduced combat regressions.

Promotion remains the farm's qualified expected-Elo decision against current
online opponents.
