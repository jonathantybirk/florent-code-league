"""Drive a tournament on the DTU HPC cluster: push, submit, poll, fetch.

One LSF array element per match. Each element is an independently scheduled job that plays one
match and writes one small JSON file, so results can be pulled down continuously while the rest of
the array is still running -- `fetch` is safe against a live directory because run_match writes
atomically.

All ssh goes through the `dtu` alias and its 8-hour ControlMaster (see docs/hpc/access.md). This
module never tries to authenticate: if the master is down it says so and stops, rather than
hanging thousands of commands on a passphrase prompt that nothing can answer.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
import tomllib
from pathlib import Path

from tournament.gitutil import REPO_ROOT
from tournament.plan import load_manifest, load_schedule, run_dir

CONFIG_PATH = Path(__file__).resolve().parent / "hpc.toml"
PACKAGE_DIR = Path(__file__).resolve().parent


class HpcError(RuntimeError):
    pass


def config() -> dict:
    with open(CONFIG_PATH, "rb") as handle:
        return tomllib.load(handle)


# --------------------------------------------------------------------------------------------
# ssh plumbing
# --------------------------------------------------------------------------------------------


def check_connection(host: str) -> None:
    """Fail fast and actionably if the ControlMaster is not up."""
    probe = subprocess.run(
        ["ssh", "-O", "check", host], capture_output=True, text=True
    )
    if probe.returncode == 0:
        return
    raise HpcError(
        f"no live ssh session to '{host}'.\n"
        f"Open one (it persists 8h, and needs your key passphrase + DTU password):\n\n"
        f"    SSH_ASKPASS_REQUIRE=never ssh {host} true\n\n"
        f"SSH_ASKPASS_REQUIRE=never matters when DISPLAY is set: without it ssh tries to pop a\n"
        f"GUI askpass helper and fails silently instead of prompting in the terminal."
    )


def ssh(host: str, command: str, check: bool = True, quiet: bool = False, login: bool = True) -> str:
    """Run a command on the cluster.

    Wrapped in a login shell by default: a plain non-interactive ssh gets neither the LSF tools
    (bsub/bjobs live under /lsf/... and are only added to PATH by the login profile) nor the
    `module` function. Pass login=False for anything that must not inherit the profile.
    """
    remote = f"bash -lc {shlex.quote(command)}" if login else command
    result = subprocess.run(
        ["ssh", host, remote], capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise HpcError(f"remote command failed ({result.returncode}): {command}\n{result.stderr}")
    if result.stderr.strip() and not quiet:
        print(result.stderr.strip())
    return result.stdout


def rsync(source: str, destination: str, delete: bool = False, extra: list[str] | None = None) -> None:
    command = ["rsync", "-az", "--partial"]
    if delete:
        command.append("--delete")
    command += extra or []
    command += [source, destination]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HpcError(f"rsync failed: {' '.join(command)}\n{result.stderr}")


def remote_root(settings: dict) -> str:
    return settings["remote_root"]


def remote_run(settings: dict, tid: str) -> str:
    return f"{remote_root(settings)}/{tid}"


# --------------------------------------------------------------------------------------------
# push
# --------------------------------------------------------------------------------------------


def push(tid: str, settings: dict | None = None, bootstrap: bool = False) -> None:
    """Upload the tournament package and the run directory, optionally bootstrapping the venv."""
    settings = settings or config()
    host = settings["host"]
    check_connection(host)

    local = run_dir(tid)
    if not (local / "schedule.jsonl").exists():
        raise HpcError(f"no schedule in {local} -- run `plan --tid {tid}` first")

    root = remote_root(settings)
    ssh(host, f"mkdir -p {shlex.quote(root)}/{shlex.quote(tid)}")

    # The package is shared across tournaments; only .py files and the shell script are needed.
    print(f"pushing tournament package -> {host}:{root}/tournament/")
    rsync(
        f"{PACKAGE_DIR}/",
        f"{host}:{root}/tournament/",
        extra=[
            "--include=*.py",
            "--include=*.sh",
            "--include=*.toml",
            "--exclude=runs/",
            "--exclude=__pycache__/",
            "--exclude=*",
        ],
    )
    rsync(f"{PACKAGE_DIR}/bootstrap.sh", f"{host}:{root}/bootstrap.sh")
    ssh(host, f"chmod +x {shlex.quote(root)}/bootstrap.sh")

    # Bots, maps and the schedule. Results are excluded: they flow the other way, and --delete
    # here would wipe results produced by a previous submission.
    print(f"pushing run directory -> {host}:{root}/{tid}/")
    rsync(
        f"{local}/",
        f"{host}:{root}/{tid}/",
        extra=[
            "--exclude=results/", "--exclude=logs/", "--exclude=matches.csv",
            "--exclude=ratings.csv", "--exclude=compliance.csv",
            "--exclude=compliance_matches.csv",
        ],
    )
    ssh(host, f"mkdir -p {shlex.quote(root)}/{shlex.quote(tid)}/results "
              f"{shlex.quote(root)}/{shlex.quote(tid)}/logs")

    if bootstrap:
        print("running bootstrap.sh on the cluster (this installs fcode; takes a minute)")
        output = ssh(host, f"cd {shlex.quote(root)} && sh bootstrap.sh")
        print(output)
    else:
        probe = ssh(host, f"test -x {shlex.quote(root)}/venv/bin/python3 && echo ok || echo missing")
        if "missing" in probe:
            raise HpcError(
                f"no venv at {root}/venv on {host}. Re-run with --bootstrap "
                f"(or run `cd {root} && sh bootstrap.sh` there yourself)."
            )
    print("push complete")


# --------------------------------------------------------------------------------------------
# submit
# --------------------------------------------------------------------------------------------


def job_script(
    tid: str, settings: dict, indices: str, name: str, chunk: int, worklist: str
) -> str:
    """An LSF array job. Element i plays the i-th group of `chunk` matches from `worklist`.

    `%<throttle>` caps concurrently running elements. Email flags are deliberately absent -- the
    job-array docs warn that notifications on a large array produce one mail per element.

    Elements index into a *file of schedule indices* rather than computing a contiguous range.
    That is what lets chunking and skip-already-done coexist: the outstanding matches are usually
    scattered through the schedule, so an element covering a contiguous range would re-run
    finished work. `sed -n 'first,last p'` also handles the ragged final element for free -- it
    simply yields fewer lines.
    """
    body = f"""
first=$(( ($LSB_JOBINDEX - 1) * {chunk} + 1 ))
last=$(( $LSB_JOBINDEX * {chunk} ))
for index in $(sed -n "${{first}},${{last}}p" {worklist}); do
    python3 -m tournament.run_match --run-dir {tid} --index "$index" || true
done
"""
    return f"""#!/bin/sh
#BSUB -q {settings["queue"]}
#BSUB -J "{name}[{indices}]%{settings["throttle"]}"
#BSUB -n {settings["cores"]}
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem={settings["memory"]}]"
#BSUB -W {settings["walltime"]}
#BSUB -o {tid}/logs/%J_%I.out
#BSUB -e {tid}/logs/%J_%I.err

set -eu
# LSF resolves the -o/-e paths above, and starts the job, relative to the submission directory.
cd "${{LS_SUBCWD:-$PWD}}"

# Batch jobs get a clean environment (docs/hpc/modules.md), and `module` is a shell function that
# only exists once gbar.sh has been sourced. `set -u` comes off first: gbar.sh pulls in
# /apps/dcc/etc/profile, which reads an unset $DT and would abort the job.
set +u
. /etc/profile.d/gbar.sh 2>/dev/null || true
if [ -f .python-module ]; then
    module load "$(cat .python-module)"
fi
. venv/bin/activate
set -u

# PYTHONPATH so `tournament` resolves from the shared package directory next to this script.
export PYTHONPATH="$PWD:${{PYTHONPATH:-}}"
{body}"""


def compress_indices(indices: list[int]) -> str:
    """Collapse a sorted index list into LSF range notation: [1-5,9,12-20]."""
    if not indices:
        raise HpcError("nothing to submit: every match already has a result")
    parts: list[str] = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = index
    parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(parts)


# Slowest match seen in 14,465 real results was 63.9s; round up for headroom. Used only to check
# that walltime covers a full element -- see the walltime note in hpc.toml.
SLOWEST_MATCH_SECONDS = 66


def check_walltime(settings: dict, chunk: int) -> None:
    """Refuse to submit an element that cannot finish inside its walltime.

    Walltime is a hard kill. An element running `chunk` matches back to back needs
    chunk x worst-case-match seconds; getting this wrong silently wastes a whole element's work
    (recoverable -- a re-submit picks the gaps back up -- but only after the fact).
    """
    minutes = int(str(settings["walltime"]).split(":")[0])
    needed = chunk * SLOWEST_MATCH_SECONDS
    if needed > minutes * 60:
        raise HpcError(
            f"walltime {minutes} min cannot cover {chunk} matches x {SLOWEST_MATCH_SECONDS}s "
            f"= {needed / 60:.1f} min. Raise `walltime` in hpc.toml or lower --chunk."
        )


def max_array_size(host: str, fallback: int = 1000) -> int:
    """LSF's MAX_JOB_ARRAY_SIZE. Exceeding it fails with 'Job array index too large'.

    Not mentioned in DTU's job-array documentation; this cluster reports 1000. Queried rather than
    hardcoded so a config change on the cluster does not silently break submission.
    """
    output = ssh(host, "bparams -a 2>/dev/null | grep MAX_JOB_ARRAY_SIZE", check=False, quiet=True)
    for piece in output.replace("=", " ").split():
        if piece.isdigit():
            return int(piece)
    return fallback


def submit(
    tid: str,
    settings: dict | None = None,
    chunk: int | None = None,
    include_done: bool = False,
) -> list[str]:
    """Submit the outstanding matches as one or more LSF arrays. Returns the job ids.

    **Matches that already have a result are skipped by default.** run_match would skip them
    anyway, but only after the job had been scheduled and paid its startup -- so submitting them
    wastes slots on a contended queue. Pass include_done=True to force a full re-run.

    Each array element plays `chunk` matches (default from hpc.toml, 20). An element costs ~3s of
    module load, venv activation and interpreter startup, so batching removes most of that and
    cuts the number of arrays -- LSF caps a single array at MAX_JOB_ARRAY_SIZE (1000 here), and
    arrays are slow to submit. Pass chunk=1 for one individually retryable job per match.
    """
    settings = settings or config()
    host = settings["host"]
    chunk = settings.get("chunk", 20) if chunk is None else chunk
    check_walltime(settings, chunk)
    check_connection(host)

    local = run_dir(tid)
    matches = load_schedule(local)

    if include_done:
        indices = [m.index for m in matches]
        print(f"submitting all {len(indices)} matches (--all: ignoring existing results)")
    else:
        finished = remote_finished(tid, settings) | local_finished(local)
        indices = [m.index for m in matches if m.match_id not in finished]
        skipped = len(matches) - len(indices)
        if skipped:
            print(f"skipping {skipped} matches that already have results")
    if not indices:
        raise HpcError("nothing to submit: every match already has a result")

    root = remote_root(settings)
    limit = max_array_size(host)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    worklist = f"{tid}/work_{stamp}.txt"

    # The element -> match mapping lives in this file, so a scattered set of outstanding indices
    # chunks exactly as well as a contiguous one.
    worklist_path = local / f"work_{stamp}.txt"
    worklist_path.write_text("\n".join(str(i) for i in indices) + "\n")
    rsync(str(worklist_path), f"{host}:{root}/{worklist}")

    elements = list(range(1, (len(indices) + chunk - 1) // chunk + 1))
    print(f"{len(indices)} matches at {chunk} per element -> {len(elements)} array elements")

    chunks = [elements[start : start + limit] for start in range(0, len(elements), limit)]
    if len(chunks) > 1:
        print(f"splitting into {len(chunks)} arrays (LSF caps one at {limit})")

    state_path = local / "hpc.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    job_ids: list[str] = []

    for number, group in enumerate(chunks, start=1):
        name = f"trn_{tid}_{number}"[:60] if len(chunks) > 1 else f"trn_{tid}"[:60]
        script = job_script(tid, settings, compress_indices(group), name, chunk, worklist)
        script_path = local / f"job_{stamp}_{number}.sh"
        script_path.write_text(script)
        rsync(str(script_path), f"{host}:{root}/job_{stamp}_{number}.sh")

        output = ssh(host, f"cd {shlex.quote(root)} && bsub < job_{stamp}_{number}.sh")
        job_id = output.split("<", 1)[1].split(">", 1)[0] if "<" in output else ""
        if not job_id:
            raise HpcError(f"could not parse a job id from bsub output: {output!r}")
        job_ids.append(job_id)
        state.setdefault("submissions", []).append(
            {
                "job_id": job_id,
                "name": name,
                "elements": len(group),
                "chunk": chunk,
                "range": f"{group[0]}-{group[-1]}",
                "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        )
        print(f"  array {number}/{len(chunks)}: {len(group)} elements -> job {job_id}", flush=True)

    state["job_ids"] = job_ids
    state["job_id"] = job_ids[0]
    state["host"] = host
    state["remote"] = remote_run(settings, tid)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"submitted {len(indices)} matches across {len(job_ids)} array(s)")
    return job_ids


def cancel(tid: str, settings: dict | None = None) -> None:
    """Kill every array submitted for this tournament."""
    settings = settings or config()
    host = settings["host"]
    check_connection(host)
    state_path = run_dir(tid) / "hpc.json"
    if not state_path.exists():
        raise HpcError(f"no submission recorded for {tid}")
    state = json.loads(state_path.read_text())
    job_ids = state.get("job_ids") or ([state["job_id"]] if state.get("job_id") else [])
    for job_id in job_ids:
        print(ssh(host, f"bkill {job_id} 2>&1 || true", check=False, quiet=True).strip())


# Everything a finished run leaves on the cluster that this machine already has a copy of.
# schedule.jsonl and the job scripts stay: they are small, and they are what makes a remote run
# directory legible if someone goes looking months later.
WORKSPACE_DIRS = ("results", "logs", "stage", "compliance-stage")


def discard_workspace(tid: str, settings: dict | None = None) -> None:
    """Delete the bulky remote scratch of a run whose results are merged and rated locally.

    The cluster home is a 30 GB per-user quota, and a run costs ~400 MB of it: ~216 MB of staged
    bot sources (every entrant, re-copied per run), ~154 MB of per-match result JSON and ~34 MB of
    LSF logs. Nothing used to remove any of it, so the quota filled twice. The second time, on
    2026-08-06, rsync failed mid-push with "No space left on device", the run never reached bsub,
    and because no hpc.json was written neither recovery path could see it -- the ladder sat at
    0/6489 for four hours.

    Safe by construction: every file here has already been fetched and merged into matches.csv
    before finalise() gets this far, and local_finished() unions the local result set with the
    remote one precisely so a cleaned run is not re-run.

    Never raises. Reclaiming space is housekeeping; failing a rated, published run over it would
    trade a disk problem for a ladder problem.
    """
    settings = settings or config()
    root = remote_run(settings, tid)
    if not tid or "/" in tid or tid.startswith("."):
        raise HpcError(f"refusing to clean a suspicious tid: {tid!r}")
    targets = " ".join(shlex.quote(f"{root}/{name}") for name in WORKSPACE_DIRS)
    try:
        ssh(settings["host"], f"rm -rf -- {targets}", check=True, quiet=True)
    except (HpcError, OSError) as error:
        print(f"  {tid}: could not reclaim remote workspace ({error})")
        return
    print(f"  {tid}: reclaimed remote workspace ({', '.join(WORKSPACE_DIRS)})")


# Deliberately no pre-flight quota check. DTU's getquota_zhome.sh reports a figure refreshed
# only every ~240 minutes -- it still read "30.00G of 30.00G" long after 20 GB had been deleted --
# so gating a submission on it would block pushes that would in fact succeed, and would miss a
# quota filled since the last refresh. Cleaning up after every finished run is what keeps the
# headroom; resubmit_abandoned_runs() is what recovers when a push fails anyway.


# --------------------------------------------------------------------------------------------
# status / fetch / watch
# --------------------------------------------------------------------------------------------


def local_finished(local: Path) -> set[str]:
    """match_ids already fetched to this machine.

    Unioned with the remote set so a tournament whose results were fetched and then cleaned off
    the cluster is not silently re-run.
    """
    return {path.stem for path in (local / "results").glob("*.json")}


def remote_finished(tid: str, settings: dict) -> set[str]:
    """match_ids that already have a result file on the cluster."""
    root = remote_run(settings, tid)
    listing = ssh(
        settings["host"],
        f"ls {shlex.quote(root)}/results 2>/dev/null | sed 's/\\.json$//'",
        check=False,
        quiet=True,
    )
    return {line.strip() for line in listing.splitlines() if line.strip()}


def status(tid: str, settings: dict | None = None) -> dict:
    settings = settings or config()
    host = settings["host"]
    check_connection(host)

    local = run_dir(tid)
    total = len(load_schedule(local))
    root = remote_run(settings, tid)

    count = ssh(
        host, f"ls {shlex.quote(root)}/results 2>/dev/null | wc -l", check=False, quiet=True
    ).strip()
    done = int(count or 0)

    state_path = local / "hpc.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    job_ids = state.get("job_ids") or ([state["job_id"]] if state.get("job_id") else [])

    summary = ""
    if job_ids:
        summary = ssh(
            host, f"bjobs -A {' '.join(job_ids)} 2>&1 || true", check=False, quiet=True
        ).strip()

    print(f"{tid}: {done}/{total} matches done on the cluster ({100 * done / total:.1f}%)")
    if summary:
        print(summary)
    return {"total": total, "done": done, "job_ids": job_ids, "bjobs": summary}


def fetch(tid: str, settings: dict | None = None) -> int:
    """Pull down whatever results exist and re-merge. Safe to run mid-flight."""
    from tournament.merge import merge

    settings = settings or config()
    host = settings["host"]
    check_connection(host)

    local = run_dir(tid)
    (local / "results").mkdir(parents=True, exist_ok=True)
    root = remote_run(settings, tid)

    # No --delete: local results are the durable copy.
    rsync(f"{host}:{root}/results/", f"{local}/results/", extra=["--exclude=.*.tmp"])
    _, rows = merge(local)
    print(f"{tid}: {rows} results merged into {local / 'matches.csv'}")
    return rows


def watch(tid: str, settings: dict | None = None, interval: int = 60) -> None:
    """Poll until every match has a result, fetching as they land."""
    settings = settings or config()
    total = len(load_schedule(run_dir(tid)))
    while True:
        rows = fetch(tid, settings)
        if rows >= total:
            print(f"{tid}: complete ({rows}/{total})")
            return
        state = status(tid, settings)
        if state["bjobs"] and "not found" in state["bjobs"].lower():
            print(
                f"{tid}: job is gone but only {rows}/{total} results exist. "
                f"Re-run `hpc submit --tid {tid}` -- it submits only the gaps."
            )
            return
        print(f"  sleeping {interval}s\n", flush=True)
        time.sleep(interval)


def logs(tid: str, settings: dict | None = None, lines: int = 40) -> None:
    """Show the tail of the most recent failing job log -- the first thing to check on trouble."""
    settings = settings or config()
    host = settings["host"]
    check_connection(host)
    root = remote_run(settings, tid)
    output = ssh(
        host,
        f"find {shlex.quote(root)}/logs -name '*.err' -size +0 -printf '%T@ %p\\n' 2>/dev/null "
        f"| sort -rn | head -3 | cut -d' ' -f2- "
        f"| xargs -r -I@ sh -c 'echo \"--- @ ---\"; tail -{lines} @'",
        check=False,
    )
    print(output.strip() or "(no non-empty error logs)")
