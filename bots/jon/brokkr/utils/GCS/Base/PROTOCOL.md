# GCS wire protocol (generated from protocol.py)

## Reserved raw values

- payload space: 0 .. 4294966779
- IDLE_A=4294967295, IDLE_B=4294967294 (reserved, unused: the store never idles)
- free: 4294967293, 4294967292
- Core HP block: 4294966780 + h (h=0..500), announced on >50 HP drift

## Layouts (most-significant field first)

| sender | layout | cost | headroom |
|---|---|---|---|
| builder_bot | move(5) · fact_a(7314) · fact_b(7314) · aux(16) | 4,279,567,680 | 1.00x |
| gunner | speaker(2) · turn(3) · fact_a(4770) · fact_b(4770) | 136,517,400 | 31.46x |
| sentinel | speaker(2) · fact_a(10706) · fact_b(10706) | 229,236,872 | 18.74x |
| launcher | speaker(2) · fact_a(9434) · fact_b(9434) | 178,000,712 | 24.13x |
| core | fact_a(11978) · fact_b(11978) | 143,472,484 | 29.94x |

## Tile states

| code | name |
|---|---|
| 0 | UNKNOWN |
| 1 | EMPTY |
| 2 | WALL |
| 3 | ORE_FREE |
| 4 | OUR_HARVESTER |
| 5 | OUR_BARRIER |
| 6 | OUR_CONVEYOR_N |
| 7 | OUR_CONVEYOR_E |
| 8 | OUR_CONVEYOR_S |
| 9 | OUR_CONVEYOR_W |
| 10 | OUR_SPLITTER_N |
| 11 | OUR_SPLITTER_E |
| 12 | OUR_SPLITTER_S |
| 13 | OUR_SPLITTER_W |
| 14 | OUR_GUNNER_N |
| 15 | OUR_GUNNER_NE |
| 16 | OUR_GUNNER_E |
| 17 | OUR_GUNNER_SE |
| 18 | OUR_GUNNER_S |
| 19 | OUR_GUNNER_SW |
| 20 | OUR_GUNNER_W |
| 21 | OUR_GUNNER_NW |
| 22 | OUR_SENTINEL_N |
| 23 | OUR_SENTINEL_NE |
| 24 | OUR_SENTINEL_E |
| 25 | OUR_SENTINEL_SE |
| 26 | OUR_SENTINEL_S |
| 27 | OUR_SENTINEL_SW |
| 28 | OUR_SENTINEL_W |
| 29 | OUR_SENTINEL_NW |
| 30 | OUR_LAUNCHER |
| 31 | OUR_CORE |
| 32 | OUR_BUILDER_BOT |
| 33 | ENEMY_HARVESTER |
| 34 | ENEMY_BARRIER |
| 35 | ENEMY_CONVEYOR_N |
| 36 | ENEMY_CONVEYOR_E |
| 37 | ENEMY_CONVEYOR_S |
| 38 | ENEMY_CONVEYOR_W |
| 39 | ENEMY_SPLITTER_N |
| 40 | ENEMY_SPLITTER_E |
| 41 | ENEMY_SPLITTER_S |
| 42 | ENEMY_SPLITTER_W |
| 43 | ENEMY_GUNNER_N |
| 44 | ENEMY_GUNNER_NE |
| 45 | ENEMY_GUNNER_E |
| 46 | ENEMY_GUNNER_SE |
| 47 | ENEMY_GUNNER_S |
| 48 | ENEMY_GUNNER_SW |
| 49 | ENEMY_GUNNER_W |
| 50 | ENEMY_GUNNER_NW |
| 51 | ENEMY_SENTINEL_N |
| 52 | ENEMY_SENTINEL_NE |
| 53 | ENEMY_SENTINEL_E |
| 54 | ENEMY_SENTINEL_SE |
| 55 | ENEMY_SENTINEL_S |
| 56 | ENEMY_SENTINEL_SW |
| 57 | ENEMY_SENTINEL_W |
| 58 | ENEMY_SENTINEL_NW |
| 59 | ENEMY_LAUNCHER |
| 60 | ENEMY_CORE |
| 61 | ENEMY_BUILDER_BOT |
| 62 | OUR_BOT_ON_CONVEYOR_N |
| 63 | OUR_BOT_ON_CONVEYOR_E |
| 64 | OUR_BOT_ON_CONVEYOR_S |
| 65 | OUR_BOT_ON_CONVEYOR_W |
| 66 | ENEMY_BOT_ON_CONVEYOR_N |
| 67 | ENEMY_BOT_ON_CONVEYOR_E |
| 68 | ENEMY_BOT_ON_CONVEYOR_S |
| 69 | ENEMY_BOT_ON_CONVEYOR_W |
| 70 | TOOK_FIRE_HERE |
| 71 | CONVEYOR_ISSUE |
| 72 | HARVESTER_ISSUE |
| 103 | ESCAPE_RUN |
| 104 | ESCAPE_REMOTE |
| 105 | ESCAPE_CONTROL |
| 73..102 | (spare) |

## Field values

- move: 0=NONE, 1=N, 2=E, 3=S, 4=W
- turn: 0=NONE, 1=CW, 2=CCW  (Gunners only; one step per round by convention)
- speaker: 0=SELF, 1=CORE
- aux: GCS slot id granted to the friendly turret/launcher named by a fact in the same message; 0 = no grant

## Control kinds

| kind | args |
|---|---|
| ASSIGN | slot(16) · period(8) · phase(8) |
| SYMMETRY | kind(3): MIRROR_X / MIRROR_Y / ROT_180 |
| DIRECTIVE | x(W) · y(H) · task(24) |

task: 0=FIX_HARVESTER (unaddressed, any sender), 1-15=FIX_CONVEYOR for the builder in that slot (Core only), 16=BUILD_HERE, 17=SCOUT_HERE, 18=DEFEND_HERE, 19-23 spare

