> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

## Why

Our team is three weeks from a €20K competition and is currently building on a documentation set that has
been **empirically proven wrong at least eleven times**. The repo's own docs carry "Correction vs. the
official docs" blocks — and independent runtime probing has now shown that several of *those corrections*
are also wrong. The shipped starter bot crashes itself. Two of our three teammate branches are iterating on
strategy built from prose nobody re-derived.

Meanwhile the single strongest result found so far is not in any teammate branch: a Gunner fed by one
adjacent Harvester **destroyed a 500 HP Core on turn 77 for roughly 96 titanium**, while every observed
bot-vs-bot game between conventional bots ran the full 1000 rounds with no Core ever dying. That result has
since been confirmed the hard way — our teammates' bots destroy AutistimusPrime's Core in 70–83% of games.

This change establishes `elias_dev` as the branch that **verifies rather than assumes**. Its deliverable is
a ground-truth register, a falsification suite, an offensive doctrine that has survived deliberate attempts
to kill it, and a bot built only from claims that survived.

Two failure modes this exists to prevent:

1. **Inherited belief.** A constant, a build order, or a "rule" that entered our codebase from prose or from
   a teammate and was never independently re-derived.
2. **Platform illusion.** Early measurements were taken on Windows/x86. The ladder runs Linux on AWS
   Graviton3 (ARM). One dramatic finding (the CPU timer reading zero, TLE never firing) turned out to be
   exactly such an illusion — real on Windows, absent on Linux.

## What Changes

- A machine-checkable **ground-truth register** of every engine claim, each tagged with its verification
  status, the platform it was verified on, and the experiment that established it. Nothing enters our bot
  logic until its claim is `VERIFIED-LINUX`.
- A **falsification suite**: for each claim, a probe bot and an arena that would *disprove* it. Claims are
  admitted by surviving refutation, not by being asserted.
- An **offensive doctrine** — the forward-gunner rush — stated as a testable thesis with explicit kill
  criteria, plus its counter and counter-counter, so we learn whether offence is real before we bet the
  competition on economy.
- A **defensive dogma audit** that treats each "obvious" defensive belief as a hypothesis to be attacked,
  with the arithmetic that refutes it where it is refutable.
- A **runtime safety contract**: the bot must be structurally incapable of the failure modes that delete
  units, and must conform to the engine's AST validator and server sandbox.
- A **deterministic evaluation harness** exploiting the discovery that this engine has zero within-map
  variance, making a 30-game sweep exhaustive rather than a sample.
- **AutistimusPrime itself**, specified against measured deficits rather than intuition.

## Capabilities

### New Capabilities

- `engine-ground-truth`: The register of verified engine facts, the verification protocol, and the rule that
  no unverified claim may influence bot logic.
- `offense-doctrine`: The forward-gunner kill thesis, its falsification criteria, its counters, and the
  decision procedure for choosing offence vs economy per map.
- `defense-dogma-audit`: Explicit refutation or confirmation of each inherited defensive belief, with
  arithmetic.
- `runtime-safety`: Structural guarantees that the bot never loses a unit to an exception, never overruns
  CPU, and never fails submission validation.
- `evaluation-harness`: The deterministic, mirrored, exhaustive arena used to decide every question,
  replacing ladder results and intuition as our arbiter.
- `bot-behaviour`: What AutistimusPrime itself must do — survive the forward-gunner kill, build chains in
  parallel, and never regress on the crash and validator gates.

### Modified Capabilities

None — this is the first OpenSpec change in the repository.

## Impact

- **New branch** `elias_dev`, branched from `main`. Does not touch `x/jon`, `x/luc`, or `x/llm-RL`.
- **New directories**: `openspec/`, `arena/` (harness), `bot/` (AutistimusPrime), `bots/zoo/` (deterministic
  reference opponents), `bots/rivals/` (teammate bots extracted for head-to-head), `docs/ground-truth.md`.
- **Corrects repo documentation**: `docs/cli/cli-submitting.md` states the entry point is `bot.py`; the
  engine imports `main`. Plus five further doc errors catalogued in the register.
- **Cross-platform requirement**: WSL or a Linux box is mandatory for CPU verification. Windows silently
  reports `get_cpu_time_elapsed() == 0` and does not enforce `--tle`.
- **No dependency on numpy** anywhere in shippable code. It cannot be imported inside the bot sandbox at all.
- **Team process**: any claim promoted into a teammate's bot must cite a register entry.
