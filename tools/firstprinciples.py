"""What the 2.3.5 constants imply, before any game is played.

Everything here is derived from `fcode.GameConstants` and the rulebook's exchange rates. No games,
no opponents, no tuning. The point is to find out what the game IS on this engine, because the
2.3.4 rebalance moved every turret number and made the accumulated 2.3.3 tuning worthless.
"""

from fcode import GameConstants as G

CORE = G.CORE_MAX_HP
PASSIVE = G.PASSIVE_TITANIUM_AMOUNT / G.PASSIVE_TITANIUM_INTERVAL
TURNS = G.MAX_TURNS


def line(k, v):
    print("  %-46s %s" % (k, v))


print("=" * 78)
print("1. THE TITANIUM BUDGET -- what a team has to spend, mining nothing")
print("=" * 78)
noecon = G.STARTING_TITANIUM + PASSIVE * TURNS
line("starting bank", "%d Ti" % G.STARTING_TITANIUM)
line("passive income", "%.2f Ti/round (%d per %d rounds)"
     % (PASSIVE, G.PASSIVE_TITANIUM_AMOUNT, G.PASSIVE_TITANIUM_INTERVAL))
line("lifetime income, zero economy", "%.0f Ti" % noecon)
line("one harvester", "%.2f Ti/round (10 per 4 rounds), 20 Ti + 5%% scale" % 2.5)
print("  -> a harvester DOUBLES income and pays back in 8 rounds, but only counts for the")
print("     tiebreak if a stack physically lands on a Core tile.")

print()
print("=" * 78)
print("2. WHAT IT COSTS TO KILL A 500 HP CORE -- the only clean win condition")
print("=" * 78)
weapons = [
    ("Sentinel", G.SENTINEL_BASE_COST, G.SENTINEL_DAMAGE, G.SENTINEL_FIRE_COOLDOWN,
     G.SENTINEL_AMMO_COST, G.SENTINEL_MAX_HP, G.SENTINEL_VISION_RADIUS_SQ, 20),
    ("Gunner", G.GUNNER_BASE_COST, G.GUNNER_DAMAGE, G.GUNNER_FIRE_COOLDOWN,
     G.GUNNER_AMMO_COST, G.GUNNER_MAX_HP, G.GUNNER_VISION_RADIUS_SQ, 20),
    ("Builder attack", 0, G.BUILDER_BOT_ATTACK_DAMAGE, 1,
     G.BUILDER_BOT_ATTACK_COST, G.BUILDER_BOT_MAX_HP, 1, 0),
]
print("  %-16s %5s %5s %5s %6s %7s %8s %8s %7s" %
      ("weapon", "build", "dmg", "cd", "ammo", "dmg/rd", "Ti/dmg", "rds/core", "Ti/core"))
for name, build, dmg, cd, ammo, hp, vis, scale in weapons:
    dps = dmg / cd
    tipd = ammo / dmg
    shots = -(-CORE // dmg)
    rounds = shots * cd
    total = build + shots * ammo
    print("  %-16s %5d %5d %5d %6d %7.2f %8.3f %8d %7d"
          % (name, build, dmg, cd, ammo, dps, tipd, rounds, total))
print()
print("  -> A Core kill costs ~310 Ti. The OPENING BANK ALONE (500) can pay for it.")
print("     Titanium is not the constraint on winning; TIME and SURVIVAL are.")

print()
print("=" * 78)
print("3. TURRET DUELS -- who kills whom, and in how many shots")
print("=" * 78)
print("  %-28s %6s %6s %8s" % ("attacker -> target", "shots", "rounds", "ammo Ti"))
for an, _ab, ad, acd, aam, _ahp, _av, _as_ in weapons:
    for tn, _tb, _td, _tcd, _tam, thp, _tv, _ts in weapons:
        if an == tn == "Builder attack":
            continue
        shots = -(-thp // ad)
        print("  %-28s %6d %6d %8d" % ("%s -> %s" % (an, tn), shots, shots * acd, shots * aam))
print()
print("  -> A Sentinel kills a Gunner in 2 shots / 4 rounds. A Gunner needs 6 shots / 6 rounds")
print("     to kill a Sentinel -- and cannot reach it: Sentinel 5 tiles vs Gunner 3.")
print("     Sentinel-vs-Sentinel is 3 shots either way, so it is a FIRST-STRIKE duel.")

print()
print("=" * 78)
print("4. REACH -- how close you must get, and how long the walk is")
print("=" * 78)
for name, r2 in (("Sentinel", G.SENTINEL_VISION_RADIUS_SQ),
                 ("Gunner", G.GUNNER_VISION_RADIUS_SQ),
                 ("Launcher throw", G.LAUNCHER_VISION_RADIUS_SQ),
                 ("Core vision", G.CORE_VISION_RADIUS_SQ),
                 ("Builder vision", G.BUILDER_BOT_VISION_RADIUS_SQ)):
    card = int(r2 ** 0.5)
    diag = int((r2 / 2) ** 0.5)
    line("%s r^2=%d" % (name, r2), "%d tiles cardinal, %d diagonal" % (card, diag))
print("  -> Movement is 1 tile/round, CARDINAL ONLY (diagonals are illegal).")
print("     A Sentinel needs to reach 5 tiles from the enemy Core; a Gunner 3.")
print("     Two extra tiles of standoff is two fewer rounds of walking AND out-ranges")
print("     every Gunner they can build to defend with.")

print()
print("=" * 78)
print("5. COST SCALE -- the tax on everything, and what is exempt")
print("=" * 78)
print("  built entity          scale delta")
for n, d in (("conveyor/splitter/barrier", "+1%"), ("harvester", "+5%"),
             ("launcher", "+10%"), ("builder bot", "+20%"),
             ("GUNNER (was +10%)", "+20%"), ("sentinel", "+20%")):
    line(n, d)
print()
print("  EXEMPT (flat at any scale): attack 2 Ti, heal 1 Ti/+4 HP, rotate 10 Ti,")
print("  convert_ammo 1:1. Only CONSTRUCTION and SPAWNING scale.")
print("  Scale is a LIVE census -- destroying an entity refunds its contribution in full.")
print("  -> Late game, titanium belongs in AMMO, not in more turrets.")

print()
print("=" * 78)
print("6. IF NOBODY DIES -- the tiebreak ladder")
print("=" * 78)
print("  titanium_collected  ->  live harvesters  ->  titanium_stored  ->  coinflip")
print("  Only stacks LANDING ON A CORE TILE count as collected. Passive income scores ZERO.")
print("  -> A bot with no belt cannot win a long game. Killing a harvester is a win condition.")

print()
print("=" * 78)
print("7. THE FLOOR -- fastest conceivable Core kill")
print("=" * 78)
for name, _b, dmg, cd, _am, _hp, r2, _s in weapons[:2]:
    shots = -(-CORE // dmg)
    reach = int(r2 ** 0.5)
    for gap in (10, 15, 20, 25):
        walk = max(0, gap - reach)
        print("  %-9s core-gap %2d: walk %2d + build 1 + %2d rounds firing = turn %d"
              % (name, gap, walk, shots * cd, walk + 1 + shots * cd))
    print()
