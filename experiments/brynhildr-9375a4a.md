# brynhildr@9375a4a

Combined wall-siege follow-up to `74ee6d7`.

- A home Builder relays a Sentinel outside Core vision into the existing Core
  defence budget instead of independently buying an unbudgeted turret.
- The relay begins during a late stalled race while the Core is still healthy,
  or immediately below 300 HP.
- A Builder that cannot advance toward its committed goal for eight rounds near
  hostile walls may build a Launcher. Each escape pad throws one friendly
  Builder only, preventing the repeated pad-to-pad bouncing observed in v118's
  Valkyrie and Jotunheim games; enemy ejection remains available.

Local 10 ms evidence over 15 maps, both seats, and seeds 1 and 2 (60 games per
opponent) exactly matches v118's established regression baseline:

- hildr78 54/60;
- steward 52/60;
- gefn 50/60;
- spar_wall 38/60;
- spar_sentinel 50/60;
- brokkr 49/60;
- 293/360 overall, zero errors.

A focused launcher controller test calls the same pad twice and records exactly
one friendly launch. This candidate is queued after `74ee6d7`, so the minimal
blind-Sentinel relay receives an attributable online sample first.

An additional control run used seeds 3-5 against the three most relevant older
categories. `9375a4a` and v118 were identical in every aggregate:

- hildr78 81/90;
- spar_wall 56/90;
- spar_sentinel 75/90;
- 212/270 overall, zero errors for both builds.

Together with the original panel this is 630 candidate games without an
observed regression. Five original-panel games built 14 escape Launchers; the
one-launch invariant itself is covered by the focused controller test because
the replay metrics count construction but not individual launch actions.
