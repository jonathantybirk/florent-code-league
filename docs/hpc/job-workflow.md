<!-- source: https://www.hpc.dtu.dk/?page_id=4204 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Job Workflow: Setup and Monitor a Job

## Before Job Submission: Estimating Resources

### CPU Cores / Number of Nodes

**Serial programs:**

```
#BSUB -n 1
#BSUB -R "span[hosts=1]"
```

**Shared memory parallelism** (single node):

```
#BSUB -n N
#BSUB -R "span[hosts=1]"
```

where N is the number of cores not exceeding the maximum per machine.

**Distributed memory parallelism** (multiple nodes):

```
#BSUB -n N
#BSUB -R "span[ptile=M]"
```

where N is total cores requested and M is cores per node.

### GPU Configuration

```
#BSUB -gpu "num=1:mode=exclusive_process"
```

Always use `mode=exclusive_process` to prevent memory conflicts. Check available GPUs with
`nodestat -g queue_name`.

### Memory Requirements

Memory specification is **per core**. For 32 GB total with 1 core:

```
#BSUB -n 1
#BSUB -R "rusage[mem=32GB]"
```

For 8 cores needing 32 GB total (4 GB per core):

```
#BSUB -n 8
#BSUB -R "rusage[mem=4GB]"
```

Check available memory with `nodestat -F queue_name`.

### Walltime

Estimate runtime with reasonable margin. Requesting excess walltime increases waiting time.

## When the Job Is Running

### CPU Core Utilization

```
bstat -C job-id
```

Good: "20 cores with 98.34% efficiency after 3:47:38". Poor: "24 cores with 49.60% efficiency"
indicates underutilization requiring investigation.

### Memory Utilization

```
bstat -M job-id
```

Shows peak usage vs. allocated memory. Requesting excessive memory wastes resources for other
users.

### GPU Utilization

Test in interactive sessions to verify the GPU is actually being used, all requested GPUs are
utilized, and usage efficiency.

## After Job Completion

The scheduler generates a report with key metrics.

### Efficiency Calculation

CPU time / Run time = average cores used. Should be close to requested cores; a significantly lower
ratio indicates scaling issues.

### Memory Analysis

"Delta Memory" shows excess memory requested versus actual peak usage.

### Oversubscription Detection

Oversubscription occurs when "the program starts more processes/threads than the number of physical
CPU cores requested." Review `Max Processes` and `Max Threads` in the report. High values relative
to requested cores may indicate oversubscription.

Programs prone to oversubscription include: julia, Python's multiprocessing library, R libraries,
cplex library, gams, gurobi.

Complex programs like MATLAB, COMSOL, ANSYS naturally start many auxiliary processes.

---

## Sizing a tournament match

One match is strictly serial — the fcode engine runs both bots in sub-interpreters sharing a single
GIL inside one process, so it can never use more than one core. Hence `-n 1` and
`-R "span[hosts=1]"`, and CPU efficiency near 100% is expected. Anything less means the engine is
blocked on I/O, which would be worth investigating.

Memory is a couple of hundred MB in practice; `rusage[mem=2GB]` is generous headroom for the
largest maps. Note the **oversubscription warning above applies to the local runner, not the HPC
one** — `tournament/local.py` uses a process pool and must be given `--jobs` no larger than the
cores you actually have.

## Contact

support@cc.dtu.dk — DTU Compute, Building 324, Room 280, Technical University of Denmark,
2800 Kgs Lyngby, Denmark
