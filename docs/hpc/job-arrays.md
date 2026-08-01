<!-- source: https://www.hpc.dtu.dk/?page_id=1434 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Job Arrays under LSF

## Overview

Job arrays allow users to submit multiple independent jobs that share the same computational
template. This is useful when running many iterations of the same code with different inputs or
outputs.

## Basic Job Script Template

```sh
#!/bin/sh
# embedded options to bsub - start with #BSUB
### -- set the job Name AND the job array --
#BSUB -J My_array[1-25]
### -- specify queue --
#BSUB -q hpc
### -- ask for number of cores (default: 1) --
#BSUB -n 4
### -- set walltime limit: hh:mm --
#BSUB -W 03:00
### -- specify that we need 4GB of memory per core/slot --
#BSUB -R "rusage[mem=4GB]"
### -- set the email address --
##BSUB -u your_email_address
### -- send notification at start --
#BSUB -B
### -- send notification at completion--
#BSUB -N
### -- Specify the output and error file. %J is the job-id %I is the job-array index --
### -- -o and -e mean append, -oo and -eo mean overwrite --
#BSUB -o Output_%J_%I.out
#BSUB -e Output_%J_%I.err

# here follow the commands you want to execute
./my_program > Out_$LSB_JOBINDEX.out
```

## Array Specification

Request a job array using: `#BSUB -J My_array[1-25]`

This creates 25 jobs numbered 1-25. Resources are multiplied accordingly (4 cores x 25 jobs = 100
cores needed).

**Note 1:** Arrays support multiple specifications:

- `[1,23,45-67]` — specific numbers and ranges
- `[1-21:2]` — step sizes (creates odd numbers 1 to 21)

## Environment Variables

Each job accesses its index via `$LSB_JOBINDEX` for differentiating inputs/outputs.

**Note 2:** In `#BSUB` options use `%I` (array index) and `%J` (job ID). In commands, use the
environment variables `$LSB_JOBINDEX` and `$LSB_JOBID`.

## Job Identification and Management

Jobs have IDs formatted as: `<jobid>[array-id]`

Commands:

- `bjobs <jobid>` — check array status
- `bjobs <jobid>[array-id]` — check single job
- `bkill <jobid>[array-id]` — delete individual job
- `bkill <jobid>` — delete all jobs
- `bkill <jobid>[1-5,212,334]` — delete selected jobs

## Important Note

> The jobs in a job array are all completely independent, and they will not necessarily run in the
> order you expect.

Execution order cannot be relied upon; use job dependencies if order matters.

## Good Practice

- Limit simultaneous jobs to avoid overloading: `#BSUB -J My_array[1-20]%5`
- Disable email notifications for large arrays to avoid excessive emails per job completion.
