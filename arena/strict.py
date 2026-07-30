"""Pre-submission gate. Run this before every submission; treat a FAIL as blocking.

Two halves.

Static audit -- catches the failure modes that turn a working bot into a zero
without any error message:

  * the engine's AST validator (reimplemented byte-for-byte from the rules
    embedded in fcode_engine, see `ALLOWED` and `check_source`). A rejected
    submission does not play at all.
  * a UTF-8 BOM at the head of a shipped file.
  * a stray `__pycache__` or `.pyc`, which makes the engine run the bot INERT
    with no error (G30) -- the single most expensive silent failure available.
  * a `.py` in the bot directory that nothing imports: it is still compiled and
    still validated, so dead code can fail a submission that otherwise works.
  * an entry point that is not `main.py` with a top-level `class Player` (G24).
  * `import numpy`, which cannot load inside the sandbox at all (G28).

Determinism check -- fails if the bot does not repeat on identical inputs. The
engine is deterministic, but a bot is not automatically: a fresh sub-interpreter
seeds `random` from os.urandom, so an unseeded bot plays a different match every
time and no sweep can be trusted. The shipped starter has this bug.

Runtime sweep -- plays the mirrored 30-game sweep against the zoo with replays
requested and fails if any of OUR units was deleted by an exception. An uncaught
exception permanently deletes the unit (G23); the shipped starter loses builders
this way 520 times across 90 games and never reports a thing.

Usage::

    python -m arena.strict bots/mybot
    python -m arena.strict bots/mybot --static-only
    python -m arena.strict bots/mybot --vs starter_fixed
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

from arena import ALL_15, bot_dir, bot_name, resolve_bot

BOM = b"\xef\xbb\xbf"

#: Exact copy of the allowlist the engine's AST validator uses. Extracted from the
#: validator source embedded in fcode_engine.cp313-win_amd64.pyd. Note what is NOT
#: here: BaseException, KeyboardInterrupt, SystemExit.
ALLOWED = {
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "BaseExceptionGroup",
    "BlockingIOError",
    "BrokenPipeError",
    "BufferError",
    "BytesWarning",
    "ChildProcessError",
    "ConnectionAbortedError",
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "DeprecationWarning",
    "EOFError",
    "EncodingWarning",
    "EnvironmentError",
    "Exception",
    "ExceptionGroup",
    "FileExistsError",
    "FileNotFoundError",
    "FloatingPointError",
    "FutureWarning",
    "GeneratorExit",
    "IOError",
    "ImportError",
    "ImportWarning",
    "IndentationError",
    "IndexError",
    "InterruptedError",
    "IsADirectoryError",
    "KeyError",
    "LookupError",
    "MemoryError",
    "ModuleNotFoundError",
    "NameError",
    "NotADirectoryError",
    "NotImplementedError",
    "OSError",
    "OverflowError",
    "PendingDeprecationWarning",
    "PermissionError",
    "ProcessLookupError",
    "RecursionError",
    "ReferenceError",
    "ResourceWarning",
    "RuntimeError",
    "RuntimeWarning",
    "StopAsyncIteration",
    "StopIteration",
    "SyntaxError",
    "SyntaxWarning",
    "SystemError",
    "TabError",
    "TimeoutError",
    "TypeError",
    "UnboundLocalError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "UnicodeError",
    "UnicodeTranslateError",
    "UnicodeWarning",
    "UserWarning",
    "ValueError",
    "Warning",
    "ZeroDivisionError",
    "GameError",
}

#: Cannot be imported inside a bot sub-interpreter under any circumstances (G28).
BANNED_IMPORTS = {"numpy", "scipy", "pandas", "torch", "sklearn"}


def check_source(source: str, fpath: str) -> list[str]:
    """Reimplementation of the engine's AST validator. Returns violation strings.

    Mirrors the engine exactly, including its blind spot: the engine tests
    `isinstance(node, ast.Try)`, and `ast.TryStar` (`try/except*`) is a sibling
    class, not a subclass, so a `finally` under `except*` slips past. We match the
    engine rather than being stricter than it, so that a PASS here means a PASS
    there. `except*` handlers ARE checked, by both -- they are ExceptHandler nodes.
    """
    out: list[str] = []
    try:
        tree = ast.parse(source, filename=fpath)
    except SyntaxError as exc:
        return [f"{fpath}:{exc.lineno}: syntax error: {exc.msg}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            out.append(f"{fpath}:{node.finalbody[0].lineno}: `finally` blocks are not allowed")
        if not isinstance(node, ast.ExceptHandler):
            continue
        lineno = node.lineno
        ty = node.type
        if ty is None:
            out.append(
                f"{fpath}:{lineno}: bare `except:` is not allowed; use a specific exception type"
            )
            continue
        if isinstance(ty, ast.Name):
            names = [ty.id]
        elif isinstance(ty, ast.Tuple):
            if not all(isinstance(e, ast.Name) for e in ty.elts):
                out.append(f"{fpath}:{lineno}: except handler types must be plain names")
                continue
            names = [e.id for e in ty.elts]  # type: ignore[attr-defined]
        else:
            out.append(f"{fpath}:{lineno}: except handler types must be plain names")
            continue
        for name in names:
            if name not in ALLOWED:
                out.append(f"{fpath}:{lineno}: `{name}` is not an allowed exception type")
    return out


def _top_level_imports(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the bot package
                if node.module:
                    mods.add(node.module.split(".")[0])
            elif node.module:
                mods.add(node.module.split(".")[0])
    return mods


def _reachable_files(root: Path) -> set[Path]:
    """The .py files reachable from main.py by static import analysis.

    Import names are matched against both sibling modules (`import helper` ->
    helper.py) and package directories (`from pkg import x` -> everything under
    pkg/). Treating a package as wholly reachable is deliberate: a package's
    __init__ can pull in siblings dynamically, and a false "stray file" would be
    a gate that cries wolf.
    """
    files = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    by_stem: dict[str, Path] = {}
    for p in files:
        by_stem.setdefault(p.stem, p)
    pkg_dirs = {d.name: d for d in root.rglob("*") if d.is_dir() and d.name != "__pycache__"}

    main_py = root / "main.py"
    seen: set[Path] = set()
    stack: list[Path] = [main_py] if main_py.is_file() else []
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for mod in _top_level_imports(tree):
            if mod in pkg_dirs:
                for q in pkg_dirs[mod].rglob("*.py"):
                    if "__pycache__" not in q.parts and q not in seen:
                        stack.append(q)
            elif mod in by_stem and by_stem[mod] not in seen:
                stack.append(by_stem[mod])
    return seen


def static_audit(bot: str | os.PathLike[str]) -> dict:
    """Everything that can be decided from the files alone."""
    main_py = resolve_bot(bot)
    root = bot_dir(main_py)
    failures: list[str] = []
    checks: dict[str, str] = {}

    # --- entry point -------------------------------------------------------
    if main_py.name != "main.py":
        failures.append(f"entry point is {main_py.name}, must be main.py (G24)")
    entry_ok = False
    if main_py.is_file():
        try:
            tree = ast.parse(main_py.read_text(encoding="utf-8", errors="replace"))
            entry_ok = any(
                isinstance(n, ast.ClassDef) and n.name == "Player" for n in tree.body
            )
        except SyntaxError as exc:
            failures.append(f"main.py:{exc.lineno}: syntax error: {exc.msg}")
    if not entry_ok:
        failures.append("main.py has no top-level `class Player` (G24)")
    checks["entry_point"] = "ok" if entry_ok and main_py.name == "main.py" else "FAIL"

    # --- __pycache__ / .pyc ------------------------------------------------
    stale = [p for p in root.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
    for p in stale:
        failures.append(
            f"stray bytecode {p.relative_to(root)} -- makes the engine run the bot INERT (G30)"
        )
    checks["no_pycache"] = "ok" if not stale else f"FAIL ({len(stale)})"

    # --- BOM ---------------------------------------------------------------
    bom_hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        with open(p, "rb") as fh:
            if fh.read(3) == BOM:
                bom_hits.append(p)
                failures.append(f"{p.relative_to(root)} starts with a UTF-8 BOM")
    checks["no_bom"] = "ok" if not bom_hits else f"FAIL ({len(bom_hits)})"

    # --- AST validator -----------------------------------------------------
    py_files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    ast_violations: list[str] = []
    for p in py_files:
        rel = p.relative_to(root).as_posix()
        ast_violations.extend(
            check_source(p.read_text(encoding="utf-8", errors="replace"), f"<bot>/{rel}")
        )
    failures.extend(ast_violations)
    checks["ast_validator"] = "ok" if not ast_violations else f"FAIL ({len(ast_violations)})"

    # --- stray modules -----------------------------------------------------
    reachable = _reachable_files(root)
    stray = [p for p in py_files if p not in reachable and p.name != "__init__.py"]
    for p in stray:
        failures.append(
            f"{p.relative_to(root)} is not imported from main.py -- it still ships and is "
            "still validated; delete it or import it"
        )
    checks["no_stray_py"] = "ok" if not stray else f"FAIL ({len(stray)})"

    # --- banned imports ----------------------------------------------------
    banned_hits: list[str] = []
    for p in py_files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for mod in _top_level_imports(tree) & BANNED_IMPORTS:
            banned_hits.append(f"{p.relative_to(root)}: imports {mod}, unavailable in the sandbox (G28)")
    failures.extend(banned_hits)
    checks["no_banned_imports"] = "ok" if not banned_hits else f"FAIL ({len(banned_hits)})"

    return {
        "bot": bot_name(main_py),
        "bot_dir": str(root),
        "main_py": str(main_py),
        "files": [str(p.relative_to(root)) for p in py_files],
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }


def runtime_sweep(
    bot: str | os.PathLike[str],
    opponents: Sequence[str] | None = None,
    maps: Sequence[str] = ALL_15,
    seed: int = 1,
    workers: int | None = None,
    replay_dir: str | os.PathLike[str] | None = None,
) -> dict:
    """Mirrored 30-game sweep per opponent, with replays, checking for dead units."""
    from arena.score import compare
    from arena.zoo import ensure_zoo

    main_py = resolve_bot(bot)
    if opponents is None:
        opponents = list(ensure_zoo().keys())

    base = Path(replay_dir or (Path("replays") / f"strict_{bot_name(main_py)}"))
    reports = []
    failures: list[str] = []
    total_exc = 0
    total_crashed = 0
    for opp in opponents:
        opp_path = resolve_bot(opp)
        rep = compare(
            main_py,
            opp_path,
            maps=maps,
            seed=seed,
            workers=workers,
            replays=True,
            replay_dir=base / bot_name(opp_path),
            capture=True,
        )
        exc = rep["exceptions"]["x"]
        total_exc += exc
        total_crashed += rep["crashed"]
        if exc:
            samples = []
            for r in rep["results"]:
                for s in r.get("traceback_samples") or []:
                    if str(main_py.parent).lower() in s.lower():
                        samples.append(s)
            failures.append(
                f"vs {rep['y']}: {exc} of our units were deleted by an uncaught exception (G23)"
                + (f"\n--- first traceback ---\n{samples[0]}" if samples else "")
            )
        replay_hits = sum(r.get("replay_traceback_hits") or 0 for r in rep["results"])
        if replay_hits:
            failures.append(
                f"vs {rep['y']}: {replay_hits} traceback markers found inside the .replay26 bytes"
            )
        if rep["crashed"]:
            failures.append(f"vs {rep['y']}: {rep['crashed']} games crashed in the harness")
        reports.append(rep)

    return {
        "bot": bot_name(main_py),
        "opponents": [r["y"] for r in reports],
        "reports": reports,
        "our_exceptions": total_exc,
        "crashed_games": total_crashed,
        "failures": failures,
        "passed": not failures,
    }


#: Four maps with distinct topologies; enough to expose an unseeded RNG immediately.
DETERMINISM_MAPS = ("atoll", "duel", "fjord", "hive")


def determinism_check(
    bot: str | os.PathLike[str],
    maps: Sequence[str] = DETERMINISM_MAPS,
    repeats: int = 2,
    workers: int | None = None,
) -> dict:
    """Fail if the bot does not produce identical results on identical inputs.

    The engine is deterministic; a bot need not be. Each unit runs in its own
    CPython sub-interpreter (G20) and a fresh interpreter seeds `random` from
    os.urandom, which the sandbox does not stub -- so a bot that calls `random`
    without seeding plays a different match every time. That is disqualifying for
    a candidate, because it means no sweep we run can be trusted to have measured
    the change rather than the dice.

    Probed twice: against a deterministic opponent (zoo `idle`, which does
    nothing) and against itself, so a divergence is unambiguously ours.
    """
    from arena.score import determinism_probe
    from arena.zoo import ensure_zoo

    main_py = resolve_bot(bot)
    zoo = ensure_zoo()
    probes = [
        determinism_probe(main_py, zoo["idle"], maps=maps, repeats=repeats, workers=workers),
        determinism_probe(main_py, main_py, maps=maps, repeats=repeats, workers=workers),
    ]
    failures = []
    for p in probes:
        if not p["deterministic"]:
            fields = sorted({f for d in p["diffs"] for f in d["fields"]})
            failures.append(
                f"not reproducible vs {p['b']}: {len(p['diverging_maps'])}/{len(p['maps'])} maps "
                f"differ across {p['repeats']} identical runs (fields: {', '.join(fields)}). "
                "Seed your RNG per unit from ct.get_id() on the unit's first turn."
            )
    return {"probes": probes, "failures": failures, "passed": not failures}


def strict_check(
    bot: str | os.PathLike[str],
    opponents: Sequence[str] | None = None,
    maps: Sequence[str] = ALL_15,
    seed: int = 1,
    workers: int | None = None,
    static_only: bool = False,
    allow_nondeterministic: bool = False,
) -> dict:
    """The gate. `passed` False means: do not submit."""
    static = static_audit(bot)
    runtime = None
    determinism = None
    failures = list(static["failures"])
    if not static_only:
        if static["passed"]:
            determinism = determinism_check(bot, workers=workers)
            if not allow_nondeterministic:
                failures.extend(determinism["failures"])
            runtime = runtime_sweep(bot, opponents, maps, seed, workers)
            failures.extend(runtime["failures"])
        else:
            failures.append("runtime sweep skipped: static audit already failed")
    return {
        "bot": static["bot"],
        "static": static,
        "determinism": determinism,
        "runtime": runtime,
        "failures": failures,
        "passed": not failures,
    }


def format_gate(res: dict) -> str:
    lines = [f"STRICT GATE -- {res['bot']}", "=" * 60, "", "static audit:"]
    for name, status in res["static"]["checks"].items():
        mark = "PASS" if status == "ok" else "FAIL"
        lines.append(f"  [{mark}] {name:<20} {status}")
    lines.append(f"  files: {', '.join(res['static']['files'])}")
    det = res.get("determinism")
    if det is not None:
        lines.append("")
        lines.append("determinism:")
        for p in det["probes"]:
            mark = "PASS" if p["deterministic"] else "FAIL"
            lines.append(
                f"  [{mark}] vs {p['b']:<16} {p['repeats']} identical runs over "
                f"{len(p['maps'])} maps, diverging: {p['diverging_maps'] or 'none'}"
            )
    rt = res["runtime"]
    if rt is not None:
        lines.append("")
        lines.append("runtime sweep:")
        for rep in rt["reports"]:
            lines.append(
                f"  vs {rep['y']:<16} S={rep['S']:+.3f}  our exceptions={rep['exceptions']['x']}  "
                f"crashed={rep['crashed']}  ({rep['throughput']['matches_per_sec']:.2f} m/s)"
            )
        lines.append(f"  total unit-deleting exceptions: {rt['our_exceptions']}")
    lines.append("")
    if res["passed"]:
        lines.append("RESULT: PASS -- safe to submit")
    else:
        lines.append(f"RESULT: FAIL ({len(res['failures'])} blocking issues)")
        for f in res["failures"]:
            lines.append(f"  - {f}")
    return "\n".join(lines)


def _cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Pre-submission gate.")
    ap.add_argument("bot")
    ap.add_argument("--vs", nargs="*", default=None, help="opponents (default: the whole zoo)")
    ap.add_argument("--maps", nargs="*", default=list(ALL_15))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--static-only", action="store_true")
    ap.add_argument(
        "--allow-nondeterministic",
        action="store_true",
        help="report reproducibility failures without blocking (you will regret this)",
    )
    args = ap.parse_args(argv)

    res = strict_check(
        args.bot,
        opponents=args.vs,
        maps=args.maps,
        seed=args.seed,
        workers=args.workers,
        static_only=args.static_only,
        allow_nondeterministic=args.allow_nondeterministic,
    )
    print(format_gate(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
