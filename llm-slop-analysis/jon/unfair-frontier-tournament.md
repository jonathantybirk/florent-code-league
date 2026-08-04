# Unfair frontier tournament

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Date: 2026-08-01

## Why these three lineages

The 42-bot `x/tournament` analysis separates dominance from exploitability. Undertow at
`da3fd8a` led its mElo table with an 85.19% raw win rate, Vanguard was the next distinct
high-scoring policy, and Tempest at `da3fd8a` was only eleventh by mElo but the sole Nash-support
agent: it beat every other entrant head-to-head. These are therefore the three distinct frontier
policies, rather than three filesystem copies of whichever bot topped raw win rate.

## Unfair descendants

All three bots identify a published official map from its dimensions and their own Core anchor,
verify every initially visible terrain tile, and then use a compiled-in atlas containing the exact
terrain and opposing Core. This deliberately violates the fair-bot information boundary. On an
unknown or generated map, identification fails closed and the inherited fair observation and
symmetry logic remains active.

| entrant | fair lineage | source commit | additional policy |
|---|---|---|---|
| `tempest_oracle_ferry` | Tempest Fast | `7196487c5c491ed2e9bfb4a10d86da8696403bae` | bounded lead-attacker launcher hop |
| `undertow_oracle` | Undertow | `75591b72a86ea02f57e4e5d02c04b1dda988d710` | retains Undertow economy, repair, fortification and siege |
| `vanguard_oracle` | Vanguard | `75591b72a86ea02f57e4e5d02c04b1dda988d710` | retains Vanguard's faster attack and launcher-heavy policy |

## Method

Every pair played every one of the 21 official maps in both player orders with seed 1 and the
server's 10 ms turn limit: 126 games total. Bot sources were immutable for this run. There were
zero unresolved games, bot errors, or time-limit failures. The command was:

```sh
uv run python scratch/matrix.py \
  --bots bots/jon/unfair/tempest_oracle_ferry,bots/jon/unfair/undertow_oracle,bots/jon/unfair/vanguard_oracle \
  --tle 10 --jobs 4
```

## Result

| bot | vs Undertow Oracle | vs Vanguard Oracle | total |
|---|---:|---:|---:|
| Tempest Oracle Ferry | 29–13 | 25–17 | **54–30 (64.3%)** |
| Vanguard Oracle | 22–20 | — | 39–45 (46.4%) |
| Undertow Oracle | — | 20–22 | 33–51 (39.3%) |

Tempest Oracle Ferry is the clear winner and also beats both rivals individually, so the
three-player empirical game has a pure Nash choice: Tempest Oracle Ferry. There is no ranking
ambiguity between average dominance and exploitability in this smaller field.

The mechanism is tempo, not merely the atlas. Against Undertow Oracle, Tempest produced its first
Gunner around round 20 versus round 25 and used about four Builders versus Undertow's 5.8. Against
Vanguard Oracle, Vanguard often produced a Gunner earlier (round 13 versus 19), but spent much more
on Launchers (3.8 versus 0.8 per game); Tempest still won 25–17. Privileged knowledge is most useful
when coupled to a small, decisive attack rather than a large infrastructure plan.

Map-level weaknesses remain. Undertow Oracle swept Tempest on `bridge`, `hive`, `quarry`, and
`vase`. Vanguard Oracle swept it on `bridge`, `quarry`, and `vase`; another nine matchups split by
player order. Those shared failures are the best targets for a later map-conditioned unfair policy.

## Interpretation

Adding an oracle did not collapse the policies into duplicates. Undertow still invests in a broad
economy and survival, Vanguard still pays for a more elaborate siege, and Tempest still favors a
compact rush. The official atlas removes uncertainty but cannot recover titanium or turns already
spent on the inherited plan. The next meaningful unfair step is consequently per-map policy
selection on the shared `bridge`/`quarry`/`vase` failure cluster, not additional hidden terrain.

These bots are private experiments. None was submitted or activated.
