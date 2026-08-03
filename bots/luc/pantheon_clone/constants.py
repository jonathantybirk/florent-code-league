"""Pantheon's opening, as measured off 150 ladder replays.

Every number here is an observed frequency, not a guess. The provenance for
each is in README.md; the short version is in the comments below. Sample:
150 games (124 won) pulled 2026-08-03 across 17 opponents and 18 map sizes.
"""

# --- The opening ------------------------------------------------------------
# 150/150 games open with exactly this, on every map, against every opponent:
#   r0 Builder, r1 Builder + Launcher, r2 Builder, r3 Builder.
# 30/150 add a Gunner on r3; nothing else varies before r4.
OPENING_BUILDERS = 4

# The Launcher goes up on round 1, built by the round-0 Builder.
LAUNCHER_ROUND = 1

# Launcher site: Chebyshev radius 2 (83/150) or 3 (67/150) from our own Core,
# always in the quadrant facing the enemy — every one of the 150 sites had both
# relative coordinates pointing enemy-ward. Never radius 1, never 4+.
LAUNCHER_RADIUS_MIN = 2
LAUNCHER_RADIUS_MAX = 3

# --- The throws -------------------------------------------------------------
# 122/150 games throw exactly four times, on rounds 2, 3, 4 and 5 — one per
# round, in Builder spawn order.
THROW_COUNT = 4
THROW_FIRST_ROUND = 2

# Throw range is dist_sq <= 26 measured from the *Launcher*, not from the bot
# being thrown (the bot is picked up from an adjacent tile first, so total
# displacement reaches 6). Observed max dist_sq from the Launcher: exactly 26.
# 353 of 581 throws land at dist_sq 25 or 26 — Pantheon throws at max range.
THROW_RANGE_SQ = 26

# Role by throw index: the first two passengers raid, the last two go to ore.
# 81/150 games are exactly RREE; RR is the prefix of every observed pattern.
RAIDER_THROWS = 2

# --- Raider ----------------------------------------------------------------
# Landing site: of the legal targets, minimise *walking* distance to the enemy
# Core (72.9% land on a BFS-optimal tile, against 38.5% for straight-line), and
# break ties by throwing as far as possible — 103/103 tied throws took the
# farthest tile. That tie-break is the one rule with no counterexample.
#
# Then the raider walks in and rings the enemy Core with Gunners at Chebyshev
# 2-4 (974 of 1069 placements; the mode is 3).
RAIDER_GUNNER_MIN = 2
RAIDER_GUNNER_MAX = 4
# A Gunner reaches dist_sq 13 and fires only along its facing. Just 54% of
# Pantheon's own Gunners sit inside that range of the Core -- the ring is a
# siege line against the defenders too, not purely a Core-killing battery.
GUNNER_RANGE_SQ = 13
RAIDER_GUNNERS = 4          # 92 raiders built exactly four; none built more

# --- Economy ---------------------------------------------------------------
# The economy passengers land next to ore that is far enough out that a walking
# Builder would never reach it, then run harvester -> conveyor -> conveyor.
# 101 of them built exactly that sequence.
ECON_CONVEYORS = 3

# --- Launcher retirement ---------------------------------------------------
# In 147 of 151 Launchers the lifetime is exactly five rounds: built r1, gone
# r6, the round after the fourth throw. Nothing is adjacent when it goes and
# the removal lands inside the Launcher's own turn, so it is self_destruct().
#
# This is the part of the opening that is easy to miss and expensive to skip:
# a Launcher carries +10% build-cost scale for as long as it is alive. Razing
# it the moment the fourth passenger is away hands that 10% back for the whole
# rest of the game.
LAUNCHER_LIFETIME = 5

# --- Ammunition ------------------------------------------------------------
# The Core converts 2 on round 0 and then nothing at all until the first Gunner
# lands. From there it tops up every round in small even amounts (2/4/6/8/10 is
# the modal set), i.e. it feeds the Gunners it actually has rather than banking
# ammo. Mean converted over a game: 185.
OPENING_AMMO = 2
# Peak pool observed is 8; the throughput comes from refilling it, not sizing it.
AMMO_BUFFER = 10
AMMO_START_ROUND = 6

# --- Map oracle -------------------------------------------------------------
# The published pool is uniquely keyed by (width, height, own Core), so the
# enemy Core can be looked up instead of inferred. Reproducing real games
# against this on/off is how we tested whether Pantheon recognises maps:
# ON, rounds 1-2 track the real games far better (17/180 matching rounds
# against 9/180); OFF, round 0 matches on five more maps. So Pantheon's
# round-0 tile is *not* aimed at the true enemy Core -- whatever it is doing,
# it is not this lookup. Kept on because it reproduces more rounds overall.
#
# NOTE: this is an oracle. `ragnarok_fair` exists precisely to exclude it.
# Anything derived from this bot that is meant to be fair must set it False.
ATLAS_ENABLED = True

# --- Store slots -----------------------------------------------------------
SLOT_OWN_CORE = 0
SLOT_ENEMY_CORE = 1        # 0 until somebody actually sees it
SLOT_ORE_HINT = 3
SLOT_THROWS_DONE = 4
SLOT_LAUNCHER = 5          # live Launcher position; 0 once it has razed itself

# The Core's spawn action radius is sqrt(8), but Pantheon never spawns past
# dist_sq 5 -- the (2,2) corners are absent from all 150 openings.
SPAWN_REACH_SQ = 5

# Pickup range is dist_sq <= 2, so a Builder the Launcher cannot reach is a
# throw wasted. Builders queue on the pad until they are picked up.
PICKUP_RANGE_SQ = 2

# Builder vision is r^2=20, so on anything bigger than ~14x14 the first throw
# has to be aimed at a guess. Reflecting our Core through the map centre is
# within a tile or two of the truth on every map in the sample; vision
# corrects it as soon as a raider gets close.
STUCK_ROUNDS = 3
