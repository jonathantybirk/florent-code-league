# Secret evaluation maps

This directory holds a **held-out** map pool. It is gitignored (`.gitignore` keeps this
README and nothing else), so the maps exist only on the machine that runs the tournament.

## Do not look at these maps

They are for evaluation only. The point is to measure how bots behave on terrain nobody
tuned against, so:

- **Do not open, read, or render them.**
- **Do not use them for development**, benchmarking during iteration, or as generator input.
- **Do not commit them**, copy them into `maps/`, paste their contents into a chat or an
  issue, or share them with anyone — including agents you are driving.
- **Do not infer them from results.** Per-map numbers on the website deliberately show only
  a name and a size; the terrain is never published.

A bot that has seen these maps produces a meaningless number on them, and there is no way to
un-see them: the pool is spent.

## What they are used for

Held-out maps answer a question the official pool cannot: does a bot generalise, or has it
been fitted to the 22 maps everybody develops against? They are played in explicit
evaluation runs (`--maps secret`), never in the standing automation, and the website keeps
them behind a map-pool selector that is off by default.

Treat the aggregate numbers with care. This pool is very unlikely to be drawn from the same
distribution as the maps the Florent team will actually use, and Nash averaging is defined
relative to whatever map pool it is computed over — so an overall secret-pool rating is hard
to interpret. Per-map results are the interpretable part.

## Running an evaluation

From a checkout that has the harness, with this directory present:

    uv run python -m tournament plan --maps secret ...
    uv run python -m tournament local   # or: hpc submit

`--maps official_secret` plays both pools in one run.
