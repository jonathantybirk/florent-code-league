#!/usr/bin/env bash
# Play the bot across many maps and opponents with tracebacks enabled, and
# report every distinct crash site. A crashed Builder is swallowed by the
# handler and simply stops working, so this is invisible in a win rate.
set -u
S=${TMPDIR:-/tmp}/fcl-bench-$$; mkdir -p "$S"; trap 'rm -rf "$S"' EXIT
SRC=${1:-bots/luc/steward_hardened_reinforced}
rm -rf "$S/hunt" && cp -r "$SRC" "$S/hunt" && rm -rf "$S/hunt/__pycache__"
python3 - "$S/hunt/builder.py" <<'EOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
t = t.replace('''        print(f"BUILDER_CRASH id={ct.get_id()} round={ct.get_current_round()} "
              f"error={error!r}", file=sys.stderr, flush=True)''',
'''        import traceback
        print(f"BUILDER_CRASH {error!r}\\n{traceback.format_exc()}", file=sys.stderr, flush=True)''')
p.write_text(t)
EOF

: > "$S/hunt.err"
for m in quarry hive aurora longship twins bridge vase sweden jackpot fjord sprint showdown vault runestone skerry crossfire pinch duel string atoll strait; do
  for opp in vidar vigil prospect heimdall; do
    uv run python -m benchmarks.run_one --a "$S/hunt/main.py" --b "bots/luc/$opp/main.py" \
        --map "maps/$m.map26" --out "$S/hunt.json" 2>>"$S/hunt.err" >/dev/null
  done
done
echo "=== distinct crash sites ==="
grep -E '^  File .*(builder|core|sentinel|launcher|gunner)\.py' "$S/hunt.err" \
  | sed 's/.*scratchpad\/hunt\///' | sort | uniq -c | sort -rn | head -20
echo "=== distinct errors ==="
grep -E '^(ValueError|KeyError|IndexError|TypeError|AttributeError|NameError|ZeroDivisionError)' "$S/hunt.err" | sort | uniq -c | sort -rn | head -10
echo "total crashes: $(grep -c BUILDER_CRASH "$S/hunt.err")"
