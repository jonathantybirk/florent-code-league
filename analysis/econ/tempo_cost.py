"""Tempo (how fast income arrives) and the titanium/scale price of builders."""
import sys
sys.path.insert(0, 'analysis/econ')
from mapstats import CORES
from simfog import simulate

HORIZONS = [150, 250, 400, 1000]
NBS = [1, 2, 3, 4]


def revenue_by(connected, horizon):
    return sum(2.5 * (horizon - c) for c, _ in connected if c < horizon)


if __name__ == "__main__":
    agg = {(n, hz): 0.0 for n in NBS for hz in HORIZONS}
    finish = {n: [] for n in NBS}
    for m in CORES:
        for n in NBS:
            _, c, t, ev = simulate(m, n)
            for hz in HORIZONS:
                agg[(n, hz)] += revenue_by(ev, hz)
            finish[n].append(max((r for r, _ in ev), default=0))
    print("Titanium delivered by round H, summed over all 15 maps (fog sim):")
    print(f"{'':>6}" + "".join(f"{f'H={h}':>12}" for h in HORIZONS))
    for n in NBS:
        print(f"NB={n:<3}" + "".join(f"{agg[(n,h)]:>12.0f}" for h in HORIZONS))
    print(f"{'':>6}" + "".join(f"{'':>12}" for h in HORIZONS))
    for n in NBS[1:]:
        print(f"NB={n} vs NB=1:" + "".join(
            f"{100*agg[(n,h)]/agg[(1,h)]-100:>10.1f}%" for h in HORIZONS))
    print()
    print("Round at which the last deposit is connected (median over maps):")
    for n in NBS:
        f = sorted(finish[n])
        print(f"  NB={n}: median={f[len(f)//2]:>4}  max={max(f):>4}")

    print()
    print("Price of a builder (scale is one global additive pool):")
    print("  cash: floor(30 * scale/100). At 120% that is 36 Ti; at 200%, 60 Ti.")
    print("  scale: +20 points, permanently, on EVERY later purchase.")
    for base_spend in (300, 400, 600):
        print(f"    a later build-out with {base_spend} Ti of base cost pays an extra "
              f"{0.20*base_spend:.0f} Ti per builder")
    print("  a harvester is +5 and a conveyor +1, so one builder costs as much")
    print("  scale as 4 harvesters or 20 conveyors.")
