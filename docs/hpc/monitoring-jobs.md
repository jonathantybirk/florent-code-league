<!-- source: https://www.hpc.dtu.dk/?page_id=2652 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Monitoring Jobs in LSF 10: Advanced

## Basic bjobs Command

The primary monitoring tool is `bjobs`, which displays information about running, pending, or
recently finished jobs.

### Default Output

```
bjobs
JOBID     USER    QUEUE      JOB_NAME   SLOTS STAT  START_TIME   TIME_LEFT
45755    s012345   hpc        large_Set      4 RUN   Aug 21 11:00 00:14:41 L
45756    s012345   hpc        *3_LSF10_1     2 RUN   Aug 21 11:00 24:00:00 L
```

Column descriptions:

- `JOBID`: Running job identifier
- `USER`: Username
- `QUEUE`: Queue submission destination
- `JOB_NAME`: Job names
- `SLOTS`: Slots used (for running jobs)
- `STAT`: Job status
- `START_TIME`: When job began
- `TIME_LEFT`: Time until completion

## Job Status Labels

| Status | Meaning |
|--------|---------|
| PEND | Queued, waiting to be scheduled |
| RUN | Currently running |
| DONE | Completed after running |
| EXIT | Exited (e.g., after being killed) |
| SSUSP | Suspended |

## Detailed Job Information

```
bjobs -l <job-id>
bjobs -l 45800
```

The verbose output displays: the original jobscript; `RUNLIMIT` (wall time allocation and host
information); `MEMLIMIT`; task count and resource allocation details; execution location and working
directory; resource usage metrics; CPU time consumed; memory, swap, thread and process information;
maximum and average memory usage; pending time details (if applicable); a scheduling parameters
table; and resource requirement specifications (combined and effective).

## Pending Job Information

For jobs awaiting dispatch, a `PENDING REASONS` section explains the delay:

```
PENDING REASONS:
 User has reached the per-user job slot limit of the queue;
```

> This is the reason the tournament array throttles at `%100` — see [queues.md](queues.md).

## Additional Resources

For comprehensive command options: `man bjobs`
