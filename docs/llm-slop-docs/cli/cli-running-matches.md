# Running Matches

Source: https://game.code.florent.vc/docs/cli-running-matches

## Local Matches

The `fcode run` command executes matches between two bots. You can run a mirror match with:

```
fcode run starter starter
```

To pit different bots against each other, use:

```
fcode run starter opponent
```

After completion, a replay file (`replay.replay26`) saves to your current directory, displaying the match result and final round in the terminal.

### Specifying a Map

Maps are optional third arguments, specified as paths or resolved from your `maps/` folder:

```
fcode run starter starter arena
```

If no map is specified, the first map in your folder is used. Add the `--map-random` flag to select a random map instead.

## Watching Replays

View replays in a browser-based visualizer using:

```
fcode watch replay.replay26
```

The visualizer displays turn-by-turn progression, including unit health bars, resource counters, and custom indicator overlays from drawing functions.

## Remote Test Matches

Test local bots against each other on the server before submission:

```
fcode match test starter opponent
```

Append map names for specific games, or omit them for 5 random maps. Testing runs on AWS Graviton3 hardware matching ranked ladder conditions. Results and replays appear on the Matches page.

**Rate limit:** 5 per 10 minutes per account, shared with unrated challenges.

## Unrated Challenges

Challenge another team's submission for scrimmage matches:

```
fcode match unrated <opponent-team-id>
```

Use `fcode team search` to locate team IDs. By default, matches use the opponent's latest ready submission. Specify maps with multiple `--map` flags (up to 5), or use 5 random maps by default.

**Rate limit:** Unrated challenges and test matches share 5 per 10 minutes per account.

## Tips

- Monitor CPU performance within `run()` using `ct.get_cpu_time_elapsed()` to stay within the 10 ms per-round CPU limit.
- Pass `--seed N` to `fcode run` to reproduce deterministic matches during development.
