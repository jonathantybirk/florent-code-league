"""Reproducible bot tournaments with mElo and Nash-averaging ratings.

Deliberately empty: `tournament.run_match` executes inside LSF array jobs and must import
nothing beyond the standard library and `fcode`. Anything imported here would be dragged into
every one of those ~23,000 processes -- and importing numpy into a process that later calls the
engine is exactly the failure mode documented in tournament/README.md.
"""
