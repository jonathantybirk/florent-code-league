# Submitting

Source: https://game.code.florent.vc/docs/cli-submitting

## Submit your bot

```
fcode submit bot.py
```

Your submission is uploaded, validated, and entered into the ladder queue. The CLI prints a submission ID when the upload succeeds.

You can submit at any time. Each submission replaces your current ladder entry — there is no limit on the number of submissions.

Manage past submissions with `fcode submission list`, `fcode submission activate VERSION`, `fcode submission rename VERSION NAME`, and `fcode submission download VERSION` — see the [CLI reference](cli-reference.md) for details.

## What happens after submission

- The platform pairs your bot against other submitted bots automatically.
- Each pairing runs as a best-of-five series on a randomly selected set of maps.
- Results are reflected on the leaderboard within a few minutes of each series completing.

## Viewing results

Open the Matches page on the platform to see:

- Match history with round-by-round outcomes
- Replays for each game in a series (downloadable with `fcode watch`)
- Win/loss records and current ladder rating

## Submitting a multi-file bot

If your bot spans multiple files, collect them into a zip archive first:

```
zip bot.zip bot.py utils.py strategy.py
fcode submit bot.zip
```

The engine runs `bot.py` as the entry point. All files in the archive are available to import at runtime.

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ValidationError: entry point not found` | No `bot.py` in the archive | Ensure the root of the zip contains `bot.py` |
| `SyntaxError` on submission | Python version mismatch | Verify you are using Python 3.12 or 3.13 |
| Bot disqualified mid-match | CPU time exceeded 10 ms | Profile with `ct.get_cpu_time_elapsed()` and optimise |
