"""#89 — STUN-assisted hole-punch transport: two NAT'd peers go direct.

Socket-honest but NAT-free: an InMemoryRendezvous returns each listener's REAL
bound TCP endpoint (the "punched" address), so two nodes learn each other and
connect directly. Symmetric NAT is modelled by marking a punch_id unreachable,
forcing the relay fallback.
"""
import asyncio

import pytest

from knitweb.core import crypto
from knitweb.fabric.node import FabricNode
from knitweb.p2p.holepunch import (
    HolePunchError,
    HolePunchTransport,
    InMemoryRendezvous,
)
from knitweb.p2p.transport import PeerAddress, parse_peer_uri


def run(coro):
    return asyncio.run(coro)


def _hp(punch_id, rv, **kw):
    return HolePunchTransport(punch_id=punch_id, rendezvous=rv, **kw)


@pytest.mark.interop
def test_two_natd_nodes_hole_punch_and_exchange_a_record():
    async def scenario():
        rv = InMemoryRendezvous()
        b = FabricNode(transport=_hp("peerB", rv))
        async with b:
            a = FabricNode(transport=_hp("peerA", rv))
            async with a:
                a.add_peer("b", b.address)          # b.address is an hp:// PeerAddress
                assert b.address.transport == "hp"
                await a.weave({"kind": "knowledge", "title": "punched",
                               "body": "x", "author": a.pub})
                # the record crossed the DIRECT punched session and B wove it
                assert b.web.size == a.web.size == (1, 0)
                assert b.state_root == a.state_root

    run(scenario())


@pytest.mark.interop
def test_symmetric_nat_falls_back_to_relay_and_still_converges():
    async def scenario():
        rv = InMemoryRendezvous()
        rv.symmetric.add("peerB")                   # B is unreachable directly

        # a stub relay that delivers straight into B's request handler in-process
        class _StubRelay:
            tag = "relay"
            def __init__(self, dest):
                self.dest = dest
                self.calls = 0
            async def dial(self, peer, request):
                self.calls += 1
                return self.dest._route(request.get("kind"), request)

        b = FabricNode(transport=_hp("peerB", rv))
        async with b:
            relay = _StubRelay(b)
            a = FabricNode(transport=_hp("peerA", rv, relay=relay))
            async with a:
                # an hp peer that also carries a relay mailbox for fallback
                peer = PeerAddress(transport="hp", params={
                    "punch_id": "peerB",
                    "relay_mailbox": "boxB", "relay_base": "http://relay",
                })
                a.add_peer("b", peer)
                await a.weave({"kind": "knowledge", "title": "relayed",
                               "body": "x", "author": a.pub})
                assert relay.calls >= 1             # punch failed → relay used
                assert b.web.size == a.web.size      # and the record still converged

    run(scenario())


@pytest.mark.interop
def test_punch_failure_without_relay_raises():
    async def scenario():
        rv = InMemoryRendezvous()
        rv.symmetric.add("peerB")
        hp = _hp("peerA", rv)                        # no relay configured
        peer = PeerAddress(transport="hp", params={"punch_id": "peerB"})
        with pytest.raises(HolePunchError):
            await hp.dial(peer, {"kind": "ping"})

    run(scenario())


@pytest.mark.interop
def test_hp_frames_are_byte_identical_to_tcp():
    """The carrier never mutates the payload: an hp dial delivers the exact same
    request into the destination as a direct tcp dial would."""
    async def scenario():
        rv = InMemoryRendezvous()
        seen = []

        async def handler(req):
            seen.append(req)
            return {"kind": "ack"}

        listener = _hp("dest", rv)
        await listener.listen(handler)
        try:
            dialer = _hp("src", rv)
            req = {"kind": "fabric-record", "author": "02aa",
                   "record": {"kind": "knowledge", "title": "t", "n": 7}, "sig": "de"}
            peer = PeerAddress(transport="hp", params={"punch_id": "dest"})
            resp = await dialer.dial(peer, req)
            assert resp == {"kind": "ack"}
            # what the listener received equals what we sent — no carrier mutation
            # (the transport-envelope may add an identity key; the request body is intact)
            got = seen[-1]
            for k, v in req.items():
                assert got[k] == v
            await dialer.close()
        finally:
            await listener.close()

    run(scenario())


@pytest.mark.interop
def test_hp_uri_round_trips_and_dialer_routes_by_tag():
    # URI round-trip
    peer = parse_peer_uri("hp://myid@http://rendezvous")
    assert peer.transport == "hp" and peer.params["punch_id"] == "myid"
    assert peer.params["rendezvous"] == "http://rendezvous"
    assert peer.uri() == "hp://myid@http://rendezvous"
    # base-less form round-trips too
    p2 = parse_peer_uri("hp://onlyid@")
    assert p2.params["punch_id"] == "onlyid" and "rendezvous" not in p2.params

    # Dialer routes an hp peer to the hp transport by tag
    from knitweb.p2p.transport import Dialer
    rv = InMemoryRendezvous()
    hp = _hp("me", rv)
    d = Dialer()
    d.register(hp)
    assert d.transport_for(PeerAddress(transport="hp", params={"punch_id": "x"})) is hp
