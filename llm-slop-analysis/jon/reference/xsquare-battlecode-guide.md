# "A Guide to Battlecode" — Ivan Geffner (XSquare)

*Read 2026-08-05. Source: [battlecode-guide-xsquare.pdf](https://battlecode.org/assets/files/battlecode-guide-xsquare.pdf), 18 pages.*

New to our register — [../legacy/sources.md](../legacy/sources.md) catalogued
battlecode.org postmortems but not this guide.

## What it is, and how much of it applies

Author is a long-running MIT Battlecode competitor (since 2015, username XSquare) who also runs
AI Coliseum. The guide states up front that it **assumes the Java bytecode engine**. Florent is
Python with a 10 ms wall-clock CPU budget, no shared-memory restriction (we have a 16-slot global
store), and a much smaller game. So:

- **Section 6 (Bytecode) does not apply to us at all.** Static-vs-instance variable costs, switch
  vs if, loop unrolling, `for (int i = a.length; i-- > 0;)`, avoiding `ArrayList`/`HashSet`,
  free-cost Battlecode library methods, String abuse — all Java-engine-specific. Our analogous
  work is CPython-specific (attribute hoisting, big-int bitmasks, avoiding enum hashing), which
  is exactly what the Pantheon postmortem covers instead. Read that for perf, not this.
- **Sections 4–5 (structure and process) are the valuable part**, and they are engine-agnostic.

## The process advice worth acting on

This is mostly a discipline document, and several items are direct criticism of how we have been
working.

**Test each upgrade individually.** "Adding a lot of upgrades is often a consequence of being
greedy hoping for a big increase in winrate... It would have been much much better if we had
tested each upgrade individually." Our x/jon commit log is already one-change-per-commit with a
tracked oracle, and Lucas's vidar log is the same. We are doing this right.

**Build maps that isolate the thing you changed.** "When we only modify a part of our code, it is
not reflected that much on the overall winrate... we can design maps in which that upgrade is
especially important. Did we upgrade the micro? Let's make small maps, or maps with no obstacles
where all the resources are behind the base. Did we upgrade the resource gathering? Let's make
maps with more resources than average. Pathfinding? Mazes and complicated maps."

We have `tournament/custom_maps/` on x/tournament and a generated-map pool, but the pools are
general-purpose. Purpose-built discriminating maps per feature is a cheap missing tool, and
`fcode map-editor` exists.

**Don't overfit the current map pool.** "Overfitting for these maps may prove fatal since Teh Devs
release a complete new set of maps for each tournament." Directly relevant to `bots/jon/unfair/`,
which bundles `maps/*.map26` and fingerprints the live map against it. That whole line is a bet
that the pool does not change. Worth knowing the failure mode is total, not gradual.

**Don't be hasty to discard upgrades.** "If the winrate is close to 50% it might be just bad luck.
If I feel that the upgrade should be good and winrate is close to 50%, I keep it. It is also really
important to check for any possible bugs in the implementation, since if we miss one we might
discard a pretty good improvement and never go back to it." Compare Lucas's `vidar: the attacker
fix is a 10pp regression -- decompose it` → `revert the attacker fix` → `is the parked attacker
actually a feature?`. That sequence is exactly the recommended handling.

**Losing to a higher-ranked bot is information.** "If your bot consistently loses against
higher-ranked bots, it means that they are doing something better. It is your job to find what
they are doing and how! Analyzing games against them is the perfect opportunity to find new
features." This is an argument for the replay-watching plan, and specifically for watching the
Pantheon and Pivot losses.

**Copy shamelessly.** "All top teams in Battlecode copy from one another and, if they tell you
they're not, they're lying! As the competition advances, the meta changes, and the strategies that
prove to be better start spreading among all the top ranked bots."

**Simple beats complex.** "In Battlecode, it is usually the other way around. Simple strategies
usually perform better, especially when having to deal with coordination: if some global
functionality can be approximated by independent behavior from each robot, this is usually the way
to go." This is the same conclusion Pantheon reached with its memoryless architecture, arrived at
independently.

**Take time off to watch replays and think.** "Some of the days in which I make the most
improvement are those in which I take some time off, watch replays, and spend some time thinking
out of the box."

**Team shape.** His stated ideal is "one person coding and N−1 people watching replays, giving
insight, testing, and keeping track of the TO-DOs." He flags this as a personal opinion others
disagree with. Given four of us on four branches with four bot lines, it is at least worth
discussing.

**Test against your own old versions, on both sides.** "Do not forget to test on both sides (red
and blue) since your bot may have a larger winrate in one side" — rng seeds, fixed direction loop
order, turn order. We should confirm our tournament harness swaps sides; a side-biased result is
easy to mistake for a real gain.

**Don't blindly import an algorithm you don't understand.** His worked example: naive Bugnav plus
"go to the closest target of type T" produces an infinite loop, because the bot re-targets every
time it nears a new wall. The fix is to switch from target `T` to `T'` only when `d(R,T')` is less
than the *historical minimum* of `d(R,T)` since `T` was adopted — not merely less than the current
`d(R,T)`. Worth remembering if any of our bots ever re-targets on proximity.

**Use game constants, not magic numbers.** "From time to time, devs decide to change the specs to
balance the game, and if this happens while having magic constants, we have to replace them all."
We just lived through this: the Aug 4 patch changed five turret numbers at once, and every
turret-heavy conclusion in `llm-slop-analysis/` had to be flagged stale. Our engine exposes
`ct.get_gunner_cost()` and friends — bots should be reading those rather than hardcoding.

## Structure advice

An abstract `Robot` base holding the controller plus shared utility objects (pathfinding,
communication), extended per unit type, with three methods: `play()` for one round, `initTurn()`,
and `endTurn()` — where `endTurn()` is explicitly where you put "expensive computations that we
want them to perform during several turns with their spare bytecode."

That last point is the Battlecode-native version of Pantheon's resumable chokepoint job, and it
maps onto our 10 ms budget the same way.

He also argues for building reusable primitives early — "if a code is recyclable, it usually
performs the best too, because it probably encapsulates its functionality quite well" — and warns
against premature optimisation: don't bytecode-golf in the early days, it makes the code longer
and harder to edit "and those days [the final ones] are the most important."
