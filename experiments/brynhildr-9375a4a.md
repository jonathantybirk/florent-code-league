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
