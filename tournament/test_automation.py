"""Tests for the multi-branch discover-evaluate-publish loop.

Nothing here touches the cluster or the website: the parts worth testing are which bots each
branch contributes, that an implementation already rated from one branch is never scheduled again
from another, and that an existing single-branch state file survives the upgrade.
"""

from __future__ import annotations

import csv
import json

import pytest

from tournament.automation import DEFAULT_SOURCES, STATE_VERSION, Source


def test_source_parses_branch_and_prefix():
    source = Source.parse("x/jon:bots/jon")
    assert (source.branch, source.prefix, source.excludes) == ("x/jon", "bots/jon", ())
    assert source.ref == "origin/x/jon"


def test_source_parses_excludes():
    source = Source.parse("elias_dev:bots:bots/rivals/*,bots/probes/*")
    assert source.excludes == ("bots/rivals/*", "bots/probes/*")


def test_source_rejects_malformed_input():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        Source.parse("x/jon")


def test_default_sources_cover_the_active_branches():
    assert {source.branch for source in DEFAULT_SOURCES} == {
        "x/jon", "x/luc", "elias_dev", "viktor",
    }
    # Every source is scoped under bots/. Contributors with their own directory get that subtree,
    # so vendored copies of rivals are never discovered; viktor works at the top level and instead
    # names its non-entrants explicitly.
    assert all(source.prefix.startswith("bots") for source in DEFAULT_SOURCES)
    for source in DEFAULT_SOURCES:
        assert source.prefix.startswith("bots/") or source.excludes


def test_state_v1_migrates_to_multi_branch(tmp_path, monkeypatch):
    """An installed evaluator has a v1 state file; upgrading must not discard its ledger."""
    from tournament import automation

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "version": 1,
        "canonical_run": "some-run",
        "canonical_bots": {"a@1111111": {"name": "a", "commit": "1" * 40, "path": "bots/x/a"}},
        "tested_hashes": {"deadbeef": {"representative": "a@1111111", "aliases": []}},
        "last_seen_ref": "f" * 40,
    }))

    seen = {}

    def fake_run(command, cwd=None):
        seen["fetched"] = command
        return ""

    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation, "discover", lambda *a, **k: [])

    code = automation.run_once(
        state_path=state_path,
        canonical_run=None,
        sources=DEFAULT_SOURCES,
        fetch_remote="origin",
        site_repo=tmp_path,
        publish=False,
        fetch=True,
        dry_run=False,
    )
    assert code == 0
    state = json.loads(state_path.read_text())
    assert state["version"] == STATE_VERSION
    assert state["tested_hashes"] == {"deadbeef": {"representative": "a@1111111", "aliases": []}}
    assert set(state["last_seen_refs"]) == {source.branch for source in DEFAULT_SOURCES}


def test_every_watched_branch_is_fetched(tmp_path, monkeypatch):
    from tournament import automation

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "version": STATE_VERSION, "canonical_run": "r", "canonical_bots": {},
        "tested_hashes": {}, "last_seen_ref": "f" * 40, "last_seen_refs": {},
    }))
    calls = []
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: calls.append(command) or "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation, "discover", lambda *a, **k: [])

    automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=True, dry_run=False,
    )
    fetch = next(c for c in calls if c[:2] == ["git", "fetch"])
    assert set(fetch[3:]) == {source.branch for source in DEFAULT_SOURCES}


def test_implementation_rated_from_one_branch_is_not_rescheduled_from_another(tmp_path, monkeypatch):
    """Elias vendors Jon's bots verbatim. Hashing .py content must recognise the copy."""
    from tournament import automation
    from tournament.registry import BotSpec

    rated = BotSpec(name="tempest", commit="a" * 40, path="bots/jon/fair/tempest")
    vendored = BotSpec(name="tempest", commit="b" * 40, path="bots/elias/rivals/tempest")

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"version": STATE_VERSION, "canonical_run": "r"}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation.duplicates, "code_hash", lambda commit, path: "samehash")
    monkeypatch.setattr(automation, "derive_ledger", lambda: (
        {"samehash": {"representative": rated.bot_id, "aliases": []}},
        {rated.bot_id: rated, vendored.bot_id: vendored},
    ))

    def fake_discover(ref, prefix, excludes=()):
        return [vendored] if prefix == "bots/elias" else []

    monkeypatch.setattr(automation, "discover", fake_discover)
    # hpc must never be reached: nothing here is unseen.
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status",
                        lambda tid, s=None: {"total": 1, "done": 0})
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda *a, **k: pytest.fail("scheduled a known copy"))

    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0


def test_ledger_comes_from_the_match_data_not_a_cache():
    """The whole point: what counts as rated is read from the repo's own results."""
    from tournament.automation import derive_ledger, played_bot_ids

    ledger, specs = derive_ledger()
    played = played_bot_ids()
    assert played, "no match data in this checkout"
    # Every implementation in the ledger is backed by a bot that actually played.
    for entry in ledger.values():
        assert entry["representative"] in played
    # And every bot that played is accounted for by exactly one ledger entry.
    covered = {entry["representative"] for entry in ledger.values()}
    covered |= {alias for entry in ledger.values() for alias in entry["aliases"]}
    assert played <= covered


def test_a_bot_that_played_but_has_no_source_is_an_error(monkeypatch):
    """Silently treating it as new would re-run it forever; the run must stop instead."""
    from tournament import automation

    monkeypatch.setattr(automation, "_all_specs", dict)
    monkeypatch.setattr(automation, "played_bot_ids", lambda: {"ghost@1234567"})
    with pytest.raises(RuntimeError, match="no source metadata"):
        automation.derive_ledger()


# ------------------------------------------------------------------------------------------
# Work already in flight must not be scheduled twice.
# ------------------------------------------------------------------------------------------


def _write_run(root, name, entries, merged_ids=(), submitted=True):
    run = root / name
    run.mkdir(parents=True)
    (run / "schedule.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    if submitted:
        # hpc.submit() always writes this before returning, so an in-flight run has one. Its
        # absence is the signal that a run never reached bsub -- see
        # test_a_run_that_never_reached_the_cluster_is_pushed_and_queued.
        (run / "hpc.json").write_text(json.dumps({"job_ids": ["999"]}))
    if merged_ids:
        import csv as _csv

        with open(run / "matches.csv", "w", newline="") as handle:
            writer = _csv.DictWriter(handle, fieldnames=["match_id", "bot_a", "bot_b", "status"])
            writer.writeheader()
            for match_id in merged_ids:
                writer.writerow({"match_id": match_id, "bot_a": "a@1", "bot_b": "b@2",
                                 "status": "ok"})
    return run


def _entry(match_id, a="a@1", b="b@2", kind="rating"):
    return {"match_id": match_id, "bot_a": a, "bot_b": b, "kind": kind}


def test_unfinished_run_is_detected(tmp_path, monkeypatch):
    from tournament import automation

    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path)
    _write_run(tmp_path, "half", [_entry("m1"), _entry("m2")], merged_ids=["m1"])
    assert automation.unfinished_runs() == {"half": {"a@1", "b@2"}}


def test_complete_run_is_not_flagged(tmp_path, monkeypatch):
    from tournament import automation

    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path)
    _write_run(tmp_path, "done", [_entry("m1"), _entry("m2")], merged_ids=["m1", "m2"])
    assert automation.unfinished_runs() == {}


def test_compliance_probes_do_not_make_a_run_look_unfinished(tmp_path, monkeypatch):
    """Probes land in compliance_matches.csv; counting them would flag every finished run."""
    from tournament import automation

    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path)
    _write_run(tmp_path, "done", [_entry("m1"), _entry("c1", kind="compliance")],
               merged_ids=["m1"])
    assert automation.unfinished_runs() == {}


def test_bots_under_test_are_not_scheduled_again(tmp_path, monkeypatch):
    """The case that caused half-finished submissions: a tick firing mid-evaluation."""
    from tournament import automation
    from tournament.registry import BotSpec

    spec = BotSpec(name="newbot", commit="c" * 40, path="bots/jon/fair/newbot")
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"version": STATE_VERSION, "canonical_run": "r"}))
    runs = tmp_path / "runs"
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", runs)
    _write_run(runs, "inflight", [_entry("m1", a=spec.bot_id, b="rival@9")], merged_ids=[])

    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation.duplicates, "code_hash", lambda commit, path: "newhash")
    monkeypatch.setattr(automation, "derive_ledger", lambda: ({}, {spec.bot_id: spec}))
    monkeypatch.setattr(automation, "discover",
                        lambda ref, prefix, excludes=(): [spec] if prefix == "bots/jon" else [])
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status",
                        lambda tid, s=None: {"total": 1, "done": 0})
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda *a, **k: pytest.fail("scheduled a bot that is already under test"))

    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0


def test_a_new_bot_waits_while_another_run_is_still_in_flight(tmp_path, monkeypatch):
    """The 2026-08-02 wedge: canonical_field() grows when the in-flight run lands, so a
    challenger planned now is finalised against entrants it was never scheduled against."""
    from tournament import automation
    from tournament.registry import BotSpec

    other = BotSpec(name="other", commit="b" * 40, path="bots/luc/other")
    fresh = BotSpec(name="fresh", commit="c" * 40, path="bots/jon/fair/fresh")
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"version": STATE_VERSION, "canonical_run": "r"}))
    runs = tmp_path / "runs"
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", runs)
    # A different bot is under test and its run is only half merged.
    _write_run(runs, "inflight", [_entry("m1", a=other.bot_id, b="rival@9")], merged_ids=[])

    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation.duplicates, "code_hash",
                        lambda commit, path: "otherhash" if "other" in path else "freshhash")
    monkeypatch.setattr(automation, "derive_ledger", lambda: ({}, {other.bot_id: other}))
    monkeypatch.setattr(automation, "discover",
                        lambda ref, prefix, excludes=(): [fresh] if prefix == "bots/jon" else [])
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status",
                        lambda tid, s=None: {"total": 1, "done": 0})
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda *a, **k: pytest.fail("planned a run while another was in flight"))

    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0


def test_in_flight_detection_survives_a_reminted_bot_id(tmp_path, monkeypatch):
    """bot_id is name@<branch-tip-sha>, so any push re-mints an id for untouched code too.
    The same implementation under test must not read as unseen under its new id."""
    from tournament import automation
    from tournament.registry import BotSpec

    old = BotSpec(name="prospect", commit="1" * 40, path="bots/luc/prospect")
    new = BotSpec(name="prospect", commit="2" * 40, path="bots/luc/prospect")
    assert old.bot_id != new.bot_id
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"version": STATE_VERSION, "canonical_run": "r"}))
    runs = tmp_path / "runs"
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", runs)
    _write_run(runs, "inflight", [_entry("m1", a=old.bot_id, b="rival@9")], merged_ids=[])

    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "2" * 40)
    # Same path -> same code -> same hash, whichever commit minted the id.
    monkeypatch.setattr(automation.duplicates, "code_hash", lambda commit, path: "prospecthash")
    monkeypatch.setattr(automation, "derive_ledger", lambda: ({}, {old.bot_id: old}))
    monkeypatch.setattr(automation, "discover",
                        lambda ref, prefix, excludes=(): [new] if prefix == "bots/luc" else [])
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status",
                        lambda tid, s=None: {"total": 1, "done": 0})
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda *a, **k: pytest.fail("re-scheduled code already under test"))

    captured = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: captured.append(" ".join(map(str, a))))
    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0
    assert any("no unseen Python implementations" in line for line in captured), captured


def test_tid_is_stable_when_an_unrelated_branch_moves():
    """A stranded partial run was the cause of the manual gap-fill; the tid must not move."""
    import hashlib

    def tid(unseen):
        return f"auto-{hashlib.sha256('|'.join(sorted(unseen)).encode()).hexdigest()[:12]}"

    # Same work to do -> same run directory, regardless of what any branch head is.
    assert tid({"h1", "h2"}) == tid({"h2", "h1"})
    assert tid({"h1"}) != tid({"h1", "h2"})


# ------------------------------------------------------------------------------------------
# A tick must not block on the cluster.
# ------------------------------------------------------------------------------------------


def test_submitting_does_not_wait_for_the_cluster(tmp_path, monkeypatch):
    """The lock is held for the whole tick, so a tick that waits blocks bot discovery for hours."""
    from tournament import automation
    from tournament.registry import BotSpec

    spec = BotSpec(name="newbot", commit="c" * 40, path="bots/jon/fair/newbot")
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"version": STATE_VERSION, "canonical_run": "r"}))
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", runs)
    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation.duplicates, "code_hash", lambda commit, path: "newhash")
    monkeypatch.setattr(automation, "derive_ledger", lambda: ({}, {spec.bot_id: spec}))
    monkeypatch.setattr(automation, "discover",
                        lambda ref, prefix, excludes=(): [spec] if prefix == "bots/jon" else [])
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "check_connection", lambda host: None)
    monkeypatch.setattr(automation.hpc, "push", lambda tid, settings: None)
    monkeypatch.setattr(automation.hpc, "submit", lambda tid, settings: None)
    monkeypatch.setattr(automation.hpc, "watch",
                        lambda *a, **k: pytest.fail("a tick must never block on hpc.watch"))

    destination = runs / "auto-x"
    destination.mkdir()
    monkeypatch.setattr(automation.planning, "plan",
                        lambda *a, **k: (destination, [{"match_id": "m1"}]))

    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0
    # The run records what it is for, so a later tick can finish it.
    marker = json.loads((destination / "automation.json").read_text())
    assert marker["challengers"] == [spec.bot_id]


def test_finalise_reports_a_run_that_is_still_going(tmp_path, monkeypatch):
    from tournament import automation

    runs = tmp_path / "runs"
    run = _write_run(runs, "auto-y", [_entry("m1"), _entry("m2")], merged_ids=["m1"])
    (run / "automation.json").write_text(json.dumps({"challengers": [], "heads": {}}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", runs)
    monkeypatch.setattr(automation.planning, "run_dir", lambda tid: runs / tid)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "check_connection", lambda host: None)
    monkeypatch.setattr(automation.hpc, "fetch", lambda tid, settings: None)
    monkeypatch.setattr(automation, "merge", lambda dest: (None, 1))

    assert automation.finalise("auto-y", state={}, state_path=tmp_path / "s.json",
                               site_repo=tmp_path, publish=False) is False


def test_rating_match_count_ignores_compliance_probes(tmp_path):
    from tournament.plan import rating_match_count

    run = _write_run(tmp_path, "r", [_entry("m1"), _entry("c1", kind="compliance")])
    assert rating_match_count(run) == 1



def test_a_run_awaiting_publication_is_still_pending(tmp_path, monkeypatch):
    """Merging is not completion: a run rated but unpublished must stay in the queue."""
    from tournament import automation

    monkeypatch.setattr(automation.planning, "RUNS_ROOT", tmp_path)
    run = _write_run(tmp_path, "auto-z", [_entry("m1")], merged_ids=["m1"])
    (run / "automation.json").write_text(json.dumps({"challengers": [], "heads": {}}))
    # Fully merged, so unfinished_runs() considers it done...
    assert automation.unfinished_runs() == {}
    # ...but it has never been rated, so it is still outstanding work.
    assert "auto-z" in automation.pending_runs()
    (run / "ratings-distinct.csv").write_text("rank,bot_id\n1,a@1\n")
    assert automation.pending_runs() == {}


# ------------------------------------------------------------------------------------------
# Only committed code is run or deployed.
# ------------------------------------------------------------------------------------------


def test_publish_skips_deploy_when_the_site_source_is_dirty(tmp_path, monkeypatch):
    """Building compiles the working tree, so a file saved mid-edit would go live."""
    from tournament import automation

    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return " M src/components/BotRankings.tsx\n"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "a" * 40 + "\n"
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation, "build_site_data", lambda run_dir, out: None)
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1})())
    automation._publish(tmp_path, tmp_path, "abc1234")

    assert ["npm", "run", "build"] not in calls, "must not build a dirty tree"
    assert not any(c[:2] == ["npm", "exec"] for c in calls), "must not deploy a dirty tree"
    # The bundle is gitignored now, so publishing never commits or pushes it anywhere.
    assert not any(c[:2] == ["git", "push"] for c in calls)
    assert not any(c[:2] == ["git", "commit"] for c in calls)


def test_publish_deploys_when_the_source_is_clean(tmp_path, monkeypatch):
    from tournament import automation

    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return ""          # the bundle is gitignored, so a data refresh leaves no trace here
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "b" * 40 + "\n"
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation, "build_site_data", lambda run_dir, out: None)
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1})())
    automation._publish(tmp_path, tmp_path, "abc1234")

    assert ["npm", "run", "build"] in calls
    assert (tmp_path / ".last-deployed-commit").read_text().strip() == "b" * 40


def test_publish_deploys_even_when_head_has_not_moved(tmp_path, monkeypatch):
    """The regression that gitignoring the bundle would otherwise have introduced.

    Publishing used to commit the data, which moved HEAD, which is what `_deploy` triggered on.
    With the bundle untracked HEAD never moves on a data refresh, so if `_publish` still deferred
    to the HEAD check the ladder would silently freeze at whatever was last deployed.
    """
    from tournament import automation

    (tmp_path / ".last-deployed-commit").write_text("c" * 40 + "\n")
    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return ""
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "c" * 40 + "\n"
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation, "build_site_data", lambda run_dir, out: None)
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 0})())
    automation._publish(tmp_path, tmp_path, "abc1234")
    assert ["npm", "run", "build"] in calls
    assert ["npm", "exec", "--yes", "wrangler@latest", "--", "deploy"] in calls


def test_deploy_assets_can_skip_the_build_for_an_already_written_dist(tmp_path, monkeypatch):
    """The live feed writes straight into dist/, so it uploads without recompiling the site."""
    from tournament import automation

    (tmp_path / "dist").mkdir()
    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "d" * 40 + "\n"
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    assert automation.deploy_assets(tmp_path, reason="live feed", build=False) is True
    assert ["npm", "run", "build"] not in calls
    assert ["npm", "exec", "--yes", "wrangler@latest", "--", "deploy"] in calls
    # It shipped whatever dist/ already held, which may predate HEAD, so it must not claim HEAD
    # is live -- that would make `_deploy` skip the rebuild that would actually put it there.
    assert not (tmp_path / ".last-deployed-commit").exists()


def test_a_feed_deploy_does_not_suppress_a_later_source_deploy(tmp_path, monkeypatch):
    """Regression: the feed timer runs far more often than source changes land."""
    from tournament import automation

    (tmp_path / "dist").mkdir()
    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        return "f" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    monkeypatch.setattr(automation, "_run", fake_run)
    automation.deploy_assets(tmp_path, reason="live feed", build=False)
    calls.clear()
    automation._deploy(tmp_path)
    assert ["npm", "run", "build"] in calls, "the new commit still needs compiling"
    assert (tmp_path / ".last-deployed-commit").read_text().strip() == "f" * 40


def test_deploy_assets_builds_anyway_when_dist_is_missing(tmp_path, monkeypatch):
    """build=False is an optimisation, not a promise there is something to upload."""
    from tournament import automation

    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        return "e" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    monkeypatch.setattr(automation, "_run", fake_run)
    assert automation.deploy_assets(tmp_path, reason="live feed", build=False) is True
    assert ["npm", "run", "build"] in calls


def test_deploy_assets_yields_rather_than_racing_a_concurrent_deploy(tmp_path, monkeypatch):
    """Two overlapping wrangler runs against one project publish whichever finishes last."""
    import fcntl

    from tournament import automation

    calls = []
    monkeypatch.setattr(
        automation, "_run",
        lambda command, cwd=None: (calls.append(command), "")[1],
    )
    with open(tmp_path / ".deploy.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert automation.deploy_assets(tmp_path, reason="live feed") is False
    assert not any(c[:2] == ["npm", "exec"] for c in calls)


def test_a_compile_lost_to_the_lock_is_retried_on_the_next_tick(tmp_path, monkeypatch):
    """Untracked data removed the retry that a moved HEAD used to provide."""
    import fcntl

    from tournament import automation

    (tmp_path / "dist").mkdir()
    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        return "a" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation, "build_site_data", lambda run_dir, out: None)

    with open(tmp_path / ".deploy.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        automation._publish(tmp_path, tmp_path, "abc1234")
    assert ["npm", "run", "build"] not in calls, "the lock was held"
    assert (tmp_path / ".deploy-pending").exists()

    # Next evaluator tick: HEAD has not moved, so only the pending marker can rescue the compile.
    calls.clear()
    automation._deploy(tmp_path)
    assert ["npm", "run", "build"] in calls
    assert not (tmp_path / ".deploy-pending").exists()


def test_a_feed_deploy_compiles_when_dist_is_missing_newer_ranking_data(tmp_path, monkeypatch):
    """How the ladder got stuck two runs behind while every log line said "deployed"."""
    from tournament import automation

    published = tmp_path / "public" / "botrankings" / "data"
    compiled = tmp_path / "dist" / "botrankings" / "data"
    published.mkdir(parents=True)
    compiled.mkdir(parents=True)
    (published / "index.json").write_text('{"run_id": "auto-new"}')
    (compiled / "index.json").write_text('{"run_id": "auto-old"}')

    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        return "a" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    monkeypatch.setattr(automation, "_run", fake_run)
    automation.deploy_assets(tmp_path, reason="live feed", build=False)
    assert ["npm", "run", "build"] in calls, "must not ship a dist/ that predates public/"

    # Once they agree the fast path is safe again, which is what keeps it cheap.
    (compiled / "index.json").write_text('{"run_id": "auto-new"}')
    calls.clear()
    automation.deploy_assets(tmp_path, reason="live feed", build=False)
    assert ["npm", "run", "build"] not in calls


def test_the_pending_marker_does_not_block_the_deploy_it_exists_to_rescue(tmp_path, monkeypatch):
    """It is untracked, so an un-ignored marker reads as a dirty tree and freezes everything."""
    from tournament import automation

    (tmp_path / "dist").mkdir()
    (tmp_path / ".deploy-pending").write_text("ranking data for abc1234\n")
    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        # What a correctly configured checkout reports: the marker is gitignored, so it is absent
        # from porcelain output even though it is sitting right there on disk.
        if command[:2] == ["git", "status"]:
            return ""
        return "a" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    monkeypatch.setattr(automation, "_run", fake_run)
    automation._deploy(tmp_path)
    assert ["npm", "exec", "--yes", "wrangler@latest", "--", "deploy"] in calls
    assert not (tmp_path / ".deploy-pending").exists()


def test_a_feed_deploy_does_not_clear_a_pending_compile(tmp_path, monkeypatch):
    """The feed uploads dist/ untouched, so it cannot satisfy a build somebody else still needs."""
    from tournament import automation

    (tmp_path / "dist").mkdir()
    (tmp_path / ".deploy-pending").write_text("ranking data for abc1234\n")
    monkeypatch.setattr(
        automation, "_run",
        lambda command, cwd=None: "b" * 40 + "\n" if command[:3] == ["git", "rev-parse", "HEAD"] else "",
    )
    automation.deploy_assets(tmp_path, reason="live feed", build=False)
    assert (tmp_path / ".deploy-pending").exists()


def test_self_update_rolls_back_when_tests_fail(tmp_path, monkeypatch):
    """A broken evaluator does not merely fail; it submits cluster jobs and publishes."""
    from tournament import automation

    calls = []
    revs = iter(["old1234" + "0" * 33, "new5678" + "0" * 33])

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return next(revs) + "\n"
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "boom"})())
    assert automation.self_update("x/tournament") is False
    assert any(c[:2] == ["git", "reset"] for c in calls), "must roll back a failing update"


def test_self_update_adopts_a_passing_commit(tmp_path, monkeypatch):
    from tournament import automation

    revs = iter(["old1234" + "0" * 33, "new5678" + "0" * 33])
    monkeypatch.setattr(automation, "_run",
                        lambda command, cwd=None: (next(revs) + "\n")
                        if command[:3] == ["git", "rev-parse", "HEAD"] else "")
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": ""})())
    assert automation.self_update("x/tournament") is True


def _push_data_calls(monkeypatch, *, branch_head, status, push_fails=False,
                     staged=True, ahead="3"):
    """Drive _push_data with a scripted git, returning the commands it issued."""
    from tournament import automation

    calls = []

    def fake_run(command, cwd=None):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return branch_head + "\n"
        if command[:2] == ["git", "status"]:
            return status
        if command[:3] == ["git", "rev-list", "--count"]:
            return ahead + "\n"
        if command[:3] == ["git", "diff", "--cached"]:
            return "tournament/runs/auto-x/matches.csv\ntournament/runs/auto-x/ratings.csv\n"
        if command[:2] == ["git", "push"] and push_fails and calls.count(command) == 1:
            raise RuntimeError("command failed (1): git push\n! [rejected] non-fast-forward")
        return ""

    monkeypatch.setattr(automation, "_run", fake_run)
    # A non-zero `git diff --cached --quiet` means there is something staged to commit.
    monkeypatch.setattr(automation.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1 if staged else 0})())
    automation._push_data("x/tournament")
    return calls


def test_push_data_commits_and_pushes_finished_run_data(monkeypatch):
    calls = _push_data_calls(monkeypatch, branch_head="x/tournament",
                             status="?? tournament/runs/auto-x/\n")
    assert ["git", "add", "--", "tournament/runs"] in calls
    assert any(c[:2] == ["git", "commit"] for c in calls)
    assert ["git", "push", "origin", "x/tournament:x/tournament"] in calls


def test_push_data_refuses_when_the_checkout_is_on_another_branch(monkeypatch):
    """Committing run data onto whatever branch happens to be checked out would be wrong."""
    calls = _push_data_calls(monkeypatch, branch_head="x/luc", status="")
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


def test_push_data_refuses_when_the_tree_is_dirty_outside_the_run_data(monkeypatch):
    """Half-edited harness code must not be swept into a results commit."""
    calls = _push_data_calls(monkeypatch, branch_head="x/tournament",
                             status=" M tournament/rating.py\n")
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


def test_push_data_rebases_and_retries_when_the_branch_moved(monkeypatch):
    """Someone else pushing during a cluster run must not silently drop the results."""
    calls = _push_data_calls(monkeypatch, branch_head="x/tournament",
                             status="?? tournament/runs/auto-x/\n", push_fails=True)
    assert ["git", "rebase", "origin/x/tournament"] in calls
    assert calls.count(["git", "push", "origin", "x/tournament:x/tournament"]) == 2


def test_push_data_names_the_runs_it_is_committing(monkeypatch):
    from tournament import automation

    calls = _push_data_calls(monkeypatch, branch_head="x/tournament",
                             status="?? tournament/runs/auto-x/\n")
    commit = next(c for c in calls if c[:2] == ["git", "commit"])
    assert commit[-1] == "Add tournament results for auto-x"


def test_push_data_retries_commits_an_earlier_tick_could_not_deliver(monkeypatch):
    """Committing and pushing fail independently, so a failed push must not need new data to retry.

    Returning early on "nothing new to commit" stranded 22 commits of match and rating CSVs on the
    workstation: the only thing that would have carried them out was the next run's data.
    """
    calls = _push_data_calls(monkeypatch, branch_head="x/tournament", status="",
                             staged=False, ahead="22")
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    assert ["git", "push", "origin", "x/tournament:x/tournament"] in calls


def test_push_data_does_nothing_when_the_branch_is_level(monkeypatch):
    """The common case -- a tick that gained no results and has nothing owed -- stays silent."""
    calls = _push_data_calls(monkeypatch, branch_head="x/tournament", status="",
                             staged=False, ahead="0")
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


def _stranded_run(root, tid, *, merged: int, scheduled: int, submitted: bool = True) -> None:
    """A run whose schedule is only partly present in matches.csv.

    Writes an hpc.json by default, because hpc.submit() always writes one before it returns --
    so in production a run with outstanding matches and no hpc.json is precisely a run that never
    reached bsub. Pass submitted=False to model that case.
    """
    run_dir = root / tid
    run_dir.mkdir(parents=True)
    if submitted:
        (run_dir / "hpc.json").write_text(json.dumps({"job_ids": ["999"]}))
    entries = [
        {"match_id": f"m{i}", "bot_a": "alpha", "bot_b": "beta", "kind": "rating"}
        for i in range(scheduled)
    ]
    (run_dir / "schedule.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n"
    )
    with open(run_dir / "matches.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["match_id", "bot_a", "bot_b", "kind"])
        writer.writeheader()
        for entry in entries[:merged]:
            writer.writerow(entry)


def test_a_finished_run_missing_local_results_is_fetched_not_waited_on(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-stranded", merged=95, scheduled=100)
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    # The cluster says every match is done; the five that never arrived are a transfer problem.
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {"total": 100, "done": 100})

    fetched = []

    def fake_fetch(tid, settings=None):
        fetched.append(tid)
        _stranded_run(root, "tmp", merged=0, scheduled=0)  # no-op guard against reuse
        run_dir = root / tid
        entries = [
            {"match_id": f"m{i}", "bot_a": "alpha", "bot_b": "beta", "kind": "rating"}
            for i in range(100)
        ]
        with open(run_dir / "matches.csv", "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["match_id", "bot_a", "bot_b", "kind"])
            writer.writeheader()
            writer.writerows(entries)
        return 100

    monkeypatch.setattr(automation.hpc, "fetch", fake_fetch)

    assert automation.unfinished_runs()  # blocked before
    recovered = automation.recover_stranded_results(["auto-stranded"])
    assert fetched == ["auto-stranded"]
    assert recovered == ["auto-stranded"]
    assert not automation.unfinished_runs()  # unblocked after


def test_a_run_still_executing_is_left_alone(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-running", merged=40, scheduled=100)
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {"total": 100, "done": 40})
    monkeypatch.setattr(
        automation.hpc, "fetch",
        lambda tid, settings=None: pytest.fail("must not fetch a run that is still executing"),
    )

    assert automation.recover_stranded_results(["auto-running"]) == []
    assert automation.unfinished_runs()  # still correctly treated as in flight


def test_an_unreachable_cluster_leaves_the_run_in_flight(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-offline", merged=95, scheduled=100)
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})

    def boom(tid, settings=None):
        raise automation.hpc.HpcError("ssh: connection refused")

    monkeypatch.setattr(automation.hpc, "status", boom)
    # Deferring is the safe outcome, so a cluster hiccup must not raise out of the tick.
    assert automation.recover_stranded_results(["auto-offline"]) == []
    assert automation.unfinished_runs()


def _bjobs_missing(*job_ids: str) -> str:
    return "\n".join(f"Job array <{job_id}> is not found" for job_id in job_ids)


def test_a_run_whose_arrays_vanished_is_requeued(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-abandoned", merged=40, scheduled=100)
    (root / "auto-abandoned" / "hpc.json").write_text(json.dumps({"job_ids": ["111", "222"]}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    # The cluster stopped short and every array it submitted is gone: no amount of fetching
    # finishes this, so it would defer every later bot forever.
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 40, "job_ids": ["111", "222"], "bjobs": _bjobs_missing("111", "222"),
    })
    monkeypatch.setattr(automation.hpc, "fetch", lambda tid, settings=None: 40)
    submitted = []
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: submitted.append(tid))

    assert automation.resubmit_abandoned_runs(["auto-abandoned"]) == ["auto-abandoned"]
    assert submitted == ["auto-abandoned"]


def test_a_run_with_one_array_still_alive_is_not_requeued(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-partly-live", merged=40, scheduled=100)
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    # Four arrays finished, one is still going. A run split across arrays reports "not found" for
    # the finished ones, and re-submitting on that alone would duplicate live work.
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 40, "job_ids": ["111", "222"], "bjobs": _bjobs_missing("111"),
    })
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: pytest.fail("re-queued a live run"))

    assert automation.resubmit_abandoned_runs(["auto-partly-live"]) == []


def _bjobs_table(job_id: str, *, njobs, pend=0, done=0, run=0, exited=0, ssusp=0) -> str:
    return (
        "JOBID       ARRAY_SPEC  OWNER   NJOBS PEND DONE  RUN EXIT SSUSP USUSP PSUSP\n"
        f"{job_id}    trn_auto  s234842  {njobs} {pend} {done} {run} {exited} {ssusp} 0 0"
    )


def test_a_run_whose_last_element_only_exited_is_requeued(tmp_path, monkeypatch):
    """LSF still lists the array, so "not found" never fires -- but nothing is left to run.

    auto-ac98e09efc0e sat on 8 of 5,901 matches this way. recover_stranded_results() skips it too
    (the cluster never reaches done == total), so without this it defers every later bot until
    LSF happens to age the array out of bjobs -- which took it 64 minutes.
    """
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-exited", merged=92, scheduled=100)
    (root / "auto-exited" / "hpc.json").write_text(json.dumps({"job_ids": ["111"]}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 92, "job_ids": ["111"],
        "bjobs": _bjobs_table("111", njobs=5, done=4, exited=1),
    })
    monkeypatch.setattr(automation.hpc, "fetch", lambda tid, settings=None: 92)
    submitted = []
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: submitted.append(tid))

    assert automation.resubmit_abandoned_runs(["auto-exited"]) == ["auto-exited"]
    assert submitted == ["auto-exited"]


@pytest.mark.parametrize("state", [
    {"njobs": 5, "done": 2, "run": 3},
    {"njobs": 5, "done": 2, "pend": 3},
    {"njobs": 5, "done": 4, "ssusp": 1},
])
def test_an_array_with_work_left_is_never_requeued(tmp_path, monkeypatch, state):
    """Pending, running and suspended elements are all still going to produce results."""
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-live", merged=40, scheduled=100)
    (root / "auto-live" / "hpc.json").write_text(json.dumps({"job_ids": ["111"]}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 40, "job_ids": ["111"], "bjobs": _bjobs_table("111", **state),
    })
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: pytest.fail("re-queued a live run"))

    assert automation.resubmit_abandoned_runs(["auto-live"]) == []


def test_a_run_that_never_reached_the_cluster_is_pushed_and_queued(tmp_path, monkeypatch):
    """No hpc.json means no bsub ever ran, so nothing owns the run and nothing retries it.

    On 2026-08-06 the staging rsync hit a full quota, the tick died before hpc.json was written,
    and auto-33ab234bb994 sat at 0/6489 for four hours deferring every later bot. _abandoned()
    returns False on empty job_ids and recover_stranded_results() needs done == total, so neither
    could see it. Recovery has to push first: nothing of this run is on the cluster yet.
    """
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-never-sent", merged=0, scheduled=100, submitted=False)
    assert not (root / "auto-never-sent" / "hpc.json").exists()
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 0, "job_ids": [], "bjobs": "",
    })
    calls = []
    monkeypatch.setattr(automation.hpc, "push",
                        lambda tid, settings=None: calls.append(("push", tid)))
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: calls.append(("submit", tid)))
    monkeypatch.setattr(automation.hpc, "fetch",
                        lambda tid, settings=None: pytest.fail("nothing to fetch; it never ran"))

    assert automation.resubmit_abandoned_runs(["auto-never-sent"]) == ["auto-never-sent"]
    assert calls == [("push", "auto-never-sent"), ("submit", "auto-never-sent")]


def test_requeueing_gives_up_after_the_cap(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    _stranded_run(root, "auto-hopeless", merged=40, scheduled=100)
    run_dir = root / "auto-hopeless"
    (run_dir / "resubmits.json").write_text(json.dumps({"count": automation.MAX_RESUBMITS}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.hpc, "config", lambda: {"host": "dtu"})
    monkeypatch.setattr(automation.hpc, "status", lambda tid, s=None: {
        "total": 100, "done": 40, "job_ids": ["111"], "bjobs": _bjobs_missing("111"),
    })
    monkeypatch.setattr(automation.hpc, "submit",
                        lambda tid, settings=None: pytest.fail("kept re-queueing a failing run"))

    # A run that keeps coming back short is failing for a reason re-queueing will not fix.
    assert automation.resubmit_abandoned_runs(["auto-hopeless"]) == []


def test_matches_with_an_unimportable_bot_do_not_keep_a_run_in_flight(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    run_dir = root / "auto-broken"
    run_dir.mkdir(parents=True)
    entries = [
        {"match_id": "m1", "bot_a": "good@1", "bot_b": "good2@1", "kind": "rating"},
        {"match_id": "m2", "bot_a": "good@1", "bot_b": "broken@1", "kind": "rating"},
    ]
    (run_dir / "schedule.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    with open(run_dir / "matches.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["match_id", "bot_a", "bot_b", "kind"])
        writer.writeheader()
        writer.writerow(entries[0])  # only the playable match ever produced a result
    (run_dir / "manifest.json").write_text(json.dumps({"bots": [
        {"bot_id": "good@1", "commit": "a" * 40, "path": "bots/good"},
        {"bot_id": "good2@1", "commit": "b" * 40, "path": "bots/good2"},
        {"bot_id": "broken@1", "commit": "c" * 40, "path": "bots/broken"},
    ]}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.loadcheck, "unloadable_ids", lambda bots: {"broken@1"})

    # m2 can never produce a result, so counting it would defer every later bot forever.
    assert automation.outstanding_matches(run_dir) == set()
    assert automation.unfinished_runs() == {}


def test_a_run_is_still_in_flight_when_its_playable_matches_are_missing(tmp_path, monkeypatch):
    from tournament import automation

    root = tmp_path / "runs"
    run_dir = root / "auto-live"
    run_dir.mkdir(parents=True)
    entries = [
        {"match_id": "m1", "bot_a": "good@1", "bot_b": "good2@1", "kind": "rating"},
        {"match_id": "m2", "bot_a": "good@1", "bot_b": "broken@1", "kind": "rating"},
    ]
    (run_dir / "schedule.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    (run_dir / "manifest.json").write_text(json.dumps({"bots": []}))
    monkeypatch.setattr(automation.planning, "RUNS_ROOT", root)
    monkeypatch.setattr(automation.loadcheck, "unloadable_ids", lambda bots: {"broken@1"})

    # The good pair has not played yet, so the run genuinely is still going.
    assert automation.outstanding_matches(run_dir) == {"m1"}
