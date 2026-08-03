"""Reproducible bot tournaments with mElo and Nash-averaging ratings.

Deliberately empty: `tournament.run_match` executes inside LSF array jobs and must import
nothing beyond the standard library and `fcode`. Anything imported here would be dragged into
every one of those ~23,000 processes -- and importing numpy into a process that later calls the
engine is exactly the failure mode documented in tournament/README.md.

The one exception is setting BLAS thread limits, which is stdlib-only and therefore drags
nothing in. It has to happen here because the limit is read when the BLAS library loads, and by
the time any module has imported numpy it is already too late.

Every matrix in this package is bots-by-bots -- about 100x100. That is far below the size where
threaded BLAS pays for itself, and the threads end up spinning against each other instead of
working: measured over four per-map solves, the default threading took 12.4s of wall clock and
180.8s of CPU, while a single thread took 6.4s of both. Twice as fast, and 28x cheaper. Left
alone it turned a site build into 32 minutes and a 2.7 GB peak on a machine that has to keep
serving a two-minute timer.
"""

import os

for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    # setdefault, so an operator who really wants threads can still ask for them.
    os.environ.setdefault(_variable, "1")
