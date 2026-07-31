# Legacy analysis — everything written before engine 2.3.3

**Default assumption: the conclusions in here are wrong until re-tested.**

Engine 2.3.3 changed three rules that most of this material was reasoned on:

- ammunition became a global pool the Core fills with `convert_ammo()`, instead
  of a physical stack delivered to each turret;
- Builder build/heal/attack became orthogonally-adjacent-only, and a Builder
  can no longer act on its **own** tile -- the attack rule is an outright
  inversion of 2.2.0;
- Builder movement became cardinal-only.

Anything resting on "damage is titanium delivered into Gunners" -- parasitism,
forward Harvesters as feeders, conveyor taps, splitter batteries, belt cutting
by standing on a belt -- is dead. Anything resting on eight-way movement or
own-tile attacks is dead.

Treat every file here as **inspiration, not evidence**. A claim graduates out of
this folder by being measured again on 2.3.3, not by sounding plausible.

The current rules live in `../reference/engine-2.3.3-changes.md`, which was
written by diffing both engine versions and probing the running engine.

`undertow.md` is Codex's, moved here only to keep the quarantine uniform.
