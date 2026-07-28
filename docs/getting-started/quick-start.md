# Quick Start

Source: https://game.code.florent.vc/docs/quick-start

Get up and running in four steps.

## Prerequisites

- Python 3.12 or 3.13 (Python 3.14 is not supported)
- pip (bundled with Python)
- A registered account on the platform

## Step 1 — Install the CLI

```
pip install fcode
fcode --version
```

## Step 2 — Authenticate and scaffold a project

```
fcode login
fcode starter
```

`fcode login` opens a browser window to link the CLI to your platform account. `fcode starter` scaffolds a project in the current directory: an `fcode.toml`, a `maps/` folder, and a starter bot at `bots/starter/main.py`.

## Step 3 — Run a local match

```
fcode run starter starter
```

`fcode run` takes two bots — pass the starter twice for a mirror match. A replay file `replay.replay26` is written to the current directory when the match finishes.

Watch the replay in the visualiser:

```
fcode watch replay.replay26
```

## Step 4 — Submit

```
fcode submit bots/starter
```

Your bot is queued for ladder matches. Check the Matches page on the platform to track results.

**Next steps:**

- [CLI reference](../cli/cli-reference.md) — full guide to each command
- [Game Rules — Overview](../game-rules/game-rules-overview.md) — understand the map, units, and win conditions
- [Controller API Reference](../api-reference/robot-api.md) — every method available inside `run()`
