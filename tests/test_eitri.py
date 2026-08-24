import sys
from pathlib import Path

EITRI = Path(__file__).resolve().parents[1] / "bots" / "jon" / "eitri"
sys.path.insert(0, str(EITRI))

import atlas_data  # noqa: E402
import board  # noqa: E402
import builder  # noqa: E402
import crew  # noqa: E402
import network  # noqa: E402
import orders  # noqa: E402
from fcode import EntityType  # noqa: E402


def test_every_map_assigns_every_lane_with_one_to_four_builders():
    for name, (width, height, rows, seats) in atlas_data.MAPS.items():
        for seat in range(2):
            terrain = board.Board(name, width, height, rows,
                                  seats[seat], seats[1 - seat])
            picks, field = network.survey(terrain)
            preferred = orders.get(name, terrain.home)
            if preferred is not None:
                assert frozenset(preferred) == frozenset(picks)
            lanes = network.lay(terrain, preferred or picks, field)
            for count in range(1, 5):
                work, spawns, done = crew.assign(terrain, lanes, count)
                assigned = [lane for builder in work for lane in builder]
                assert sorted(assigned) == list(range(len(lanes)))
                assert len(work) == len(spawns) == count
                assert len(done) == len(lanes)


def test_parked_builder_only_yields_to_persistent_friendly_traffic():
    class Sight:
        nearby = [7]

        def get_nearby_units(self, _distance):
            return self.nearby

        def get_position(self, _unit):
            return (2, 1)

        def get_team(self, unit=None):
            return "A" if unit in (None, 7) else "B"

        def get_entity_type(self, _unit):
            return EntityType.BUILDER_BOT

    sight = Sight()
    worker = builder.Crewman()
    assert not builder._traffic(sight, worker, (1, 1))
    assert not builder._traffic(sight, worker, (1, 1))
    assert builder._traffic(sight, worker, (1, 1))
    sight.nearby = []
    assert not builder._traffic(sight, worker, (1, 1))
