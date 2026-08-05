# Ladder vs our tournament, 5 August 2026 (fcode 2.3.4)

Measured on 2.3.4. Ladder figures pulled from `fcode match list` full history
(≈800 matches per top-10 team) on 2026-08-05; tournament figures from
`tournament/runs/v2-full-20260804` on `x/tournament`.

## 1. The tournament run is post-patch, and it is real

`v2-full-20260804`: **81 bots, 31 maps** (21 official + 10 secret), **202,581 matches**,
200,880 of them rated. `x/tournament` bumped `fcode` to 2.3.4 at 17:06 on Aug 4; the run was
committed at 19:49. So it is a genuine 2.3.4 measurement, not a pre-patch leftover.

## 2. But every bot in its top five was *designed* for 2.3.3

| local rank | bot | `BOT_VERSION.engine` | descends from |
|---|---|---|---|
| 1 (mElo) | `prospect_rushonly@bf9b3e3` | 2.3.3 | vigil ← tempest_reinforcements |
| 2 (mElo) | `prospect@bf9b3e3` | 2.3.3 | vigil ← tempest_reinforcements |
| 3 (mElo) | `janus@8a1e7a1` | 2.3.3 | — |
| 4 (mElo) / 1 (Nash) | `odin@38e1456` | 2.3.3 | heimdall ← warden_walk |
| 6 (mElo) / **top Nash** | `steward@e55aab5` | 2.3.3 | warden |

Every one is stamped `engine = "2.3.3"`. They encode the pre-patch turret doctrine directly —
`odin/builder.py` still carries the docstring *"It pays 2.78x more per point of damage, which is
why this runs only after the Gunner and Launcher-breaker searches have both come up empty."*
The Sentinel is the **fallback of last resort** in all five.

Lucas's `vidar` work (Aug 5, `x/luc`) re-derived that ratio from the engine's own `GameConstants`
under 2.3.4 and found it **inverted**: both turrets now carry the same +20% cost scale, and the
Sentinel wins on damage/round (1.71×), HP (1.6×), range (2.46×), damage/ammo, and is unblockable
by terrain. Under 2.3.3 the Gunner's +10% against the Sentinel's +20% is exactly what made Gunner
spam correct; that asymmetry is gone.

**So the leaderboard-v2 top five is five pre-patch bots re-measured on the new engine.** They rank
highly because the *whole 81-bot field* shares their obsolete assumption. `vidar` — our only
genuinely post-patch design — is not in the run at all.

## 3. The harness already says the field is redundant

`duplicates.csv` is empty (no exact clones), but Nash averaging collapses the 81 bots to **five
strategies with any support at all**:

| bot | Nash mass | mElo rank |
|---|---|---|
| steward@e55aab5 | 0.523 | 6 |
| vigil@e267eeb | 0.199 | 9 |
| heimdall@daf0de0 | 0.099 | 10 |
| heimdall@840a180 | 0.094 | 12 |
| odin@38e1456 | 0.085 | 4 |

The mElo top three (`prospect_rushonly`, `prospect`, `janus`) have **zero Nash mass**. They are
beating a redundant field, which is precisely the failure mode the harness's own README quotes
Balduzzi et al. about. The harness is working; we are not acting on its output.

## 4. Is the tournament representative of the ladder? Currently unanswerable — and that is the finding

Online exposure of our locally-strong bots is almost nil:

| our version | what it is | ladder record | vs Pantheon |
|---|---|---|---|
| v5 | Tempest Fast (jon) | 302W-255L (0.542) over 557 | **1W-27L** |
| v9 | steward — *top Nash bot* | 0W-1L over 1 | 0-1 |
| v15 | Odin | 22W-9L (0.710) over 31 | 0W-2L |
| **v16** | active bot | **119W-43L (0.735) over 162** | 7W-8L |
| v19 | MapOracle v2 | 4W-2L over 6 | 1W-0L |
| v20 | prospect_rushonly — *top mElo bot* | **2W-3L over 5** | 0W-1L |

Our #1 local bot has **five ladder matches**. Our top-Nash bot has **one**. The only two bots with
a real online sample are v5 and v16, and v16 was never in the tournament.

The one honest comparison we can make is v5, and it is instructive rather than reassuring:
v5 scored **0.542 overall online but 0.036 against Pantheon**. A round-robin average over our own
family completely concealed a matchup that loses 27 games out of 28.

**That is the structural problem.** A 202k-match round robin against 81 bots from three lineages
measures *average-case strength inside our own doctrine*. Nash averaging corrects for redundancy
within the field; it cannot invent a strategy the field does not contain. Every opponent that
actually threatens us on the ladder — Pantheon, Pivot, Pareto-ion — is outside it.

## 5. Ladder ratings across the patch: the top ten genuinely reshuffled

Reconstructed from `ratingBefore` on every match in each team's history.

| team | last pre-patch | post-patch low | now | swing |
|---|---|---|---|---|
| **Pivot** | 1627 | 1635 | **1960** | **+333** |
| sporks | — (debut Aug 5 03:56) | 1500 | 1759 | +259 (39 matches) |
| OopsGotYourElo | 1653 | 1641 | 1782 | +129 |
| Powered by SmartFridge | 1770 | 1775 | 1845 | +75 |
| Pareto-ion | 1860 | 1863 | 1893 | +34 |
| Orizon | 1719 | 1653 | 1738 | +18 |
| CtrlAltDefeat | 1779 | 1755 | 1794 | +15 |
| team lazy | 1824 | 1673 | 1791 | −33 |
| **Erebus** | 1912 | 1794 | 1801 | **−111** |
| **Pantheon** | **1960** | 1772 | 1782 | **−177** |

Pre-patch the ladder was led by **Pantheon (1960)** and **Erebus (1912)**, with Pivot down at 1627.
Post-patch those two collapsed and **Pivot took the exact rating Pantheon vacated**. The patch
rewarded whoever re-derived the turret maths fastest, which is the same lesson `vidar` reached
locally.

Two teams worth watching for the "held back the good bot" pattern:

- **Pivot** — 490 matches against everyone else's ~800, and only **v24** submissions. Few uploads,
  high rating: they are not iterating on the ladder, they are iterating privately and submitting
  when ready.
- **sporks** — debut match Aug 5 03:56 at the 1500 floor, **1759 within 39 matches**. A brand-new
  account does not climb 259 points that fast by accident. Either a strong team's second account
  or a team that developed entirely offline.

By contrast CtrlAltDefeat (v71→v85), team lazy (v71→v76) and Erebus (v30→v36) are visibly
ladder-tuning in public.

## 6. Pantheon: it is one specific build that beats us, not the team

Full chronological head-to-head, 61 matches. We are **11W-50L** overall, but that splits cleanly:

| our bot | their build | record |
|---|---|---|
| v5 | v6–v20 | **1W-27L** |
| v16 | v20 | 4W-0L |
| v16 | v23 | 1W-0L |
| v16 | v25 | 1W-0L |
| v16 | v27 | 1W-0L |
| **v16** | **v24** | **1W-8L** |

**We beat every Pantheon build except v24.** Their v25, v26 and v27 experiments all lose to us —
and they keep reverting to v24, which is what they are running now.

This reframes the matchup completely. It is not "Pantheon is better than us." It is **one opponent
build that counters our current bot**, worth 8 losses, and their own attempts to move off it have
failed. Getting the v16-vs-v24 replays and finding the mechanism is the single highest-value
replay-analysis task available, and it is narrow enough to actually finish.

(My earlier read of "2W-7L vs Pantheon" came from the last-100-match window only. Across full
history v16 is 7W-8L against them overall; the recent window is dominated by their v24.)

## 7. What v24 actually does — decoded from a real ladder loss

Downloaded match `b405fc69-d28c-4acc-a310-b9567490294f` (we lost 1–4 on Aug 5 07:13) with
`fcode match replay`, and decoded all five games with Lucas's `tools/pantheon_analysis/decode.py`.
It reads live ladder replays without modification. TEAM_A is Pantheon v24, TEAM_B is our v16.

| game | winner | length | Pantheon v24 | us (v16) |
|---|---|---|---|---|
| 1 | A | 63 | 2 harv@r4, 4 conv@r6, 9 barrier@r14, **2 sentinel@r21** | 10 conv@r1, **4 launcher@r2**, **2 gunner@r10** |
| 2 | A | 66 | 2 harv@r3, 6 conv@r5, **2 sentinel@r30** | 14 conv@r1, **6 launcher@r2**, 2 gunner@r36 |
| 3 | A | 55 | 2 harv@r3, 6 conv@r5, **2 sentinel@r19** | 11 conv@r1, **4 launcher@r2**, 2 gunner@r9 |
| 4 | A | **37** | 1 launcher@r1, **2 sentinel@r3**, 5 barrier@r6 | **5 gunner@r3** |
| 5 | B | 126 | 2 harv@r6, 6 conv@r7, 2 sentinel@r22 | 13 conv@r1, 5 launcher@r2, 1 gunner@r12 |

The pattern is the same in every game and it is exactly the doctrine split the patch created:

- **Pantheon v24 builds Sentinels.** Two of them, every game, between r19 and r30 — and in the
  37-turn game, at **r3**. Lean economy behind it: two harvesters, ~6 conveyors.
- **We build Gunners**, plus a wide conveyor net (10–14 conveyors from r1) and **4–6 Launchers at
  r2** before anything else.
- **Games end between turn 37 and 66.** Our economy investment never amortises. `titanium_collected`
  is only a tiebreak at round 1000 and these games do not get near it.

Game 4 is the whole thesis in 37 turns: we put **five Gunners** down at r3 and lost to **two
Sentinels** placed at r3 behind barriers.

This independently confirms, on live ladder data, two things our own branches already established
by other means:

1. Lucas's `GameConstants` re-derivation — under 2.3.4 the Sentinel beats the Gunner on damage,
   HP, range and ammo efficiency at identical +20% cost scale.
2. Elias's cost-scale audit — a Launcher is +10 pp on every later purchase for a measured 1.6–1.9
   throws per game, and should be retired. We are paying that tax on 4–6 Launchers from round 2.

So the "Pantheon v24 counter" is not a mystery tactic. **It is the 2.3.4 turret inversion, and we
are on the wrong side of it because our active ladder bot is a 2.3.3 design.** The fix is already
written — it is `vidar` — and it has never been submitted.

## 8. The "global instant communication" rumour — tested, and it is false on our engine

Ground-truth claim **G20** ("module-level globals are not shared between units — each runs in its
own CPython sub-interpreter") was marked `CARRIED-2.2.0`, never re-run on 2.3.x, and sat on
Elias's P2 backlog. Given the Discord rumour, it was worth settling.

Probe: `bots/jon/probes/sharedglobals` (2.3.4, duel). The Core writes `12345` into a module-level
dict on round 2 and every unit increments a module-level counter every round. A Builder Bot reads
both on round 8.

```
G20=ISOLATED canary=0 core_round=-1 ticks=8 mine=8 slot5=777
```

- `canary=0` — the Core's write never reached the builder.
- `ticks=8 == mine=8` — the module counter equals the builder's *own private* contribution, so the
  Core's eight increments were invisible. The module object is genuinely per-unit.
- `slot5=777` — the official store carried the same value across units without trouble.

**G20 is confirmed on 2.3.4.** There is no shared-globals side channel in this engine.

Two things worth separating, because they are probably the source of the rumour:

1. **Cambridge Battlecode had no global store at all** — comms there were markers, one u32 per unit
   per turn, and Pantheon's postmortem spends pages bit-packing them. Anyone with Cambridge
   experience would reasonably describe *our* engine's 16-slot team-wide store as "global instant
   communication", because relative to what they are used to, it is. That is an official feature of
   our game, documented in `global-comms.txt`, not a bug.
2. It is **not instant**. Writes are buffered and visible only from the next round (docs
   `agents-md.txt:24`; Elias measured exactly one round of lag). So anyone claiming *instant*
   global comms is describing something we cannot reproduce.

If someone has a concrete claim, the cheap next probes are: a shared mutable default argument, an
`import`-time singleton in a second module, and `sys.modules` reuse. All three are variants of the
same isolation question this probe already answers, so I would not spend time on them without a
specific claim to test.

**On Discord access:** I have no way to read Discord — no connector for it, and its content is not
public to fetch. If you want it in the analysis loop, export the relevant channels (Discord's own
data export, or copy-paste the threads into a file under `docs/` if they are verbatim, or into
`llm-slop-analysis/` if summarised) and I can work from that. It is worth doing: a rules-adjacent
rumour like this one is exactly the sort of thing that decides a competition, and right now we are
guessing at second-hand paraphrases.
