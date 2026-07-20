"""P6: BitChat-over-Bluetooth transport seam.

Acceptance criteria
-------------------
AC1  honest seam: with no radio bridge, dial/listen/local_address raise
     BluetoothUnavailable (never a silent no-op).
AC2  address/peer-id helpers: correct shape; empty pubkey raises.
AC3  round-trip over the loopback bridge: request reaches the handler, reply
     returns, with the transport envelope stripped both ways.
AC4  the verified sender is stamped onto the inbound request as the peer key.
AC5  malformed inbound frame fires the frame-fault hook.
AC6  dial_timeout_s validation; close() idempotent and safe with no bridge.
AC7  satisfies the Transport protocol surface; tag == BITCHAT_TAG.
"""

from __future__ import annotations

import asyncio

import pytest

from knitweb.p2p.bluetooth_transport import (
    BITCHAT_TAG,
    BluetoothError,
    BluetoothTransport,
    BluetoothUnavailable,
    LoopbackBluetoothBridge,
    bitchat_peer_id,
    bluetooth_address,
)
from knitweb.p2p.relay import ENVELOPE_PEER_KEY, RELAY_ENVELOPE_PREFIX

_KEY = "02" + "ab" * 32  # a plausible 33-byte compressed pubkey hex


# ── AC1: honest unavailability without a radio ────────────────────────────────
@pytest.mark.property
def test_no_bridge_dial_raises_unavailable():
    t = BluetoothTransport(self_key=_KEY)
    with pytest.raises(BluetoothUnavailable):
        asyncio.run(t.dial(bluetooth_address(_KEY), {"op": "ping"}))


@pytest.mark.property
def test_no_bridge_listen_and_local_address_raise():
    t = BluetoothTransport(self_key=_KEY)
    with pytest.raises(BluetoothUnavailable):
        asyncio.run(t.listen(lambda req: req))  # type: ignore[arg-type]
    with pytest.raises(BluetoothUnavailable):
        t.local_address()


# ── AC2: helpers ──────────────────────────────────────────────────────────────
@pytest.mark.property
def test_peer_id_and_address():
    assert bitchat_peer_id(_KEY).startswith(f"{BITCHAT_TAG}:")
    addr = bluetooth_address(_KEY, name="kitchen-pi")
    assert addr.transport == BITCHAT_TAG
    assert addr.params["pubkey"] == _KEY and addr.params["name"] == "kitchen-pi"


@pytest.mark.property
def test_peer_id_requires_pubkey():
    with pytest.raises(BluetoothError):
        bitchat_peer_id("")


# ── AC3 / AC4: loopback round-trip ────────────────────────────────────────────
@pytest.mark.property
def test_loopback_round_trip_and_envelope_stripped():
    seen: dict = {}

    async def handler(request: dict) -> dict:
        seen.update(request)
        return {"echo": request.get("op"), "ok": True}

    async def run():
        bridge = LoopbackBluetoothBridge(self_key=_KEY)
        t = BluetoothTransport(bridge=bridge, self_key=_KEY)
        await t.listen(handler)
        return await t.dial(bluetooth_address(_KEY), {"op": "hello"})

    reply = asyncio.run(run())
    assert reply == {"echo": "hello", "ok": True}
    # handler saw no transport-envelope keys ...
    assert not any(k.startswith(RELAY_ENVELOPE_PREFIX) for k in seen if k != ENVELOPE_PEER_KEY)
    # ... but did see the stamped sender identity (AC4).
    assert seen[ENVELOPE_PEER_KEY] == bitchat_peer_id(_KEY)
    # and the reply handed back to the caller is also envelope-free
    assert not any(k.startswith(RELAY_ENVELOPE_PREFIX) for k in reply)


# ── AC5: malformed inbound frame fires the fault hook ─────────────────────────
@pytest.mark.property
def test_malformed_inbound_frame_faults():
    faults: list = []

    async def handler(request: dict) -> dict:  # pragma: no cover - should not run
        return {}

    async def run():
        bridge = LoopbackBluetoothBridge(self_key=_KEY)
        t = BluetoothTransport(bridge=bridge, self_key=_KEY)
        await t.listen(handler, on_frame_fault=lambda peer, err: faults.append((peer, err)))
        # Feed garbage straight to the inbound path.
        await t._on_inbound(_KEY, 1, b"\xff\xff not a frame")

    asyncio.run(run())
    assert faults and faults[0][0] == bitchat_peer_id(_KEY)


# ── AC6: validation / lifecycle ───────────────────────────────────────────────
@pytest.mark.property
def test_dial_timeout_must_be_positive_int():
    with pytest.raises(ValueError):
        BluetoothTransport(self_key=_KEY, dial_timeout_s=0)


@pytest.mark.property
def test_close_idempotent_without_bridge():
    t = BluetoothTransport(self_key=_KEY)
    asyncio.run(t.close())
    asyncio.run(t.close())  # second call is a no-op, no raise


@pytest.mark.property
def test_dial_missing_pubkey_raises():
    from knitweb.p2p.transport import PeerAddress

    async def run():
        bridge = LoopbackBluetoothBridge(self_key=_KEY)
        t = BluetoothTransport(bridge=bridge, self_key=_KEY)
        await t.dial(PeerAddress(transport=BITCHAT_TAG), {"op": "x"})

    with pytest.raises(BluetoothError):
        asyncio.run(run())


# ── AC7: Transport protocol surface ───────────────────────────────────────────
@pytest.mark.property
def test_transport_protocol_surface():
    t = BluetoothTransport(self_key=_KEY)
    assert t.tag == BITCHAT_TAG
    for method in ("dial", "listen", "close", "local_address"):
        assert callable(getattr(t, method))


@pytest.mark.property
def test_local_address_via_bridge():
    bridge = LoopbackBluetoothBridge(self_key=_KEY)
    t = BluetoothTransport(bridge=bridge, self_key=_KEY)
    addr = t.local_address()
    assert addr.transport == BITCHAT_TAG and addr.params["pubkey"] == _KEY
