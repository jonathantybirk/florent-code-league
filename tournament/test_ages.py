from __future__ import annotations

from tournament import ages


def test_duplicate_groups_all_take_the_oldest_age():
    dated = {
        "old@1111111": {"commit": "aaaaaaa", "date": "2026-07-31T04:13:08+02:00"},
        "new@2222222": {"commit": "bbbbbbb", "date": "2026-08-02T14:22:00+02:00"},
        "unrelated@3": {"commit": "ccccccc", "date": "2026-08-03T09:00:00+02:00"},
    }
    resolved = ages.apply_duplicate_groups(dated, [("old@1111111", "new@2222222")])

    # The survivor of a duplicate group stands for the whole group, so re-running old work must
    # not read as new.
    assert resolved["new@2222222"] == dated["old@1111111"]
    assert resolved["old@1111111"] == dated["old@1111111"]
    assert resolved["unrelated@3"] == dated["unrelated@3"]


def test_a_group_member_with_no_known_age_is_skipped_not_crashed():
    dated = {"known@1": {"commit": "aaaaaaa", "date": "2026-08-01T00:00:00+02:00"}}
    resolved = ages.apply_duplicate_groups(dated, [("known@1", "vanished@2")])
    assert resolved == dated


def test_ages_compare_across_timezones_not_by_string():
    # The repo's commits carry mixed offsets (+08:00 and +02:00 both appear), so an age that
    # sorted on the raw string would pick the wrong member of a group.
    dated = {
        "early@1": {"commit": "aaaaaaa", "date": "2026-07-31T04:13:08+08:00"},
        "later@2": {"commit": "bbbbbbb", "date": "2026-07-30T23:00:00+02:00"},
    }
    resolved = ages.apply_duplicate_groups(dated, [("early@1", "later@2")])
    # 2026-07-30T23:00+02:00 is 21:00Z; 2026-07-31T04:13+08:00 is 20:13Z, so early@1 is older.
    assert resolved["later@2"]["commit"] == "aaaaaaa"


def test_a_pruned_original_still_supplies_the_group_date():
    # The usual shape: the oldest member of a behavioural group is the one pruning dropped, so it
    # is absent from the rated field. Its date is exactly the one worth keeping.
    dated = {
        "original@1111111": {"commit": "aaaaaaa", "date": "2026-07-31T04:13:08+02:00"},
        "survivor@2222222": {"commit": "bbbbbbb", "date": "2026-08-02T14:22:00+02:00"},
    }
    resolved = ages.apply_duplicate_groups(dated, [("original@1111111", "survivor@2222222")])
    assert resolved["survivor@2222222"]["commit"] == "aaaaaaa"
    assert resolved["survivor@2222222"]["date"].startswith("2026-07-31")


def test_groups_recorded_by_different_runs_merge_transitively():
    # The same implementations are regrouped run after run under re-minted ids, so {a,b} from one
    # run and {b,c} from another are one group of three. Per-group minima would leave c dated
    # later than a has already disproved.
    dated = {
        "a@1": {"commit": "aaaaaaa", "date": "2026-07-30T10:00:00+02:00"},
        "b@2": {"commit": "bbbbbbb", "date": "2026-08-01T10:00:00+02:00"},
        "c@3": {"commit": "ccccccc", "date": "2026-08-02T10:00:00+02:00"},
        "loner@4": {"commit": "ddddddd", "date": "2026-08-03T10:00:00+02:00"},
    }
    resolved = ages.apply_duplicate_groups(dated, [("a@1", "b@2"), ("b@2", "c@3")])

    assert resolved["c@3"]["commit"] == "aaaaaaa"
    assert resolved["b@2"]["commit"] == "aaaaaaa"
    assert resolved["a@1"]["commit"] == "aaaaaaa"
    assert resolved["loner@4"]["commit"] == "ddddddd"


def test_an_undatable_group_member_does_not_erase_the_others():
    dated = {"known@1": {"commit": "aaaaaaa", "date": "2026-08-01T00:00:00+02:00"}}
    resolved = ages.apply_duplicate_groups(dated, [("known@1", "never_seen@2")])
    assert resolved["known@1"]["commit"] == "aaaaaaa"
