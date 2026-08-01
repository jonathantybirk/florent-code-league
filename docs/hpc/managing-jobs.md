<!-- source: https://www.hpc.dtu.dk/?page_id=1519 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Managing Jobs under LSF 10

## Submitting and Checking Job Status

### Job Submission

```
bsub < your_job_script
```

Output example:

```
Job <44951> is submitted to default queue .
```

The number in brackets is the job ID. The `bsub` command accepts many options. Refer to `man bsub`.

### Monitoring Jobs with bstat

```
bstat
```

Output shows columns: `JOBID, USER, QUEUE, JOB_NAME, NALLOC, STAT, START_TIME, ELAPSED`

Common status labels:

- **PEND**: Job queued, waiting to be scheduled
- **RUN**: Job running
- **DONE**: Job completed after running
- **EXIT**: Job exited (after being killed)
- **SSUSP**: Job suspended

Usage options:

```
bstat [-h] [-v] [-C | -M] [-u uname] [-q qname] [jobID [jobId ...]]
```

- `-h`: Show help message
- `-v`: Show version history
- `-C`: Show CPU usage (running jobs only)
- `-M`: Show memory usage (running jobs only)
- `-u uname`: Filter by user ("all" for all users)
- `-q qname`: Filter by queue
- `jobID`: Specific job ID(s)

Check a specific job:

```
bstat 45678
```

CPU efficiency — shows an `EFFIC` column (ideal value: 100%):

```
bstat -C
```

Memory usage — shows `JOBID, USER, QUEUE, JOB_NAME, NALLOC, MEM, MAX, AVG, LIM`:

```
bstat -M
```

Memory limit enforcement note: the `LIM` limit is per-host. For multi-node jobs, the limit applies
per node.

### Removing Jobs

```
bkill <your-job-id>
bkill -s SIGTERM <your-job-id>
```

## Additional Commands

### classstat

```
classstat hpc
```

Output columns: `queue, total, used, avail, pend, j-mig, j-abs`

```
queue                total  used avail  pend j-mig j-abs
--------------------------------------------------------
hpc                   1376   478   898   216   0     0
```

### nodestat

```
nodestat hpc
nodestat -F hpc     # adds Model, Memory, Feature
nodestat -g hpc     # GPU information
nodestat -G hpc
nodestat -h
```

Output columns: `Node, State, Procs, Load`

### showstart

Estimated start time for pending jobs:

```
showstart 758888
```

Output columns: `JOBID, USER, QUEUE, SUBMIT_TIME, ESTIMATED_SIM_START_T, JOB_NAME`

### bhist

Historical job information:

```
bhist -a              # all user jobs, compact
bhist -t -T .-2,      # jobs from the last 2 days
bhist -l <jobid>      # detailed info for a specific job
```

Detailed output includes submission details, dispatch information, completion status, CPU time and
memory usage.

### bpeek

Displays stdout and stderr of unfinished jobs:

```
bpeek <jobid>
```

```
<< output from stdout >>
.......
<< output from stderr >>
.....
```

### bacct

Accounting statistics for finished jobs (`DONE` or `EXIT`):

```
bacct <jobid>
```

Provides a summary including number of done/exited jobs, total and average CPU time, wait times and
turnaround time, hog factor and expansion factor, and run time statistics.

## Contact

support@cc.dtu.dk — DTU Compute, Building 324, Room 280, Technical University of Denmark,
2800 Kgs Lyngby, Denmark
