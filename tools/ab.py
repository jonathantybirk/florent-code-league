"""A/B two bots over the map pool, both seats, N seeds. Streams a CSV as it goes.

    uv run python tools/ab.py bots/jon/sigrun bots/rivals/bryn109 --seeds 1 --jobs 10
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
WINNER = re.compile(r"Winner:\s+(\S+)")


def maps_available() -> list[str]:
    return sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))


def play(a: str, b: str, m: str, seed: int, tle: int):
    cmd = [str(ROOT / ".venv/bin/fcode"), "run", a, b, f"maps/{m}.map26", "--seed", str(seed),
           "--replay", f"/tmp/ab-{a.rsplit('/',1)[-1]}-{b.rsplit('/',1)[-1]}-{m}-{seed}.replay26"]
    if tle:
        cmd += ["--tle", str(tle)]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900).stdout
    except subprocess.TimeoutExpired:
        return None
    mo = WINNER.search(out)
    if not mo:
        return None
    return a if mo.group(1) == a.rsplit("/", 1)[-1] else b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bot"); ap.add_argument("opp", help="comma list of opponents")
    ap.add_argument("--maps", default="")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=10)
    ap.add_argument("--tle", type=int, default=0)
    ap.add_argument("--csv", default="")
    args = ap.parse_args()

    maps = args.maps.split(",") if args.maps else maps_available()
    opps = args.opp.split(",")
    jobs = [(o, m, s, seat) for o in opps for m in maps
            for s in range(1, args.seeds + 1) for seat in "AB"]

    def run_one(j):
        o, m, s, seat = j
        a, b = (args.bot, o) if seat == "A" else (o, args.bot)
        return (o, m, s, seat, play(a, b, m, s, args.tle))

    w = l = u = 0
    per_map: dict[str, list[int]] = {}
    per_opp: dict[str, list[int]] = {o: [0, 0, 0] for o in opps}
    rows = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for i, (o, m, s, seat, res) in enumerate(ex.map(run_one, jobs), 1):
            r = per_map.setdefault(m, [0, 0, 0])
            ro = per_opp[o]
            if res is None:
                u += 1; r[2] += 1; ro[2] += 1; tag = "?"
            elif res == args.bot:
                w += 1; r[0] += 1; ro[0] += 1; tag = "W"
            else:
                l += 1; r[1] += 1; ro[1] += 1; tag = "L"
            rows.append(f"{o},{m},{s},{seat},{tag}")
            if i % 20 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  {w}-{l} ({u}?)  {time.time()-t0:.0f}s", flush=True)

    print(f"\n{args.bot}: {w}-{l} ({u} unresolved) over {len(jobs)} games\n")
    for o in opps:
        a, b, c = per_opp[o]
        print(f"  {o:40s} {a:4d}-{b:<4d} {(a/(a+b) if a+b else 0):6.3f}" + (f"  ({c}?)" if c else ""))
    print()
    bad = [(m, r) for m, r in sorted(per_map.items()) if r[1] > r[0]]
    if bad:
        print("maps where we are behind:")
        for m, r in bad:
            print(f"  {m:16s} {r[0]}-{r[1]}" + (f" ({r[2]}?)" if r[2] else ""))
    if args.csv:
        pathlib.Path(args.csv).write_text("opp,map,seed,seat,result\n" + "\n".join(rows) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
