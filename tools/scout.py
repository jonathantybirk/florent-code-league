"""Sample the live ladder with unrated matches, choosing opponents that actually teach us something.

The platform allows five unrated matches per ten minutes and they cost no rating, so the binding
resource is not titanium or CPU but INFORMATION. Firing five at random wastes most of it: beating
rank 20 for the fourth time tells us nothing we did not already know.

WHAT WE ARE ESTIMATING
    For each opponent, the probability our bot wins a game -- and, separately, the probability our
    RUSH lands, which is the thing the bot is actually built to do. A match we win 3-2 after four
    300-round grinds is a different animal from one we win 5-0 by round 40, and the aggregate score
    hides that completely.

HOW OPPONENTS ARE CHOSEN  (UCB1, the standard bandit rule)

    score(t) = p_hat(t) + C * sqrt( ln(N) / n(t) )   ... then re-ranked by INFORMATION, below

    Straight UCB1 chases the opponents we beat most, which is backwards here: we already know we
    beat them. What we want is the opponent whose outcome we are least able to predict, because
    that is where a sample moves our estimate furthest. So the ranking is

        value(t) = uncertainty(t) * relevance(t)

    uncertainty  = p_hat * (1 - p_hat) + exploration bonus   -- maximal at a 50/50 matchup, and
                   large for anyone barely sampled
    relevance    = weight by how close their rating is to ours, since those are the teams whose
                   games decide our rank; a 2323 and a 1500 both tell us little about rank 32

    That is a Bayesian-experiment-design reading of the same bandit machinery: maximise expected
    information about the decision we face (will this build climb?), not expected reward.

RUSH-FAILURE VALUE FUNCTION
    Per game we record whether the Core died and on what round. A rush that lands does so by ~70
    (median 37 against a passive opponent, worst 67 across the pool), so:

        landed   = core destroyed at or before RUSH_DEADLINE
        stalled  = core destroyed later -- we won, but the rush did not do it
        failed   = no Core destroyed, or ours died

    The failure rate per opponent is the single most diagnostic number we have: it separates "they
    out-heal our ring" from "they kill our Builder on the way in".

USAGE
    python tools/scout.py fire          pick and launch up to 5 (respects the rate limit)
    python tools/scout.py collect       harvest finished matches into the log
    python tools/scout.py report        show what we know, sorted by rush-failure rate
    python tools/scout.py loop          collect, then fire -- the thing to run every 10 minutes
"""

import json
import pathlib
import re
import subprocess
import sys
import math

ROOT = pathlib.Path(__file__).resolve().parent.parent
FCODE = str(ROOT / ".venv" / "Scripts" / "fcode.exe")
LOG = ROOT / "tournament" / "scrim-log.json"
US = "Powered by SmartFridge"

BATCH = 5                 # platform cap per 10 minutes
RUSH_DEADLINE = 80        # a rush that has not killed by here did not land
RATING_SCALE = 250.0      # how quickly relevance decays with rating distance
EXPLORE = 0.35            # uncertainty floor for an opponent we have barely played


def run(*args, timeout=180):
    try:
        return subprocess.run([FCODE] + list(args), capture_output=True,
                              text=True, timeout=timeout).stdout
    except Exception as exc:
        return "ERROR %s" % exc


def load():
    if LOG.exists():
        return json.loads(LOG.read_text(encoding="utf-8"))
    return {"opponents": {}, "pending": {}, "our_rating": 1500.0}


def save(state):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def ladder(limit=30):
    out = run("ladder", "--limit", str(limit), "--json")
    try:
        rows = json.loads(out)
    except Exception:
        return []
    return [(r["teamId"], r["teamName"], float(r["rating"]), int(r["_rank"])) for r in rows]


def our_rating():
    out = run("status")
    m = re.search(r"Rating:\s+(\d+)", out)
    return float(m.group(1)) if m else 1500.0


# ---------------------------------------------------------------- selection
def value(rec, ours, total_played):
    """Uncertainty about this matchup, weighted by how much it bears on our rank."""
    n = rec.get("games", 0)
    wins = rec.get("wins", 0)
    p = (wins + 1.0) / (n + 2.0)                      # Laplace, so 0 games is not 0 or 1
    uncertainty = p * (1.0 - p)
    if n == 0:
        uncertainty += EXPLORE
    else:
        uncertainty += EXPLORE * math.sqrt(math.log(max(total_played, 2)) / n) / 3.0
    gap = abs(rec.get("rating", ours) - ours)
    relevance = math.exp(-(gap / RATING_SCALE) ** 2)
    return uncertainty * relevance


def pick(state, pool):
    ours = state.get("our_rating", 1500.0)
    total = sum(r.get("games", 0) for r in state["opponents"].values())
    scored = []
    for tid, name, rating, rank in pool:
        rec = state["opponents"].setdefault(tid, {"name": name, "rating": rating,
                                                  "rank": rank, "games": 0, "wins": 0,
                                                  "landed": 0, "stalled": 0, "failed": 0})
        rec["name"], rec["rating"], rec["rank"] = name, rating, rank
        if tid in state["pending"].values():
            continue
        scored.append((value(rec, ours, total), tid, name, rating))
    scored.sort(reverse=True)
    return scored[:BATCH]


# ---------------------------------------------------------------- collection
def collect(state):
    done = []
    for mid, tid in list(state["pending"].items()):
        out = run("match", "info", mid)
        if "Status:  complete" not in out:
            continue
        a = re.search(r"Team A:\s+(.*?)\s+\(", out)
        if not a:
            done.append(mid)
            continue
        we_are_a = US in a.group(1)
        rec = state["opponents"].setdefault(tid, {"games": 0, "wins": 0, "landed": 0,
                                                  "stalled": 0, "failed": 0})
        # Split on the column separator instead of pattern-matching the winner cell. A regex that
        # tried to read "A (Team Name)" broke on the team actually called O(1): the bracket inside
        # the name ended the capture early, the row failed to match, and the game was silently
        # dropped. It dropped only games the OPPONENT won, because our own name has no bracket --
        # so O(1) logged as 3 games at 100% when it was 5 games at 60%. Parsing that fails loudly
        # is fine; parsing that fails in our favour is how a bot looks better than it is.
        for line in out.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 5 or not cells[0].isdigit() or not cells[4].isdigit():
                continue
            _map, winner, condition, turns = cells[1], cells[2], cells[3], int(cells[4])
            if not winner.startswith(("A ", "B ")):
                continue
            we_won = (winner[0] == "A") == we_are_a
            rec["games"] += 1
            if we_won:
                rec["wins"] += 1
                if "Core" in condition and turns <= RUSH_DEADLINE:
                    rec["landed"] += 1
                else:
                    rec["stalled"] += 1
            else:
                rec["failed"] += 1
        done.append(mid)
    for mid in done:
        state["pending"].pop(mid, None)
    return len(done)


def fire(state):
    pool = ladder()
    if not pool:
        print("could not read the ladder")
        return
    state["our_rating"] = our_rating()
    launched = 0
    for score, tid, name, rating in pick(state, pool):
        out = run("match", "unrated", tid)
        mid = re.search(r"Match ID: ([a-f0-9-]+)", out)
        if mid:
            state["pending"][mid.group(1)] = tid
            launched += 1
            print("  fired  %-26s %5.0f  value=%.3f" % (name[:26], rating, score))
        elif "Rate limit" in out:
            print("  rate limited after %d" % launched)
            break
        else:
            print("  failed %-26s %s" % (name[:26], out.strip()[:60]))
    print("launched %d, %d pending" % (launched, len(state["pending"])))


def report(state):
    ours = state.get("our_rating", 1500.0)
    rows = [(r.get("rank", 99), t, r) for t, r in state["opponents"].items()
            if r.get("games", 0)]
    rows.sort()
    print("our rating %.0f | rush lands = Core destroyed by round %d" % (ours, RUSH_DEADLINE))
    print("%-26s %5s %4s %6s  %6s %7s %6s  %s" % (
        "opponent", "elo", "rank", "games", "win%", "landed", "stalled", "RUSH FAILS"))
    for rank, tid, r in rows:
        n = r["games"]
        fails = n - r["landed"]
        print("%-26s %5.0f %4d %6d  %5.0f%% %7d %6d  %5.0f%%" % (
            r.get("name", tid)[:26], r.get("rating", 0), rank, n,
            100.0 * r["wins"] / n, r["landed"], r["stalled"], 100.0 * fails / n))


def refresh(state):
    """Attach names, ratings and ranks from the live ladder to whatever we have logged."""
    for tid, name, rating, rank in ladder(40):
        rec = state["opponents"].get(tid)
        if rec is not None:
            rec["name"], rec["rating"], rec["rank"] = name, rating, rank


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    state = load()
    refresh(state)
    if cmd in ("collect", "loop"):
        got = collect(state)
        print("collected %d finished match(es)" % got)
    if cmd in ("fire", "loop"):
        fire(state)
    save(state)
    if cmd in ("report", "loop"):
        report(state)


if __name__ == "__main__":
    main()
