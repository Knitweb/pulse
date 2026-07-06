"""STUN-assisted hole-punch transport (knitweb/molgang#89).

Home peers sit behind NAT, so today they are only reachable through the
``RelayTransport`` HTTP mailbox on 5mart.ml — making one PHP box a bottleneck and
a single point of failure. ``transport.py`` reserves the ``HOLE-PUNCH SEAM`` for
exactly this: a :class:`Transport` that (1) learns its public ``host:port`` from
a rendezvous/STUN spider, (2) coordinates simultaneous-open with the dialing
peer, then (3) hands the connected socket to the shared accept loop — same
opaque canonical-CBOR frames, zero payload inspection.

This module implements that transport (tag ``"hp"``) by **composition, not
reimplementation**: the coordination is an injected :class:`Rendezvous` (the
5mart relay registry in production; an in-memory one in tests), and the direct
carriage is the existing :class:`~knitweb.p2p.transport.TcpTransport`. Because a
punched session *is* a TCP connection carrying the same ``write_frame`` bytes,
``hp://`` frames are byte-identical to ``tcp://`` for the same request — the
carrier never mutates the payload. On punch failure (symmetric NAT: the
rendezvous cannot give the dialer a reachable endpoint) the transport falls back
to the peer's relay mailbox, so the peer stays reachable and the record still
converges.

Injectable + socket-honest: no STUN server is hard-coded, no clock, no RNG, no
float, no new dependency. The ``serve()`` wiring (register via ``add_transport``)
is the node layer's call, exactly like the relay transport.
"""
from __future__ import annotations

from typing import Optional, Protocol, Tuple, runtime_checkable

from .transport import FrameFaultHandler, FrameHandler, PeerAddress, TcpTransport

__all__ = [
    "HolePunchError",
    "Rendezvous",
    "InMemoryRendezvous",
    "HolePunchTransport",
]


class HolePunchError(Exception):
    """Raised when a hole-punch cannot be established and there is no fallback."""


@runtime_checkable
class Rendezvous(Protocol):
    """The coordination spider behind a hole punch (injected).

    Production binds this to the 5mart.ml relay registry so the relay is used
    ONLY for the brief coordination handshake, after which traffic goes direct.
    Tests bind an in-memory implementation so the punch is deterministic and
    socket-honest without a real STUN server.
    """

    async def public_address(self, listener: "HolePunchTransport") -> Tuple[str, int]:
        """STUN step: the public ``host:port`` peers should dial for ``listener``."""
        ...

    async def register(self, punch_id: str, host: str, port: int) -> None:
        """Publish a listener's punched endpoint under its ``punch_id``."""
        ...

    async def resolve(self, punch_id: str) -> "Optional[Tuple[str, int]]":
        """The dialer's endpoint for ``punch_id``, or ``None`` if none is reachable
        (symmetric NAT / no direct path) — the signal to fall back to relay."""
        ...

    async def unregister(self, punch_id: str) -> None:
        """Drop a listener's endpoint (best-effort; idempotent)."""
        ...


class InMemoryRendezvous:
    """A deterministic, socket-honest rendezvous for tests/local runs.

    A shared registry maps ``punch_id -> (host, port)``. ``public_address``
    returns the listener's ACTUAL bound TCP address, so the "punched" endpoint is
    genuinely dialable in-process — modelling two peers learning each other's
    public endpoints and then connecting directly, without any real NAT. Add a
    ``punch_id`` to ``symmetric`` to model a symmetric NAT: ``resolve`` returns
    ``None`` for it, forcing the relay fallback.
    """

    def __init__(self) -> None:
        self.registry: dict[str, Tuple[str, int]] = {}
        self.symmetric: set[str] = set()

    async def public_address(self, listener: "HolePunchTransport") -> Tuple[str, int]:
        addr = listener._tcp.local_address()
        return addr.host, addr.port

    async def register(self, punch_id: str, host: str, port: int) -> None:
        self.registry[punch_id] = (host, port)

    async def resolve(self, punch_id: str) -> "Optional[Tuple[str, int]]":
        if punch_id in self.symmetric:
            return None
        return self.registry.get(punch_id)

    async def unregister(self, punch_id: str) -> None:
        self.registry.pop(punch_id, None)


class HolePunchTransport:
    """A NAT-traversing carrier: coordinate via rendezvous, then carry over TCP.

    ``punch_id`` is this node's stable coordination id (peers resolve it through
    the rendezvous). ``relay`` (+ a peer's relay params) is the fallback used when
    a punch cannot be established. The direct carriage is a composed
    :class:`TcpTransport`, so the listen/accept loop, its connection caps, and the
    byte-exact framing are reused verbatim.
    """

    tag = "hp"

    def __init__(
        self,
        *,
        punch_id: str,
        rendezvous: Rendezvous,
        tcp: "TcpTransport | None" = None,
        relay=None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        if not punch_id:
            raise ValueError("punch_id must be a non-empty string")
        self.punch_id = punch_id
        self.rendezvous = rendezvous
        self.relay = relay
        self._tcp = tcp or TcpTransport(host=host, port=port)
        self._registered = False

    # -- dial --------------------------------------------------------------
    async def dial(self, peer: PeerAddress, request: dict) -> dict:
        """Dial ``peer`` directly through a punched TCP session, or fall back.

        Resolves the peer's punched endpoint via the rendezvous. A reachable
        endpoint ⇒ a direct TCP dial (byte-identical frames). ``None`` ⇒ punch
        failed (symmetric NAT): fall back to the peer's relay mailbox if one is
        available, else raise :class:`HolePunchError`.
        """
        punch_id = peer.params.get("punch_id")
        if not punch_id:
            raise ValueError("hp peer address must carry a punch_id param")
        endpoint = await self.rendezvous.resolve(punch_id)
        if endpoint is not None:
            host, port = endpoint
            direct = PeerAddress(host=host, port=port, transport="tcp")
            return await self._tcp.dial(direct, request)
        # symmetric NAT / no direct path → transparent relay fallback
        fallback = self._relay_peer(peer)
        if fallback is not None and self.relay is not None:
            return await self.relay.dial(fallback, request)
        raise HolePunchError(f"hole punch failed for {punch_id!r} and no relay fallback")

    @staticmethod
    def _relay_peer(peer: PeerAddress) -> "PeerAddress | None":
        """The relay:// fallback address carried alongside an hp:// peer, if any."""
        mailbox = peer.params.get("relay_mailbox")
        base = peer.params.get("relay_base")
        if mailbox and base:
            return PeerAddress(transport="relay", params={"mailbox": mailbox, "base_url": base})
        return None

    # -- listen ------------------------------------------------------------
    async def listen(
        self, handler: FrameHandler, on_frame_fault: "FrameFaultHandler | None" = None
    ) -> None:
        """Learn our public endpoint, publish it, and serve punched sessions.

        Binds the composed TCP listener first (so ``public_address`` can read the
        real bound port), registers ``(punch_id -> public host:port)`` with the
        rendezvous, then delegates the accept loop to the TCP transport unchanged.
        """
        await self._tcp.listen(handler, on_frame_fault)
        host, port = await self.rendezvous.public_address(self)
        await self.rendezvous.register(self.punch_id, host, port)
        self._registered = True

    async def close(self) -> None:
        if self._registered:
            try:
                await self.rendezvous.unregister(self.punch_id)
            finally:
                self._registered = False
        await self._tcp.close()

    def local_address(self) -> PeerAddress:
        """The ``hp://`` address peers dial to reach this listener (via rendezvous)."""
        return PeerAddress(transport="hp", params={"punch_id": self.punch_id})
