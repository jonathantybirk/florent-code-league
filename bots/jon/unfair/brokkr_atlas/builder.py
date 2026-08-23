"""What one Builder does with its turn.

The order below is the whole policy, and it is an ordering rule rather than a
contest: each branch answers "is this my job this round", and the first that
says yes spends the turn. Anything that is not mining gives its deposit back
first, so a Builder recalled to heal does not keep a lane reserved that
nobody is walking to.

The siege outranks mending because an attacker recalled is an attacker that
never arrives. Mending does not outrank harassment: tried the other way round,
measured 48/90 against hildr_best and 38/90 against steward where the order
here measures 60/90 against both. A cut belt is worth more than it looks --
it is damage the enemy has to spend Builder-turns repairing, and those turns
come out of the same budget as their attack.

Who is a mender, a harasser, an attacker or a miner is roster.py's decision,
taken from the spawn index alone so the Core and the Builder always agree.
"""
import debug
import store
from assault import besiege
from harassing import harass_turn
from mending import mend
from mining import mine


def run(player, ct) -> None:
    brain = player.brain
    brain.sense(ct)

    if brain.index is None:
        brain.index = store.claim_index(ct)
        debug.log(f"r{brain.round} b{ct.get_id()} INDEX={brain.index}")
    gossip(brain, ct)

    # The siege outranks mending. An attacker recalled to heal is an attacker
    # that never arrives, and against an economy the healing exchange is one
    # we lose anyway -- they can afford to spend more on damage than we can on
    # repair. The Builders that mend are chosen by roster.is_mender, which
    # never picks an attacker, so this is an ordering rule and not a contest.
    # Anything that is not mining gives its deposit back first. See
    # store.release_claim.
    if besiege(player, ct):
        store.release_claim(ct, brain.index)
        brain.job = None
        return
    if harass_turn(player, ct):
        store.release_claim(ct, brain.index)
        brain.job = None
        return
    if mend(player, ct):
        store.release_claim(ct, brain.index)
        brain.job = None
        return
    mine(player, ct)


def gossip(brain, ct) -> None:
    """Read the ore bulletin, then add one deposit of our own to it.

    Traced on stavkirke, Builders spawned on rounds 2-4 wandered until round
    12 with no deposit in sight, while the Core -- which sees radius 6 from
    round 0 -- had been looking at ore the whole time and had no way to say
    so. Sharing deposits is the cheapest thing the store can carry and it is
    what the opening was missing.
    """
    brain.sync_symmetry(ct, store)
    board = store.ore_board(ct)
    brain.learn_ore(board)
    spare = brain.unreported_ore(board)
    if spare is not None:
        store.publish_ore(ct, brain.index, spare)
