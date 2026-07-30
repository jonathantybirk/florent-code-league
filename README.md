# Florent Code League 2026

Team repo for the [Florent Code League 2026](https://code.florent.vc/) — write a
Python `Player` class that autonomously harvests titanium, builds logistics, and
fights on a live Nordic leaderboard.

Official tutorials: <https://game.code.florent.vc/tutorials>

## Setup

The game package supports CPython 3.12 and 3.13. This project pins Python
3.13.14, the newest supported release.

```sh
uv sync
uv run fcode --help
```

## Play

Bot paths resolve under `bots/`, and they are nested, so pass the full path:

```sh
uv run fcode run jon/fair/jonbot common/starter duel
uv run fcode watch replay.replay26
```

Omit the map to use the alphabetically first one in `maps/` (atoll); add
`--map-random` to pick one at random, or `--tle 10` to enforce the server's
per-turn CPU limit locally.

## Layout

```
AGENTS.md             the one rule for coding agents
bots/
  common/             starter, donothingbot, shell (copy to start a new bot)
  jon/ lucas/ vaek/ elias/
docs/                 original sources ONLY — no summaries, no LLM output
llm-slop-analysis/    LLM-authored notes, one folder per person
maps/                 the 15 competition maps
```

Everyone owns their folder under `bots/` and organises it however they like;
`jon/` happens to split `fair/` (plays from in-game observation only) from
`unfair/` (bundles the published map pool and fingerprints the live map against
it to recover unscouted terrain). Both are legal, but they are not comparable —
benchmark like against like.

If a bot does bundle `maps/*.map26`, those copies are load-bearing: it reads
them at runtime and `fcode submission` zips only the bot directory, so do not
de-duplicate them.

**LLM output never mixes with sources.** Anything a model wrote lives in
`llm-slop-analysis/<person>/`; `docs/` is verbatim official material only. We
all drive LLMs continuously, and without this split one model's guess quietly
becomes the next model's "documentation".

## Branches

Everyone works on their own branch; `main` is where we meet, so keep it
organised — no scratch bots, no dead iterations, no generated artifacts.

Work on your own branch and publish by merging it into `main`, dropping the
scaffolding on the way out:

```sh
git checkout main && git merge x/<you> --no-ff --no-commit
git rm -rq --cached analysis scripts        # plus anything else branch-only
git commit
```

Merge first, then `git rm --cached`: those paths are already tracked on your
branch, so `.gitignore` alone will not keep them off `main`. If a later merge
reports `modify/delete` on one of them, that is the same thing happening again —
resolve it with `git rm`.
