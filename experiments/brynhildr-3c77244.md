# brynhildr@3c77244

Lifecycle hardening for `9375a4a`'s one-use wall-escape Launchers.

A Launcher still throws only one friendly Builder, preventing the repeated
pad-to-pad bouncing observed in v118. A later Builder can now recognize a
spent or unusable pad indirectly: after four rounds without being thrown, it
dismantles the allied pad and preserves its stalled-route counter. Escape-pad
construction is capped at two attempts per Builder; after that, the existing
barrier-digging fallback takes over.

This closes two opposite failure loops:

- waiting forever beside a spent one-use pad;
- endlessly destroying and rebuilding a pad when no legal throw exists.

Focused brokkr control over the six affected maps, both seats, and seeds 1-5:

- score unchanged at 42/60, zero errors;
- Launchers built reduced from 35 to 22;
- stalled Builders reduced from 141 to 137;
- aggregate worst-stall rounds reduced from 11,254 to 11,087;
- the pathological Jotunheim cases use no Launchers, reduce worst stall from
  156 to 99 rounds, and deal 3,978 rather than 1,440 Core damage.

Full local gate over 15 maps, both seats, seeds 1-5, and six older category
leaders (900 games total):

- hildr78 135/150;
- steward 130/150;
- gefn 125/150;
- spar_wall 94/150;
- spar_sentinel 125/150;
- brokkr 122/150;
- 731/900 overall, exactly matching the parent control, zero errors.

Focused controller tests also verify one friendly throw per pad and timed-out
pad removal without resetting the Builder's stalled-route state.
