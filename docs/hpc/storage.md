<!-- source: https://www.hpc.dtu.dk/?page_id=927 and https://www.hpc.dtu.dk/?page_id=59 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Disk Space and Quota

## Home Directory Quota

Each HPC user is given a **30 GB home directory**. The home directory **is backed up**. A user can
ask for extra home space, usually only for a limited amount of time (write to support@cc.dtu.dk).

### Checking Home Directory Quota

Log in and in a terminal type:

```
getquota_zhome.sh
```

which will display output like `You are using 12.34 GB of 30.00 GB.`

## Scratch Filesystem (/work3)

When you request space on the scratch filesystem, a directory named after your username will be
created under `/work3`. It is accessible from HPC nodes as `/work1/<username>` or
`/work3/<username>`. **Scratch filesystems are not backed up.**

To request space, write to support@cc.dtu.dk asking for space on the scratch filesystem,
specifying the reason why you need it.

## Important Warning

> It is important to take care of not exceeding your disk quota, as if this happens, your jobs will
> be killed for lack of disk space, and you'd likely not be able to run any other program and even
> log-in.

## Freeing up space

See <https://www.hpc.dtu.dk/?page_id=5556>. Common wins: `rm -rvf ~/.cache/pip/http/*`,
`du -sh *` to find offenders.

---

## What the tournament stores where

Disk discipline matters here because a full tournament is tens of thousands of matches:

| Data | Location | Size |
|---|---|---|
| Bot sources, maps, schedule | `$HOME/florent-tournament/<tid>/` | a few MB |
| Result JSONs (one per match) | `$HOME/florent-tournament/<tid>/results/` | ~400 B each |
| LSF stdout/stderr logs | `$HOME/florent-tournament/<tid>/logs/` | small, but **one pair per match** |
| **Replays** | node-local `$TMPDIR`, **deleted immediately** | MB each — never kept |

23,562 matches produce roughly 10 MB of results but ~47,000 log files, so `logs/` is the real
inode consumer. `tournament/hpc.py` does not need `/work3`; if home quota becomes tight, clear
`logs/` after a successful `fetch` — the result JSONs are the only durable artefact.
