# Game Rules — How Matches Work

Source: https://game.code.florent.vc/docs/game-rules-how-matches-work

## Series structure

Each ladder match is a best-of-five series. The two bots play five individual games; the team that wins three or more games wins the series. Series results (not individual game results) affect ladder ratings.

All five games in a series are played to completion regardless of the intermediate score — there are no early series terminations.

## Map selection

Maps for each series are drawn at random from the current competition map pool. Different games in the same series may use different maps. The map pool is announced at the start of the competition and may be updated between rounds.

The current map pool is listed on the platform.

## Remote infrastructure

Ladder matches and remote test matches (`fcode match test`) run on AWS Graviton3 instances. This is the same hardware used for all ranked games, so performance measured in remote tests is representative of what you will see on the ladder.

Local matches (`fcode run`) run on your own machine and may differ in speed — always profile CPU usage on remote tests before submitting.

## Replays

Every game produces a `.replay26` replay file. Replays for all your games are available on the Matches page. Open one directly from the platform with:

```
fcode watch --match <match-id>
```

or download the file and open it locally with `fcode watch <file>.replay26`.

Replays include the full round-by-round state of the map, unit HP, resource counts, and any indicator overlays (`ct.draw_indicator_line` / `ct.draw_indicator_dot`) your bot drew.

## Scheduling

The scheduler runs every 10 minutes. Your bot is automatically paired after submission — you do not need to initiate matches manually. The first match after a new submission may take up to 10 minutes to appear.
