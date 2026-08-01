<!-- source: https://www.hpc.dtu.dk/?page_id=282 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Modules on HPC Clusters

## Purpose

In multi-user HPC environments, a modular approach manages software availability. Users can load
only needed programs without system-wide version conflicts, maintaining control over their shell
environment without specifying full paths.

## Core Module Commands

**System information**

- `module list` — Display currently loaded modules
- `module avail` — Show all available modules
- `module avail -t` — Display modules in terse format

**Loading and unloading**

- `module load <module name>` — Load a specified module
- `module unload <module name>` — Remove a loaded module
- `module switch <old> <new>` — Replace one module with another

**Module details**

- `module whatis <module name>` — Brief module description
- `module show/display <module name>` — Detailed module information and environment changes

## Usage Example

```
module list
module avail -t
module load gcc/12.2.0-binutils-2.39
module load mpi/4.1.4-gcc-12.2.0-binutils-2.39
module list
gcc --version
```

## Batch Job Considerations

Batch jobs run in clean environments. Include module loading commands before program execution:

```bash
#!/bin/sh
#BSUB ......

module load gcc/12.2.0-binutils-2.39
myapplication.x < input.in > output.out
```

## Automatic Module Loading

Edit `~/.gbarrc` to autoload modules:

```
MODULES=python3/3.10.7
```

**Note:** Modules unload at logout; automatic loading via `.gbarrc` prevents clean environment
resets.

---

## Python for the tournament

`fcode` 2.3.3 publishes wheels for **CPython 3.12 and 3.13 only**. `tournament/hpc.py bootstrap`
runs `module avail python3` and picks the newest 3.13, falling back to 3.12, then builds a venv and
`pip install fcode==2.3.3` into it. Because batch jobs get a clean environment, the generated job
script re-runs `module load` before activating the venv.
