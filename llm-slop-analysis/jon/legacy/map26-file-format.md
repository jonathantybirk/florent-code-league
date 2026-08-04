# `.map26` File Format

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

*LLM-generated, not from the official site.* Reverse-engineered by hex-dumping bundled `.map26` files and writing a from-scratch varint/protobuf-field reader (no `.proto` schema is published; the official parser is bundled JS/wasm in the map editor).

## Wire schema

`.map26` map files (in `maps/`) are **protobuf**:

- field 1 (varint) = `width`
- field 2 (varint) = `height`
- field 3 (repeated, len-delim) = one per **row**, each holds field 1 = raw bytes, one byte per column (row-major, index = y, col = x)
- field 4 (repeated, len-delim) = **Cores**: field 1 = owner (1 or 2), field 3 = `{f1:x, f2:y}` (Team 2 also has field 2 = 1)

Tile byte values: **0 = EMPTY, 1 = WALL, 2 = ORE_TITANIUM**.

Maps are symmetric between the two starting corners, but **not always via 180° rotation** — some are mirrored horizontally, some vertically. Don't assume rotational symmetry when inferring one half of a map from the other; check the actual axis per map. The stored 2×2 Core block placement is generally mirrored/rotated consistently with the tile symmetry, but the single anchor tile the game records for a Core is just one corner of that block, so naively mirroring the anchor coordinate does not always land on the corresponding corner of the other team's block — verify against the actual second Core record rather than deriving it.

## Core geometry & teams

Each Core occupies a **2×2 block**; the stored `(x, y)` is the block's **top-left** tile, so render/reason about the sprite centered on the block (not the single tile). **Team A = owner 1 = gold, starts bottom-left**; Team B = owner 2 = top-right. Coordinate system (robot-api convention): `(0, 0)` = NW corner, x → east, y → south. Replay window flat sprites: A = `base_gold`, B = `base_silver`. Editor iso (dimetric): `base_team2` = gold, `base_team1` = blue — so owner 1 → `base_team2`. Default local map (no arg to `fcode run`) = **atoll** (first alphabetically).

**Iso Core sprite placement** (from map-editor JS): the `base_team*` art is a 3×3-footprint sprite drawn at **scale 2/3** (→ 2×2), origin `(0.5, 0.79375)`, placed at `projection.center(col+0.5, row+0.5)` — the 2×2 block centre (tile centre shifted +32px down in a 128×64 diamond). Forgetting the 2/3 scale makes the Core 1.5× too big / off-centre. Editor team colors: A = `0xFFC300` gold, B = `0x6EA0BF` blue.

## Parsing without a protobuf library

Just varint decode + wire-type dispatch (0 = varint, 1 = 64-bit, 2 = length-delimited, 5 = 32-bit) — no `protobuf` package needed:

```python
def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def fields(data: bytes, offset: int = 0, end: int | None = None):
    if end is None:
        end = len(data)
    out = []
    while offset < end:
        key, offset = read_varint(data, offset)
        field_number, wire_type = key >> 3, key & 0x07
        if wire_type == 0:
            value, offset = read_varint(data, offset)
        elif wire_type == 1:
            value, offset = data[offset:offset + 8], offset + 8
        elif wire_type == 2:
            length, offset = read_varint(data, offset)
            value, offset = data[offset:offset + length], offset + length
        elif wire_type == 5:
            value, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
        out.append((field_number, wire_type, value))
    return out
```

## Replay visualiser art (for rendering maps yourself)

Lives in `<fcode package>/data/visualiser/dimetric/`: 128×64 dimetric diamond tiles (sprite 128×160, floor-diamond center at `(64,127)`). Key sprites: `bg.png` (floor), `natural_wall.png` (wall), `titanium_ore.png` (ore), `base_team1.png`/`base_team2.png` (Cores, 3×3 = 384×480, anchor `(192,381)`). Compositing these reproduces the exact replay look — used to build the isometric renders in the [map atlas](../maps/map-atlas.md).

See [.replay26 file format](replay26-file-format.md) for the match-replay event-log format, which reuses this same map snapshot schema for its embedded starting board state.
