<!-- source: https://www.hpc.dtu.dk/?page_id=3098 -->
<!-- fetched: 2026-08-01 — condensed by a summarising fetch tool; see docs/hpc/README.md -->

# Queue Parameters

## Queue Comparison Table

| Parameter | hpc-queue/LSF | thinlinc/application-node |
|-----------|---------------|---------------------------|
| Default queue | Yes | No |
| Max wallclock | 72 hours | 48 hours |
| Max CPU time | N/A | 24 hours |
| Max nodes/job | N/A | 1 node |
| Max processes/job | 100 | 1 |
| Max processes/queue | 100..120 | 64 |
| Max processes/node | "20 or 24 depending on node and queue" | 1 |
| Default walltime | 15 minutes | 48 hours |

---

**Contact:** support@cc.dtu.dk — DTU Compute, Building 324, Room 280, Technical University of
Denmark, 2800 Kgs Lyngby, Denmark

---

## Why this page matters for the tournament

`Max processes/queue: 100..120` is a **per-user** cap on the `hpc` queue. A job array of 20,000
elements is legal to submit, but LSF will only ever run ~100 of them concurrently for one user;
the rest sit `PEND` with reason `User has reached the per-user job slot limit of the queue`.

`tournament/hpc.py` therefore defaults the array throttle to `%100` — matching the cap rather than
fighting it. Raising it does not increase throughput.

Also note **default walltime is 15 minutes**, which a long 1000-round match could plausibly exceed,
so the generated job script always sets `-W` explicitly.
