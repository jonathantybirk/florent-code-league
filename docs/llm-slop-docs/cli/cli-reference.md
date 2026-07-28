# CLI Reference

Source: https://game.code.florent.vc/docs/cli-reference

## Global flags

| Flag | Description |
|---|---|
| `--version` | Print the installed fcode version and exit. |
| `--help` | Show help for the command or subcommand. |

## `fcode login`

Authenticate the CLI with your Florent Code League account.

```
fcode login
```

Opens a browser window for OAuth approval. Credentials are stored in `~/.fcode/credentials.json`.

## `fcode logout`

Remove stored credentials.

```
fcode logout
```

## `fcode starter`

Scaffold a new project in the current directory: an `fcode.toml`, a `.gitignore`, `bots/` and `maps/` folders, and a starter bot at `bots/starter/main.py`.

```
fcode starter
```

## `fcode run`

Run a local match between two bots.

```
fcode run BOT_A BOT_B [MAP] [--replay FILE] [--seed N] [--watch] [--map-random] [--tle MS]
```

| Argument / Flag | Default | Description |
|---|---|---|
| `BOT_A` | — | First bot — a path, or a name resolved against your `bots/` folder. |
| `BOT_B` | — | Second bot. Pass the same value as `BOT_A` for a mirror match. |
| `MAP` | first map | Optional map — a path or a name resolved against your `maps/` folder. Omitted uses the first map in `maps/`. |
| `--replay FILE` | `replay.replay26` | Path for the output replay file (default from `fcode.toml`). |
| `--seed N` | from config | Deterministic match seed. |
| `--watch` | off | Open the visualiser automatically when the match finishes. |
| `--map-random` | off | Pick a random map from `maps/` when no map is given. |
| `--tle MS` | 0 (disabled) | Enforce a per-turn CPU time limit locally, in milliseconds. The ladder server always enforces 10 ms; local runs don't unless you pass this. |

## `fcode watch`

Open a replay in the browser-based visualiser.

```
fcode watch REPLAY
fcode watch --match MATCH_ID [--game N]
```

| Argument / Flag | Description |
|---|---|
| `REPLAY` | Path to a local `.replay26` replay file. |
| `--match MATCH_ID` | Open a match's replay from the platform instead of a local file. |
| `--game N` | Game number within the match (for `--match`). |

## `fcode map-editor`

Open the map editor to create or edit `.map26` files.

```
fcode map-editor
fcode map-editor --platform
```

| Flag | Description |
|---|---|
| `--platform` | Open the map editor on the platform in your browser instead of running it locally. |

## `fcode submit`

Submit a bot to the ladder. Shorthand for `fcode submission upload`.

```
fcode submit PATH [--name NAME]
```

| Argument / Flag | Description |
|---|---|
| `PATH` | A bot directory (containing `main.py`), a `.py` file, or a `.zip` archive. |
| `--name, -n NAME` | Optional name for this submission. |

## `fcode submission`

Manage bot submissions: upload, list, activate, rename, and download.

### `submission upload`

```
fcode submission upload PATH [--name NAME]
```

| Argument / Flag | Description |
|---|---|
| `PATH` | A bot directory (containing `main.py`), a `.py` file, or a `.zip` archive. |
| `--name, -n NAME` | Optional name for this submission. |

Identical to `fcode submit`.

### `submission list`

```
fcode submission list
```

Lists all of your team's submissions with version, name, status, and which one is active.

### `submission activate`

```
fcode submission activate VERSION
```

| Argument | Description |
|---|---|
| `VERSION` | Version number of the submission to make active on the ladder. |

### `submission rename`

```
fcode submission rename VERSION NAME
```

| Argument | Description |
|---|---|
| `VERSION` | Version number of the submission to rename. |
| `NAME` | New name for the submission. |

### `submission download`

```
fcode submission download [VERSION] [--output FILE]
```

| Argument / Flag | Default | Description |
|---|---|---|
| `VERSION` | active/ready submission | Version number to download. Omitted downloads your currently active (or most recent ready) submission. |
| `--output, -o FILE` | `v<VERSION>.zip` | Output file path for the downloaded archive. |

## `fcode match`

View, list, and manage matches. Running `fcode match MATCH_ID` without naming a subcommand is shorthand for `fcode match info MATCH_ID`.

### `match info`

```
fcode match info MATCH_ID
```

Shows detailed match info: status, teams, score, rating changes, and a per-game breakdown.

### `match list`

```
fcode match list [--type ladder|unrated] [--team TEAM] [--mine] [--limit N] [--cursor CURSOR]
```

| Flag | Default | Description |
|---|---|---|
| `--type ladder\|unrated` | all types | Filter by match type. |
| `--team TEAM` | — | Filter by team name or team ID. |
| `--mine` | off | Show only your own team's matches. |
| `--limit N` | 20 | Number of matches to show (max 100). |
| `--cursor CURSOR` | — | Pagination cursor from a previous page. |

### `match unrated`

```
fcode match unrated OPPONENT_ID [--match SOURCE_MATCH_ID] [--map MAP_NAME]
```

| Argument / Flag | Description |
|---|---|
| `OPPONENT_ID` | Team ID to request an unrated match against. |
| `--match SOURCE_MATCH_ID` | Use the opponent's submission from this specific match instead of their currently active one. |
| `--map MAP_NAME` | Map to play (repeatable, up to 5). Omitted picks random maps. |

Requests a friendly, non-rated match against another team using your currently active submission.

### `match test`

Run a remote test match between two local bots on the server, with time-limit enforcement.

```
fcode match test BOT_A BOT_B [MAPS...]
```

| Argument | Description |
|---|---|
| `BOT_A, BOT_B` | Each is a directory (containing `main.py`), a `.py` file, or a `.zip`. |
| `MAPS...` | Optional map names, one per game. Omitted runs 5 random maps. |

**Rate limit:** 5 matches per 10 minutes per account.

### `match replay`

```
fcode match replay MATCH_ID [--game N] [--output FILE]
```

| Argument / Flag | Default | Description |
|---|---|---|
| `MATCH_ID` | — | Match to download replays from. |
| `--game, -g N` | all games | Game number (1-5) to download. Omitted downloads all games in the match. |
| `--output, -o FILE` | `<matchId>_game_<N>.replay26` | Output file path. |

### `match watch`

```
fcode match watch MATCH_ID [--game N]
```

| Argument / Flag | Description |
|---|---|
| `MATCH_ID` | Match to open in the browser-based visualiser. |
| `--game, -g N` | Game number within the match. |

Shorthand for `fcode watch --match MATCH_ID [--game N]`.

### `match tests`

```
fcode match tests [--limit N]
```

| Flag | Default | Description |
|---|---|---|
| `--limit N` | 20 | Number of test runs to show. |

Lists your recent `fcode match test` runs.

## `fcode team`

Search teams and view team profiles.

### `team search`

```
fcode team search QUERY
```

| Argument | Description |
|---|---|
| `QUERY` | Search text matched against team names. |

### `team info`

```
fcode team info TEAM_ID
```

| Argument | Description |
|---|---|
| `TEAM_ID` | Team to show — name, rating, match count, and members. |

## `fcode ladder`

Show the ladder rankings.

```
fcode ladder [--limit N] [--around]
```

| Flag | Default | Description |
|---|---|---|
| `--limit N` | 20 | Number of teams to show. |
| `--around` | off | Center the list on your own team's rank (±5), instead of starting from the top. |

## `fcode status`

Show your current ladder rating, rank, active submission, and recent match record.

```
fcode status
```
