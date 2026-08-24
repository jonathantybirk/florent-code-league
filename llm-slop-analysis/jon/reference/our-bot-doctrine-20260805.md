# Where our bots come from — the two private ladders and what the top bots actually do

Written 2026-08-05. Sources: `tournament/runs-v1/secret-eval-1` (pre-patch) and
`tournament/runs/v2-full-20260804` (post-patch) on `x/tournament`; bot READMEs and
source on `x/luc`, `elias_dev`, `x/jon`.

## 1. The two private ladders, side by side

### Pre-patch — `secret-eval-1`, fcode 2.3.3
92 bots, 31 maps (official + secret), **85,652 matches**. Ratings recomputed with the
harness's own `rate` command.

| # | bot | win% | mElo |
|---|---|---|---|
| 1–6 | `v233_h`, `vanguard@9713344`, `vanguard_1e88ae8`, `vanguard@da3fd8a`, `vanguard@ba943b9`, `vanguard@bb03f14` | **76.6%** | 294 |
| 7 | `v233_g@9713344` | 76.0% | 284 |
| 8 | `vanguard@9932bec` | 75.4% | 281 |
| 9–10 | `tempest_reinforcements@51ad530` / `@025dd51` | 74.9% | 269 |

Six bots tied at *identical* rating to four decimal places — that is the redundancy
problem in its purest form.

**Nash core (10 agents):** `vanguard@9932bec` (0.158), `tempest_reinforcements@edf93ad`
(0.138), `@51ad530` / `@025dd51` (0.071 each), `vanguard@26e6792` / `@c407e79` /
`@259c188` / `v233_i` (0.067 each), `mistral_fast` (0.010), and —

**`autistimusprime@ecd4d24` (0.282), ranked 32nd by mElo.** Elias's bot carried the
*largest* Nash mass in the entire pre-patch field while sitting 31 places below the top on
raw win rate. It is the most strategically distinct thing we have ever built, and the
headline ranking buried it.

### Post-patch — `v2-full-20260804`, fcode 2.3.4
81 bots, 31 maps, **202,581 matches**.

| # | bot | win% | mElo | Nash |
|---|---|---|---|---|
| 1 | `prospect_rushonly@bf9b3e3` | 72.2% | 196 | **0.000** |
| 2 | `prospect@bf9b3e3` | 71.6% | 189 | **0.000** |
| 3 | `janus@8a1e7a1` | 70.4% | 176 | **0.000** |
| 4 | `odin@38e1456` | 71.2% | 171 | 0.085 |
| 6 | `steward@e55aab5` | 69.7% | 162 | **0.523** |
| 9 | `vigil@e267eeb` | 67.6% | 154 | 0.199 |
| 10 / 12 | `heimdall@daf0de0` / `@840a180` | 68.8% / 68.3% | 153 / 151 | 0.099 / 0.094 |

**The turnover between the two ladders is near-total.** The `vanguard` / `tempest` /
`undertow` lineage that owned every top slot pre-patch does not appear in the post-patch top
twelve at all. Lucas's `warden` lineage took the whole board. The Nash core shrank from ten
agents to five.

## 2. The lineage map

Three families, and almost everything we own descends from one of them.

```
jon      tempest ─┬─ tempest_reinforcements ── vigil ──┬── prospect ── prospect_rushonly
                  │                                    └── (janus: prospect + vanguard, both intact)
         vanguard ─┴─ v233_* probes
         undertow, casemate, mistral

luc      ragnarok ── valkyrie ── warden ─┬─ warden_walk ── heimdall ── odin
                                          └─ steward
                                          └─ aegis
         tyr ── vidar          (the only 2.3.4-native design)

elias    autistimusprime ── gobbleglitch
```

`janus` is the interesting shape: it ships **prospect and vanguard as two whole bots behind
one entry point** and picks between them per unit on its first turn, rather than trying to
tune one bot to do both jobs.

## 3. What each top bot actually does

### `warden_walk` — the Launcher cap
`warden` with the escape-Launcher relay chain capped at **one hop per Builder**.

The insight came from an anomaly: `ragnarok_fair` beat `valkyrie` 25/42 while `ragnarok`
itself only drew 21/42 — the *fair* twin is the same bot with the atlas removed, and since
the ferry is gated on the atlas, the fair twin **cannot ferry at all**. Being forced to walk
made it stronger. On aurora, valkyrie (chains freely) ends with 6 Launchers / 1 Harvester /
4 Gunners; ragnarok_fair (walks) ends with 3 / 2 / 7.

> "Every relay hop is 20 Ti and a permanent +10% on every price the team pays, and the bill
> lands on exactly the two things that kill a Core: turrets and Harvesters."

And critically, **the cap is not monotonic** — 0 hops is nearly as bad as unlimited. The
first hop clears the Builder out of its own half while the map is empty; every hop after
costs more than it buys. Same shape for the Launcher ring: 8 sites and 1 site are both worse
than 2. Together the two caps take the worst-map rate from 5% to 33%.

### `heimdall` — the home guard, and going atlas-free
`warden_walk` with **no atlas at all** plus a **home guard**: the Builder at our Core answers
an enemy on *sighting*, instead of waiting for the Core to lose 50 HP.

The old trigger fired five Gunner-rounds after the enemy turret went up. The guard is
decisive because the attack it interrupts is so thin — **the entire enemy attack is carried
by one Builder**, and their Core will not spawn a replacement while any Builder still answers
the heartbeat. So a Builder killed on our doorstep is an attack that never comes back. A
Gunner is 10 Ti and kills a 40 HP Builder in four rounds.

Worth 14pp without the atlas, 17pp with it. Final: **0.905 over 336 games, every opponent
above 80%**; 0.838 on 40 generated maps.

The lesson Lucas drew is the one that matters most for process:

> "Getting there was not a new mechanic — it was re-measuring five constants that had been
> tuned on an earlier version of this same bot and never revisited... Every one had a comment
> next to it explaining why its value was right, and the comments were honest about a
> measurement that had genuinely been taken — **on a chassis that no longer existed**."

### `odin` — repair caps and Core-death projection
`heimdall` plus three changes, two of which are *deletions* of things that used to pay:

1. **`REPAIR_ATTEMPT_LIMIT = 3`.** On `bridge`, one conveyor tile sat inside an enemy Gunner's
   ray and the bot rebuilt it **22 times** (66 Ti plus 22% compounding scale), mining 10
   titanium in 1000 rounds. "A hole that keeps reappearing is not damage — it is a tile the
   enemy controls." With the cap: 2,340 mined.
2. **`AVOID_ENEMY_RAYS = False`** and 3. **`SIEGE_BARRIER_ENABLED = False`** — both were worth
   real games on the older atlas-carrying chassis and re-measured negative here.

Plus the **Core-death projection**: the Core estimates its own death from the damage rate over
the last 20 rounds and spawns up to two Builders — one guard, one dedicated mender — because
in the traced loss the bot died on round 192 holding **762 banked titanium** with its only
survivor across the map. That loss is now a 1000-round tiebreak win.

**0.926 over 336 games; 0.875 on 40 generated maps** — the best off-pool score in the record.

### `steward` — the highest Nash mass, from a one-line bug
`warden` plus: **the Core replaces Builders it has lost.**

`core.py` gated respawn on `has_live_builder`, which reads the shared heartbeat slot — and
that slot only proves *one* Builder is alive. Lose two of three and you never replace them.
Traced on sweden: died on T103 holding 358 titanium, having lost to an opponent **that mined
nothing at all**.

The fix is neat because a live headcount is impossible (store writes are invisible until the
next round, so a per-round bitmask never accumulates) — so it uses **the bank itself as the
signal**. A working three-Builder team converts income as it arrives; a large idle bank *means*
the workforce cannot keep up. `REPLACEMENT_BANK_THRESHOLD = 110`.

Why it carries 0.523 Nash mass:

> "Every previous change traded one matchup for another along a fixed frontier... This is the
> first change that is **off** that frontier."

### `prospect` / `prospect_rushonly` — map-shape doctrine
Picks one of two openings from **round-0 vision only** (map dimensions, own Core position,
vision disc r²=36).

The motivating measurement, over 138,785 matches: the same pair of bots swings from **3.6% on
bridge to 96.9% on showdown**. Three rules were tried; only one survived being played — **is
our Core in a corner?** (a Core touching two perpendicular edges cannot be enveloped; the map
guards two of four approaches for free). Wall-density and ore-richness rules both lost their
test maps and are recorded as measured failures rather than left in.

The two doctrines differ in exactly **one** thing: field Gunners, 0 under RUSH and 2 under
FORTIFY. Reallocating Builder roles was tried and is the wrong lever — FORTIFY with two
economy Builders and no attacker lost 2–12 to plain RUSH.

`prospect_rushonly` is the same bot pinned to RUSH. That it out-ranks `prospect` on mElo while
both carry zero Nash mass is a hint the doctrine switch is not paying in the current field.

### `janus` — ship both lineages, choose per unit
Prospect's conclusion taken seriously:

> "The families that win the two kinds of map are not the same machine tuned differently. At
> the end of a game the tempest lineage has about 5.6 buildings standing and has collected
> about 90 titanium, killing on median turn 38–40; vanguard has 15–19 buildings and 500–650
> titanium and kills on turn 50–63. Adding two field Gunners to a rusher moves it a tenth of
> the way there, and a tenth of the way is worth nothing."

So it imports both bots unmodified and picks once per unit on its first turn. Note the
engineering detail: both are imported **at module load**, because loading is paid when the
engine builds the `Player`, outside the 10 ms `run()` budget.

## 4. So what *is* our doctrine?

Strip the names away and almost every bot we own is the same machine:

- **Three Builders**, fixed roles (economy / attacker / guard), spawned in the opening.
- **A Gunner-first turret policy** — Sentinel only as fallback, on the 2.3.3 arithmetic that a
  Gunner "pays 2.78× less per point of damage."
- **Launcher ferrying** to get the attacker across the map early, now capped at one hop.
- **A conveyor belt home**, with repair logic, now capped at three attempts per tile.
- **Win by killing the Core fast** — the tempest branch kills on turn 38–40, vanguard on 50–63.
- **Cost scale as the real currency.** Nearly every improvement in the last week was *deleting*
  something (relay hops, ring Launchers, denial turrets, repair attempts, siege barriers)
  because each living entity is a permanent +10–20% on every future price.

That last point is the genuine intellectual achievement of the lineage, and it is ours — Elias
verified the live-census mechanic across 1,224 checks, and Lucas built four bots on top of it.

## 5. Where `vidar` breaks from all of it

`vidar` is the only 2.3.4-native design, and it inverts three of the five points above:

- **Sentinel, not Gunner**, in every role — because under 2.3.4 both cost the same +20% scale
  and the Sentinel wins on damage, HP, range and ammo efficiency. Measured by role group: guard
  and defend carry it; **field and denial turrets measured worst and are off entirely**.
- **Defence is ~2.2× more titanium-efficient than offence** — a Builder heals 4 HP for a flat
  1 Ti unaffected by scale, while a Sentinel deals 6 damage for 3.33 Ti of ammo. One mender
  cancels two thirds of a Sentinel.
- **Therefore Cores mostly do not die and the median game reaches round 1000**, so the win
  condition becomes the tiebreak: titanium collected → live Harvesters → titanium stored. This
  is the opposite of the whole lineage's "kill by turn 40" assumption.

Two consequences it found and fixed, both of which had been invisible in every win rate:

- **Our Sentinels could not see the win condition.** `get_nearby_entities` returns *units*;
  conveyors, harvesters and barriers are *buildings*. "Every Sentinel this lineage ever built
  simply held its fire whenever no unit stood on its line." They now shoot the supply line —
  and deliberately **never turrets**, because killing a turret hands back its +20% of cost
  scale and makes everything the enemy builds cheaper.
- **Nothing funded the win condition.** Past the opening the Core only replaced the dead. It now
  spawns income Builders after round 200 — which does not contradict the headcount-of-three
  finding, because that was about the *opening*, where +20% falls on unbought Launchers and
  Harvesters, versus round 250 where it falls on 3 Ti conveyors.

And the diagnostic method is worth copying: when the economy sweep changed *nothing*, Lucas
stopped theorising and **counted Builder-rounds**. Out of ~750 rounds each on quarry: two
Builders idle 555 and 509 rounds on a construction lock, three scouts that moved all game and
**built nothing at all**. The root cause was a two-bit `owner` field that could not name more
than three Builders — index 3 wrote owner 4 → `0b00` → "nobody owns this."

## 6. The through-line

Our process is genuinely good at one thing and has one blind spot.

**Good at:** single-variable measurement with honest negative results. Every README above
records what was tried and rejected, with numbers. `warden_walk` found a non-monotonic optimum.
`prospect` shipped one rule out of three and wrote up the two failures. `odin` deleted two
features that used to pay. `heimdall` articulated "a constant is only measured for the bot it
was measured on."

**Blind spot:** the field is all our own children. Nash says so twice — pre-patch it put the
most mass on the one bot from a different author, ranked 32nd; post-patch it collapsed 81 bots
to five and gave the mElo top three zero. Both ladders were measuring how well we beat
ourselves, and the patch showed what that is worth: the entire pre-patch top ten evaporated.
