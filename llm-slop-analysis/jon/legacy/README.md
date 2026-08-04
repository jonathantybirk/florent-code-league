# Legacy analysis — everything written before engine 2.3.3

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

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
