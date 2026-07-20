"""HttpRendezvous — the production Rendezvous against the api/relay/punch API.

Socket-honest for the punched TCP path, socket-free for the HTTP hop: a
FakePunchServer implements the exact JSON semantics of
``deploy/5mart/api/relay/punch.php`` (server-observed host, declared port,
owner-pinned entries) behind the same injectable :class:`HttpPoster` seam the
relay tests use. Two NAT-free nodes coordinate through it and connect
DIRECTLY over real TCP; outage and stale-endpoint paths degrade to the relay
fallback instead of failing the dial.
"""
import asyncio

import pytest

from knitweb.core import crypto  # noqa: F401  (interop fixture parity)
from knitweb.fabric.node import FabricNode
from knitweb.p2p.holepunch import (
    HolePunchError,
    HolePunchTransport,
    HttpRendezvous,
)
from knitweb.p2p.relay import HttpPoster, RelayError
from knitweb.p2p.transport import PeerAddress


def run(coro):
    return asyncio.run(coro)


class FakePunchServer(HttpPoster):
    """In-memory twin of punch.php: same actions, same reply shapes.

    ``observed_host`` plays REMOTE_ADDR — in these tests every caller is
    127.0.0.1, which is also where the listeners genuinely bind, so a resolved
    endpoint is genuinely dialable (the InMemoryRendezvous trick, but through
    the HTTP protocol shape).
    """

    def __init__(self, observed_host="127.0.0.1"):
        self.observed_host = observed_host
        self.registry = {}
        self.requests = []
        self.down = False

    async def post(self, url, payload):
        if self.down:
            raise RelayError("rendezvous unreachable")
        self.requests.append((url, dict(payload)))
        action = payload.get("action")
        if action == "whoami":
            return {"ok": True, "host": self.observed_host, "port": 0}
        pid = payload.get("punch_id", "")
        if action == "register":
            self.registry[pid] = {"host": self.observed_host, "port": payload["port"]}
            return {"ok": True}
        if action == "resolve":
            e = self.registry.get(pid)
            return {"ok": True, "endpoint": dict(e) if e else None}
        if action == "unregister":
            self.registry.pop(pid, None)
            return {"ok": True}
        return {"ok": False, "error": "unknown action"}


def _hp(punch_id, server, **kw):
    rv = HttpRendezvous("https://5mart.ml", poster=server)
    return HolePunchTransport(punch_id=punch_id, rendezvous=rv, **kw)


@pytest.mark.interop
def test_two_nodes_go_direct_through_the_http_rendezvous():
    async def scenario():
        server = FakePunchServer()
        b = FabricNode(transport=_hp("peerB", server))
        async with b:
            # listen() published B's genuinely dialable endpoint
            assert server.registry["peerB"]["host"] == "127.0.0.1"
            assert server.registry["peerB"]["port"] > 0
            a = FabricNode(transport=_hp("peerA", server))
            async with a:
                a.add_peer("b", b.address)
                await a.weave({"kind": "knowledge", "title": "punched-http",
                               "body": "x", "author": a.pub})
                assert b.web.size == a.web.size == (1, 0)
                assert b.state_root == a.state_root
        # close() unregistered both listeners
        assert "peerB" not in server.registry and "peerA" not in server.registry

    run(scenario())


@pytest.mark.interop
def test_wire_shape_matches_punch_php():
    """The client speaks exactly the API punch.php serves — one URL, action in
    the body, declared port on register — so the PHP side can be verified with
    the same payloads."""
    async def scenario():
        server = FakePunchServer()
        hp = _hp("nodeX", server)
        await hp.listen(lambda req: asyncio.sleep(0))  # handler unused here
        try:
            urls = {u for u, _ in server.requests}
            assert urls == {"https://5mart.ml/api/relay/punch"}
            actions = [p["action"] for _, p in server.requests]
            assert actions == ["whoami", "register"]
            reg = server.requests[-1][1]
            assert reg["punch_id"] == "nodeX" and isinstance(reg["port"], int)
        finally:
            await hp.close()
        assert server.requests[-1][1]["action"] == "unregister"

    run(scenario())


@pytest.mark.interop
def test_rendezvous_outage_resolves_to_relay_fallback():
    async def scenario():
        server = FakePunchServer()

        class _StubRelay:
            tag = "relay"
            def __init__(self):
                self.calls = 0
            async def dial(self, peer, request):
                self.calls += 1
                return {"kind": "ack"}

        relay = _StubRelay()
        hp = _hp("peerA", server, relay=relay)
        server.down = True                      # rendezvous outage, not NAT
        peer = PeerAddress(transport="hp", params={
            "punch_id": "peerB",
            "relay_mailbox": "boxB", "relay_base": "http://relay",
        })
        resp = await hp.dial(peer, {"kind": "ping"})
        assert resp == {"kind": "ack"} and relay.calls == 1

    run(scenario())


@pytest.mark.interop
def test_stale_endpoint_falls_back_to_relay_instead_of_failing():
    """A registered-but-dead endpoint (listener crashed inside the TTL) must
    degrade to the relay mailbox, not surface as a dial error."""
    async def scenario():
        server = FakePunchServer()

        class _StubRelay:
            tag = "relay"
            def __init__(self):
                self.calls = 0
            async def dial(self, peer, request):
                self.calls += 1
                return {"kind": "ack"}

        # find a port that is certainly closed by binding+closing one
        probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        dead_port = probe.sockets[0].getsockname()[1]
        probe.close()
        await probe.wait_closed()
        server.registry["peerB"] = {"host": "127.0.0.1", "port": dead_port}

        relay = _StubRelay()
        hp = _hp("peerA", server, relay=relay)
        peer = PeerAddress(transport="hp", params={
            "punch_id": "peerB",
            "relay_mailbox": "boxB", "relay_base": "http://relay",
        })
        resp = await hp.dial(peer, {"kind": "ping"})
        assert resp == {"kind": "ack"} and relay.calls == 1

        # without a relay the same dead endpoint is a loud HolePunchError
        bare = _hp("peerC", server)
        with pytest.raises(HolePunchError):
            await bare.dial(PeerAddress(transport="hp",
                                        params={"punch_id": "peerB"}), {"kind": "ping"})

    run(scenario())


@pytest.mark.interop
def test_register_refusal_raises():
    async def scenario():
        class RefusingServer(FakePunchServer):
            async def post(self, url, payload):
                if payload.get("action") == "register":
                    return {"ok": False, "error": "punch_id taken"}
                return await super().post(url, payload)

        hp = _hp("nodeX", RefusingServer())
        with pytest.raises(HolePunchError):
            await hp.listen(lambda req: asyncio.sleep(0))
        await hp.close()

    run(scenario())
