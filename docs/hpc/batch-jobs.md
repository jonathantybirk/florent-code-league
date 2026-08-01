<!-- source: https://www.hpc.dtu.dk/?page_id=1416 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Batch Jobs under LSF 10

## Overview

The HPC system uses IBM Spectrum LSF as its Resource Manager to schedule and allocate computing
resources across multiple users. Users submit applications through job scripts rather than running
them directly.

## Key Components of a Job Script

A job script requires three main elements:

1. **Resource specifications** — cores, memory, nodes, and special hardware requirements
2. **Queue specification** — which queue to submit to
3. **Execution environment** — modules, paths, and working directories

## Essential #BSUB Options

| Option | Purpose |
|--------|---------|
| `-J name` | Assign job name |
| `-q queue` | Specify target queue |
| `-n cores` | Request number of cores |
| `-W hh:mm` | Set walltime limit |
| `-R "span[hosts=1]"` | Keep cores on single node |
| `-R "rusage[mem=XXX]"` | Memory per core requirement |
| `-M limit` | Per-process memory limit |
| `-o file` | Standard output file |
| `-e file` | Standard error file |
| `-B` | Email notification at start |
| `-N` | Email notification at completion |

## Core Distribution Options

- `span[hosts=1]` — All cores on one machine
- `span[ptile=N]` — N cores per machine (MPI programs)
- `span[block=N]` — Groups of N cores (may share nodes, MPI programs)

## Default Enforced Settings

When not specified, these defaults are applied:

- Job name: `-J NONAME`
- Walltime: `-W 15` (15 minutes)
- Output file: `-o jobname_%J.out`
- Memory limit: `-M 1024MB` (if no rusage specified)
- Memory requested: `-R "rusage[mem=1024MB]"`
- Core distribution: `-R span[hosts=1]` (for multiple cores)

## Submission Process

Submit scripts using: `bsub < submit.sh`

Check status with: `bstat`

## Important Notes

- Applications must run unattended without user intervention
- Specify full paths for executables and input files
- Load required modules before execution
- Avoid special characters and spaces in filenames and job names
- The `-o` and `-e` flags append by default; use `-oo` and `-eo` to overwrite
