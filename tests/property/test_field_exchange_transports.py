"""End-to-end proofs: field-observation bundles over the real transport seams.

Two simulated wearers exchange observation bundles over the actual carriers —
the BitChat/BLE transport (loopback bridge) and the WebRTC DataChannel
transport (in-process fake bridge pair). The bundle bytes ride as an OPAQUE
value inside the standard length-prefixed canonical-CBOR wire frames, so
nothing new touches a signed path.

Covers:
  * glass A observes → commit → pack; glass B receives the bundle over BLE and
    accepts the nearby sighting;
  * the same loop over a two-peer WebRTC pair, including the ack contract;
  * a tampered bundle crossing a real carrier is refused and leaves the
    receiver untouched (the carrier is honest, the content is not);
  * spatial acceptance still applies end to end (faraway sightings dropped).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

import pytest

from knitweb.core import crypto
from knitweb.edge.exchange import ExchangeVerifyError, FieldGlass, pack_observations
from knitweb.edge.observer import GlassObserver
from knitweb.edge.recognize import MarkerBackend, recognize
from knitweb.fabric.web import Web
from knitweb.p2p.bluetooth_transport import (
    BluetoothTransport,
    LoopbackBluetoothBridge,
    bluetooth_address,
)
from knitweb.p2p.transport import PeerAddress
from knitweb.p2p.webrtc_transport import WEBRTC_TAG, WebRtcError, WebRtcTransport, WorkerBridge

_POT_CID = "bafyreilp001"
_AMS = (52.3702, 4.8952)
_PARIS = (48.8566, 2.3522)

BUNDLE_OP = "field-bundle"


def _bundle_at(lat: float, lon: float, marker: str = "qr:pot-7") -> bytes:
    """A signed one-observation bundle produced by a wearer at (lat, lon)."""
    priv, _pub = crypto.generate_keypair()
    glass = GlassObserver(priv, lat, lon, precision=9)
    glass.observe(recognize(marker, MarkerBackend({marker: _POT_CID})), label=marker, beat=1)
    [(_o, _a, attestation)] = glass.commit(Web())
    return pack_observations([attestation])


def _receiver_handler(receiver: FieldGlass) -> Callable[[dict], Awaitable[dict]]:
    """The device-side dispatch a listening glass runs for field bundles."""

    async def handler(request: dict) -> dict:
        if request.get("op") != BUNDLE_OP:
            return {"op": BUNDLE_OP, "error": "unknown-op"}
        try:
            accepted = receiver.receive(request["bundle"])
        except ExchangeVerifyError:
            return {"op": BUNDLE_OP, "error": "verify-failed"}
        return {"op": BUNDLE_OP, "accepted": accepted}

    return handler


# ── BitChat / BLE ───────────────────────────────────────────────────────────

@pytest.mark.property
def test_bundle_over_bitchat_loopback_accepted():
    """Glass A's sighting reaches glass B over the BLE carrier and is kept."""
    receiver = FieldGlass(*_AMS, precision=5)
    key = "02" + "ab" * 32

    async def run():
        transport = BluetoothTransport(
            bridge=LoopbackBluetoothBridge(self_key=key), self_key=key
        )
        await transport.listen(_receiver_handler(receiver))
        reply = await transport.dial(
            bluetooth_address(key), {"op": BUNDLE_OP, "bundle": _bundle_at(*_AMS)}
        )
        await transport.close()
        return reply

    reply = asyncio.run(run())
    assert reply["accepted"] == 1
    assert receiver.accepted_count == 1
    [entry] = receiver.overlays()
    assert entry["target"] == _POT_CID


@pytest.mark.property
def test_tampered_bundle_over_bitchat_is_refused():
    """A forged bundle crosses the carrier fine — and is refused on arrival."""
    receiver = FieldGlass(*_AMS, precision=5)
    key = "02" + "cd" * 32
    bundle = bytearray(_bundle_at(*_AMS))
    bundle[len(bundle) // 2] ^= 0xFF

    async def run():
        transport = BluetoothTransport(
            bridge=LoopbackBluetoothBridge(self_key=key), self_key=key
        )
        await transport.listen(_receiver_handler(receiver))
        reply = await transport.dial(
            bluetooth_address(key), {"op": BUNDLE_OP, "bundle": bytes(bundle)}
        )
        await transport.close()
        return reply

    reply = asyncio.run(run())
    assert reply == {"op": BUNDLE_OP, "error": "verify-failed"}
    assert receiver.accepted_count == 0


# ── WebRTC DataChannel pair ─────────────────────────────────────────────────

class _PairBridge(WorkerBridge):
    """In-process two-peer bridge: frames cross directly to the wired peer.

    NOT a real DataChannel — the same fake-shell pattern the WebRTC transport
    proofs use, so the framing/envelope/dispatch logic runs without a browser.
    """

    def __init__(self, self_key: str) -> None:
        self._self_key = self_key
        self.peer: Optional["_PairBridge"] = None
        self._inbound: Optional[Callable[[str, int, bytes], Awaitable[None]]] = None
        self._waiters: dict[int, asyncio.Future] = {}

    async def dial_frame(self, peer_key: str, rid: int, frame: bytes) -> bytes:
        assert self.peer is not None
        waiter = asyncio.get_running_loop().create_future()
        self._waiters[rid] = waiter
        if self.peer._inbound is not None:
            asyncio.ensure_future(self.peer._inbound(self._self_key, rid, frame))
        return await waiter

    def respond_frame(self, peer_key: str, rid: int, frame: bytes) -> None:
        assert self.peer is not None
        waiter = self.peer._waiters.pop(rid, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(frame)

    def set_inbound(self, callback) -> None:
        self._inbound = callback

    def set_frame_fault(self, callback) -> None:
        self._fault = callback

    async def close(self) -> None:
        for waiter in self._waiters.values():
            if not waiter.done():
                waiter.set_exception(WebRtcError("closed"))
        self._waiters.clear()

    def local_params(self) -> dict:
        return {"pubkey": self._self_key}


def _webrtc_pair() -> tuple[WebRtcTransport, WebRtcTransport, PeerAddress]:
    bridge_a, bridge_b = _PairBridge("pub_a"), _PairBridge("pub_b")
    bridge_a.peer, bridge_b.peer = bridge_b, bridge_a
    ta = WebRtcTransport(bridge=bridge_a, self_key="pub_a")
    tb = WebRtcTransport(bridge=bridge_b, self_key="pub_b")
    addr_b = PeerAddress(transport=WEBRTC_TAG, params={"pubkey": "pub_b"})
    return ta, tb, addr_b


@pytest.mark.property
def test_bundle_over_webrtc_pair_end_to_end():
    """Two wearers, two transports: nearby kept, faraway dropped, over the wire."""
    receiver = FieldGlass(*_AMS, precision=5)

    async def run():
        ta, tb, addr_b = _webrtc_pair()
        await tb.listen(_receiver_handler(receiver))
        near = await ta.dial(addr_b, {"op": BUNDLE_OP, "bundle": _bundle_at(*_AMS)})
        far = await ta.dial(
            addr_b, {"op": BUNDLE_OP, "bundle": _bundle_at(*_PARIS, marker="qr:tour-1")}
        )
        await ta.close()
        await tb.close()
        return near, far

    near, far = asyncio.run(run())
    assert near["accepted"] == 1
    assert far["accepted"] == 0          # verified fine, but anchored elsewhere
    assert receiver.accepted_count == 1
    [entry] = receiver.overlays()
    assert entry["label"] == "qr:pot-7"


@pytest.mark.property
def test_webrtc_receiver_weaves_shared_sightings_locally():
    """After the wire crossing, peer sightings serve through the local Web."""
    from knitweb.edge.observer import overlay_near
    from knitweb.fabric.spatial import geohash
    from knitweb.fabric.spatial_index import SpatialIndex

    receiver = FieldGlass(*_AMS, precision=5)

    async def run():
        ta, tb, addr_b = _webrtc_pair()
        await tb.listen(_receiver_handler(receiver))
        reply = await ta.dial(addr_b, {"op": BUNDLE_OP, "bundle": _bundle_at(*_AMS)})
        await ta.close()
        await tb.close()
        return reply

    assert asyncio.run(run())["accepted"] == 1
    web = Web()
    receiver.weave_into(web)
    index = SpatialIndex.from_web(web)
    [entry] = overlay_near(web, index, geohash(*_AMS, 9), 6)
    assert entry["target"] == _POT_CID
