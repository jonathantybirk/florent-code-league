#!/bin/sh
# One-time cluster setup: build a venv with fcode in it.
#
# Run from the tournament root on the cluster. Idempotent -- safe to re-run.
# fcode 2.3.6 publishes wheels for CPython 3.12 and 3.13 only, so this picks the newest of those
# that the module system offers rather than whatever `python3` happens to be.

set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "== picking a Python module =="
# `module` is a shell function set up by gbar.sh; a non-interactive ssh shell does not get it
# automatically, so source it explicitly. `set -u` has to come off first: gbar.sh pulls in
# /apps/dcc/etc/profile, which reads an unset $DT and would abort the script.
set +u
. /etc/profile.d/gbar.sh 2>/dev/null || true
set -u

# `module avail` writes to stderr. Prefer 3.13, fall back to 3.12 -- fcode 2.3.6 publishes wheels
# for CPython 3.12 and 3.13 only, so the 3.14 modules on this cluster are unusable.
AVAILABLE="$(module avail python3 2>&1 | tr ' ' '\n' | grep -E '^python3/3\.(12|13)\.' | sort -V || true)"
if [ -z "$AVAILABLE" ]; then
    echo "!! no python3/3.12.x or 3.13.x module found. Available python3 modules:" >&2
    module avail python3 2>&1 >/dev/null || true
    echo "!! fcode only ships wheels for CPython 3.12 and 3.13." >&2
    exit 1
fi
PYMODULE="$(echo "$AVAILABLE" | tail -1)"
echo "using $PYMODULE"
module load "$PYMODULE"
echo "$PYMODULE" > .python-module
python3 --version

echo "== creating venv =="
if [ ! -d venv ]; then
    python3 -m venv venv
fi
. venv/bin/activate
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet "fcode==2.3.6"

echo "== verifying =="
python3 -c "import fcode; from fcode.fcode_engine import run_game; print('fcode', fcode.__version__ if hasattr(fcode, '__version__') else 'ok', 'engine ok')"

echo "== scratch quota =="
getquota_work3.sh 2>/dev/null || echo "(getquota_work3.sh unavailable)"

echo "bootstrap complete: $ROOT/venv"
