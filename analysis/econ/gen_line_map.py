"""24x24 rot-180 map: cores at (2,2)/(20,20), one ore per team at distance d east."""
import sys
sys.path.insert(0, 'analysis/econ')
from maplib import EMPTY, ORE, write_map_with_cores

W = H = 24


def gen(d, path):
    rows = [[EMPTY] * W for _ in range(H)]
    rows[2][2 + d] = ORE                       # team A ore, row y=2
    rows[H - 1 - 2][W - 1 - (2 + d)] = ORE     # rot-180 mirror
    write_map_with_cores(path, rows, (2, 2), (20, 20))


if __name__ == "__main__":
    for d in range(3, 16):
        gen(d, f"maps/_line{d}.map26")
    print("wrote", list(range(3, 16)))
