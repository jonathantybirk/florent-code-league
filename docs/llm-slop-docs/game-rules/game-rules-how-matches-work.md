# Game Rules — How Matches Work

Source: https://game.code.florent.vc/docs/game-rules-how-matches-work

## Series Structure

Each ladder match is a **best-of-five series**. The competing bots play five games total, with the winner being whichever team secures three or more victories. All five games in a series are played to completion regardless of the intermediate score — there are no early series terminations. Series outcomes determine ladder ratings, not individual game results.

## Map Selection

The platform selects maps randomly from an active competition pool. Different games in the same series may use different maps. The map pool gets announced when competitions begin and may be adjusted between rounds.

## Remote Infrastructure

Matches and remote test matches run on AWS Graviton3 instances, which represents the standard hardware for ranked games. Local matches use your own machine and may show different performance characteristics, so the guidance recommends profiling CPU usage on remote tests before submitting.

## Replays

Every game generates a `.replay26` file. Players can access replays through the Matches page, either by running `fcode watch --match <match-id>` or downloading and opening files locally with `fcode watch <file>.replay26`. These replays contain complete round-by-round map state, unit health, resource data, and any indicator overlays the bot created.

## Scheduling

The scheduler operates every 10 minutes, automatically pairing your bot after submission without manual match initiation. New submissions may take up to 10 minutes before their first match appears.
