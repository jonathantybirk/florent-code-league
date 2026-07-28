# Quick Start

Source: https://game.code.florent.vc/docs/quick-start

## Getting Started

Get up and running in four steps.

### Prerequisites

- Python **3.12 or 3.13** (Python 3.14 is not supported)
- pip (bundled with Python)
- A registered account on the platform

### Step 1 — Install the CLI

```
pip install fcode
fcode --version
```

### Step 2 — Authenticate and scaffold a project

```
fcode login
fcode starter
```

The `fcode login` command launches a browser to connect your CLI with your platform account. The `fcode starter` command generates a project structure including an `fcode.toml` configuration file, a `maps/` directory, and a sample bot located at `bots/starter/main.py`.

### Step 3 — Run a local match

```
fcode run starter starter
```

The `fcode run` command executes matches between two bots—use the starter bot for both parameters to test a mirror match. Upon completion, a replay file named `replay.replay26` is generated in your current directory.

Watch the replay using the visualizer:

```
fcode watch replay.replay26
```

### Step 4 — Submit

```
fcode submit bots/starter
```

Your bot enters the queue for ladder matches. Navigate to the **Matches** page on the platform to monitor results.

---

## Next Steps

- [CLI reference](../cli/cli-reference.md) — comprehensive guide to all available commands
- [Game Rules — Overview](../game-rules/game-rules-overview.md) — learn about maps, units, and winning conditions
- [Controller API Reference](../api-reference/robot-api.md) — complete list of methods usable within `run()`
