"""Tests for the scheduling/staging/merging machinery, and the import boundary it depends on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tournament import registry
from tournament.gitutil import REPO_ROOT
from tournament.maps import label, resolve
from tournament.plan import build_schedule, match_id
from tournament.registry import BotSpec


# --------------------------------------------------------------------------------------------
# Registry metadata
# --------------------------------------------------------------------------------------------


def test_every_registered_bot_has_one_fairness_tag():
    for spec in registry.load(validate=False):
        fairness = {"fair", "unfair"}.intersection(spec.tags)
        assert len(fairness) == 1, f"{spec.bot_id} has fairness tags {sorted(fairness)}"


# --------------------------------------------------------------------------------------------
# The module boundary that keeps the engine alive
# --------------------------------------------------------------------------------------------


def test_run_match_imports_no_scientific_stack():
    """run_match executes in-process with the engine's sub-interpreters; numpy must stay out.

    The engine creates bot sub-interpreters with SHARED_GIL and use_main_obmalloc=1, so a numpy or
    torch import in this process shares an allocator and GIL with them. This repo has already been
    bitten by that (segfaults, and an autograd "called while holding the GIL" failure), so the
    boundary is asserted rather than merely documented.
    """
    probe = (
        "import sys; import tournament.run_match; "
        "bad = [m for m in ('numpy', 'scipy', 'torch', 'pandas') if m in sys.modules]; "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f"run_match pulled in {result.stdout.strip()}"


def test_local_runner_imports_no_scientific_stack():
    """Same rule for the local pool: its workers call the engine too."""
    probe = (
        "import sys; import tournament.local; "
        "bad = [m for m in ('numpy', 'scipy', 'torch') if m in sys.modules]; "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f"local pulled in {result.stdout.strip()}"


# --------------------------------------------------------------------------------------------
# Match identity
# --------------------------------------------------------------------------------------------


def test_match_id_is_stable_and_order_sensitive():
    """Re-planning must reproduce ids (so results survive), but the two orders are distinct games."""
    first = match_id("a@1", "b@2", "duel", 1, 0)
    assert first == match_id("a@1", "b@2", "duel", 1, 0)
    assert first != match_id("b@2", "a@1", "duel", 1, 0)
    assert first != match_id("a@1", "b@2", "atoll", 1, 0)
    assert first != match_id("a@1", "b@2", "duel", 2, 0)
    assert first != match_id("a@1", "b@2", "duel", 1, 10)


def test_compliance_match_ids_do_not_collide_with_rating_matches():
    assert match_id("a@1", "b@2", "duel", 1, 10) != match_id(
        "a@1", "b@2", "duel", 1, 10, kind="compliance-v1"
    )


# --------------------------------------------------------------------------------------------
# Schedule construction
# --------------------------------------------------------------------------------------------


def _spec(name: str) -> BotSpec:
    return BotSpec(name=name, commit=f"{name:0>40}".replace(" ", "0"), path=f"bots/{name}")


def _schedule(names: list[str], maps: list[str], seeds: tuple[int, ...] = (1,)):
    specs = [_spec(name) for name in names]
    paths = [resolve(name)[0] for name in maps]
    mains = {s.bot_id: f"stage/{s.bot_id}/main.py" for s in specs}
    staged = {m: f"maps/{m}.map26" for m in maps}
    return specs, build_schedule(specs, paths, list(seeds), 0, mains, staged)


def test_every_pair_plays_both_orders_on_every_map():
    specs, matches = _schedule(["a", "b", "c"], ["duel", "atoll"])
    # 3 bots -> 3 pairs, 2 maps, 2 orders
    assert len(matches) == 3 * 2 * 2

    for left in specs:
        for right in specs:
            if left is right:
                continue
            for name in ("duel", "atoll"):
                assert any(
                    m.bot_a == left.bot_id and m.bot_b == right.bot_id and m.map == name
                    for m in matches
                ), f"missing {left.name} vs {right.name} on {name}"


def test_schedule_indices_are_dense_and_one_based():
    """These are LSF array indices; a gap would submit a job that reads the wrong line."""
    _, matches = _schedule(["a", "b", "c", "d"], ["duel"])
    assert [m.index for m in matches] == list(range(1, len(matches) + 1))


def test_schedule_match_ids_are_unique():
    _, matches = _schedule(["a", "b", "c"], ["duel", "atoll"], seeds=[1, 2])
    ids = [m.match_id for m in matches]
    assert len(set(ids)) == len(ids)


def test_no_bot_is_scheduled_against_itself():
    _, matches = _schedule(["a", "b", "c"], ["duel"])
    assert all(m.bot_a != m.bot_b for m in matches)


def test_seeds_multiply_the_schedule():
    _, one = _schedule(["a", "b"], ["duel"], seeds=[1])
    _, three = _schedule(["a", "b"], ["duel"], seeds=[1, 2, 3])
    assert len(three) == 3 * len(one)


# --------------------------------------------------------------------------------------------
# Challenger mode
# --------------------------------------------------------------------------------------------


def test_challenger_mode_plays_challengers_against_the_roster_and_each_other():
    from tournament.plan import pairings

    challengers = [_spec("new1"), _spec("new2")]
    roster = [_spec("old1"), _spec("old2"), _spec("old3")]
    pairs = {frozenset((a.name, b.name)) for a, b in pairings(challengers, roster)}

    for c in challengers:
        for r in roster:
            assert frozenset((c.name, r.name)) in pairs
    assert frozenset(("new1", "new2")) in pairs
    # ...and crucially NOT roster-vs-roster, whose results already exist and cannot have changed.
    assert frozenset(("old1", "old2")) not in pairs
    assert len(pairs) == 2 * 3 + 1


def test_challenger_mode_does_not_pair_a_bot_with_itself():
    """A challenger that is also in the roster list must not be scheduled against itself."""
    from tournament.plan import pairings

    shared = _spec("both")
    pairs = pairings([shared, _spec("new")], [shared, _spec("old")])
    assert all(a.bot_id != b.bot_id for a, b in pairs)
    assert frozenset(("both", "new")) in {frozenset((a.name, b.name)) for a, b in pairs}


def test_challenger_mode_emits_each_pair_once():
    from tournament.plan import pairings

    challengers = [_spec("a"), _spec("b")]
    roster = [_spec("a"), _spec("b"), _spec("c")]
    pairs = [frozenset((x.bot_id, y.bot_id)) for x, y in pairings(challengers, roster)]
    assert len(pairs) == len(set(pairs))


def test_round_robin_is_unchanged_without_vs():
    from tournament.plan import pairings

    specs = [_spec(n) for n in "abcd"]
    assert len(pairings(specs, None)) == 6


def test_same_name_at_two_commits_are_distinct_entrants():
    """The point of commit pinning: old and new vanguard must be comparable head to head."""
    from tournament.plan import pairings
    from tournament.registry import BotSpec

    old = BotSpec(name="vanguard", commit="a" * 40, path="bots/jon/fair/vanguard")
    new = BotSpec(name="vanguard", commit="b" * 40, path="bots/jon/fair/vanguard")
    assert old.bot_id != new.bot_id
    assert len(pairings([new], [old])) == 1


# --------------------------------------------------------------------------------------------
# Map sets
# --------------------------------------------------------------------------------------------


def test_official_and_generated_map_sets_are_disjoint():
    """The two corpora are deliberately kept apart on disk; selecting one must not leak the other."""
    official = set(resolve("official"))
    generated = set(resolve("generated"))
    assert official and generated
    assert not (official & generated)
    assert set(resolve("all")) == official | generated


def test_official_pool_is_the_21_competition_maps():
    official = resolve("official")
    assert len(official) == 21
    assert all(path.parent.name == "maps" for path in official)


def test_map_labels_distinguish_the_corpora():
    """Labels are CSV keys, so a generated map must never collide with an official one."""
    assert label(resolve("duel")[0]) == "duel"
    generated = [label(path) for path in resolve("generated")]
    assert all(name.startswith("generated/") for name in generated)
    assert len(set(generated)) == len(generated)


def test_screen_is_a_subset_of_official():
    assert set(resolve("screen")) <= set(resolve("official"))
    assert len(resolve("screen")) == 6


def test_unknown_map_raises():
    with pytest.raises((FileNotFoundError, ValueError)):
        resolve("no-such-map")


# --------------------------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------------------------


def test_merge_is_idempotent_and_keyed_by_match_id(tmp_path):
    from tournament.merge import merge, read

    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "tournament_id": "t",
                "map_set": "official",
                "bots": [
                    {"bot_id": "a@111", "name": "a", "commit": "1" * 40},
                    {"bot_id": "b@222", "name": "b", "commit": "2" * 40},
                ],
            }
        )
    )
    record = {
        "match_id": "deadbeef",
        "bot_a": "a@111",
        "bot_b": "b@222",
        "map": "duel",
        "seed": 1,
        "tle": 0,
        "status": "ok",
        "winner": "a",
        "score_a": 1.0,
        "turns": 500,
    }
    (run_dir / "results" / "deadbeef.json").write_text(json.dumps(record))

    merge(run_dir)
    first = read(run_dir)
    merge(run_dir)
    second = read(run_dir)

    assert first == second
    assert len(first) == 1
    assert first[0]["bot_a_name"] == "a"
    assert first[0]["tournament_id"] == "t"
    assert first[0]["map_set"] == "official"


def test_merge_keeps_compliance_matches_out_of_rating_csv(tmp_path):
    from tournament.merge import merge, read

    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "tournament_id": "t",
                "map_set": "official",
                "bots": [
                    {"bot_id": "a@111", "name": "a", "commit": "1" * 40},
                    {"bot_id": "b@222", "name": "b", "commit": "2" * 40},
                ],
                "compliance": {"targets": ["a@111"], "matches_per_bot": 1},
            }
        )
    )
    rating = {
        "match_id": "rating",
        "kind": "rating",
        "bot_a": "a@111",
        "bot_b": "b@222",
        "status": "ok",
        "winner": "a",
        "score_a": 1.0,
    }
    check = {
        "match_id": "check",
        "kind": "compliance",
        "bot_a": "a@111",
        "bot_b": "__compliance_baseline__@v1",
        "map": "duel",
        "seed": 1,
        "tle": 12,
        "status": "ok",
        "winner": "b",
        "compliance_samples": 20,
        "compliance_turn_us": [400, 1_000, 2_000, 4_000, 8_500],
        "compliance_max_turn_us": 8_500,
        "compliance_max_round": 4,
        "compliance_timeouts": 0,
        "compliance_exceptions": 0,
        "compliance_terminal_starts": 0,
    }
    for record in (rating, check):
        (run_dir / "results" / f"{record['match_id']}.json").write_text(json.dumps(record))

    _, count = merge(run_dir)

    assert count == 2  # completion counts every scheduled result
    assert [row["match_id"] for row in read(run_dir)] == ["rating"]
    summary = (run_dir / "compliance.csv").read_text()
    assert "a@111" in summary and "pass" in summary
    assert "min_turn_us,p25_turn_us,p50_turn_us,p75_turn_us,max_turn_us" in summary
    assert "check" in (run_dir / "compliance_matches.csv").read_text()


def test_compliance_replay_parser_distinguishes_timeouts_errors_and_terminal_actions(tmp_path):
    from tournament.compliance import END_MARKER, ERROR_MARKER, START_MARKER
    from tournament.run_match import compliance_timings

    replay = tmp_path / "probe.replay26"
    replay.write_bytes(
        b"\x00".join(
            line.encode()
            for line in [
                f"{START_MARKER}:1:7",
                f"{END_MARKER}:1:7:9100",
                f"{START_MARKER}:2:7",  # interrupted, then the same entity runs again
                f"{START_MARKER}:3:7",
                f"{END_MARKER}:3:7:400",
                f"{START_MARKER}:4:8",  # self-destruct or match end: no later run
                f"{START_MARKER}:5:9",
                f"{ERROR_MARKER}:5:9",
            ]
        )
    )

    result = compliance_timings(str(replay))

    assert result == {
        "compliance_samples": 2,
        "compliance_turn_us": [9100, 400],
        "compliance_max_turn_us": 9100,
        "compliance_max_round": 1,
        "compliance_timeouts": 1,
        "compliance_exceptions": 1,
        "compliance_terminal_starts": 1,
    }


def test_compliance_percentiles_use_all_observed_turns():
    from tournament.compliance import timing_percentiles

    assert timing_percentiles([100, 200, 300, 400, 500]) == {
        "min_turn_us": 100,
        "p25_turn_us": 200,
        "p50_turn_us": 300,
        "p75_turn_us": 400,
        "max_turn_us": 500,
    }
    assert timing_percentiles([100, 200, 300], timeouts=2) == {
        "min_turn_us": 100,
        "p25_turn_us": 200,
        "p50_turn_us": 300,
        "p75_turn_us": ">12000",
        "max_turn_us": ">12000",
    }


# --------------------------------------------------------------------------------------------
# LSF array index ranges
# --------------------------------------------------------------------------------------------


def test_compress_indices_collapses_runs():
    from tournament.hpc import compress_indices

    assert compress_indices([1, 2, 3, 4, 5]) == "1-5"
    assert compress_indices([1]) == "1"
    assert compress_indices([1, 2, 3, 9, 12, 13, 14]) == "1-3,9,12-14"
    assert compress_indices([2, 4, 6]) == "2,4,6"


def test_compress_indices_round_trips_a_gappy_resume_set():
    """The worklist holds exactly the indices with no result yet; none may be lost or gained."""
    from tournament.hpc import compress_indices

    indices = [1, 2, 3, 7, 8, 15, 16, 17, 18, 40]
    expanded: list[int] = []
    for part in compress_indices(indices).split(","):
        if "-" in part:
            start, end = part.split("-")
            expanded.extend(range(int(start), int(end) + 1))
        else:
            expanded.append(int(part))
    assert expanded == indices


def test_compress_indices_rejects_an_empty_schedule():
    from tournament.hpc import HpcError, compress_indices

    with pytest.raises(HpcError):
        compress_indices([])


def test_array_chunks_respect_the_lsf_cap():
    """LSF rejects an array larger than MAX_JOB_ARRAY_SIZE (1000 here) with a fatal error."""
    limit = 1000
    indices = list(range(1, 23563))
    chunks = [indices[start : start + limit] for start in range(0, len(indices), limit)]
    assert all(len(chunk) <= limit for chunk in chunks)
    assert sum(len(chunk) for chunk in chunks) == len(indices)
    assert [i for chunk in chunks for i in chunk] == indices


@pytest.mark.parametrize("total,chunk", [(23562, 20), (100, 7), (36, 1), (5, 10), (1000, 1000)])
def test_chunked_elements_cover_every_worklist_entry_exactly_once(total, chunk):
    """Mirrors job_script: element i runs `sed -n 'first,last p'` over the worklist file.

    An off-by-one silently skips or replays matches, so coverage is checked rather than assumed,
    including the ragged final element (where sed just yields fewer lines).
    """
    worklist = list(range(1, total + 1))
    elements = (total + chunk - 1) // chunk
    covered: list[int] = []
    for i in range(1, elements + 1):
        first, last = (i - 1) * chunk + 1, i * chunk
        covered.extend(worklist[first - 1 : last])  # sed -n 'first,last p', 1-based inclusive
    assert covered == worklist


def test_chunking_works_over_a_scattered_worklist():
    """The reason elements index a file rather than a range: outstanding matches are gappy.

    A contiguous element range over a partially-finished schedule would re-run completed work.
    """
    worklist = [3, 7, 8, 15, 40, 41, 42, 99]
    chunk = 3
    covered: list[int] = []
    for i in range(1, (len(worklist) + chunk - 1) // chunk + 1):
        first, last = (i - 1) * chunk + 1, i * chunk
        covered.extend(worklist[first - 1 : last])
    assert covered == worklist


def test_default_chunk_comes_from_config_and_is_batched():
    """Default is batched, not one-per-match: measured overhead makes chunk=1 wasteful."""
    from tournament.hpc import config

    assert config().get("chunk", 1) > 1


def test_shipped_walltime_covers_the_default_chunk():
    """Walltime is a hard kill; the shipped config must not be able to lose a whole element."""
    from tournament.hpc import check_walltime, config

    settings = config()
    check_walltime(settings, settings["chunk"])  # must not raise


def test_walltime_guard_rejects_an_element_that_cannot_finish():
    from tournament.hpc import HpcError, SLOWEST_MATCH_SECONDS, check_walltime

    settings = {"walltime": "22"}
    check_walltime(settings, 20)
    over = 22 * 60 // SLOWEST_MATCH_SECONDS + 1
    with pytest.raises(HpcError, match="cannot cover"):
        check_walltime(settings, over)


def test_job_script_reads_its_slice_from_the_worklist():
    from tournament.hpc import job_script

    settings = {
        "queue": "hpc", "throttle": 100, "cores": 1, "memory": "2GB", "walltime": "22",
    }
    script = job_script("t", settings, "1-1000", "n", 20, "t/work_X.txt")
    assert "first=$(( ($LSB_JOBINDEX - 1) * 20 + 1 ))" in script
    assert "last=$(( $LSB_JOBINDEX * 20 ))" in script
    assert 'sed -n "${first},${last}p" t/work_X.txt' in script
    # The index passed to run_match must come from the worklist, never from the array index.
    assert '--index "$index"' in script
    assert '--index "$LSB_JOBINDEX"' not in script


def test_job_script_uses_the_worklist_even_at_chunk_one():
    """chunk=1 must still map through the worklist, or a resubmit re-runs finished matches."""
    from tournament.hpc import job_script

    settings = {
        "queue": "hpc", "throttle": 100, "cores": 1, "memory": "2GB", "walltime": "22",
    }
    script = job_script("t", settings, "1-10", "n", 1, "t/work_X.txt")
    assert "sed -n" in script
    assert '--index "$LSB_JOBINDEX"' not in script


def test_merge_survives_a_truncated_result_file(tmp_path):
    """A job killed mid-write must not take the whole merge down with it."""
    from tournament.merge import merge

    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"tournament_id": "t", "map_set": "official", "bots": []})
    )
    (run_dir / "results" / "good.json").write_text(
        json.dumps({"match_id": "good", "status": "ok", "winner": "a", "score_a": 1.0})
    )
    (run_dir / "results" / "bad.json").write_text('{"match_id": "bad", "stat')

    _, count = merge(run_dir)
    assert count == 1
