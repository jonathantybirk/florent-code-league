# Running Matches

Source: https://game.code.florent.vc/docs/cli-running-matches

## Local matches

`fcode run` takes two bots. Run the starter against itself for a mirror match:

```
fcode run starter starter
```

Run two different bots (each is a path, or a name resolved against your `bots/` folder):

```
fcode run starter opponent
```

When the match finishes, a replay file (`replay.replay26`) is written to the current directory. The match result and final round are printed to the terminal.

### Specifying a map

The map is an optional third argument — a path, or a name resolved against your `maps/` folder:

```
fcode run starter starter arena
```

Omitting the map uses the first map in your `maps/` folder. Add `--map-random` to pick a random one instead.

### Watching replays

Open a replay in the browser-based visualiser:

```
fcode watch replay.replay26
```

The visualiser shows the full match turn by turn, with unit health bars, resource counters, and indicator overlays drawn by `ct.draw_indicator_line()` / `ct.draw_indicator_dot()`.

## Remote test matches

Test two local bots against each other on the server before submitting:

```
fcode match test starter opponent
```

You can append one or more map names (one per game); omit them for 5 random maps. Remote test matches run on the same AWS Graviton3 hardware as ranked ladder matches, giving you an accurate picture of performance. Results, including replays, are available on the Matches page.

**Rate limit:** 5 per 10 minutes per account, shared with unrated challenges (see below).

## Unrated challenges

Challenge another team's submission directly on the server — a scrimmage that doesn't affect either team's ladder rating:

```
fcode match unrated <opponent-team-id>
```

Use `fcode team search` to find team IDs. By default your submission plays against the opponent's latest ready submission; pass `--match <match-id>` to instead play against whichever submission they had in a specific past match. Add one or more `--map` flags to choose maps (up to 5); omit for 5 random maps:

```
fcode match unrated <opponent-team-id> --map arena --map fortress
```

Results, including replays, are available on the Matches page, same as any other match.

**Rate limit:** 5 per 10 minutes per account, shared with remote test matches — each unrated challenge and each `fcode match test` run counts against the same 10-minute bucket.

## Tips

- Use `ct.get_cpu_time_elapsed()` inside `run()` to detect if your bot is approaching the 10 ms per-round CPU limit.
- Pass `--seed N` to `fcode run` to reproduce the exact same match deterministically while you iterate.
