import sys
from pathlib import Path

EITRI = Path(__file__).resolve().parents[1] / "bots" / "jon" / "eitri"
sys.path.insert(0, str(EITRI))

import atlas_data  # noqa: E402
import board  # noqa: E402
import crew  # noqa: E402
import network  # noqa: E402


def test_every_map_assigns_every_lane_with_one_to_four_builders():
    for name, (width, height, rows, seats) in atlas_data.MAPS.items():
        terrain = board.Board(name, width, height, rows, seats[0], seats[1])
        picks, field = network.survey(terrain)
        lanes = network.lay(terrain, picks, field)
        for count in range(1, 5):
            work, spawns, done = crew.assign(terrain, lanes, count)
            assigned = [lane for builder in work for lane in builder]
            assert sorted(assigned) == list(range(len(lanes)))
            assert len(work) == len(spawns) == count
            assert len(done) == len(lanes)
