"""Proofs for peer-exchange discovery: dedup, merge accounting, and gossip convergence."""

import pytest

from knitweb.core import canonical
from knitweb.p2p.discovery import (
    PEER_EXCHANGE_KIND,
    MAX_PEERS,
    PeerDirectory,
    handle_peer_exchange,
    peer_exchange_message,
    peers_from_records,
)
from knitweb.p2p.node import PeerAddress


def _p(port: int) -> PeerAddress:
    return PeerAddress("127.0.0.1", port)


@pytest.mark.property
def test_dedup_and_deterministic_order():
    d = PeerDirectory([_p(9002), _p(9001), _p(9001)])
    assert len(d) == 2                                   # dup collapsed
    assert d.known() == [_p(9001), _p(9002)]             # sorted by host:port


@pytest.mark.property
def test_merge_accounting():
    d = PeerDirectory([_p(9001)])
    assert d.merge([_p(9001), _p(9002), _p(9003)]) == 2  # only 9002/9003 are new
    assert d.merge([_p(9002)]) == 0                      # already known
    assert len(d) == 3


@pytest.mark.property
def test_message_round_trips_canonically():
    d = PeerDirectory([_p(9001), _p(9002)])
    msg = peer_exchange_message(d)
    assert msg["kind"] == PEER_EXCHANGE_KIND
    assert canonical.decode(canonical.encode(msg)) == msg     # wire-safe
    assert peers_from_records(msg["peers"]) == [_p(9001), _p(9002)]


@pytest.mark.property
def test_exchange_makes_both_sides_learn():
    a = PeerDirectory([_p(9001)])
    b = PeerDirectory([_p(9002)])
    # A sends its peers to B; B merges + replies; A merges the reply.
    reply = handle_peer_exchange(b, peer_exchange_message(a))
    handle_peer_exchange(a, reply)
    assert _p(9002) in a and _p(9001) in b               # both learned the other


@pytest.mark.property
def test_gossip_converges_across_a_component():
    # three nodes, disjoint seeds; pairwise exchanges spread every address to all.
    a = PeerDirectory([_p(9001)])
    b = PeerDirectory([_p(9002)])
    c = PeerDirectory([_p(9003)])
    for _ in range(2):                                   # a<->b, b<->c per round
        handle_peer_exchange(a, handle_peer_exchange(b, peer_exchange_message(a)))
        handle_peer_exchange(b, handle_peer_exchange(c, peer_exchange_message(b)))
    everyone = {_p(9001), _p(9002), _p(9003)}
    for d in (a, b, c):
        assert set(d.known()) == everyone               # full convergence


@pytest.mark.property
def test_handle_rejects_bad_message():
    d = PeerDirectory()
    with pytest.raises(ValueError):
        handle_peer_exchange(d, {"kind": "not-pex", "peers": []})
    with pytest.raises(ValueError):
        peers_from_records([{"host": "x"}])              # missing port


# -- flat-directory cap (fix #74) -------------------------------------------


@pytest.mark.property
def test_flood_capped_at_max_peers():
    """Merging 2000 addresses must not grow the directory beyond MAX_PEERS."""
    d = PeerDirectory()
    flood = [PeerAddress("10.0.0.1", p) for p in range(1, 2001)]
    d.merge(flood)
    assert len(d) <= MAX_PEERS


@pytest.mark.property
def test_static_peers_survive_flood():
    """Static/seed peers are never evicted, even when a flood fills the directory."""
    static_a = PeerAddress("192.168.0.1", 7001)
    static_b = PeerAddress("192.168.0.2", 7002)
    d = PeerDirectory([static_a, static_b])
    # Flood with MAX_PEERS addresses using different IPs so they are all distinct.
    flood = [PeerAddress(f"10.{i // 256}.{i % 256}.1", 5000) for i in range(MAX_PEERS)]
    d.merge(flood)
    assert len(d) <= MAX_PEERS
    assert static_a in d
    assert static_b in d


@pytest.mark.property
def test_honest_peers_join_below_cap():
    """Before the directory is full, honest peers join without eviction."""
    d = PeerDirectory()
    honest = [PeerAddress("10.1.0.1", p) for p in range(1, 11)]
    learned = d.merge(honest)
    assert learned == 10
    assert len(d) == 10
    for p in honest:
        assert p in d
