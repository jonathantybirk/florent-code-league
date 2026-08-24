# oarena — third-party Florent Code League web UI and local league runner

*Read 2026-08-05. Source: <https://github.com/frkns/oarena> (author: frkns).
Screenshots in the repo are dated 2026-08-03, so it is current with the 2.3.x engine.*

New to our register. Not a Battlecode artifact — it targets **our competition specifically**.

## What it is

README in full:

> A better Florent Ventures Code Web UI and visualiser. Supports local testing too.
> Updates not planned.
>
> Screenshots: 2D replay viewer / Ladder and rating history / Map browser
>
> Install: `./install.sh` and run `oarena serve`

Python (`pyproject.toml`) plus a JS frontend (`package.json`), ~30 test files, so it is a real
project rather than a sketch. "Updates not planned" means treat it as a frozen tool: usable now,
but it will rot when the engine moves.

## What it actually does, from the source

- `cli.py` — "the primary interface to a local fcode league": a ladder view with **shared-scale
  sigma bands**, a live arena view, and a **coloured head-to-head crosstable**. Everything
  machine-readable is also available under `--json`.
- `ratings.py` — ratings with confidence intervals (`CI`, `CI_PERCENT`), not bare Elo.
- `league.py`, `pool.py`, `matchmaking.py`, `runner.py` — local league: syncs bots on disk into a
  store, schedules matches, runs them.
- `fcode_platform.py` + `platform_rpc.py` — a **read-only client for the live platform**. It can
  pull ladder data and **download replay bytes** (the RPC transport has a 64 MB replay body limit
  and fetches via signed URL then object storage). There is a sidecar mode
  (`OARENA_PLATFORM_SOCKET`) so the platform client can run outside the game-worker sandbox.
- A bundled 2D replay visualiser (`test_square_visualiser_bundle.py`, `..._shim.py`).

## Why it matters to us

**The replay viewer is the immediate win.** `fcode watch` opens one replay at a time; oarena gives
a browsable 2D viewer plus ladder/rating history in one place. For the plan of "watch the online
replays and find where our frontier bots fall short," this is the better instrument.

**It overlaps heavily with what we already built.** x/tournament has `tournament/` with its own
harness, ratings, leaderboard-v2 cutover, systemd evaluator timer, and ~2,900 lines of tests;
x/luc has `tools/pantheon_analysis/` with a hand-rolled `.replay26` protobuf decoder. oarena
independently implements: local league + matchmaking, ratings with CIs, head-to-head crosstables,
platform replay download, and replay visualisation.

So the question for the team is **build vs adopt vs cherry-pick**, and it is worth asking before
more effort goes into ours:

- Our harness is tuned to how we run experiments (EXPERIMENT markers, opt-in ladder evidence,
  held-out map pools, generated maps). oarena will not have that.
- But its **platform replay download** and **2D viewer** are things we do not have, and are exactly
  what the current plan needs. Those two pieces are the cherry-pick candidates even if we keep
  our own harness.
- Its `.replay26` handling is a second, independent implementation to check Lucas's decoder
  against — useful for validating `tools/pantheon_analysis/decode.py` and `schema.json`.

**Caveat before running it.** It is third-party code that authenticates against our platform
account and, in the default (non-sidecar) mode, runs in the same process that executes bots. Read
`fcode_platform.py` and `install.sh` before pointing it at our credentials. The sidecar mode exists
precisely because the author considered this; "hardened installations" should use it.

Also note it is a *read-only* platform client by design — it does not submit, so there is no risk
of it uploading a bot.
