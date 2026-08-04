# Florent Code League — Map Atlas

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

*LLM-generated, not from the official site — see [.map26 file format](../reference/map26-file-format.md) for how this was produced.* Every map in the competition pool, shown in two views side by side — **isometric** (the map-editor's dimetric render) and **replay top-down** (the flat 2D replay style).

Maps are symmetric between the two starting corners, but not always via 180° rotation — some are mirrored horizontally, some vertically. Don't assume rotational symmetry when reasoning about one half of a map from the other. Each ranked match uses a randomly selected map from this pool. Locally, `fcode run` uses the first map alphabetically — **atoll** — unless you pass a map name or `--map-random`.

**Teams** — Team A (gold) always starts bottom-left · Team B (silver/blue) top-right. Each **Core occupies a 2×2 block** (its listed coordinate is the top-left tile). ◆ = titanium ore deposit; stone = walls (impassable, block line-of-sight).

| Map | Grid | Ore tiles | Wall tiles | Core A (gold) | Core B |
|---|---|---|---|---|---|
| [atoll](#atoll) | 18×18 | 8 | 18 | (2, 14) | (14, 2) |
| [aurora](#aurora) | 26×26 | 14 | 64 | (3, 22) | (21, 2) |
| [crossfire](#crossfire) | 16×16 | 10 | 24 | (2, 11) | (12, 3) |
| [duel](#duel) | 12×12 | 6 | 2 | (1, 8) | (9, 2) |
| [fjord](#fjord) | 20×20 | 12 | 20 | (2, 15) | (16, 3) |
| [hive](#hive) | 25×25 | 12 | 34 | (2, 20) | (21, 3) |
| [longship](#longship) | 28×20 | 16 | 40 | (2, 8) | (24, 8) |
| [pinch](#pinch) | 14×18 | 10 | 24 | (2, 2) | (2, 14) |
| [quarry](#quarry) | 24×24 | 22 | 8 | (2, 2) | (20, 20) |
| [runestone](#runestone) | 24×24 | 16 | 16 | (2, 11) | (20, 11) |
| [skerry](#skerry) | 22×22 | 12 | 24 | (2, 17) | (18, 3) |
| [sprint](#sprint) | 10×10 | 6 | 0 | (1, 1) | (7, 7) |
| [strait](#strait) | 20×26 | 12 | 64 | (2, 2) | (2, 22) |
| [twins](#twins) | 21×21 | 13 | 16 | (2, 2) | (2, 17) |
| [vault](#vault) | 24×24 | 10 | 26 | (2, 19) | (20, 3) |

---

## atoll

**18×18** · 8 ore · 18 walls · Core A (2, 14) · Core B (14, 2)

<table><tr>
<td align="center"><img src="atoll-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="atoll-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## aurora

**26×26** · 14 ore · 64 walls · Core A (3, 22) · Core B (21, 2)

<table><tr>
<td align="center"><img src="aurora-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="aurora-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## crossfire

**16×16** · 10 ore · 24 walls · Core A (2, 11) · Core B (12, 3)

<table><tr>
<td align="center"><img src="crossfire-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="crossfire-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## duel

**12×12** · 6 ore · 2 walls · Core A (1, 8) · Core B (9, 2)

<table><tr>
<td align="center"><img src="duel-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="duel-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## fjord

**20×20** · 12 ore · 20 walls · Core A (2, 15) · Core B (16, 3)

<table><tr>
<td align="center"><img src="fjord-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="fjord-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## hive

**25×25** · 12 ore · 34 walls · Core A (2, 20) · Core B (21, 3)

<table><tr>
<td align="center"><img src="hive-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="hive-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## longship

**28×20** · 16 ore · 40 walls · Core A (2, 8) · Core B (24, 8)

<table><tr>
<td align="center"><img src="longship-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="longship-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## pinch

**14×18** · 10 ore · 24 walls · Core A (2, 2) · Core B (2, 14)

<table><tr>
<td align="center"><img src="pinch-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="pinch-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## quarry

**24×24** · 22 ore · 8 walls · Core A (2, 2) · Core B (20, 20)

<table><tr>
<td align="center"><img src="quarry-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="quarry-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## runestone

**24×24** · 16 ore · 16 walls · Core A (2, 11) · Core B (20, 11)

<table><tr>
<td align="center"><img src="runestone-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="runestone-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## skerry

**22×22** · 12 ore · 24 walls · Core A (2, 17) · Core B (18, 3)

<table><tr>
<td align="center"><img src="skerry-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="skerry-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## sprint

**10×10** · 6 ore · 0 walls · Core A (1, 1) · Core B (7, 7)

<table><tr>
<td align="center"><img src="sprint-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="sprint-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## strait

**20×26** · 12 ore · 64 walls · Core A (2, 2) · Core B (2, 22)

<table><tr>
<td align="center"><img src="strait-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="strait-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## twins

**21×21** · 13 ore · 16 walls · Core A (2, 2) · Core B (2, 17)

<table><tr>
<td align="center"><img src="twins-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="twins-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>

## vault

**24×24** · 10 ore · 26 walls · Core A (2, 19) · Core B (20, 3)

<table><tr>
<td align="center"><img src="vault-iso.png" width="460"><br><sub>Isometric</sub></td>
<td align="center"><img src="vault-flat.png" width="380"><br><sub>Replay top-down</sub></td>
</tr></table>
