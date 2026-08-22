"""Local clone of the engine's submission validator, plus packaging invariants.

Run before every submission. Everything here is a rule we verified the real engine enforces
(docs/ground-truth.md G24, G25, G30), so a failure here is a failure on the ladder.
"""

import ast
import builtins
import pathlib
import sys

ALLOWED_EXC = set(dir(builtins)) | {"GameError"}


def check_file(path):
    problems = []
    raw = path.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        problems.append(f"{path}: UTF-8 BOM (engine rejects: invalid non-printable character U+FEFF)")
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except SyntaxError as exc:
        problems.append(f"{path}: SyntaxError {exc}")
        return problems, None
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            problems.append(f"{path}:{node.lineno}: `finally` blocks are not allowed")
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                problems.append(f"{path}:{node.lineno}: bare `except:` is not allowed")
            else:
                # `except (ValueError, GameError):` is ordinary Python and the engine
                # accepts it -- verified by playing a full game with a bot that uses it.
                # This checker rejected every tuple handler as "not a plain name", which
                # was our bug, not the bot's: it failed the team's live flagship, a build
                # sitting on the ladder at 1951 Elo. A validator that is stricter than the
                # thing it models is worse than no validator, because it rejects work that
                # would have shipped.
                handlers = (node.type.elts if isinstance(node.type, ast.Tuple)
                            else [node.type])
                for handler in handlers:
                    if not isinstance(handler, ast.Name):
                        problems.append(f"{path}:{node.lineno}: except handler types must "
                                        f"be plain names or a tuple of them")
                    elif handler.id not in ALLOWED_EXC:
                        problems.append(f"{path}:{node.lineno}: exception name "
                                        f"{handler.id!r} not allowed")
                    elif handler.id in {"BaseException", "KeyboardInterrupt", "SystemExit"}:
                        problems.append(f"{path}:{node.lineno}: exception name "
                                        f"{handler.id!r} not allowed")
    return problems, tree


def main(bot_dir):
    root = pathlib.Path(bot_dir)
    problems = []

    entry = root / "main.py"
    if not entry.is_file():
        problems.append(f"{root}: entry point main.py missing (the CLI docs say bot.py — they are wrong)")

    # A stray __pycache__ makes the engine silently run the bot as INERT (G30).
    for cache in root.rglob("__pycache__"):
        problems.append(f"{cache}: __pycache__ present — engine would run the bot as inert")

    entry_tree = None
    for path in sorted(root.rglob("*.py")):
        file_problems, tree = check_file(path)
        problems.extend(file_problems)
        if path == entry:
            entry_tree = tree

    if entry_tree is not None:
        has_player = any(
            isinstance(n, ast.ClassDef) and n.name == "Player" for n in entry_tree.body
        )
        if not has_player:
            problems.append(f"{entry}: no top-level `class Player`")

    if problems:
        print("FAIL")
        for p in problems:
            print("  " + p)
        return 1
    print(f"PASS  {root} is submission-clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "bot"))
