"""Compare the clone's own replays against Pantheon's measured profile."""
import glob, os, sys, collections, statistics
import decode


def profile(paths, side_of):
    build_prefix = collections.Counter()
    throws = collections.Counter()
    throw_rounds = collections.Counter()
    throw_rangesq = collections.Counter()
    launcher_life = collections.Counter()
    gunner_radius = collections.Counter()
    kill_round = []

    for p in paths:
        side = side_of(p)
        r = decode.decode(p)
        cores = {c.get("team", "TEAM_A"): c for c in r["map"]["cores"]}
        other = "TEAM_B" if side == "TEAM_A" else "TEAM_A"
        if side not in cores or other not in cores:
            continue
        enemy_core = cores[other]["pos"]
        enemy_core_id = cores[other]["id"]
        ents, posn, builds, deaths = {}, {}, [], {}
        launchers = []
        for rnd, ups in enumerate(r["turns"]):
            for u in ups:
                if "placeEntity" in u:
                    e = u["placeEntity"]["entity"]
                    t = e.get("team", "TEAM_A")
                    k = decode.entity_kind(e)
                    pos = decode.pos(e.get("position", {}))
                    ents[e["id"]] = (t, k, rnd)
                    posn[e["id"]] = pos
                    if t == side:
                        builds.append((rnd, k, pos))
                        if k == "launcher":
                            launchers.append((e["id"], rnd, pos))
                        if k == "gunner":
                            gunner_radius[max(abs(pos[0]-enemy_core[0]),
                                              abs(pos[1]-enemy_core[1]))] += 1
                elif "moveBuilderBot" in u:
                    mv = u["moveBuilderBot"]
                    i = mv["id"]
                    to = decode.pos(mv.get("to", {}))
                    frm = posn.get(i)
                    posn[i] = to
                    if frm and ents.get(i, ("", "", 0))[0] == side:
                        if max(abs(to[0]-frm[0]), abs(to[1]-frm[1])) > 1:
                            throw_rounds[rnd] += 1
                            if launchers:
                                lp = launchers[0][2]
                                throw_rangesq[(to[0]-lp[0])**2 + (to[1]-lp[1])**2] += 1
                elif "removeEntity" in u:
                    deaths.setdefault(u["removeEntity"]["id"], rnd)
        build_prefix[tuple((rr, kk) for rr, kk, _ in builds if rr < 4)] += 1
        n = sum(1 for rr in throw_rounds.elements() if True)
        for lid, lr, lp in launchers:
            d = deaths.get(lid)
            launcher_life[(d - lr) if d is not None else "survives"] += 1
        if enemy_core_id in deaths:
            kill_round.append(deaths[enemy_core_id])
    return dict(build_prefix=build_prefix, throw_rounds=throw_rounds,
                throw_rangesq=throw_rangesq, launcher_life=launcher_life,
                gunner_radius=gunner_radius, kill_round=kill_round)


def show(name, p):
    print(f"=== {name} ===")
    top = p["build_prefix"].most_common(2)
    tot = sum(p["build_prefix"].values())
    for s, n in top:
        print(f"  opening r0-3 ({n}/{tot}): {[f'{r}:{k}' for r, k in s]}")
    print(f"  throw rounds: {sorted(p['throw_rounds'].items())[:8]}")
    rs = p["throw_rangesq"]
    if rs:
        atmax = sum(v for k, v in rs.items() if k >= 25)
        print(f"  throws at max range (dist_sq>=25): {100*atmax/sum(rs.values()):.0f}%"
              f"  max seen {max(rs)}")
    print(f"  launcher lifetime: {p['launcher_life'].most_common(4)}")
    gr = p["gunner_radius"]
    if gr:
        near = sum(v for k, v in gr.items() if 2 <= k <= 4)
        print(f"  gunners at enemy-core radius 2-4: {100*near/sum(gr.values()):.0f}%"
              f"  (n={sum(gr.values())})")
    kr = p["kill_round"]
    if kr:
        print(f"  enemy core killed in {len(kr)} games, median round {statistics.median(kr):.0f}")
