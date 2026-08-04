# Backlog — what we said we'd build and didn't, plus what vanguard just taught us

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Two lists. The first is debt against `openspec/changes/elias-verification-and-offense/tasks.md`. The second
is new work forced by the discovery that Jon's map-blind `vanguard` beats us **30–0 on the fifteen maps we
memorised**, with zero core kills for us.

---

## Part 1 — promised, not built

| # | Item | Spec ref | Why it still matters |
|---|---|---|---|
| **D1** | **Falsify the rush against a real defender** — one that heals, covers the approach with its own gunner, and kills the attacking harvester | task 4.2 | **Never ran. Jon ran it for us and the doctrine failed 0–30.** The spec said the doctrine was not adopted until it survived this. We shipped it anyway and reported it as a win against opponents that could not answer it. |
| **D2** | **Held-out maps** — designate maps excluded from all tuning, report separately | task 3.5 | Never done. This is precisely the hole vanguard walked through: 23–7 on memorised maps collapses to 13–11 on unseen ones. |
| **D3** | **TLE audit on Linux** — do rival bots exceed 10 ms under enforcement? | task 2.x | Died to session limits 3×. `luc1` reportedly carries a routine its author timed at ~21 ms with the fix on another branch. Could reorder the whole leaderboard on the real ladder. |
| **D4** | **`arena/strict.py` as an actual gate** | task 3.3 | Built, never wired into a pre-submission workflow. |
| **D5** | **Ammo bus / splitters** | task 5.5 | One harvester sustains exactly one continuously-firing Gunner. We have never built a splitter. |
| **D6** | **Harvester passability** (docs say "blocks movement: No"; a probe disputed it) | open G42 | Unverified. If harvesters block, auto-build can wall in its own corridor. |
| **D7** | **Team integration** — publish register, harness and leaderboard | group 6 | Nothing pushed. The arena and ground-truth register are our most valuable output and nobody else can use them. |
| **D8** | **Store protocol v1** — single-writer Core slots, max-register merges | task 5.3 | Partially built; claims are ad hoc. |

Correctly dropped after measurement (not debt): barrier denial, launcher relay for economy, magazine
discipline, atlas ore-seeding, chain-length ore ranking, **exposure term in ore selection**, **home-line
length cap**, **launcher ferry for our own rusher**, **danger-weighted Dijkstra**.

### Why the two economy levers died, and the finding that killed them

The premise — that our economy reaches into contested ground and arms their turrets — is **wrong**. A
histogram of where the anchoring building actually sits on the our-Core→enemy-Core axis (0 = ours,
1 = theirs) over 131 adjacencies: **mean 0.19, with 111 of 131 inside 0.3.** Our whole economy averages
0.266 and even its furthest building averages 0.502 — we barely touch the midline.

`vanguard` walks into **our** base and builds against the belts that must terminate on our own Core ring.
Those tiles are forced by G02 (a chain one tile short scores zero), so **no ore-selection rule can move
them**. The exposure term did exactly what it claimed — buildings past the midline −19% — and moved 0 games.
The home-line cap was flat from 5 upward and cost real income at 4.

---

## Part 2 — new, forced by vanguard

`vanguard` reaches the same siege doctrine we did — its own constants state *"a Gunner turns 1 Ti of
delivered ammunition into 5 damage… a 500 HP Core in 40 rounds"* — but implements it as an **algorithm over
observed terrain** instead of a **lookup table over memorised maps**. That difference is the entire gap.

| # | Item | Rationale |
|---|---|---|
| **N1** | **Runtime siege planner.** Derive firing geometry at match time from observed terrain plus inferred symmetry. Atlas becomes an accelerator, never a precondition. | Our rush produces **zero** kills on any unrecognised map because `atlas.identify()` returns `None` and `RUSH_MAPS` never matches. The runtime path *is* the unseen-map fallback — one change fixes both. |
| **N2** | **Defensible forward harvester.** It is 30 HP and the single point of failure of the whole attack. | 0–30 vs vanguard with zero kills says it dies every game. Options: heal it, barrier its approach, build a second, or site it out of their gunner arc. |
| **N3** | **Re-site the siege when blocked.** | We walk to one hardcoded tile and have no plan B. Vanguard replans. |
| **N4** | **Counter-harassment.** Jon's last commit before vanguard was "Add early harassment". | Something is killing our rusher early and consistently. We have no response to a builder shadowing ours. |
| **N5** | **Plan conveyor lines over *observed* terrain only** — vanguard's `plan_line()`, whose docstring reads *"unknown ground is not permission to spend titanium"*. | Our belt is laid by walking. The agent ablation already showed the valuable half is **L2** (refusing to start a chain you cannot prove reaches the Core), not L1. |
| **N6** | **Re-examine the economy/siege builder split.** Vanguard runs `ECONOMY_BUILDERS = 2`; we run 6 with one rusher. | Our builder count was tuned entirely on memorised maps against opponents that could not punish us. |
| **N7** | **Every measurement on BOTH map sets, always.** | Known-map numbers are memorisation, not strength. `tools/unseen.py` exists; it must become mandatory, not optional. |

---

## Order of work

1. **N1** — runtime siege planner. Fixes the doctrine and the unseen-map collapse together. Biggest item.
2. **N2 + N3 + N4** — make the siege survive contact. This is D1's falsification, answered in code.
3. **N5** — observed-terrain conveyor planning (the L2 half).
4. **N7** — bake dual-map-set evaluation into the harness so this cannot recur.
5. **D3, D7** — the TLE audit and publishing to the team.

**Standing rule from here:** no result is reported as a gain unless it holds on unseen maps too.
