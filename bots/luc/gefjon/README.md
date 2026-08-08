# Gefjon — a second miner, added rather than reallocated

`steward_relent` plus one structural change: the opening runs **two** economy
Builders instead of one, without giving up the attacker or the mender.

## Why

Every opponent that beats us on the live ladder out-mines us roughly two to one,
and the gap is not subtle. From the Besvikomat sweep of 2026-08-08 — Harvesters
built, us against them: 4–10 on nordkap over 624 rounds, 9–20 on eider, 5–7 on
antler, 2–17 on jackpot. Locally, on generated maps against vidar, this lineage
averages **1.33 Harvesters a game**.

`builder.py`'s `_pick` already records the shape and rules out the obvious
cause: "live Harvesters ran 1.80 at round 50 down to 1.42 at round 500 in games
this bot won, and 1.69 down to 0.24 in games it lost … NETWORK_CAP_EARLY 6 was
measured inert because permission was never the binding constraint." Permission
allows eight Harvesters. This bot builds two.

Instrumenting the economy Builder on two long generated games says what does
bind, and it is not permission:

- **r05** (747 rounds, lost): the economy Builder sits in `phase=goto` with
  `alarm=1` from round 25 to round 725. `seen` never leaves 82 — it does not
  move for seven hundred rounds. `load=0`; the team finishes with no conveyor
  network and no Harvesters at all. `core.py` raises the alarm when the Core
  loses HP and `builder.py:348` conscripts **Builder 0** as a mender for as long
  as it is up, and Builder 0 is the *only* economy Builder in every doctrine.
- **r04** (1000 rounds, won on the titanium tiebreak): `phase=scout`,
  `load=2` against `cap=8`, one or two known unclaimed deposits — and nothing
  happens between round 225 and round 900. Spare capacity, a free deposit, and
  675 idle rounds.

Both failures are the same single point of failure. One economy Builder means
any sustained pressure on the Core, or any one Builder getting stuck, takes the
entire economy to zero for the rest of the game.

## What changed

`_ROLES` goes from `(1, 1)` to `(2, 1)` in all three doctrines, and
`LAUNCHER_BUILDER_INDEX` from 2 to 3.

The second constant is the load-bearing one. With `PAD_FIRST_ORDER` off, indices
below `economy_builders` are miners, `ring_slot = index - LAUNCHER_BUILDER_INDEX`
picks the ring Builder, and anything else that is not the ring is the attacker.
At 2 that yields `0=miner, 1=attacker, 2=ring`. Raising `economy_builders` alone
would have produced `0=miner, 1=miner, 2=ring` and **no attacker at all** —
which is the `(2, 0)` reallocation `doctrine.py` already measured losing 2–12 to
plain RUSH. At 3 it yields `0=miner, 1=miner, 2=attacker, 3=ring`: a miner
*added* to the opening, not taken from anyone.

`MAX_OPENING_BUILDERS` follows to 4, so the opening pays for one extra Builder —
30 Ti and a permanent +20% on later prices. That is the real cost and the reason
this is a measurement rather than an argument.

It also fixes the r05 failure directly: the conscription reads
`p.builder_index == 0`, so with two miners the second keeps mining while the
first mends.

## Numbers

Generated maps (guaranteed atlas misses, and where the long games are), each
build vs vidar over 12 maps × both seats:

| build | wins /24 | mean rounds | Harvesters built | alive @150 / @300 / @500 |
|---|---|---|---|---|
| `steward_hardened_reinforced` | 5 | 374 | 1.33 | 1.00 / 0.88 / 1.14 |
| `steward_relent` | 5 | 372 | 1.33 | 1.00 / 1.11 / 1.14 |
| **`gefjon`** | **10** | 297 | **1.75** | **1.71** / 1.33 / 1.25 |

Twice the wins, and the economy is visibly larger from early on. 24 games is
about two standard deviations on a win count, so this is suggestive rather than
settled — the official-pool panel is the check that matters, and it is in the
same file as the rest of the session's numbers, `bots/luc/LUC_LOOP_LOG.md`.

## CPU: the check that nearly did not happen

A second miner tripled worst-case Builder CPU and put it **over** the platform's
10 ms per-turn kill threshold — 11,237 us on aurora with nine turns over,
against `steward_relent`'s 3,657 and the flagship's 2,846. The first timing run
appeared clean only because `tail` had cut aurora off the table.

The cost is `_pick`, which runs a `_route` *and* a `_distance` — two searches —
per candidate deposit, every round, per miner. `PICK_CANDIDATE_LIMIT = 4` bounds
it by work rather than by a clock, and the list is sorted nearest-first, so what
is dropped is deposits a nearer routable candidate would have beaten anyway.

| candidate limit | aurora worst turn |
|---|---|
| unbounded | 11,237 us |
| 6 | 8,233 us |
| **4** | **2,426 us** |
| 2 | 2,853 us |

At 4 the worst Builder turn is 2,426 us with p99 1,482 — *better* than either
parent, because the bound helps whatever the miner count. It costs nothing in
play: on generated maps only about four deposits are ever known, so the limit is
inert there and the 24-game result is unchanged. It bites only on ore-rich pool
maps, which is where the spike was.

Deterministic: three identical runs agree to the last unit of titanium.

## Status

Under test.
