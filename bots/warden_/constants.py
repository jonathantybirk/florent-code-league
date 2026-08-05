"""Comm-store slots and tunable thresholds for warden.

Keep every knob here, named, so retuning never means hunting through
policy.py/core.py/modes/*.py for a bare literal.

Mode lives here rather than in modes/__init__.py so that constants.py has
no dependency on the modes package -- QUOTA_CYCLE below needs Mode, and
modes/__init__.py (which wires up economy.py/defence.py/scouting.py, each
of which needs SLOT_* from here) would otherwise create an import cycle.
"""

from __future__ import annotations

from enum import IntEnum


class Mode(IntEnum):
    ECONOMY = 0
    DEFENCE = 1
    SCOUTING = 2
    OFFENCE = 3


# --- Communication store slots (16 total) ---
SLOT_BUILDER_TICKET = 0    # Builder (self, first run): spawn-order counter
SLOT_ORE_SHARE = 1         # any Builder: last-seen unclaimed ore, packed
SLOT_THREAT_LEVEL = 2      # Core only: decaying home-threat flag
SLOT_DEFENCE_COUNT = 3     # Builder (promote/demote): live promoted-defender census
SLOT_ENEMY_SIGHTING = 4    # Scouting Builder: last reported (non-Core) enemy position, packed
SLOT_THREAT_POS = 5        # Core only: nearest sighted-threat position, packed (see SLOT_THREAT_LEVEL)
SLOT_ENEMY_CORE = 6        # any Builder: enemy Core position once spotted, packed -- see modes/offence.py
SLOT_OFFENCE_COUNT = 7     # Builder (join, one-way): live Offence-builder census
# 8-15 reserved for future signals.

# --- Ticket -> default mode ---
# No Defence ticket at all -- every Builder starts as an Economy rush,
# racing to find and start mining titanium as fast as possible, with
# Scouting mixed in to range further out (map intel, and it shares ore
# it passes too -- see modes/scouting.py). Defence is 100% reactive:
# policy.maybe_reassign() promotes idle Economy builders to Defence only
# once the Core actually senses a threat (see SLOT_THREAT_LEVEL), capped
# at MAX_PROMOTED_DEFENDERS -- a standing Defence ticket would station
# builders at the Core guarding against nothing while the economy is
# still trying to get off the ground. Not yet measured against real
# opponents beyond this -- tune this tuple first when adjusting team
# composition. default_mode_for_ticket() in policy.py indexes it by
# ticket % len(QUOTA_CYCLE).
QUOTA_CYCLE = (
    Mode.ECONOMY, Mode.ECONOMY, Mode.ECONOMY, Mode.ECONOMY, Mode.SCOUTING,
)

# --- Core ---
# Ceiling on ct.get_unit_count() (Core + every Builder + every turret --
# the team's whole population), not just Builder Bots, since they all
# share the same 50-unit team cap; see core.py. 16 was leaving most of
# that cap on the table -- an economy that stops growing its workforce
# long before the team cap is even close can't keep expanding.
MAX_TOTAL_BUILDERS = 40
# Minimum rounds between spawns. Affordability alone let the Core burst
# out a handful of Builders in the first few rounds, all racing for
# whatever ore tiles happen to be nearest the spawn -- only one can claim
# each, so most of that burst ends up idling before any of them has even
# reached one. Pacing spawns gives each new Builder time to disperse,
# claim ore (or fail and get reassigned -- see ECON_IDLE_ROUNDS_BEFORE_
# SCOUT) before the next one shows up. Late-game this rarely binds --
# affordability is the real limit by then -- so it only really shapes
# the opening.
BUILDER_SPAWN_COOLDOWN_ROUNDS = 4
AMMO_TARGET = 20
AMMO_CHUNK = 10

# --- Threat / defence promotion ---
THREAT_DECAY_ROUNDS = 30
CORE_THREAT_VISION_SQ = 36  # matches the Core's own vision radius^2
# The only source of Defence builders now that QUOTA_CYCLE has no Defence
# ticket -- at most 2 Economy builders ever get pulled off mining to
# defend at once, however large the team grows.
MAX_PROMOTED_DEFENDERS = 2
# Consecutive idle rounds (no ore_target, no route -- genuinely nothing
# to do, not mid-walk) an Economy builder tolerates before giving up and
# switching to Scouting instead -- always useful (there's always more
# map, and it now shares ore back too, see modes/scouting.py), unlike
# sitting in Economy mode calling explore_randomly forever. One-way: this
# doesn't use the promoted/demote machinery above, since there's no
# "threat cleared" style condition to revert on.
ECON_IDLE_ROUNDS_BEFORE_SCOUT = 8

# --- Defence mode ---
DEFENCE_RADIUS_SQ = 18
PATROL_RADIUS_SQ = 9
# Cap on friendly turrets a single Defence builder will help place near the
# Core -- without this, the first successful build permanently blocked any
# more (a real bug: it read as "no turrets ever" once tile clutter from
# Economy's old every-step belt-laying denied the first placement too).
MAX_DEFENCE_TURRETS_NEAR_CORE = 3

# --- Offence mode ---
# Like Defence, Offence is 100% reactive rather than a standing ticket --
# see policy.py's OFFENCE branch -- and pulls from the same two sources:
# an idle Economy builder (never mid-route -- see modes/economy.py), or a
# Scout that itself just found the enemy Core, converting on the spot
# rather than reporting home and waiting for someone else to make the
# trip. Capped small: this is harassment, not an invasion, and every
# Builder it pulls off mining is one fewer growing the economy that's
# still trying to outscale everyone else.
MAX_OFFENCE_UNITS = 2
# How close to the enemy Core counts as "arrived" -- close enough to
# sabotage adjacent buildings and consider seating a forward Gunner,
# rather than trying to walk all the way onto Core-adjacent tiles that
# are usually the most heavily defended ground in the game.
OFFENCE_ENGAGE_RADIUS_SQ = 18
# A single forward Gunner is a nuisance the enemy has to spend a turret
# or a few Builder-rounds clearing; a battery is titanium this Builder
# will not live to spend twice. Keep it cheap.
MAX_OFFENCE_TURRETS_NEAR_ENEMY = 1

# --- Economy / Scouting movement ---
STUCK_THRESHOLD = 3
SCOUT_ARRIVAL_DIST_SQ = 4
# The route-to-core walk in modes/economy.py resets its stuck counter every
# time it successfully places a conveyor, since the build-then-move-next-
# round cadence (a successful build consumes the round, so position repeats
# every other round) would otherwise look "stuck" while actually making
# steady progress -- so this only needs to catch a genuine dead end (can
# neither move nor build), not the normal cadence. Kept separate from
# STUCK_THRESHOLD (ore-seeking, where nothing resets it) for clarity.
ROUTE_STUCK_THRESHOLD = 5
