# Staged rolling wire-protocol upgrade (#136)

The wire carries a version byte and reads both the current and legacy (`0`)
frame formats (`knitweb.p2p.wire`: `WIRE_VERSION`, `write_frame_bytes`,
`read_frame_bytes`). The **version-drift guard** (`test_version_drift.py`)
refuses to converge on an *incompatible* engine at release time. This document
covers the complementary run-time half: how a live fabric moves from wire
version **N** to **N+1** without partitioning.

## The negotiation primitive

`knitweb.p2p.negotiation` is pure, deterministic logic:

- `version_hello(min_version, max_version)` — the capability a peer advertises on
  connect. A build speaks every version in `[LOCAL_MIN_VERSION, LOCAL_MAX_VERSION]`
  (today `[0, WIRE_VERSION]`), so it can talk to any peer in the rollout window.
- `negotiate(local, remote)` — the **highest version both sides support**, or
  `None` when the ranges are disjoint. `None` is an explicit "cannot talk"; it is
  never downgraded to a silent `0` that would corrupt frames.
- `swarm_is_connected(ranges)` — `True` iff every pair can negotiate. Use it as a
  pre-rollout safety check: the fabric stays connected iff adjacent version bands
  overlap.

The `serve()` wiring (exchange `version_hello` on the `BaseNode` connect path,
then frame each connection at `negotiate`'s result) is the node layer's call,
exactly like the other activation adapters (hole-punch, relay).

## Why it degrades instead of partitioning

During a rollout the swarm splits into two bands:

| Band | Speaks | Range |
|------|--------|-------|
| Not yet upgraded | N-1 and N | `[N-1, N]` |
| Upgraded | N and N+1 | `[N, N+1]` |

Every peer supports **N**, so *any* pair shares at least version N — the
connectivity graph is complete and no peer falls off the fabric. Upgraded peers
talk N+1 to each other and transparently drop to N with laggards. This is the
`test_rolling_upgrade_swarm_stays_connected` invariant.

## Staged procedure

1. **Ship N+1 as additive.** Bump `WIRE_VERSION` to N+1 and keep the N reader.
   The new build now advertises `[0, N+1]` but every peer still accepts N.
2. **Verify overlap before rolling.** `swarm_is_connected` over the fleet's
   advertised ranges must be `True`. Because both bands include N, it is — an
   *island* version (e.g. a peer misconfigured to `[N+2, N+2]`) is flagged here,
   up front, instead of silently partitioning (`test_island_version_...`).
3. **Roll the fleet.** Restart peers in waves. Each restarted peer immediately
   negotiates N+1 with already-upgraded peers and N with the rest. Convergence is
   never interrupted.
4. **Retire N-1, then N.** Only once **every** peer advertises `max_version >= N+1`
   may `LOCAL_MIN_VERSION` be raised to drop the oldest reader. Confirm with a
   fleet-wide `min(max_version)` check before narrowing the range; narrowing while
   any laggard remains would re-introduce a partition.

Never advance two versions at once (`[N-1,N]` and `[N+1,N+2]` share nothing —
`negotiate` returns `None`). One version per rollout window keeps the bands
overlapping.
