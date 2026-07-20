"""Two in-process FabricNodes converge on the same web_state_root.

Covers the first increment of issue #9: record propagation + convergence over
the asyncio p2p transport.
"""

import asyncio

import pytest

from knitweb.core import crypto
from knitweb.fabric.items import web_state_root
from knitweb.fabric.node import FabricNode


def run(coro):
    return asyncio.run(coro)


@pytest.mark.interop
def test_two_nodes_converge_on_state_root_via_broadcast():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            # a knows about b and gossips its weaves there.
            a.add_peer("b", b.address)

            assert a.state_root == b.state_root  # both empty → equal

            await a.weave({"kind": "knowledge", "title": "alpha", "body": "x", "author": a.pub})
            await a.weave({"kind": "resource", "resource_kind": "gpu",
                           "capacity": 4, "price_per_epoch": 9, "provider": a.pub})

            # b ingested both records → identical node set → identical root.
            assert b.web.size == a.web.size == (2, 0)
            assert a.state_root != crypto.sha256(b"").hex()  # non-empty root
            assert b.state_root == a.state_root

        assert web_state_root(b.web) == a.state_root

    run(scenario())


@pytest.mark.interop
def test_late_joiner_catches_up_with_sync_from():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            # Records woven *before* b is wired up: broadcast misses b.
            cid1 = await a.weave({"kind": "knowledge", "title": "early", "body": "1", "author": a.pub})
            cid2 = await a.weave({"kind": "knowledge", "title": "later", "body": "2", "author": a.pub})

            assert b.web.size == (0, 0)
            assert b.state_root != a.state_root

            # b pulls a's full record set and converges.
            added = await b.sync_from(a.address)
            assert added == 2
            assert b.web.get(cid1) is not None
            assert b.web.get(cid2) is not None
            assert b.state_root == a.state_root

            # Idempotent: a second sync weaves nothing new.
            assert await b.sync_from(a.address) == 0

    run(scenario())


@pytest.mark.interop
def test_idempotent_and_order_independent_convergence():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            a.add_peer("b", b.address)
            rec = {"kind": "knowledge", "title": "dup", "body": "z", "author": a.pub}
            cid_first = await a.weave(rec)
            cid_again = await a.weave(rec)  # re-weave identical content
            assert cid_first == cid_again
            assert a.web.size == (1, 0)
            assert b.web.size == (1, 0)
            assert a.state_root == b.state_root

    run(scenario())


@pytest.mark.interop
def test_tampered_record_is_rejected_by_signature_check():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with b:
            rec = {"kind": "knowledge", "title": "honest", "body": "h", "author": a.pub}
            msg = a._signed_record_msg(rec)
            # Tamper with the record after signing → signature no longer matches.
            msg["record"] = {**rec, "body": "forged"}
            reply = await a._send(b.address, msg)
            # Server rejects with an error frame and weaves nothing.
            assert reply.get("kind") == "error"
            assert b.web.size == (0, 0)

    run(scenario())


def test_gossiped_frames_bounded_while_authored_survive():
    """#92: the gossiped-in (non-authored) frame portion is size-bounded with LRU
    eviction, while every weave()-authored CID stays served — our own records are the
    authoritative source (their loss would be permanent), a gossiped frame is re-fetch-safe
    via anti-entropy. A blanket LRU (no _authored exemption) would evict `mine` and fail."""
    async def scenario():
        a = FabricNode()
        b = FabricNode(max_gossiped_frames=3)
        async with a, b:
            mine = await b.weave({"kind": "knowledge", "title": "mine", "body": "0", "author": b.pub})
            gcids = []
            for i in range(10):                      # flood gossiped-in past the cap of 3
                rec = {"kind": "knowledge", "title": f"g{i}", "body": str(i), "author": a.pub}
                cid = await a.weave(rec)
                b._ingest_signed(a._signed_record_msg(rec))   # b._serve_peer_key is None -> no throttle
                gcids.append(cid)
            assert mine in b._frames                                   # authored survives the flood
            assert sum(c in b._frames for c in gcids) <= 3            # non-authored bounded at the cap
            assert gcids[-1] in b._frames and gcids[0] not in b._frames  # LRU: newest kept, oldest evicted

    asyncio.run(scenario())


# ── #90: equivocation quarantine on the fabric gossip path ───────────────────

def _signed_head(priv, feed, root, length, fork):
    from knitweb.fabric.feed import FeedHead
    tmp = FeedHead(feed=feed, root=root, length=length, fork=fork, sig="")
    return FeedHead(feed=feed, root=root, length=length, fork=fork,
                    sig=crypto.sign(priv, tmp.signable()))


def _report_record(reporter="did:key:watcher"):
    """A verified equivocation report record + the offender's keypair."""
    from knitweb.fabric.equivocation import prove_equivocation
    priv, feed = crypto.generate_keypair()
    a = _signed_head(priv, feed, "aa" * 32, 3, 0)
    b = _signed_head(priv, feed, "bb" * 32, 3, 0)
    report = prove_equivocation(a, b, reporter)
    assert report is not None
    return report.to_record(), priv, feed


@pytest.mark.interop
def test_equivocation_report_bans_offender_and_quarantines_their_records():
    node = FabricNode()
    record, offender_priv, offender_feed = _report_record()
    carrier_priv, _carrier_pub = crypto.generate_keypair()

    # evidence arrives as a normal signed fabric record — verified, policed, NOT woven
    from knitweb.fabric.node import _record_signable
    env = {"kind": "fabric-record", "author": crypto.public_from_private(carrier_priv),
           "record": record,
           "sig": crypto.sign(carrier_priv, _record_signable(record))}
    root_before = web_state_root(node.web)
    assert node._ingest_signed(env) is False
    assert web_state_root(node.web) == root_before      # evidence never moves the state root
    assert node.reputation.is_banned(offender_feed)
    assert offender_feed in node.equivocation_reports
    assert node.metrics.get("equivocations_detected") == 1

    # any record AUTHORED by the banned key is quarantined: refused, not woven, no raise
    bad = {"kind": "molgang-term", "term": "H2O"}
    bad_env = {"kind": "fabric-record", "author": offender_feed, "record": bad,
               "sig": crypto.sign(offender_priv, _record_signable(bad))}
    assert node._ingest_signed(bad_env) is False
    assert web_state_root(node.web) == root_before
    assert node.metrics.get("records_quarantined") == 1


@pytest.mark.interop
def test_stored_report_reverifies_trustlessly():
    from knitweb.fabric.equivocation import verify_equivocation_report
    node = FabricNode()
    record, _priv, feed = _report_record()
    assert node._police_report_record(record) is True
    assert verify_equivocation_report(node.equivocation_reports[feed])
    # policing the same evidence twice is idempotent on the ban, no double count
    node._police_report_record(record)
    assert node.reputation.is_banned(feed)


@pytest.mark.interop
def test_unverifiable_report_is_ignored_never_penalized():
    node = FabricNode()
    record, _priv, feed = _report_record()
    record = dict(record)
    record["head_b"] = dict(record["head_b"], root="cc" * 32)   # break the evidence
    assert node._police_report_record(record) is False
    assert not node.reputation.is_banned(feed)
    assert node.metrics.get("equivocations_detected") in (0, None)


@pytest.mark.interop
def test_honest_fork_bump_is_not_reportable():
    """A legitimate truncate-and-rewrite bumps the fork counter → no equivocation."""
    from knitweb.fabric.equivocation import prove_equivocation
    priv, feed = crypto.generate_keypair()
    a = _signed_head(priv, feed, "aa" * 32, 3, 0)
    rewritten = _signed_head(priv, feed, "bb" * 32, 3, 1)       # fork bumped
    assert prove_equivocation(a, rewritten, "did:key:watcher") is None


# ── #91: range-multiproof catch-up — pull only the missing slice ─────────────

def _weave_n(node, n, prefix):
    async def go():
        for i in range(n):
            await node.weave({"kind": "knowledge", "title": f"{prefix}-{i}",
                              "body": "x", "author": node.pub})
    run(go())


@pytest.mark.interop
def test_late_joiner_pulls_only_the_missing_range():
    from knitweb.p2p import wire

    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            for i in range(48):
                await b.weave({"kind": "knowledge", "title": f"k-{i}",
                               "body": "x", "author": b.pub})
            # cold start: full snapshot, cursor primed on b's head
            added = await a.sync_from(b.address)
            assert added == 48 and a.state_root == b.state_root
            assert a._sync_cursors[b.pub] == 48

            # already converged: O(1) — no records pulled
            assert await a.sync_from(b.address) == 0

            for i in range(4):
                await b.weave({"kind": "knowledge", "title": f"late-{i}",
                               "body": "x", "author": b.pub})
            # incremental: exactly the 4 missing records over a verified slice
            added = await a.sync_from(b.address)
            assert added == 4
            assert a.state_root == b.state_root
            assert a._sync_cursors[b.pub] == 52
            assert a.metrics.get("sync_range_verified") == 1

            # O(count + log n), not O(total): the range reply is far smaller
            # than the full snapshot for the same converged set
            full = wire.write_frame_bytes(b._serve_sync())
            slice_ = wire.write_frame_bytes(b._serve_sync_range({"start": 48, "count": 4}))
            assert len(slice_) < len(full) / 5

    run(scenario())


@pytest.mark.interop
def test_forged_slice_is_rejected_and_server_penalised():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            for i in range(12):
                await b.weave({"kind": "knowledge", "title": f"k-{i}",
                               "body": "x", "author": b.pub})
            await a.sync_from(b.address)                      # prime the cursor
            for i in range(3):
                await b.weave({"kind": "knowledge", "title": f"late-{i}",
                               "body": "x", "author": b.pub})

            # tamper the served slice: entries no longer match the signed head
            real_serve = b._serve_sync_range
            def forged(msg):
                resp = real_serve(msg)
                if resp.get("kind") == "fabric-sync-range-data" and resp["entries"]:
                    resp["entries"][0] = dict(resp["entries"][0], title="FORGED")
                return resp
            b._serve_sync_range = forged

            root_before = a.state_root
            try:
                await a.sync_from(b.address)
                assert False, "forged slice must not be accepted"
            except Exception as exc:
                assert "multiproof" in str(exc)
            assert a.state_root == root_before               # nothing woven
            assert a.reputation.score(b.pub) > 0             # STALE_OR_FORGED_PROOF landed
            assert a.metrics.get("sync_range_rejected") == 1

    run(scenario())


@pytest.mark.interop
def test_cold_start_and_legacy_peer_fall_back_to_full_snapshot():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            for i in range(6):
                await b.weave({"kind": "knowledge", "title": f"k-{i}",
                               "body": "x", "author": b.pub})
            # legacy peer: pretend b does not speak fabric-sync-head
            real_route = b._route
            def legacy(kind, msg, source_id=None):
                if kind in ("fabric-sync-head", "fabric-sync-range"):
                    return {"kind": "error", "code": "unknown-kind", "message": str(kind)}
                return real_route(kind, msg, source_id)
            b._route = legacy
            added = await a.sync_from(b.address)             # falls back, converges
            assert added == 6 and a.state_root == b.state_root

    run(scenario())
