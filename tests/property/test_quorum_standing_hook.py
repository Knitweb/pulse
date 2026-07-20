"""Property tests for PeerStanding integration in quorum settlement.

Confirmed quorum → credit the worker's streak.
DECLARED_FAULT or DETECTED_FAULT → fault (reset) the worker's streak.
INCONCLUSIVE outcome → standing unchanged.
standing=None (default) → behaviour is byte-identical to the pre-standing path.
"""

from __future__ import annotations

import pytest

from knitweb.core import crypto
from knitweb.ledger.node import AccountNode
from knitweb.p2p.standing import BASE_WEIGHT_BPS, PeerStanding
from knitweb.pouw.job import SynapticCompileJob, WorkProof, execute
from knitweb.pouw.quorum_settlement import settle_on_quorum


def _make_job() -> tuple[SynapticCompileJob, object]:
    priv, pub = crypto.generate_keypair()
    asset = {
        "origintrail_id": 1,
        "originator": "Acme",
        "linked_sources": [{"type": "IFRS_File", "url": "https://ifrs.org"}],
    }
    return SynapticCompileJob(asset=asset, originator_pub=pub), priv


def _accounts(pulses: int = 100) -> tuple[AccountNode, AccountNode]:
    consumer = AccountNode(genesis_balances={"PLS": pulses})
    worker = AccountNode()
    return consumer, worker


def _good_proofs(job, priv, n: int = 3) -> list[WorkProof]:
    return [execute(job, priv) for _ in range(n)]


def _forged_proofs(job, priv, n: int = 3) -> list[WorkProof]:
    real = execute(job, priv)
    return [WorkProof(bytecode=real.bytecode, signature="deadbeef", digest=real.digest)] * n


# ── CONFIRMED quorum → credit ────────────────────────────────────────────────

@pytest.mark.property
def test_confirmed_quorum_credits_worker_standing():
    job, priv = _make_job()
    consumer, worker = _accounts()
    s = PeerStanding()

    paid, result = settle_on_quorum(
        consumer, worker, 10, job, _good_proofs(job, priv), timestamp=1, standing=s
    )

    assert paid is True
    assert s.streak(worker.address) == 1
    assert s.reward_weight_bps(worker.address) > BASE_WEIGHT_BPS


@pytest.mark.property
def test_repeated_confirmed_quorums_accumulate_streak():
    job, priv = _make_job()
    s = PeerStanding()

    # One worker, five independent consumers (fresh escrow each round).
    worker = AccountNode()

    for ts in range(1, 6):
        consumer = AccountNode(genesis_balances={"PLS": 100})
        paid, _ = settle_on_quorum(
            consumer, worker, 5, job, _good_proofs(job, priv), timestamp=ts, standing=s
        )
        assert paid is True

    assert s.streak(worker.address) == 5


# ── DECLARED_FAULT → fault ───────────────────────────────────────────────────

@pytest.mark.property
def test_declared_fault_resets_worker_standing():
    job, priv = _make_job()
    consumer, worker = _accounts()
    s = PeerStanding()

    # Build up some streak first.
    for ts in range(1, 4):
        c = AccountNode(genesis_balances={"PLS": 100})
        settle_on_quorum(c, worker, 5, job, _good_proofs(job, priv), timestamp=ts, standing=s)
    assert s.streak(worker.address) == 3

    # Worker admits a fault.
    c = AccountNode(genesis_balances={"PLS": 100})
    paid, result = settle_on_quorum(
        c, worker, 5, job, _good_proofs(job, priv), timestamp=4,
        worker_declared_fault=True, standing=s,
    )

    assert paid is False
    assert s.streak(worker.address) == 0
    assert s.reward_weight_bps(worker.address) == BASE_WEIGHT_BPS


# ── DETECTED_FAULT → fault ───────────────────────────────────────────────────

@pytest.mark.property
def test_detected_fault_resets_worker_standing():
    job, priv = _make_job()
    consumer, worker = _accounts()
    s = PeerStanding()

    # Build streak.
    for ts in range(1, 4):
        c = AccountNode(genesis_balances={"PLS": 100})
        settle_on_quorum(c, worker, 5, job, _good_proofs(job, priv), timestamp=ts, standing=s)
    assert s.streak(worker.address) == 3

    # Submit all-forged proofs → DETECTED_FAULT quorum.
    c = AccountNode(genesis_balances={"PLS": 100})
    paid, result = settle_on_quorum(
        c, worker, 5, job, _forged_proofs(job, priv), timestamp=4, standing=s
    )

    assert paid is False
    assert s.streak(worker.address) == 0


# ── INCONCLUSIVE → no standing change ───────────────────────────────────────

@pytest.mark.property
def test_inconclusive_leaves_standing_unchanged():
    job, priv = _make_job()
    s = PeerStanding()

    # Pre-warm standing.
    consumer0, worker = _accounts()
    settle_on_quorum(consumer0, worker, 5, job, _good_proofs(job, priv), timestamp=1, standing=s)
    assert s.streak(worker.address) == 1

    # Single verifier with 1 confirm, 1 mismatch → INCONCLUSIVE (no supermajority).
    real_proof = execute(job, priv)
    forged = WorkProof(bytecode=real_proof.bytecode, signature="deadbeef", digest=real_proof.digest)
    consumer1 = AccountNode(genesis_balances={"PLS": 100})
    paid, result = settle_on_quorum(
        consumer1, worker, 5, job, [real_proof, forged], timestamp=2, standing=s
    )

    assert paid is False
    # Streak must be unchanged — INCONCLUSIVE must not trigger fault().
    assert s.streak(worker.address) == 1


# ── standing=None → backward-compat ─────────────────────────────────────────

@pytest.mark.property
def test_no_standing_arg_is_backward_compatible():
    job, priv = _make_job()
    consumer, worker = _accounts()

    # Must not raise; paid/result are identical to the pre-standing path.
    paid, result = settle_on_quorum(
        consumer, worker, 10, job, _good_proofs(job, priv), timestamp=1
    )
    assert paid is True
