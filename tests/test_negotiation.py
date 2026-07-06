"""Mixed-version swarm negotiation (#136).

Asserts the migration property the version-drift *guard* alone cannot give: a
swarm that spans two adjacent wire versions stays fully connected — every pair
negotiates a common version, so the fabric degrades to the older shared format
instead of partitioning. Also pins the boundary cases: highest-common selection
and the honest 'no common version' signal (disjoint ranges, never silent).
"""
from __future__ import annotations

from knitweb.p2p.negotiation import (
    LOCAL_MAX_VERSION,
    LOCAL_MIN_VERSION,
    negotiate,
    swarm_is_connected,
    version_hello,
)
from knitweb.p2p.wire import WIRE_VERSION


def test_local_range_covers_legacy_through_current():
    assert LOCAL_MIN_VERSION == 0
    assert LOCAL_MAX_VERSION == WIRE_VERSION
    # a default build always negotiates with an identical peer at the top version
    assert negotiate(version_hello(), version_hello()) == WIRE_VERSION


def test_negotiate_picks_highest_common():
    old = version_hello(min_version=0, max_version=1)
    new = version_hello(min_version=1, max_version=2)
    assert negotiate(old, new) == 1          # highest both speak
    assert negotiate(new, old) == 1          # symmetric


def test_negotiate_none_when_disjoint():
    # a peer that dropped legacy vs one that only speaks legacy: honest None,
    # not a silent 0 that would corrupt frames.
    assert negotiate(version_hello(min_version=1, max_version=1),
                     version_hello(min_version=0, max_version=0)) is None


def test_rolling_upgrade_swarm_stays_connected():
    # rollout window: some peers upgraded to speak [N, N+1], some still [N-1, N].
    # every peer supports N ⇒ the connectivity graph is complete (no partition).
    N = WIRE_VERSION
    upgraded = version_hello(min_version=N, max_version=N + 1)
    legacy = version_hello(min_version=max(0, N - 1), max_version=N)
    swarm = [upgraded, legacy, upgraded, legacy, legacy]
    assert swarm_is_connected(swarm)


def test_island_version_partitions_and_is_detectable():
    # a misconfigured peer speaking only a future island version [N+2, N+2]
    # cannot talk to anyone on [N-1, N] — swarm_is_connected flags it up-front
    # rather than the peer silently dropping off the fabric.
    N = WIRE_VERSION
    good = version_hello(min_version=max(0, N - 1), max_version=N)
    island = version_hello(min_version=N + 2, max_version=N + 2)
    assert not swarm_is_connected([good, good, island])
