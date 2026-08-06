# ladderfarm

Turns the platform's 5-unrated-matches-per-10-minutes allowance into a standing
data feed: roughly every 12 minutes it plays one bot against five ladder teams,
records every game, and keeps a running Elo estimate per bot.

## Working on it from another machine

The farm deploys from the `x/ladderfarm` branch. Clone it, change it, push it:

```bash
git clone --single-branch -b x/ladderfarm https://github.com/jonathantybirk/florent-code-league.git
python3 farm.py --once --dry-run     # works anywhere; fires nothing
git push origin x/ladderfarm
```

`sync.sh` runs immediately before every round, so a push is live on the **next
round** (within ~11 minutes), and again on a 5-minute timer in between. It
exports the pushed commit to a scratch directory and runs a full dry run first;
only a clean exit is deployed, otherwise the running code stays and the failure
is logged. `state.json`, `data/` and `exports/` are gitignored and survive the
hard reset. `sync.sh` itself is deliberately untracked, so a bad push cannot
break the thing that deploys the fix.

## Giving the rate limit back to a human

The account may run **5 unrated matches per 10 minutes, shared by everyone**, and
the farm spends about 25 of the ~30 an hour. Anyone who wants to test their own
bot needs that budget back, and can take it by pushing `config.json`:

```json
{ "yield_until": "2026-08-06T18:30:00Z" }   // stops firing until then, resumes itself
{ "enabled": false }                        // stops firing until someone re-enables
```

Prefer `yield_until`: it cannot be forgotten. Either way the farm keeps collecting
results and deciding the live bot; it just stops spending slots.

## Three timers

| unit | when | what |
|---|---|---|
| `ladderfarm.timer` | `:05 :16 :27 :38 :49` | pulls, then fires a round of five |
| `ladderfarm-decide.timer` | every `:X2:30` | collects, re-estimates, promotes |
| `ladderfarm-sync.timer` | every 5 min | deploys pushed changes if they pass |

The ladder scheduler queues rated matches at ~`:X2:43`. Rounds keep two minutes
clear either side of it, which confines them to cycle offsets 4:43–10:00 — that
is, minutes ending 5–9. `:05 :16 :27 :38 :49` is the schedule that satisfies this
while staying 11 minutes apart (16 on the wrap, averaging 12) — comfortably above
the 10 minutes the rate limit needs between rounds of five.

The decision pass deliberately runs *inside* that forbidden window, 13 seconds
before the tick, so a promotion is already live for the rated series the tick
queues. That is safe only because this pass can activate nothing but a flagship;
it never puts a bot under test on the ladder. It also re-asserts the flagship if
a hand-run test or another agent left something else active.

## Kill switch

```bash
touch /home/Ucals/projects/florent-code-league-ci/tournament/ladderfarm/PAUSE  # skip rounds, keep the timer
systemctl --user disable --now ladderfarm.timer                                # stop entirely
```

## What one round does

1. **Collect** — polls the matches fired last round, appends them to
   `data/series.csv` (one row per five-game series) and `data/games.csv` (one row
   per game: map, seed, win condition, turn count).
2. **Nominate** — reads the newest finished CI run's `ratings.csv` and takes every
   bot in the top 3 by mElo, the top 3 by Nash average, or anywhere in the Nash
   core (`nash_prob > 0`). New arrivals are extracted straight out of git
   (`git archive`, no working tree touched) and uploaded once.
3. **Choose a bot** — UCB1 over online game win rate, `mean + 0.6 * sqrt(2 ln N / n)`.
   Anything never tested online goes first; after that the bonus keeps a promising
   newcomer in rotation without abandoning the incumbent.
4. **Choose five opponents** — 2 from the ladder top 5, 2 from within ±5 ranks of
   us, 1 from the top 25. Inside each band the least-sampled team is picked first,
   so coverage evens out instead of hammering whoever is #1.
5. **Fire** — activates the test bot, sends five `fcode match unrated` requests,
   restores the flagship. `match unrated` snapshots the active submission at
   request time, so the swap window is ~2 seconds.
6. **Promote** — among **qualified** bots (≥7 of the 10 opponents closest to us in
   rating faced, ≥25 games), the highest expected Elo goes live.

Opponents keep upgrading, and an upgrade almost always makes them stronger. A bot
scored on a lopsided slice of the field is therefore measured against a different
— usually easier — field than its rivals were, and the two Elo numbers are not
comparable. Facing most of our own neighbourhood is what makes them commensurable;
the full ladder is not worth waiting for, because rated pairings come from nearby
teams anyway. `--status` shows each bot's `closest` count.

**When the flagship itself falls below 7/10** — it never qualified, or the ladder
moved and its neighbourhood is now teams it has not faced — it *stays live* and
becomes the bot under test, spending its round on the close opponents it has not
met so it re-qualifies fast. It is still the best bot we can defend; there is no
reason to put something less-tested on the rated ladder. The exception is a
qualified challenger whose Elo already beats it, which is a normal promotion.

## Why it is safe to leave running

- **The rated ladder never sees a test bot.** The scheduler queues rated matches
  ~2:43 past every ten-minute mark; rounds run at :05, :25, :45 and the code
  refuses to touch the active submission anywhere inside `163 ± (60, 90)` seconds.
  The flagship is restored in a `finally`, verified by re-reading `fcode status`,
  and retried four times; failure is logged at ERROR.
- **It yields to other agents.** It uses at most 15 of the ~30 hourly unrated
  slots, and a `RateLimited` response ends the round quietly rather than retrying.
- **Promotion is conservative.** Five-game series swing hard — on 2026-08-05 the
  same build went 5-0 and 2-3 against Pareto-ion twenty minutes apart — so a
  challenger must clear the incumbent by more than its own standard error.

## Commands

```bash
python3 farm.py --test-next NAME@COMMIT --rounds 2   # jump the queue with a specific build
python3 farm.py --once      # fire one round (what ladderfarm.timer runs)
python3 farm.py --decide    # collect + re-estimate + promote (ladderfarm-decide.timer)
python3 farm.py --collect   # harvest finished matches only, fire nothing
python3 farm.py --status    # arms, Elo estimates, opponent coverage
python3 farm.py --once --dry-run
journalctl --user -u ladderfarm -u ladderfarm-decide -n 50   # or: tail farm.log
```

## Files

| path | what |
|---|---|
| `farm.py` | round logic, collection, promotion |
| `arms.py` | candidate nomination, git export, Elo MLE, UCB |
| `fcodecli.py` | `fcode` CLI wrappers |
| `state.json` | flagship, upload registry, pending matches, opponent counts |
| `data/series.csv`, `data/games.csv` | the harvested data |
| `exports/` | bot directories extracted from git for upload |

## Where the numbers come from

**Decisions read the live feed**, not this farm's own CSVs:
`~/projects/portfolio/public/botrankings/data/live.json`, regenerated every couple
of minutes by `tournament.live_feed` (the `botrankings-live` timer).

That matters more than it sounds. The feed groups builds by **code hash**, so the
same code uploaded as two versions counts once, and it counts **every** match a
build has played — including the rated ladder games the flagship racks up while
it is live. The farm's own log sees neither. On 2026-08-06 the live build had 130
games and had faced all 10 of the closest opponents in the feed, against 25 games
and 5 opponents in `data/series.csv`; judging it on the latter was simply wrong.

So:

* **qualification** counts opponents faced according to the feed;
* **expected Elo** is the feed's fitted estimate (`estimate.elo`, with
  `elo_lo`/`elo_hi` reported as ±), and a build the feed withholds an estimate for
  (`few-current-games`, `pre-patch-only`, `no-matches`) cannot be promoted;
* **UCB exploration** still runs off the farm's own log, because that is the
  right thing for deciding what *this* farm has under-sampled.

`data/series.csv` and `data/games.csv` remain the point of the exercise — per-game
map, seed, win condition and turn count, which the feed does not keep.

## Seeding note

`state.json` was seeded with `steward_hardened_reinforced@c04e46e -> v28`, which
was already uploaded by hand, so the farm reuses that submission instead of
uploading the same code again. Results gathered before the farm existed are
**not** backfilled into `data/`; the estimates start from the farm's own matches.
