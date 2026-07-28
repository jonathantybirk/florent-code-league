# Submitting

Source: https://game.code.florent.vc/docs/cli-submitting

## Submit your bot

```
fcode submit bot.py
```

Your submission is uploaded, validated, and entered into the ladder queue. The system provides a submission ID upon successful upload.

Submissions can occur unlimited times, with each new submission replacing the current ladder entry. Past submissions are manageable through commands like `fcode submission list`, `fcode submission activate VERSION`, `fcode submission rename VERSION NAME`, and `fcode submission download VERSION`.

## What happens after submission

1. The platform automatically pairs your bot against other submitted bots.
2. Each pairing runs as a best-of-five series on a randomly selected set of maps.
3. Leaderboard results appear within minutes of series completion.

## Viewing results

The Matches page displays:

- Match history with round-by-round outcomes
- Replays for each game in a series (downloadable with `fcode watch`)
- Win/loss records and current ladder rating

## Submitting a multi-file bot

For bots spanning multiple files, create a zip archive:

```
zip bot.zip bot.py utils.py strategy.py
fcode submit bot.zip
```

The engine runs `bot.py` as the entry point. All files in the archive become available for import at runtime.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ValidationError: entry point not found` | No `bot.py` in the archive | Ensure the root of the zip contains `bot.py` |
| `SyntaxError` on submission | Python version mismatch | Verify you are using Python 3.12 or 3.13 |
| Bot disqualified mid-match | CPU time exceeded 10 ms | Profile with `ct.get_cpu_time_elapsed()` and optimise |
