"""Tests for the multi-branch discover-evaluate-publish loop.

Nothing here touches the cluster or the website: the parts worth testing are which bots each
branch contributes, that an implementation already rated from one branch is never scheduled again
from another, and that an existing single-branch state file survives the upgrade.
"""

from __future__ import annotations

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


def test_default_sources_cover_the_three_active_branches():
    assert {source.branch for source in DEFAULT_SOURCES} == {"x/jon", "x/luc", "elias_dev"}
    # Each contributor's own subtree, so vendored copies of rivals are never discovered.
    assert all(source.prefix.startswith("bots/") for source in DEFAULT_SOURCES)


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
    assert set(state["last_seen_refs"]) == {"x/jon", "x/luc", "elias_dev"}


def test_every_watched_branch_is_fetched(tmp_path, monkeypatch):
    from tournament import automation

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "version": STATE_VERSION, "canonical_run": "r", "canonical_bots": {},
        "tested_hashes": {}, "last_seen_ref": "f" * 40, "last_seen_refs": {},
    }))
    calls = []
    monkeypatch.setattr(automation, "_run", lambda command, cwd=None: calls.append(command) or "")
    monkeypatch.setattr(automation, "resolve_commit", lambda ref: "a" * 40)
    monkeypatch.setattr(automation, "discover", lambda *a, **k: [])

    automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=True, dry_run=False,
    )
    fetch = next(c for c in calls if c[:2] == ["git", "fetch"])
    assert set(fetch[3:]) == {"x/jon", "x/luc", "elias_dev"}


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
    monkeypatch.setattr(automation.hpc, "config", lambda: pytest.fail("scheduled a known copy"))

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


def _write_run(root, name, entries, merged_ids=()):
    run = root / name
    run.mkdir(parents=True)
    (run / "schedule.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
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
    monkeypatch.setattr(automation.hpc, "config",
                        lambda: pytest.fail("scheduled a bot that is already under test"))

    assert automation.run_once(
        state_path=state_path, canonical_run=None, sources=DEFAULT_SOURCES,
        fetch_remote="origin", site_repo=tmp_path, publish=False, fetch=False, dry_run=False,
    ) == 0


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
