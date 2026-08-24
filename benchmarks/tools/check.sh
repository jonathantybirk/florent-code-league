#!/usr/bin/env bash
# Gate every edit: undefined names (the launcher.py NameError class of bug),
# then one real match so an init-block exception cannot hide behind a caught
# handler and score 0.000 across a whole panel.
set -u
BOT=${1:-bots/luc/steward_hardened_reinforced}
S=${TMPDIR:-/tmp}/fcl-bench-$$; mkdir -p "$S"; trap 'rm -rf "$S"' EXIT

python3 - "$BOT" <<'EOF'
import sys, ast, pathlib, builtins
bot = pathlib.Path(sys.argv[1])
bad = False
for f in sorted(bot.glob("*.py")):
    tree = ast.parse(f.read_text())
    defined = set(dir(builtins))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): defined.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store): defined.add(n.id)
        elif isinstance(n, ast.arg): defined.add(n.arg)
        elif isinstance(n, ast.alias): defined.add((n.asname or n.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name: defined.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)): defined.update(n.names)
    missing = {n.id for n in ast.walk(tree)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - defined
    if missing:
        print(f"UNDEFINED in {f.name}: {sorted(missing)}")
        bad = True
sys.exit(1 if bad else 0)
EOF
[ $? -ne 0 ] && { echo "FAIL: undefined names"; exit 1; }

uv run python -m benchmarks.run_one --a "$BOT/main.py" --b bots/luc/vidar/main.py \
    --map maps/quarry.map26 --out "$S/check.json" 2>"$S/check.err" >/dev/null
if grep -qE "CRASH|Traceback|PLAN_FAILED .*(NameError|AttributeError)" "$S/check.err"; then
    echo "FAIL: runtime errors"; grep -E "CRASH|NameError|AttributeError" "$S/check.err" | head -3; exit 1
fi
python3 -c "
import json,sys
d=json.load(open('$S/check.json'))
print('OK: status', d['status'], 'rounds', d.get('metrics',{}).get('rounds'))
sys.exit(0 if d['status']=='ok' else 1)"
