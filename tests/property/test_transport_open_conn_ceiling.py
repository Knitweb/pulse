"""Hard ceiling on concurrently-open inbound sockets (issue #174, follows #168/#173).

#173 added ``accept_queue_timeout_s``, which drops a connection parked too long
waiting for a serving slot — bounding parked fds by ``arrival_rate × timeout``.
Under a high enough arrival rate that window still lets a burst transiently
exhaust the fd table. ``max_open_conns`` adds a hard ceiling on concurrently-OPEN
inbound sockets, checked *before* a connection parks: over the ceiling the newest
connection is closed immediately, so a burst can never pin more than the ceiling
of fds regardless of arrival rate.

Deterministic integer policy knob; never touches the wire framing bytes (signed
record byte-identity is unaffected).
"""

import asyncio

import pytest

from knitweb.p2p.transport import (
    DEFAULT_MAX_INBOUND,
    DEFAULT_MAX_OPEN_CONNS,
    TcpTransport,
)
from knitweb.p2p.wire import read_frame, write_frame


@pytest.mark.property
def test_default_open_ceiling_is_int_above_serving_cap():
    assert isinstance(DEFAULT_MAX_OPEN_CONNS, int)
    # The ceiling must leave room for every serving slot.
    assert DEFAULT_MAX_OPEN_CONNS >= DEFAULT_MAX_INBOUND


@pytest.mark.property
def test_open_ceiling_below_serving_cap_rejected():
    with pytest.raises(ValueError):
        TcpTransport(max_inbound=64, max_open_conns=63)


def test_open_ceiling_drops_excess_connection_immediately():
    """Beyond ``max_open_conns`` open sockets, the newest is dropped at once.

    One held handler occupies the single serving slot, a second connection parks
    on it (open, at the ceiling), and the third — over the ceiling — is closed
    immediately without ever being served.
    """

    async def run() -> None:
        live = 0
        peak = 0
        gate = asyncio.Event()

        async def handler(request: dict) -> dict:
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            await gate.wait()
            live -= 1
            return {"ok": True}

        # 1 served slot, ceiling of 2 open sockets, long park timeout so the
        # parked connection stays open (does not time out) during the assertions.
        transport = TcpTransport(
            host="127.0.0.1",
            port=0,
            max_inbound=1,
            max_open_conns=2,
            accept_queue_timeout_s=30,
        )
        await transport.listen(handler)
        host, port = transport.host, transport.port

        # conn1 takes the only slot; handler held by the gate.
        r1, w1 = await asyncio.open_connection(host, port)
        await write_frame(w1, {"kind": "ping"})
        for _ in range(200):
            await asyncio.sleep(0)
            if peak >= 1:
                break
        assert peak == 1

        # conn2 is accepted (open) but parks on the busy slot — open_conns hits the
        # ceiling. Poll the real counter so the next step is race-free.
        r2, w2 = await asyncio.open_connection(host, port)
        await write_frame(w2, {"kind": "ping"})
        for _ in range(200):
            await asyncio.sleep(0)
            if transport._open_conns >= 2:
                break
        assert transport._open_conns == 2

        # conn3 is over the ceiling → server drops it immediately (EOF), no serve.
        r3, w3 = await asyncio.open_connection(host, port)
        assert await asyncio.wait_for(r3.read(), timeout=5) == b""
        assert peak == 1  # the handler still ran only once

        # Releasing conn1 frees the slot; the parked conn2 is then served.
        gate.set()
        assert await read_frame(r1) == {"ok": True}
        assert await read_frame(r2) == {"ok": True}
        for w in (w1, w2, w3):
            w.close()
        await transport.close()

    asyncio.run(asyncio.wait_for(run(), timeout=15))


def test_open_counter_returns_to_zero_after_drops_and_serves():
    """Every accepted connection — served, parked-then-served, or ceiling-dropped —
    decrements the open counter, so the ceiling never silently leaks capacity."""

    async def run() -> None:
        async def handler(request: dict) -> dict:
            return {"echo": request.get("n")}

        transport = TcpTransport(
            host="127.0.0.1", port=0, max_inbound=2, max_open_conns=4
        )
        await transport.listen(handler)
        host, port = transport.host, transport.port

        for n in range(6):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                await write_frame(writer, {"kind": "ping", "n": n})
                assert await read_frame(reader) == {"echo": n}
            finally:
                writer.close()
                await writer.wait_closed()

        # Let the server-side finally blocks run to completion.
        for _ in range(200):
            await asyncio.sleep(0)
            if transport._open_conns == 0:
                break
        assert transport._open_conns == 0
        await transport.close()

    asyncio.run(asyncio.wait_for(run(), timeout=15))
