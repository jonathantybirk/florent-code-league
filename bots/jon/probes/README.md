# Probes: the measuring instruments

Nothing here is meant to win a ladder. These exist so a change to a real bot
can be *measured*, and they only work if they hold still.

## Two kinds, with opposite requirements

**Version archives** — `v233_a` .. `v233_h` (Vanguard), `uw_v1`, `uw_v2`
(Undertow). One frozen copy per meaningful step, taken at the moment the step
was adopted. These answer "are we still moving forward?" A build that cannot
beat its own predecessor has regressed, whatever the headline number says, and
that has already caught two changes this session that looked good head-to-head
and lost the panel.

Both live bots are edited by two different agents, so a snapshot is also the
only stable thing to measure against: a run against live `undertow` was
fingerprinted mid-run and **the hash had changed**, which is why `arena.py`
now prints `!! CONTAMINATED`.

- `uw_v1` — the straight 2.3.3 adaptation (commit `d2c6970`).
- `uw_v2` — Codex's rewrite, the build that led Vanguard 27-15.

**Counters** — `turtle`, `nemesis`, `reaver`, `baiter`, `riptide` (in
`../legacy/`, written for 2.2.0). Deliberately lopsided bots built to attack
one specific weakness. `reaver` and `baiter` both found real defects.

## Do the probes need version histories too?

**No, and wanting one would mean we had already broken them.** The two kinds
fail in opposite directions:

A real bot must keep *improving*, so it needs a trail of past selves to prove
it has not slipped. A probe must keep *measuring the same thing*, so its whole
value is that it never changes. Versioning a probe would only be necessary if
we were editing it -- and editing a probe silently redefines every number ever
recorded against it, including the ones already written down as evidence.

So the requirement for a probe is not versioning but **immutability**. Every
probe here has `DEBUG = False` hard-coded and should otherwise be treated as
read-only. If a probe genuinely needs to change, it gets a new name and the old
one stays; the archives above are exactly that discipline applied to bots that
*do* change.

The one real risk is silent rot: an engine update can break a frozen probe
without anyone noticing, which is what happened to every 2.2.0 bot in
`../legacy/`. The guard is cheap -- run each probe against `donothingbot` after
an engine change and confirm it still wins.
