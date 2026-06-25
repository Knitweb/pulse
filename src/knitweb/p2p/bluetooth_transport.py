"""BitChat-over-Bluetooth transport seam.

A neighbourhood carrier: when two peers are physically close they can exchange
knits and chat over **Bluetooth Low Energy** without any internet or relay —
"BitChat".  It pairs with the opt-in neighbourhood scope
(:mod:`knitweb.fabric.neighbourhood`): you see and talk to your *buren*, not
random strangers on the wider web.

This module is a **seam, not a radio.**  Real BLE needs platform-specific access
(CoreBluetooth / Android BLE / BlueZ via ``bleak``), which the dependency-free
core cannot provide.  So the actual radio lives behind an injectable
:class:`BluetoothBridge` — exactly the pattern :mod:`knitweb.p2p.webrtc_transport`
uses for its JS shell.  With **no bridge installed the transport refuses
honestly** (:class:`BluetoothUnavailable`); it never pretends to send over a
radio that isn't there.  A :class:`LoopbackBluetoothBridge` is provided for
in-process testing and is clearly labelled as *not* a real radio.

Frames are the same OPAQUE length-prefixed canonical-CBOR produced by
:mod:`knitweb.p2p.wire`; this carrier moves bytes and never interprets them, so
signed-record byte-identity is preserved end to end.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Awaitable, Callable, Optional

from .relay import (
    ENVELOPE_PEER_KEY,
    RELAY_ENVELOPE_PREFIX,
    _strip_envelope,
)
from .transport import FrameFaultHandler, FrameHandler, PeerAddress
from .wire import WireError, read_frame_bytes, write_frame_bytes

BITCHAT_TAG = "bitchat"
_DIAL_TIMEOUT_S = 30  # integer-seconds policy ceiling (BLE is slow; be patient)

_RID_KEY = RELAY_ENVELOPE_PREFIX + "rid"
_REPLY_TO_KEY = RELAY_ENVELOPE_PREFIX + "reply_to"


class BluetoothError(RuntimeError):
    """A BitChat/BLE carriage failure."""


class BluetoothUnavailable(BluetoothError):
    """Raised when BLE is used but no radio bridge is installed."""


def bitchat_peer_id(pubkey: str) -> str:
    """Stable short peer id used for BLE advertising / reputation keying."""
    if not pubkey:
        raise BluetoothError("bitchat peer id requires a pubkey")
    return f"{BITCHAT_TAG}:{pubkey[:16]}"


def bluetooth_address(pubkey: str, *, name: str | None = None) -> PeerAddress:
    """Build a dialable BitChat :class:`PeerAddress` for ``pubkey``."""
    params = {"pubkey": pubkey}
    if name:
        params["name"] = name
    return PeerAddress(transport=BITCHAT_TAG, params=params)


class BluetoothBridge:
    """Injectable seam to the actual BLE radio.

    A real implementation wraps the platform BLE stack (advertise + GATT
    read/write characteristics, or an L2CAP CoC) and is supplied by an optional
    backend.  The base class is abstract: every method raises so an
    accidentally-unwired transport fails loudly instead of silently dropping
    traffic.  ``frame`` args are OPAQUE wire bytes.
    """

    async def dial_frame(self, peer_key: str, rid: int, frame: bytes) -> bytes:
        raise NotImplementedError

    def respond_frame(self, peer_key: str, rid: int, frame: bytes) -> None:
        raise NotImplementedError

    def set_inbound(
        self, callback: Callable[[str, int, bytes], Awaitable[None]]
    ) -> None:
        raise NotImplementedError

    def set_frame_fault(self, callback: Callable[[str, str], None]) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    def local_params(self) -> dict:
        raise NotImplementedError


class BluetoothTransport:
    """BitChat carrier satisfying the :class:`knitweb.p2p.transport.Transport` Protocol.

    Parameters
    ----------
    bridge:
        A :class:`BluetoothBridge` to the real radio.  If ``None``, every I/O
        operation raises :class:`BluetoothUnavailable` — an honest "no radio
        here" rather than a silent no-op.
    self_key:
        This node's compressed pubkey hex (its reply address).
    dial_timeout_s:
        Integer-seconds ceiling for a correlated reply.
    """

    tag = BITCHAT_TAG

    def __init__(
        self,
        *,
        bridge: BluetoothBridge | None = None,
        self_key: str,
        dial_timeout_s: int = _DIAL_TIMEOUT_S,
    ) -> None:
        if dial_timeout_s < 1:
            raise ValueError("dial_timeout_s must be a positive integer")
        self.bridge = bridge
        self.self_key = self_key
        self.dial_timeout_s = dial_timeout_s
        self._handler: Optional[FrameHandler] = None
        self._on_frame_fault: Optional[FrameFaultHandler] = None
        self._rid = itertools.count(1)  # pure integer counter, never a clock
        self._closed = False

    def _require_bridge(self) -> BluetoothBridge:
        if self.bridge is None:
            raise BluetoothUnavailable(
                "no Bluetooth radio bridge installed; supply a BluetoothBridge "
                "backend (or LoopbackBluetoothBridge for tests)"
            )
        return self.bridge

    async def dial(self, peer: PeerAddress, request: dict) -> dict:
        """Send one ``request`` to a nearby ``peer`` over BLE; return the reply."""
        bridge = self._require_bridge()
        peer_key = peer.params.get("pubkey")
        if not peer_key:
            raise BluetoothError("bitchat peer address is missing a pubkey")
        rid = next(self._rid)
        envelope = dict(request)
        envelope[_RID_KEY] = rid
        envelope[_REPLY_TO_KEY] = self.self_key
        frame = write_frame_bytes(envelope)
        try:
            reply_frame = await asyncio.wait_for(
                bridge.dial_frame(peer_key, rid, frame), timeout=self.dial_timeout_s
            )
        except asyncio.TimeoutError as exc:
            raise BluetoothError("bitchat dial timed out waiting for reply") from exc
        except BluetoothError:
            raise
        except Exception as exc:
            raise BluetoothError(f"bitchat dial failed: {exc}") from exc
        try:
            decoded = read_frame_bytes(reply_frame)
        except WireError as exc:
            raise BluetoothError(f"bitchat reply frame malformed: {exc}") from exc
        return _strip_envelope(decoded)

    async def listen(
        self,
        handler: FrameHandler,
        on_frame_fault: "FrameFaultHandler | None" = None,
    ) -> None:
        """Begin accepting inbound BLE requests, dispatching to ``handler``."""
        bridge = self._require_bridge()
        self._handler = handler
        self._on_frame_fault = on_frame_fault
        bridge.set_inbound(self._on_inbound)
        bridge.set_frame_fault(self._on_inbound_fault)

    async def _on_inbound(self, peer_key: str, rid: int, frame: bytes) -> None:
        if self._handler is None:
            return
        try:
            decoded = read_frame_bytes(frame)
        except WireError as exc:
            self._on_inbound_fault(peer_key, str(exc))
            return
        request = _strip_envelope(decoded)
        request[ENVELOPE_PEER_KEY] = bitchat_peer_id(peer_key)
        try:
            response = await self._handler(request)
        except Exception:
            return
        try:
            out_frame = write_frame_bytes(response)
        except WireError:
            return
        self._require_bridge().respond_frame(peer_key, rid, out_frame)

    def _on_inbound_fault(self, peer_key: str, error: str) -> None:
        if self._on_frame_fault is None:
            return
        self._on_frame_fault(bitchat_peer_id(peer_key), WireError(error))

    async def close(self) -> None:
        """Release the radio. Idempotent; safe with no bridge."""
        if self._closed:
            return
        self._closed = True
        if self.bridge is not None:
            await self.bridge.close()

    def local_address(self) -> PeerAddress:
        """Address neighbours scan for to reach this node over BitChat."""
        params = dict(self._require_bridge().local_params())
        params.setdefault("pubkey", self.self_key)
        return PeerAddress(transport=BITCHAT_TAG, params=params)


class LoopbackBluetoothBridge(BluetoothBridge):
    """In-process bridge for tests — loops a single node's frames to itself.

    NOT a real radio.  It hands every dialed frame straight to the registered
    inbound callback and returns the produced reply, so the transport's framing /
    envelope / dispatch logic is exercised without any Bluetooth hardware.
    """

    def __init__(self, *, self_key: str) -> None:
        self.self_key = self_key
        self._inbound: Optional[Callable[[str, int, bytes], Awaitable[None]]] = None
        self._fault: Optional[Callable[[str, str], None]] = None
        self._replies: dict[int, bytes] = {}

    async def dial_frame(self, peer_key: str, rid: int, frame: bytes) -> bytes:
        if self._inbound is None:
            raise BluetoothError("loopback has no inbound handler registered")
        await self._inbound(self.self_key, rid, frame)
        if rid not in self._replies:
            raise BluetoothError("loopback produced no reply")
        return self._replies.pop(rid)

    def respond_frame(self, peer_key: str, rid: int, frame: bytes) -> None:
        self._replies[rid] = frame

    def set_inbound(
        self, callback: Callable[[str, int, bytes], Awaitable[None]]
    ) -> None:
        self._inbound = callback

    def set_frame_fault(self, callback: Callable[[str, str], None]) -> None:
        self._fault = callback

    async def close(self) -> None:
        self._inbound = None
        self._replies.clear()

    def local_params(self) -> dict:
        return {"pubkey": self.self_key}
