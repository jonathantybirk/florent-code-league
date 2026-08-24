"""Regenerate bots/luc/maporacle's vendored sub-bots as one flat namespace.

The submission sandbox does not expose the bot as files: ``__file__`` is
undefined, the working directory is ``/``, and no ``sys.path`` entry holds the
bot.  Sibling modules are importable anyway -- that is how odin's own
``import builder`` works on the server -- so the archive's modules are injected
by name, and anything that reaches for a *path* (``sub/odin/main.py``) fails to
load.  Everything therefore has to live flat at the archive root.

Flat means the three bots' identically-named modules (``builder``, ``core``,
``constants``, ...) would collide, so each is copied to ``<bot>_<module>.py``
and its intra-bot imports are rewritten to match.  ``import builder`` becomes
``import odin_builder as builder`` so that every ``builder.foo()`` call site in
the body still reads the same.

Usage:  uv run python tools/build_maporacle.py
"""

import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "bots" / "luc" / "maporacle"
SOURCES = {"heimdall": "heimdall", "odin": "odin", "vigil": "vigil"}


def target_name(prefix: str, module: str) -> str:
    """The flat module name a sub-bot's module is copied to.

    Atlas modules keep `atlas` as their *leading* component -- `atlas_vigil`,
    not `vigil_atlas`.  tournament/fairness.py decides fairness by reading the
    code rather than the directory, and it matches `import atlas\\w*` /
    `from atlas\\w* import`.  A `vigil_atlas` name slips straight past it, so
    this bot would enter the ladder labelled fair while carrying vigil's
    published-map oracle -- exactly the mislabelling that classifier exists to
    catch.  Keeping the prefix in front keeps the detection honest.
    """
    if module.startswith("atlas"):
        return "%s_%s" % (module, prefix)
    return "%s_%s" % (prefix, module)


def rewrite(text: str, prefix: str, local: set[str]) -> str:
    """Point every intra-bot import at its flattened copy."""

    def fix_import(match: re.Match) -> str:
        module = match.group(1)
        if module not in local:
            return match.group(0)
        # `as module` keeps every existing `module.attr` call site valid.
        return "import %s as %s" % (target_name(prefix, module), module)

    def fix_from(match: re.Match) -> str:
        module = match.group(1)
        if module not in local:
            return match.group(0)
        return "from %s import" % target_name(prefix, module)

    text = re.sub(r"^import ([a-z_][a-z0-9_]*)$", fix_import, text, flags=re.M)
    text = re.sub(r"^(?:from) ([a-z_][a-z0-9_]*) import", fix_from, text, flags=re.M)
    # TYPE_CHECKING-only, indented, and never executed -- but keep it honest.
    text = re.sub(
        r"^(\s+)from main import",
        r"\1from %s import" % target_name(prefix, "main"),
        text,
        flags=re.M,
    )
    return text


def main() -> None:
    shutil.rmtree(OUT / "sub", ignore_errors=True)
    for stale in OUT.glob("*_*.py"):
        stale.unlink()

    written = 0
    for prefix, directory in SOURCES.items():
        source = ROOT / "bots" / "luc" / directory
        modules = {p.stem for p in source.glob("*.py")}
        for path in sorted(source.glob("*.py")):
            target = OUT / ("%s.py" % target_name(prefix, path.stem))
            target.write_text(rewrite(path.read_text(), prefix, modules))
            written += 1
        print("%-9s %2d modules from %s" % (prefix, len(modules), source))
    print("wrote %d files to %s" % (written, OUT))


if __name__ == "__main__":
    main()
