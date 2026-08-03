"""Gunner: fire down the lane it was built pointing at."""


def run(player, ct) -> None:
    target = ct.get_gunner_target()
    if target is not None and ct.can_fire(target):
        ct.fire(target)
