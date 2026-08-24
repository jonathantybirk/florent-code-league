"""Regenerate Tempest Oracle's import-only terrain atlas."""

from pathlib import Path
import sys

from fcode import Environment


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bots/jon/unfair/lockin"))
from utils.map import _parse_map_file  # noqa: E402

TARGET = ROOT / "bots/jon/unfair/tempest_oracle_ferry/atlas_data.py"
SYMBOL = {Environment.EMPTY: ".", Environment.WALL: "#",
          Environment.ORE_TITANIUM: "O"}


def main():
    maps = {}
    for path in sorted((ROOT / "maps").glob("*.map26")):
        known = _parse_map_file(path)
        maps[path.stem] = tuple(
            "".join(SYMBOL[tile] for tile in row)
            for row in known.environments
        )
    TARGET.write_text(
        '"""Generated static terrain for the published official map pool."""\n\n'
        f"ROWS = {maps!r}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
