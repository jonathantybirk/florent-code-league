#!/bin/sh
# Keep bots/jon/unfair/brokkr_atlas byte-identical to bots/jon/brokkr except
# for mapdata.py, so the pair measures exactly what map knowledge is worth.
set -e
root=$(git rev-parse --show-toplevel)
src="$root/bots/jon/brokkr"
dst="$root/bots/jon/unfair/brokkr_atlas"
rm -rf "$dst/utils"
cp "$src"/*.py "$dst/"
cp -R "$src/utils" "$dst/utils"
uv run python "$root/tools/build_mapdata.py" >/dev/null
find "$dst" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "synced $dst"
