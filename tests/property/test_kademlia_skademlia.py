"""Proofs for the S/Kademlia keyspace-eclipse hardening (#70).

RFC: docs/P2P_DHT_ECLIPSE_HARDENING.md. Pins the four defences it specifies:

  * **Static id puzzle** — :func:`id_puzzle_ok` accepts a mined pubkey at ``c1``
    and rejects below; verification is two hashes; expected grinding cost scales
    ``2^c1`` (measured on a deterministic corpus).
  * **Dynamic epoch puzzle** — :func:`epoch_puzzle_ok` binds to ``epoch_seed``:
    a proof for one epoch does not carry to another.
  * **Routing-table admission gate** — with a puzzle-backed ``admission_gate``,
    ground-but-unpuzzled ids never gain a k-bucket slot (the #88 acceptance:
    "ids below threshold rejected from routing table").
  * **Disjoint-path lookups** — the ``d`` paths share no queried intermediate,
    and a fully-controlled single neighbourhood cannot push fake near-target
    contacts past the ``quorum`` filter (while a plain single-shortlist lookup IS
    eclipsed by the same adversary — the mutation-kill contrast).
  * **Byte-identity (SACRED)** — puzzles + disjoint lookups never perturb a
    canonical-CBOR record or a fresh Knit CID.

Everything is deterministic: fixed strings hashed with SHA-256, injected
responders, no clock, no RNG.
"""

import hashlib

import pytest

from knitweb.core import canonical
from knitweb.p2p.kademlia import (
    DEFAULT_C1,
    DEFAULT_C2,
    DEFAULT_D,
    DEFAULT_QUORUM,
    ID_BITS,
    ID_BYTES,
    Contact,
    DisjointLookup,
    RoutingTable,
    disjoint_lookup,
    epoch_puzzle_ok,
    id_puzzle_ok,
    iterative_lookup,
    leading_zero_bits,
    node_id,
    xor_distance,
)
from knitweb.p2p.transport import PeerAddress


def _id(n: int) -> bytes:
    return n.to_bytes(ID_BYTES, "big")


def _contact(nid: bytes, port: int = 9000) -> Contact:
    return Contact(node_id=nid, address=PeerAddress("10.0.0.1", port))


def _puzzle_bits(pubkey_hex: str) -> int:
    """The static-puzzle difficulty a pubkey actually achieves."""
    return leading_zero_bits(hashlib.sha256(node_id(pubkey_hex)).digest())


def _mine_static(c1: int, prefix: str = "pk", *, start: int = 0) -> str:
    """Deterministically grind counter-pubkeys until one clears ``c1`` bits."""
    i = start
    while True:
        pub = f"{prefix}{i}"
        if _puzzle_bits(pub) >= c1:
            return pub
        i += 1


# -- leading_zero_bits --------------------------------------------------------


@pytest.mark.property
def test_leading_zero_bits_known_values():
    assert leading_zero_bits(b"\x80" + b"\x00" * 31) == 0
    assert leading_zero_bits(b"\x00\x80" + b"\x00" * 30) == 8
    assert leading_zero_bits(b"\x01" + b"\xff" * 31) == 7
    assert leading_zero_bits(b"\x00" * 32) == 256  # all-zero → every bit
    with pytest.raises(TypeError):
        leading_zero_bits("00ff")  # str is not bytes


# -- static id puzzle (RFC §3.1) -----------------------------------------------


@pytest.mark.property
def test_id_puzzle_accepts_mined_and_rejects_at_exact_boundary():
    pub = _mine_static(12)
    bits = _puzzle_bits(pub)
    assert bits >= 12
    # Boundary semantics: valid at exactly its achieved difficulty, invalid one above.
    assert id_puzzle_ok(pub, c1=bits)
    assert not id_puzzle_ok(pub, c1=bits + 1)
    # And an unmined pubkey below the threshold is rejected.
    weak = "pk0" if _puzzle_bits("pk0") < 12 else "pk1"
    assert _puzzle_bits(weak) < 12
    assert not id_puzzle_ok(weak, c1=12)
    # c1=0 accepts anything (advisory-off floor).
    assert id_puzzle_ok(weak, c1=0)


@pytest.mark.property
def test_id_puzzle_difficulty_validation():
    for bad in (-1, ID_BITS + 1, True, 1.5, "12"):
        with pytest.raises((ValueError, TypeError)):
            id_puzzle_ok("pk0", c1=bad)


@pytest.mark.property
def test_grinding_cost_scales_with_c1():
    """On a fixed 4096-key corpus the pass-count halves (≈) per extra bit —
    the puzzle prices id-minting at ~2^c1 expected hashes."""
    corpus = [f"corpus{i}" for i in range(4096)]
    achieved = [_puzzle_bits(p) for p in corpus]
    count = {c1: sum(1 for b in achieved if b >= c1) for c1 in (2, 5, 8)}
    # Strictly harder ⇒ strictly rarer, and each level is within loose 2× bounds
    # of the geometric expectation N / 2^c1 (deterministic corpus, no flake).
    assert count[2] > count[5] > count[8] > 0
    for c1 in (2, 5, 8):
        expected = 4096 // (2**c1)
        assert expected / 2 <= count[c1] <= expected * 2


# -- dynamic epoch puzzle (RFC §3.2) ---------------------------------------------


@pytest.mark.property
def test_epoch_puzzle_binds_to_seed():
    c2 = 10
    seed_a, seed_b = b"epoch-A", b"epoch-B"
    # Deterministically mine a pubkey valid for epoch A but NOT for epoch B, so
    # the test proves the seed is load-bearing (a one-off proof cannot be reused).
    i = 0
    while True:
        pub = f"ek{i}"
        if epoch_puzzle_ok(pub, seed_a, c2=c2) and not epoch_puzzle_ok(pub, seed_b, c2=c2):
            break
        i += 1
    assert epoch_puzzle_ok(pub, seed_a, c2=c2)
    assert not epoch_puzzle_ok(pub, seed_b, c2=c2)
    # str seeds are accepted (utf-8) and equal their bytes form.
    assert epoch_puzzle_ok(pub, "epoch-A", c2=c2)
    with pytest.raises(TypeError):
        epoch_puzzle_ok(pub, 123, c2=c2)


# -- routing-table admission gate (#88 acceptance) --------------------------------


@pytest.mark.property
def test_admission_gate_rejects_unpuzzled_ids_from_routing_table():
    c1 = 8
    # Six candidate peers: three mined ≥ c1, three below it (deterministic grind).
    strong, weak, i = [], [], 0
    while len(strong) < 3 or len(weak) < 3:
        pub = f"gate{i}"
        bucket = strong if _puzzle_bits(pub) >= c1 else weak
        if len(bucket) < 3:
            bucket.append(pub)
        i += 1
    pub_by_id = {node_id(p): p for p in strong + weak}
    gate = lambda c: id_puzzle_ok(pub_by_id[c.node_id], c1=c1)  # noqa: E731

    table = RoutingTable.from_pubkey("02" + "ab" * 32, admission_gate=gate)
    for pub in strong + weak:
        assert table.offer(_contact(node_id(pub))) is None  # never surfaces a probe
    admitted = {c.node_id for c in table.contacts()}
    assert admitted == {node_id(p) for p in strong}
    for pub in weak:
        assert node_id(pub) not in table  # ground-but-unpuzzled: no slot, ever

    # Known peers refresh without re-gating (admission-time check only).
    calls = []
    table2 = RoutingTable.from_pubkey(
        "02" + "cd" * 32, admission_gate=lambda c: (calls.append(c.id_hex), True)[1]
    )
    nid = node_id(strong[0])
    table2.offer(_contact(nid))
    table2.offer(_contact(nid, port=9001))  # refresh: address moved
    assert calls.count(nid.hex()) == 1

    with pytest.raises(TypeError):
        RoutingTable(_id(1), admission_gate="not-callable")


# -- disjoint-path lookup (RFC §3.3) ----------------------------------------------


def _build_network(n: int, k: int = 8):
    """A fully-informed simulated overlay (mirrors test_kademlia's builder)."""
    ids = [hashlib.sha256(f"net{i}".encode()).digest() for i in range(n)]
    contacts = {nid.hex(): _contact(nid, 9000 + i) for i, nid in enumerate(ids)}
    tables = {}
    for nid in ids:
        t = RoutingTable(nid, k=k)
        for other in ids:
            if other != nid:
                t.add(contacts[other.hex()])
        tables[nid.hex()] = t

    def responder(contact, target):
        return tables[contact.id_hex].closest(target, k)

    return ids, contacts, responder


@pytest.mark.property
def test_disjoint_paths_share_no_queried_intermediate():
    ids, contacts, responder = _build_network(40)
    target = _id(11)
    seeds = [contacts[nid.hex()] for nid in ids[:9]]
    dl = disjoint_lookup(target, seeds, responder, d=3, quorum=2, k=8)
    assert isinstance(dl, DisjointLookup) and len(dl.paths) == 3
    queried = [st.queried for st in dl.paths]
    assert all(q for q in queried)  # every path actually worked
    for a in range(3):
        for b in range(a + 1, 3):
            assert not (queried[a] & queried[b])  # node-disjoint intermediates


@pytest.mark.property
def test_disjoint_quorum_converges_to_global_truth_on_honest_network():
    ids, contacts, responder = _build_network(40)
    target = _id(11)
    seeds = [contacts[nid.hex()] for nid in ids[:9]]
    dl = disjoint_lookup(target, seeds, responder, d=3, quorum=2, k=8)
    truth = sorted(ids, key=lambda nid: xor_distance(nid, target))[:8]
    assert [c.node_id for c in dl.agreed()] == truth
    # Determinism: an identical run yields the identical answer.
    dl2 = disjoint_lookup(target, list(seeds), responder, d=3, quorum=2, k=8)
    assert [c.node_id for c in dl2.agreed()] == [c.node_id for c in dl.agreed()]


@pytest.mark.property
def test_controlled_neighborhood_cannot_reach_quorum():
    """The eclipse scenario the RFC exists for: an adversary controls one seed and
    every fake contact it advertises, answering FIND_NODE with ids ground to sit
    right next to the target. A plain single-shortlist lookup swallows the fakes;
    the disjoint-path quorum discards them (only one path ever talks to them)."""
    ids, contacts, honest_responder = _build_network(40)
    target = _id(11)

    evil_ids = [_id(12), _id(13), _id(14)]  # "ground" ids: closer to 11 than any honest sha256 id
    evil_seed = _contact(_id(15), 6666)
    evil = {c.hex() for c in evil_ids} | {evil_seed.id_hex}

    def responder(contact, tgt):
        if contact.id_hex in evil:  # a controlled node answers only with fakes
            return [_contact(nid, 6666) for nid in evil_ids]
        return honest_responder(contact, tgt)

    seeds = [contacts[nid.hex()] for nid in ids[:8]] + [evil_seed]

    # Baseline (no defence): the single-shortlist lookup is eclipsed — every fake
    # lands in its k-closest answer.
    eclipsed = iterative_lookup(target, seeds, responder, k=8)
    assert set(evil_ids) <= {c.node_id for c in eclipsed.result()}

    # Disjoint paths + quorum: fakes are reported by at most the one path that
    # queried a controlled node — below quorum, so agreed() is fake-free while
    # still returning honest near-target contacts.
    dl = disjoint_lookup(target, seeds, responder, d=3, quorum=2, k=8)
    fake_votes = sum(
        1 for st in dl.paths if {c.node_id for c in st.result()} & set(evil_ids)
    )
    assert fake_votes <= 1
    agreed_ids = {c.node_id for c in dl.agreed()}
    assert not (agreed_ids & set(evil_ids))
    assert agreed_ids  # the defence did not blank the answer


@pytest.mark.property
def test_disjoint_lookup_parameter_validation_and_degenerate_form():
    _, contacts, responder = _build_network(10)
    seeds = list(contacts.values())[:3]
    for d, q in ((0, 1), (3, 0), (3, 4), (True, 1), (3, True)):
        with pytest.raises(ValueError):
            disjoint_lookup(_id(1), seeds, responder, d=d, quorum=q)
    # d=1, quorum=1 degenerates to a plain iterative lookup's answer.
    dl = disjoint_lookup(_id(1), seeds, responder, d=1, quorum=1, k=5)
    plain = iterative_lookup(_id(1), seeds, responder, k=5)
    assert [c.node_id for c in dl.agreed()] == [c.node_id for c in plain.result()]


@pytest.mark.property
def test_rfc_parameter_defaults_pinned():
    # §4 of the RFC — conservative initial parameters. Changing them is a design
    # decision, not a drive-by: this pin makes that explicit.
    assert (DEFAULT_C1, DEFAULT_C2, DEFAULT_D, DEFAULT_QUORUM) == (20, 12, 3, 2)


# -- byte-identity / canonical safety (SACRED) ------------------------------------


@pytest.mark.property
def test_puzzles_and_disjoint_lookup_never_touch_canonical_bytes_or_cid():
    record = {"host": "1.2.3.4", "port": 9001, "kind": "knit"}
    cid_before = canonical.cid(record)
    bytes_before = canonical.encode(record)

    pub = _mine_static(8)
    id_puzzle_ok(pub, c1=8)
    epoch_puzzle_ok(pub, b"seed", c2=4)
    ids, contacts, responder = _build_network(20)
    disjoint_lookup(_id(7), list(contacts.values())[:6], responder, d=3, quorum=2).agreed()

    assert canonical.cid(record) == cid_before
    assert canonical.encode(record) == bytes_before
