# DTU HPC documentation

Scraped from <https://www.hpc.dtu.dk/> on 2026-08-01 for the tournament harness in
[`tournament/`](../../tournament/).

> **Provenance note.** Unlike [`docs/official/`](../official/), which is verbatim Florent Code
> League material, these pages were fetched through a summarising tool. Code blocks, `#BSUB`
> options, command flags and table values came through intact, but prose is condensed and some
> sections are abridged. **Treat these as a working reference, not as a citable source** — each
> file carries its upstream URL, so follow the link when a detail matters.

| File | Upstream | Topic |
|---|---|---|
| [access.md](access.md) | [page_id=2501](https://www.hpc.dtu.dk/?page_id=2501) | Logging in to the LSF 10 cluster |
| [ssh-keys.md](ssh-keys.md) | [page_id=4317](https://www.hpc.dtu.dk/?page_id=4317) | SSH keys / access without VPN |
| [batch-jobs.md](batch-jobs.md) | [page_id=1416](https://www.hpc.dtu.dk/?page_id=1416) | Batch jobs, `#BSUB` options, defaults |
| [job-arrays.md](job-arrays.md) | [page_id=1434](https://www.hpc.dtu.dk/?page_id=1434) | **Job arrays — how the tournament submits matches** |
| [managing-jobs.md](managing-jobs.md) | [page_id=1519](https://www.hpc.dtu.dk/?page_id=1519) | `bstat`, `bkill`, `bhist`, `bpeek`, `classstat` |
| [monitoring-jobs.md](monitoring-jobs.md) | [page_id=2652](https://www.hpc.dtu.dk/?page_id=2652) | `bjobs` in depth, status labels, pending reasons |
| [queues.md](queues.md) | [page_id=3098](https://www.hpc.dtu.dk/?page_id=3098) | **Queue limits — the per-user slot cap** |
| [job-workflow.md](job-workflow.md) | [page_id=4204](https://www.hpc.dtu.dk/?page_id=4204) | Sizing resources, efficiency, oversubscription |
| [modules.md](modules.md) | [page_id=282](https://www.hpc.dtu.dk/?page_id=282) | `module load`, `.gbarrc` |
| [storage.md](storage.md) | [page_id=927](https://www.hpc.dtu.dk/?page_id=927), [59](https://www.hpc.dtu.dk/?page_id=59) | Home quota, `/work3` scratch |

## What this means for the tournament harness

Four facts from these pages shape `tournament/hpc.py`:

1. **Per-user slot cap.** The `hpc` queue allows only ~100–120 processes per user
   ([queues.md](queues.md)), and exceeding it produces `PENDING REASONS: User has reached the
   per-user job slot limit of the queue` ([monitoring-jobs.md](monitoring-jobs.md)). The array
   throttle therefore defaults to **100** (`#BSUB -J "trn[1-N]%100"`), not higher — going above it
   buys nothing and only clogs the queue.
2. **Default walltime is 15 minutes** ([batch-jobs.md](batch-jobs.md)), which a long match could
   exceed, so the job script sets `-W 20` explicitly. Queue maximum is 72 h.
3. **Home is 30 GB and backed up; `/work3` must be requested from support**
   ([storage.md](storage.md)). Result JSONs are a few hundred bytes each, so `$HOME` is fine —
   but replays are megabytes, so matches write them to node-local `$TMPDIR` and delete them.
4. **Array elements are independent and unordered** ([job-arrays.md](job-arrays.md)), so each match
   must be self-describing and write its own result file. Nothing may depend on execution order.
