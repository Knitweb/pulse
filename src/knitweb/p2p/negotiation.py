"""Protocol version negotiation for a mixed-version swarm (#136).

The wire framing already carries a version byte and reads N and legacy (0)
frames (``knitweb.p2p.wire``: ``WIRE_VERSION``, ``read_frame_bytes`` translates
at the boundary). Sprint 4 added a version-drift *guard* — refuse to converge on
a mismatch — but a guard hard-partitions the fabric on a wire bump. This adds the
missing *migration* half: peers advertise a supported-version RANGE and each
connection negotiates the **highest commonly-supported version**, so a rolling
upgrade degrades (talks the older common version) instead of partitioning.

Pure logic — no sockets, no clock, no float. The ``serve()`` wiring (exchange
:func:`version_hello`, then frame at :func:`negotiate`'s result) is the node
layer's call, exactly like the other activation adapters.
"""
from __future__ import annotations

from .wire import WIRE_VERSION

__all__ = [
    "LOCAL_MIN_VERSION",
    "LOCAL_MAX_VERSION",
    "version_hello",
    "negotiate",
    "swarm_is_connected",
]

# This build speaks legacy (0) through the current wire version, so it can talk to
# any peer during an N-1 -> N rollout window. Bumping WIRE_VERSION widens the top.
LOCAL_MIN_VERSION = 0
LOCAL_MAX_VERSION = WIRE_VERSION


def version_hello(*, min_version: int = LOCAL_MIN_VERSION,
                  max_version: int = LOCAL_MAX_VERSION) -> dict:
    """The capability advertisement a peer sends on connect."""
    if min_version < 0 or max_version < min_version:
        raise ValueError("invalid version range")
    return {"min_version": int(min_version), "max_version": int(max_version)}


def negotiate(local: dict, remote: dict) -> "int | None":
    """The highest version both sides support, or ``None`` if their ranges are
    disjoint (an explicit 'cannot talk', never a silent partition).

    Both args are :func:`version_hello`-shaped maps. Deterministic: the result is
    ``min(local_max, remote_max)`` when the ranges overlap, else ``None``.
    """
    lo = max(int(local["min_version"]), int(remote["min_version"]))
    hi = min(int(local["max_version"]), int(remote["max_version"]))
    return hi if hi >= lo else None


def swarm_is_connected(ranges: "list[dict]") -> bool:
    """True iff every pair of peers can negotiate a common version (the fabric
    stays connected, degrades not partitions). Used by the mixed-version test and
    a pre-rollout check: a rollout is safe iff adjacent version bands overlap so
    the connectivity graph is complete."""
    hellos = list(ranges)
    for i in range(len(hellos)):
        for j in range(i + 1, len(hellos)):
            if negotiate(hellos[i], hellos[j]) is None:
                return False
    return True
