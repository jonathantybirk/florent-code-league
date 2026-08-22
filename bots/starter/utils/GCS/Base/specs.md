# Overview
This module contains the GCS store standards and mechanics

# Slot usage
Slots are dedicated to units so one unit owns one slot. In cases where there are too many units, a round-robin can function as fallback, especially for launchers and turrets as they are less important than builders irt. to sharing info 
1: core
2: builder
… (prioritize builders getting a slot)

16: launchers/turrets (if there are empty slots they are given one each starting from 16 and going down until the last empty slot, new builder’s are prioritized to take over turret/launcher slots, until n (hyperparameter) slots are left for turrets/launchers). When there are too many builders (i.e. >15-n) or too many launcher/turrets (i.e. >min(,n) we do a round robin where some builders or turrets/launchers must share the same slot, that means they only get to use it every p rounds (calculated from the global round number, order can be determined from ID) where p is the amount sharing the same slot. This can be per-slot (I.e. 15 is shared by p=2, 16 is only used by p=1. Or 15 is shared by p=6 and 16 is shared by p=5)

# Info-sharing roles:
0: unless more important (free to be determined by a priority system which is a “hyperparameter”) things need to be communicated, all units should try to update everyone on the GCS store with their internal map. In their internal map (different module), it should be updated whether a piece of information has been shared already or not
1: Core will be the central memory system. When new builders are spawned, it assigns them a GCS ID (1-16) based on what is not already taken, and how long it will take to update the bot. Then it uses the bots GCS slot for the next 5-10 (hyperparameter, if not variable the core obviously need not announce how many rounds it will take) rounds and give it map updates including of course map symmetry and more.

# What if needed functionality outside the module’s scope isn’t implemented yet
Use placeholders and inform the user. Keep current implementation to the scope of the module. 

# How to embed
We have a single uint32 number per GCS slot (thus per unit). Instead of assigning bits, we can just assign what is necessary. I.e. if “what is the next message” is 5 potential message, don’t use 3 bits, just divide by 5 instead of 8, use modulo 5 instead of 8 etc. mixed-radix
# Embeddings
## encoder/decoder conventions (and convolutions??)
we need a convention for indicating the state of a tile, we could just make a convention for all possible tile states and enumerate/encode them: {1: “empty”, 2: “titanium_empty”, 3: “titanium_occupied_us”, 4: “titanium_occupied_theirs”, [...], 45: “enemy_turret_N”, 46: “enemy_turret_NW” [etc…] } which in turn can be decoded “locally” at each unit. with this, lookup and updating game state correspondingly would be O(1) for units, so satisfying 10ms max per unit remains  a negligible constraint. 
Another idea is taking common, super-tile patterns and compressing them into less bits such as a long path of enemy conveyors, which can be expressed as a starting coordinate, a cardinal direction, a length and obviously a compression marker, although it might be limited how often this representation is cheaper than just utilizing the already streamlined worker FOV tile order (read below) for relaying conveyer belt locations; Some simple experiments can decide this in minutes.

## builders
since these can move, they simply share their movements (5 possibilities) and the other units can then derive their exact location from this. Then, they also send updated info on all visible tiles in an embedding order we decide (reading direction of rows from top to bottom is likely the simplest, but doesn't really matter as long as we are consistent). the things it can update on includes but is likely not limited to: enemy workers, enemy core health, enemy turrets/sentinels (plus their directions, the worker also marks tiles in which it has been under fire if the adversary is not visible, but this is low-priority information to share), enemy miners, enemy conveyers, titanium ores, walls, enemy barriers, enemy launchers. Another important note is that fov can be obstructed by walls/barriers which should be accounted for (we don’t have info on tiles that are not in FOV)

Obviously also information negatives are important

### formatting
[message_type] x [detes] x [message_type] x [detes] etc… until filled
4 reserved for special messsage types (literally just the 4 last numbers, barely reduces the amount of information we can tell). One of these can e.g. be to tell everyone to not write to GCS next round because this unit wants to use all of them. 

## turrets 
- share if turning

## enemy builders
# TODO special embeddings for a builder moving so we don’t have to announce both the disappearance and appearance of a bot we see moving. Honestly, if a bot has moved it can be inferred that it must have been the one that was next to that spot one round ago.


