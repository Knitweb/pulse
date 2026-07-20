"""#88 — Kademlia routing wired to flat-PEX discovery via the dht_discovery adapter.

Proves the bridge without sockets: contacts feed both stores, bare peer-exchange
stays byte-identical, and an iterative find_node converges to the k closest peers
in a simulated 1k-node network in O(log n) rounds.
"""
import math

import pytest

from knitweb.core import crypto
from knitweb.p2p import discovery, kademlia
from knitweb.p2p.dht_discovery import (
    DhtDiscovery,
    handle_peer_exchange,
    peer_exchange_query,
)
from knitweb.p2p.kademlia import Contact, node_id, xor_distance
from knitweb.p2p.transport import PeerAddress


def _peer(i):
    """A deterministic (pubkey, Contact) for node i — no clock, no RNG."""
    priv = crypto.sha256(f"dht-node-{i}".encode()).hex()
    pub = crypto.public_from_private(priv)
    addr = PeerAddress(host=f"10.{i // 256}.{i % 256}.1", port=9000 + (i % 1000))
    return pub, Contact(node_id=node_id(pub), address=addr)


def test_bare_peer_exchange_is_byte_identical_to_legacy():
    pub, _ = _peer(0)
    dht = DhtDiscovery(pub)
    dht.directory.merge([PeerAddress(host="10.0.0.1", port=9001),
                         PeerAddress(host="10.0.0.2", port=9002)])
    legacy = discovery.peer_exchange_message(dht.directory)
    assert handle_peer_exchange(dht, {"kind": discovery.PEER_EXCHANGE_KIND}) == legacy
    # and with no target present at all
    assert handle_peer_exchange(dht, {}) == legacy


def test_learned_contacts_feed_both_table_and_directory():
    pub, _ = _peer(0)
    dht = DhtDiscovery(pub)
    contacts = [c for _, c in (_peer(i) for i in range(1, 25))]
    added = dht.learn_contacts(kademlia.contacts_to_records(contacts))
    assert added == len(contacts)
    assert len(dht.table) == len(contacts)          # routable
    assert len(dht.directory) == len(contacts)          # dialable
    # a node never routes to itself
    self_rec = kademlia.contacts_to_records([Contact(node_id=dht.self_id,
                                                     address=PeerAddress(host="1.1.1.1", port=1))])
    assert dht.learn_contacts(self_rec) == 0


def test_closest_query_is_xor_correct():
    pub, _ = _peer(0)
    dht = DhtDiscovery(pub)
    contacts = [c for _, c in (_peer(i) for i in range(1, 200))]
    dht.learn_contacts(kademlia.contacts_to_records(contacts))
    target = node_id(_peer(500)[0])
    got = dht.closest_contacts(target, 8)
    # brute-force over exactly what the table actually holds (buckets are bounded,
    # so some contacts may have been refused — closeness must be correct over the
    # retained set, deterministically)
    held = dht.table.contacts()
    brute = sorted(held, key=lambda c: (xor_distance(c.node_id, target), c.id_hex))[:8]
    assert [c.id_hex for c in got] == [c.id_hex for c in brute]


def test_target_aware_pex_replies_with_closest_contacts():
    pub, _ = _peer(0)
    dht = DhtDiscovery(pub)
    contacts = [c for _, c in (_peer(i) for i in range(1, 120))]
    dht.learn_contacts(kademlia.contacts_to_records(contacts))
    target = node_id(_peer(777)[0])
    q = peer_exchange_query(dht.directory, target)
    assert q["kind"] == discovery.PEER_EXCHANGE_KIND and "target" in q
    reply = handle_peer_exchange(dht, q)
    ids = [r["id"] for r in reply["peers"]]
    brute = sorted(contacts, key=lambda c: xor_distance(c.node_id, target))
    assert ids[0] == brute[0].id_hex               # nearest first


def test_find_node_converges_in_log_n_rounds_over_a_1k_network():
    """1000-node simulated network: each node answers find_node from its own table."""
    N = 1000
    peers = [_peer(i) for i in range(N)]
    # give every node a routing table over the whole network (simulation only —
    # the lookup still only *queries* alpha per round and must converge fast)
    tables = {}
    for pub, c in peers:
        t = kademlia.RoutingTable(node_id(pub))
        for _pub2, c2 in peers:
            if c2.node_id != c.node_id:
                t.add(c2)
        tables[c.id_hex] = t

    by_id = {c.id_hex: c for _, c in peers}

    def responder(contact, target):
        return tables[contact.id_hex].closest(target, kademlia.DEFAULT_K)

    # a fresh node that only knows a handful of random-ish seeds
    seeker_pub, seeker_c = _peer(10_000)
    dht = DhtDiscovery(seeker_pub)
    seeds = [c for _, c in peers[::137]][:8]        # sparse, deterministic seed set
    dht.learn_contacts(kademlia.contacts_to_records(seeds))

    target = node_id(peers[424][0])
    result = dht.find_node(target, responder)

    true_closest = sorted((c for _, c in peers),
                          key=lambda c: xor_distance(c.node_id, target))[:kademlia.DEFAULT_K]
    assert {c.id_hex for c in result} == {c.id_hex for c in true_closest}
    # the actual target is found
    assert peers[424][1].id_hex in {c.id_hex for c in result}


def test_find_node_round_count_is_logarithmic():
    N = 1000
    peers = [_peer(i) for i in range(N)]
    tables = {}
    for pub, c in peers:
        t = kademlia.RoutingTable(node_id(pub))
        for _p2, c2 in peers:
            if c2.node_id != c.node_id:
                t.add(c2)
        tables[c.id_hex] = t

    def responder(contact, target):
        return tables[contact.id_hex].closest(target, kademlia.DEFAULT_K)

    seeker_pub, _ = _peer(20_000)
    dht = DhtDiscovery(seeker_pub)
    dht.learn_contacts(kademlia.contacts_to_records([c for _, c in peers[::100]]))
    target = node_id(peers[42][0])
    from knitweb.p2p.kademlia import iterative_lookup
    state = iterative_lookup(target, dht.table.closest(target), responder)
    # O(log n): comfortably under a small multiple of log2(N) ≈ 10
    assert state.rounds <= 6 * math.ceil(math.log2(N))
