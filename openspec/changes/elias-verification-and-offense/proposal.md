## Why

Our team is three weeks from a €20K competition and is currently building on a documentation set that has
been **empirically proven wrong at least eleven times**. The repo's own docs carry "Correction vs. the
official docs" blocks — and independent runtime probing has now shown that several of *those corrections*
are also wrong. The shipped starter bot crashes itself. Two of our three teammate branches are iterating on
strategy built from prose nobody re-derived.

Meanwhile the single strongest result found so far is not in any teammate branch: a Gunner fed by one
adjacent Harvester **destroyed a 500 HP Core on turn 77 for roughly 96 titanium**, while every observed
bot-vs-bot game between conventional bots ran the full 1000 rounds with no Core ever dying. If that result
holds, the entire field — including us — is playing the wrong game.

This change establishes `elias_dev` as the branch that **verifies rather than assumes**. Its deliverable is
not a bot. It is a ground-truth register, a falsification suite, and an offensive doctrine that has survived
deliberate attempts to kill it.

Two failure modes this exists to prevent:

1. **Inherited belief.** A constant, a build order, or a "rule" that entered our codebase from prose or from
   a teammate and was never independently re-derived.
2. **Platform illusion.** Every measurement so far was taken on Windows/x86. The ladder runs Linux on AWS
   Graviton3 (ARM). At least two dramatic findings (Builder Bots dealing zero damage; the CPU timer reading
   zero) are plausibly Windows-wheel regressions rather than game rules.

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

### Modified Capabilities

None — this is the first OpenSpec change in the repository.

## Impact

- **New branch** `elias_dev`, branched from `main`. Does not touch `x/jon`, `x/luc`, or `x/llm-RL`.
- **New directories**: `openspec/`, `probes/` (falsification bots and arenas), `arena/` (harness),
  `docs/ground-truth.md` (generated register).
- **Corrects repo documentation**: `docs/cli/cli-submitting.md` states the entry point is `bot.py`; the
  engine imports `main`. This will be fixed in-repo so no teammate loses an evening to it.
- **Cross-platform requirement**: WSL or a Linux box becomes mandatory for CPU and combat verification.
  Windows silently reports `get_cpu_time_elapsed() == 0` and does not enforce `--tle`.
- **No dependency on numpy** anywhere in shippable code. It cannot be imported inside the bot sandbox at all.
- **Team process**: any claim promoted into a teammate's bot must cite a register entry.
