# Hodr_bank — we lose 96% of the games decided on titanium *stored*

`nott` with `LATE_BANK_ROUND = 880`: past that round the Core stops converting
titanium into ammunition and Builders stop buying turrets, so the bank survives
to the round-1000 tiebreak. **Measured, safe, and not queued** — the reason is
at the bottom.

## The defect

Over 21,400 recorded games, split by how they end:

| ending | share of 300+ round games | our win rate |
|---|---|---|
| core_destroyed | 63.7% | 0.535 |
| titanium_collected | 26.4% | 0.652 |
| **titanium_stored** | **7.3%** | **0.116** |
| coinflip | 1.2% | 0.364 |

**All 199 `titanium_stored` games end at exactly round 1000, and in every one
both sides collected zero titanium** — no Harvester ever delivered, so the
tiebreak falls past "collected" to the bank. There we hold a median of **16
against their 68**: we spent the opening 500 on turrets and ammunition while
the opponent sat on it.

We win 23 of 199. That is the single most lopsided ending in the data.

## What the fix does

| build | bank at round 1000 | `titanium_stored` won |
|---|---|---|
| `nott` | 18 | 2 / 56 |
| ammunition only, from round 950 | 42 | 6 / 56 |
| **this build** (880, ammunition + turrets) | 41 | 6 / 54 |

On 58 stalemate-prone maps, 232 strictly paired cells against two opponents:
0.491 -> **0.517**, +0.026 (+0.6 sd), McNemar **z = +2.12**.

And it is inert where it does not apply — on `maps/livelike` plus
`maps/livelike2`, 648 paired cells, it is **identical in 646 of 648 games**
(-0.1 sd), because only 3.2% of those games reach round 1000 at all.

## Why it is not queued

Three reasons, and they are worth being explicit about:

1. **The bank still loses.** 41 against their 68 — the fix captures the
   ammunition but not the rest, so 48 of 54 of these games are still lost. The
   remaining spend is barriers, conveyors and Builder replacements, and finding
   it is the actual completion of this work.
2. **The gain rests on 4 extra wins out of 56** (2 -> 6). That is a binomial
   p of about 0.14 on its own; the +2.12 McNemar comes from the wider game set,
   not from the ending this was built for.
3. **The map set was selected for the mechanism.** The 58 maps were chosen
   because a quarter or more of their games reach round 1000. That is legitimate
   for *observing* a rare code path, and illegitimate for deciding what to ship
   — the lesson `sunna` cost this session.

On live-representative maps it does not beat `nott`, so it does not clear the
bar. Kept because the diagnosis is worth more than the build: **a 7% slice of
long games that we lose 96% of, for a reason that is entirely mechanical.**
