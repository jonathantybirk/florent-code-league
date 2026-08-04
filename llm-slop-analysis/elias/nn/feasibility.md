# NN inference feasibility on fcode 2.3.3

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Seat: inference feasibility. One question: what is the largest neural network that can
actually run inside the engine's constraints, and is that big enough to be worth anything?

Everything below is measured. Benchmark sources are in the session scratchpad
(`bench_matmul.py`, `bench_tricks.py`, `bench_net.py`, `bench_load.py`, `bench_perunit.py`,
`bench_mem.py`, `gen_probe.py`); in-engine probes are checked in under `bots/probes/`
(`nnclock`, `nnimport`, `nnload256`, `nnload1k`, `nnload2k`, `nnload2kb64`, `nnfloat`).

## Headline

**Inference is not the binding constraint.** A binary (XNOR/popcount) MLP with **1.21 million
weights** — `128 → 1024 → 1024 → 32` — runs a forward pass in **307–442 µs measured inside the
engine**, roughly **4 % of the 10 ms per-unit budget**, with a one-time per-unit load cost of
**536–655 µs**. The same shape as a float MLP would cost 27 ms and 33 MB per unit and is
impossible. The whole feasibility question turns on one CPython primitive: `int.bit_count()`.

## Measurement caveats — read these before quoting any number

1. **Windows does not enforce the limit.** `ct.get_cpu_time_elapsed()` returned `0` in every
   probe, including with `run_game(..., turn_timeout_ms=10)`. Confirms G21. All wall-clock here
   is `time.perf_counter()`, which is *optimistic* relative to enforced CPU accounting.
2. **The ladder runs AWS Graviton3 (aarch64); every number here is x86-64 Windows.** No claim
   here is ARM-confirmed (repo G44). I plan against a **2× derate** throughout.
3. **The host was shared with other committee agents during these runs.** Repeat measurements of
   the same float matvec ranged **2.05e7 – 4.80e7 MACs/s** (2.3× spread). Where a single figure
   is quoted I use the *conservative* end. The in-engine probe numbers were stable across two
   independent runs for every config except the 2048-wide one (see §2).
4. **`time.perf_counter()` is live in the local engine but is stubbed to `0.0` in the shipped
   server hardening block** (recovered from `fcode_engine.pyd`). A bot cannot self-profile on
   the ladder; `ct.get_cpu_time_elapsed()` is the only timing channel there.

---

## 1. Pure-Python matmul throughput

Dense matrix-vector `y = W @ x`, M×N. MACs/sec, CPython 3.13.12, quiet-machine run.

### 1a. Conventional methods (M=64, N=128, 8192 MACs)

| method | µs/matvec | MACs/sec |
|---|---:|---:|
| `[sum(map(mul, row, x)) for row in W]` — **best** | 170.7 | **4.80e7** |
| flat list + slice + `map(mul)` | 181.4 | 4.52e7 |
| flat list, pre-loop slice | 192.9 | 4.25e7 |
| `list[array('d')]` + `map(mul)` | 214.7 | 3.82e7 |
| `array('d')` flat + slice | 219.4 | 3.73e7 |
| nested lists, explicit index loop | 226.1 | 3.62e7 |
| **int fixed-point** `sum(map(mul, row, x))` | 262.1 | **3.13e7** |
| axpy / column-major accumulate | 285.0 | 2.87e7 |
| `list[array('i')]` int + `map(mul)` | 296.9 | 2.76e7 |
| int fixed-point, index loop | 335.9 | 2.44e7 |
| `sum(a*b for a, b in zip(row, x))` | 357.0 | 2.30e7 |
| big-int packed matmul (one `*`), K=24 | 685.9 | 1.19e7 |

Findings:

- `sum(map(mul, row, x))` over plain nested lists is the fastest conventional form. The `array`
  module is **slower**, not faster — element access boxes a new Python object each time.
- The **big-int packing trick loses**, decisively and for a structural reason. Packing `W` into
  one integer and doing a single multiply costs `O(M·N²)` CPython digit-multiplies to produce
  `M·N` MACs — an `O(N)` waste factor. It only breaks even around **N ≈ 16**. The corrected
  tight packing (M·N limbs, no stride waste, verified bit-exact against the reference) still
  peaks at 1.08× the baseline at M=32/N=64 and degrades to **0.14×** at M=256/N=512. Dead end.
- `bytes`/`memoryview` tricks are not available: the server hardening block **deletes
  `builtins.memoryview`**.

### 1b. Low-precision methods — these change the asymptotics

| method | M=32,N=64 | M=64,N=128 | M=128,N=256 | M=256,N=512 |
|---|---:|---:|---:|---:|
| float baseline `sum(map(mul))` | 4.44e7 | 2.54e7 | 2.36e7 | 2.24e7 |
| sparse float, 10 % nnz | 9.62e7 | 1.01e8 | 1.28e8 | 1.28e8 |
| ternary weights, `itemgetter` index-sum | 6.13e7 | 7.57e7 | 7.29e7 | 8.48e7 |
| **binary XNOR, `(w ^ x).bit_count()`** | **5.30e8** | **1.04e9** | **2.13e9** | **2.97e9** |

The binary row is the finding. `y_i = N − 2·popcount(W_i XOR X)` computes an entire N-length
dot product in **two Python-level operations**, and `int.bit_count()` on a 512-bit int is a
handful of machine popcounts. Throughput *rises* with layer width because the per-neuron Python
overhead is amortised over more bits: **N/2 MACs per Python bytecode**, versus 1 for every
conventional method. That is a 40–130× speedup and it is why a million-parameter network fits.

Ternary weights (`sum(itemgetter(*plus)(x)) − sum(itemgetter(*minus)(x))`) are the best option
when real-valued activations must be preserved: ~3× float, at 12.5 bytes/weight.

---

## 2. The largest feasible network

`bench_net.py`, whole forward pass including bias, activation and — for binary — the
`b = (b << 1) | (…)` re-binarisation cost that raw MAC counts hide. Percentages are of a 10 ms
budget on **this** x86 core; halve the headroom for a 2× Graviton derate.

| architecture | MACs | float MLP | ternary | **binary XNOR** |
|---|---:|---:|---:|---:|
| 64-64-32-8 | 6.4 k | 152 µs (1.5 %) | 51 µs | 10–13 µs (0.1 %) |
| 64-128-64-8 | 16.9 k | 412 µs (4.1 %) | 146 µs | 18–27 µs (0.3 %) |
| 64-256-128-8 | 50.2 k | **1090 µs (10.9 %)** | 426 µs | 33–52 µs (0.5 %) |
| 96-256-256-16 | 94.2 k | 2010 µs (20.1 %) | 778 µs | 52–69 µs (0.7 %) |
| 128-512-512-16 | 336 k | 11 327 µs (**113 %** ✗) | 4904 µs (49 %) | 176–254 µs (2.5 %) |
| 128-1024-1024-16 | 1.20 M | 46 589 µs (466 % ✗) | 15 453 µs (155 % ✗) | **367–554 µs (5.5 %)** |
| 256-2048-2048-32 | 4.78 M | 189 696 µs ✗ | 64 252 µs ✗ | 946–1462 µs (14.6 %) |

A hybrid (real-valued float first layer, binary trunk) was also measured and is **not worth it**:
128-1024-1024-16 hybrid costs 6415 µs, 12× the pure-binary version, because binarising 1024
float pre-activations costs more than the entire binary trunk. Feed the network binarised
features directly (thermometer / threshold encoding of game state).

### In-engine verification

Run through `fcode_engine.run_game` on map `sprint`, 6 units, forward pass every round on every
unit, min/max over 15 rounds, two independent runs.

| probe | net | params | src | per-unit init | forward min–max |
|---|---|---:|---:|---:|---:|
| `nnload256` | binary 64-256-256-16 | 86 k | 33 KB | 121–129 µs | **68–84 µs** |
| `nnload1k` | binary 128-1024-1024-32 | 1.21 M | 428 KB | 536–655 µs | **307–442 µs** |
| `nnload2k` | binary 128-2048-2048-32 | 4.52 M | 1589 KB | 1394–5601 µs | **723–6184 µs** |
| `nnfloat` | float 64-256-128-8 | 50 k | 67 KB | 3084–3983 µs | **1045–1679 µs** |

Two things to read off this table:

- The in-engine binary numbers **agree with the standalone bench** once module globals are bound
  as function default args. My first probe was 4× slower purely because `forward()` looked `_L`
  up in module globals every layer; `def forward(x, _L=_L)` recovered it. Do this in the real bot.
- **The 2048-wide net is not safe.** Its forward pass ranged 723 µs to 6184 µs across runs — an
  8.5× spread from GC and memory pressure with 6 units each holding a 600 KB net. At 50 units it
  will be worse. Against a hard 10 ms limit on unknown-speed ARM hardware, that variance alone
  disqualifies it.

### Recommended architecture

```
input   128 binary features (threshold/thermometer encoding of game state)
hidden  1024, binary weights, per-neuron learned threshold (batchnorm folded in)
hidden  1024, binary weights, per-neuron learned threshold
output  32,   binary weights, integer scores (no binarisation)
```

1.21 M binary weights = **148 KB** of weights, **428 KB** of `main.py` as a `bytes` literal.

| | measured (x86) | 2× Graviton derate | of 10 ms |
|---|---:|---:|---:|
| forward pass | 307–442 µs | ~880 µs | **8.8 %** |
| per-unit init (once) | 536–655 µs | ~1.3 ms | 13 % of one turn |
| RAM per unit | ~0.25 MB | — | 12 MB across 50 units |

That leaves **>90 % of the budget** for the bot's own logic, against the existing bot's stated
3 ms working budget. The ceiling before variance turns dangerous is ~2048 wide.

---

## 3. Import / startup cost — once, or once per unit?

**Both, split at a specific line.** I recovered the engine's actual loader and then verified it.

The engine does, per match:

```python
ast.parse(source)              # validator
code = compile(source, ...)    # ONCE
bytecode = marshal.dumps(code) # ONCE, handed to Rust as Vec<u8>
```

and then, per sub-interpreter (per unit), through a `_BytecodeFinder` on `sys.meta_path`:

```python
code = marshal.loads(self.bytecode)   # PER UNIT
exec(code, module.__dict__)           # PER UNIT
```

**Verified empirically.** `bots/probes/nnclock` puts a module-level `SHARED = []` and has each
unit append to it and report `len(SHARED)` through the comm store. Result with 4 units, and
again with 6 units in every later probe:

```
units_run=4  len_SHARED_max=1  my_len=1
```

Every unit sees a list of length 1. **The module body is re-executed per unit. Module-level
globals are not shared** — G20 confirmed on 2.3.3, and confirmed mechanically (the `.pyd`
imports `Py_NewInterpreterFromConfig`, `Py_EndInterpreter`, `PyInterpreterState_GetID`).

So: **source parsing and compilation are paid once; everything the module body *does* is paid
50 times.** Measured split, for a blob unpacked into big-int rows:

**552 KB blob / 4.52 M binary weights:**

| embedding | src | ast.parse (once) | compile (once) | `marshal.loads` /unit | `exec` /unit | **per-unit** | ×50 units |
|---|---:|---:|---:|---:|---:|---:|---:|
| **`bytes` literal** | 1584 KB | 12.4 ms | 16.3 ms | 0.019 ms | 1.043 ms | **1.06 ms** | 53 ms |
| base64 + `b64decode` | 736 KB | 3.8 ms | 3.7 ms | 0.062 ms | 2.607 ms | 2.67 ms | 133 ms |
| `str`.encode('latin-1') | 977 KB | 52.1 ms | 46.9 ms | 2.963 ms | 1.557 ms | 4.52 ms | 226 ms |
| one big hex int literal | 1104 KB | 11.7 ms | 11.8 ms | 0.892 ms | 105.957 ms | **106.8 ms** | 5.3 s |

**148 KB blob / 1.21 M weights, `bytes` literal:** 4.4 ms + 4.7 ms once, **0.48 ms per unit.**

Conclusions:

- **This is not the binding constraint.** 1.06 ms per unit for a 4.5 M-weight network, and
  0.48 ms for the recommended one. It comfortably fits even if it is charged against the unit's
  first-turn budget (which I could not verify — Windows does not enforce; see §5 caveat).
- **Use a `bytes` literal, not base64.** Because the engine compiles once and `exec`s per unit,
  a `bytes` literal front-loads all its cost into the once-per-match `compile` and costs
  essentially nothing per unit. Base64 moves 2.6 ms of `b64decode` onto every unit. Base64 is
  the right answer for a normal Python program and the *wrong* answer here.
- **Never embed weights as one giant hex int** (107 ms/unit — shifting a 4.5 M-bit int 2080
  times is quadratic) **and never as a tuple literal** (`tuple` of 512 KB of ints: 939 ms to
  compile; floats: 1892 ms — see `bench_load.py`).
- `marshal.loads` of the code object is free (0.019 ms for a 1.5 MB module). The per-unit cost
  is entirely the module body's own unpacking work — so keep the module body to
  `int.from_bytes` slicing and nothing else.
- Aggregate: 50 units × 0.48 ms = 24 ms of one-time load per match. Irrelevant against 1000 rounds.

---

## 4. Quantisation: int8 vs float32

**Fixed-point integer arithmetic does not beat float in CPython. It loses.**

| | MACs/sec (M=64,N=128) | vs float |
|---|---:|---:|
| float, `sum(map(mul, row, x))` | 4.80e7 | 1.00× |
| int fixed-point, same form | 3.13e7 | **0.65×** |
| int in `array('i')` | 2.76e7 | 0.58× |
| int fixed-point, index loop | 2.44e7 | 0.51× |

CPython's `float.__mul__` is a single C double multiply on an unboxed value; `int.__mul__` goes
through the arbitrary-precision path with a digit-count check and a fresh allocation for every
result. There is no int8 in CPython — there is only `PyLong`. **Quantise for size, never for
speed.** The only integer representation that wins is the 1-bit packed one, and it wins by
replacing arithmetic with `bit_count()` rather than by being integer.

### Size (RAM per unit — each of up to 50 units holds its own copy)

| representation | bytes/weight | 1024×1024 layer, 1 unit | × 50 units |
|---|---:|---:|---:|
| `list[list[float]]` | 32.66 | 32.7 MB | **1633 MB** |
| `list[list[int]]` (int8 values) | 24.00 | 24.0 MB | 1200 MB |
| ternary index lists (34 % nnz) | 11.24 | 11.2 MB | 562 MB |
| `list[array('d')]` | 8.09 | 8.1 MB | 404 MB |
| `list[array('b')]` | 1.09 | 1.1 MB | 54 MB |
| **`list[int]` packed binary** | **0.17** | **0.2 MB** | **8.4 MB** |

A Python `float` is a 24-byte heap object plus an 8-byte list pointer, so a "float32" network
costs 32.7 bytes per weight in RAM — 32× its on-disk size, replicated per sub-interpreter. **A
1024-wide float MLP is not merely slow, it needs 1.6 GB of RAM across a full team.** Packed
binary is 190× smaller.

### Load-time cost of the float representation

| strategy | per-unit init (50 k weights) | blob |
|---|---:|---:|
| int8 blob → `list[list[float]]` (dequantise) | 5.43 ms | 49 KB |
| float64 blob → `list[list[float]]` via `.tolist()` | 1.86 ms | 392 KB |
| float64 blob → `list[array('d')]` via `.frombytes()` | 0.58 ms | 392 KB |

Dequantising int8 to float costs **more per unit than the forward pass does** (confirmed
in-engine: `nnfloat` measured 3.1–4.0 ms init against a 1.0–1.7 ms forward). If a float net is
used anyway, ship float64 and `array('d').frombytes` — but note `array('d')` compute is 0.78×
plain-list speed, so you trade 5 ms of one-time init for ~25 % slower every round.

---

## 5. Can numpy be shipped?

**No — assume pure Python. I am confident but the final confirmation requires a server round-trip
I did not run.**

Evidence, in descending strength:

1. **The engine never puts bot files on a filesystem.** Bot modules are compiled to code objects
   and served per sub-interpreter by a `_BytecodeFinder`/`_BytecodeLoader` pair installed on
   `sys.meta_path`, which does `exec(marshal.loads(bytecode))`. A `.so` in the zip is not Python
   source, is never written to disk, and there is no path for `ExtensionFileLoader` to `dlopen`.
   **`zipimport` has zero references in `fcode_engine.pyd`.**
2. **The server hardening block deletes `builtins.open`** and pops `ctypes`, `_ctypes`, `mmap`,
   `socket`, `subprocess`, `_ssl`, `resource`, `signal`, `multiprocessing` and `select` out of
   `sys.modules`. Even if a `.so` reached disk, there is no loader left to reach it with.
3. **The ladder is AWS Graviton3 (aarch64 Linux).** A shipped wheel would have to be
   `manylinux_*_aarch64`, matched to the server's exact CPython ABI. The local wheel is
   `cp313-cp313-win_amd64` (`maturin`, `Root-Is-Purelib: false`).
4. **Repo ground truth G28**: "numpy cannot be imported inside the bot sandbox at all" — status
   `CARRIED-2.2.0`, *not* re-verified on 2.3.3. `arena/strict.py` bans
   `{numpy, scipy, pandas, torch, sklearn}` on the strength of it.
5. `import numpy` in `bots/probes/nnimport` returns `ModuleNotFoundError` — but this is
   **uninformative**, because numpy is not installed in this venv at all.

**Important negative result: the local engine applies none of the hardening.** `bots/probes/nnimport`
shows that under `run_game` (with and without `turn_timeout_ms=10`), a bot can do all of this:

```
B:lzma=OK   B:_lzma=OK   B:sqlite3=OK   B:ctypes=OK   B:_ssl=OK   B:_decimal=OK
C:click=OK(8.4.2)   C:rich=OK        <- third-party, from the venv's site-packages
D:helper=OK(sibling-import-works)    <- sibling .py in the bot's own directory
E:open=OK   E:memoryview=OK   E:__file__=OK(C:\Users\edlun\Desktop\l...)
```

Arbitrary C extensions load, third-party packages import from `site-packages`, and `__file__` is
a real path. **Any local experiment about what a bot may import is therefore worthless as
evidence about the ladder.** The hardening exists only in the server code path.

**The test that would settle it** (I did not run it — it consumes the shared 5-per-10-minutes
remote bucket that other committee agents may need, and it puts a submission on the server):

```python
# bots/probes/numpyprobe/main.py
R = []
for m in ("numpy", "ctypes", "_ctypes", "mmap", "zipimport"):
    try:
        R.append(m + "=OK")
    except ImportError as exc:      # note: must be a named exception, no bare except (G25)
        R.append(m + "=" + type(exc).__name__)
    # (wrap the __import__ call inside the try)

class Player:
    def run(self, ct):
        if ct.get_current_round() == 3:
            ct.resign(" ".join(R)[:499])
```

Run `fcode match test numpyprobe idle` and read the resign message off the Matches page. That
executes on the real Graviton3 ladder hardware under the real hardening. A second variant should
ship a trivial hand-built `.so`/`.pyd` in the zip and try to import it, to test point 1 directly.
Until then: **build for pure Python.**

---

## 6. Secondary findings worth carrying

- **Bind weights as function default args.** `def forward(x, _L=_L)` was a 4× speedup in-engine
  over module-global lookup for the 1024-wide net. Module-global loads dominate a binary net
  whose real work is two bytecodes per neuron.
- **Whole-match wall time.** 50 units × 0.4 ms × 1000 rounds ≈ 20 s of pure NN compute per match,
  on top of everything else. Not a rule violation (the limit is per-unit) but it slows local
  iteration and sweeps materially. Consider running the net only on units whose decision matters.
- **`__pycache__` still bites** (G30/M04): every probe run here scrubbed it before and after,
  and `PYTHONDONTWRITEBYTECODE=1` was set. A stray `__pycache__` makes the bot silently inert.
- **`ct.get_cpu_time_elapsed()` returned 0 in every configuration tested**, including
  `turn_timeout_ms=10`. Windows cannot verify any timing claim (G21 re-confirmed on 2.3.3).
- The submission zip has **no size check in the CLI** (`submission.py` only prints the size).
  A 1.6 MB `main.py` uploaded fine locally; a server-side limit is untested and is a risk for
  the 2048-wide configuration.

---

## Verdict

**A network of size X fits and is worth it — where X is a binary (XNOR/popcount) MLP of
`128 → 1024 → 1024 → 32`, 1.21 million weights, 148 KB of packed weights, 428 KB of `main.py`.**

Measured inside the engine: **307–442 µs per forward pass** and **536–655 µs of one-time
per-unit initialisation**, against a 10 ms budget — under 5 % on this x86 core, under 9 % with a
2× Graviton3 derate. Two thousand and forty-eight wide (4.5 M weights) also fits on average but
its 723–6184 µs variance makes it unsafe; 1024 wide is the recommendation and 2048 is the hard
ceiling.

The three things that make this work, none of which is obvious:

1. `int.bit_count()` on wide ints does **N/2 MACs per Python bytecode** — 1.0e9–3.0e9 MACs/s
   against 2.0e7–4.8e7 for float. Everything else follows from this.
2. The engine **compiles the module once and `exec`s it per unit**, so a `bytes` literal costs
   ~0 per unit while base64 costs 2.6 ms per unit. Weight embedding is free if done right and a
   5-second disaster if done wrong (hex int).
3. Packed binary weights are **0.17 bytes/weight in RAM** against 32.66 for `list[list[float]]`.
   The float version of the same network needs 1.6 GB across 50 sub-interpreters. Memory, not
   time, is what makes a large *float* net impossible.

**Constraint on this verdict.** "Worth it" here means *the inference budget is not what stops
you* — 1.2 M weights at 5 % of budget is not a toy, and it is ~24× the parameter count of the
largest float net that fits (50 k, at 11–17 % of budget and 3–4 ms of per-unit init). Whether a
binary net of that size, trained on whatever signal is available, beats hand-written strategy
code is a training and feature-engineering question that belongs to other seats. I note only
that binary networks typically need 4–8× the width of a float net to match its accuracy, so
1024-wide binary is worth roughly a 128–256-wide float net in representational terms — which is
still comfortably larger than anything the float path could ever run here.

**The one open item that could overturn this** is Graviton3: no number in this document has been
confirmed on ARM. At a 5 % budget occupancy the recommended net survives a 10× derate, so the
risk is bounded — but the 2048-wide configuration does not survive even 2×.
