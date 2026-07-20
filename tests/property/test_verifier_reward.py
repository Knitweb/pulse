"""Property tests for the verifier kickback ledger.

verifier_fee_split: integer, bounded, zero-safe.
VerifierRewardLedger: credit, claim, balance, committee batch.
Marketplace integration: confirmed job credits committee; failed job credits nothing.
"""

from __future__ import annotations

import pytest

from knitweb.pouw.verifier_reward import (
    DEFAULT_VERIFIER_FEE_BPS,
    VerifierRewardLedger,
    verifier_fee_split,
)


V1 = "did:key:verifier1"
V2 = "did:key:verifier2"
V3 = "did:key:verifier3"


# ── verifier_fee_split ────────────────────────────────────────────────────────

@pytest.mark.property
def test_fee_split_is_integer_floor():
    # 200 bps of 100 PLS among 3 verifiers: total_fee=2, per_v=0 (floor)
    assert verifier_fee_split(100, 200, 3) == 0
    # 200 bps of 1000 PLS among 3 verifiers: total_fee=20, per_v=6 (20//3)
    assert verifier_fee_split(1000, 200, 3) == 6


@pytest.mark.property
def test_fee_split_zero_cases():
    assert verifier_fee_split(0, 200, 3) == 0    # no reward → no fee
    assert verifier_fee_split(100, 0, 3) == 0    # fee_bps=0 → no fee
    assert verifier_fee_split(100, 200, 0) == 0  # k=0 → no fee (no committee)


@pytest.mark.property
def test_fee_split_full_bps_does_not_exceed_reward():
    # fee_bps=10000 (100%): all reward goes to verifiers
    per_v = verifier_fee_split(1000, 10_000, 4)
    assert per_v == 250   # 1000 // 4
    assert per_v * 4 <= 1000


@pytest.mark.property
def test_fee_split_rejects_over_100_percent():
    with pytest.raises(ValueError):
        verifier_fee_split(100, 10_001, 3)


@pytest.mark.property
def test_fee_split_rejects_non_int():
    with pytest.raises(TypeError):
        verifier_fee_split(100.0, 200, 3)   # type: ignore[arg-type]
    with pytest.raises(TypeError):
        verifier_fee_split(100, True, 3)    # type: ignore[arg-type]


# ── VerifierRewardLedger ──────────────────────────────────────────────────────

@pytest.mark.property
def test_fresh_ledger_has_zero_balance():
    ledger = VerifierRewardLedger()
    assert ledger.balance(V1) == 0
    assert ledger.tracked() == 0


@pytest.mark.property
def test_credit_accumulates():
    ledger = VerifierRewardLedger()
    ledger.credit(V1, 10)
    ledger.credit(V1, 5)
    assert ledger.balance(V1) == 15
    rec = ledger.earning(V1)
    assert rec is not None and rec.jobs == 2


@pytest.mark.property
def test_mark_claimed_reduces_balance():
    ledger = VerifierRewardLedger()
    ledger.credit(V1, 100)
    remaining = ledger.mark_claimed(V1, 60)
    assert remaining == 40
    assert ledger.balance(V1) == 40


@pytest.mark.property
def test_overclaim_raises():
    ledger = VerifierRewardLedger()
    ledger.credit(V1, 50)
    with pytest.raises(ValueError):
        ledger.mark_claimed(V1, 51)


@pytest.mark.property
def test_credit_committee_splits_evenly():
    ledger = VerifierRewardLedger(fee_bps=200)  # 2% of spider reward
    # spider_reward=1000, fee_bps=200 → total_fee=20, per_v=20//3=6
    per_v = ledger.credit_committee([V1, V2, V3], spider_reward=1000)
    assert per_v == 6
    assert ledger.balance(V1) == 6
    assert ledger.balance(V2) == 6
    assert ledger.balance(V3) == 6


@pytest.mark.property
def test_credit_committee_zero_reward_credits_nothing():
    ledger = VerifierRewardLedger(fee_bps=200)
    per_v = ledger.credit_committee([V1, V2], spider_reward=0)
    assert per_v == 0
    assert ledger.balance(V1) == 0
    assert ledger.tracked() == 0


@pytest.mark.property
def test_all_earners_sorted_descending():
    ledger = VerifierRewardLedger()
    ledger.credit(V1, 5)
    ledger.credit(V2, 20)
    ledger.credit(V3, 10)
    earners = ledger.all_earners()
    assert earners[0] == (V2, 20)
    assert earners[1] == (V3, 10)
    assert earners[2] == (V1, 5)


# ── Marketplace integration ───────────────────────────────────────────────────

@pytest.mark.property
def test_marketplace_confirmed_job_credits_verifiers():
    from fractions import Fraction
    from knitweb.ledger.node import AccountNode
    from knitweb.pouw.marketplace import ComputeJob, Marketplace, SpiderAd

    ledger = VerifierRewardLedger(fee_bps=DEFAULT_VERIFIER_FEE_BPS)
    mp = Marketplace(committee_size=3, verifier_reward=ledger)

    verifiers = [f"did:key:v{i}" for i in range(5)]
    # price_per_block=100 so escrow=1000, mint=500; 2% fee → 10 per verifier
    ad = SpiderAd(spider="did:key:spider", gpus=2, ram_mib=4096, price_per_block=100)
    job = ComputeJob(job_id="job-1", seed=b"test-seed-1", n_blocks=10,
                     need_gpus=1, need_ram_mib=512)
    mp.advertise(ad, verifiers)

    client = AccountNode(genesis_balances={"PLS": 10_000})
    spider = AccountNode()

    result = mp.run_job(job, ad, client, spider, submit_beat=1)

    assert result.confirmed
    assert result.reward > 0
    assert result.verifier_fee_per_member > 0
    # Each committee member earned the per-member fee.
    for v in result.committee:
        assert ledger.balance(v) == result.verifier_fee_per_member


@pytest.mark.property
def test_marketplace_failed_job_credits_nothing():
    from knitweb.ledger.node import AccountNode
    from knitweb.pouw.marketplace import ComputeJob, Marketplace, SpiderAd

    ledger = VerifierRewardLedger(fee_bps=DEFAULT_VERIFIER_FEE_BPS)
    mp = Marketplace(committee_size=3, verifier_reward=ledger)

    verifiers = [f"did:key:v{i}" for i in range(5)]
    ad = SpiderAd(spider="did:key:spider", gpus=2, ram_mib=4096)
    job = ComputeJob(job_id="job-bad", seed=b"test-seed-bad", n_blocks=4)
    mp.advertise(ad, verifiers)

    client = AccountNode(genesis_balances={"PLS": 1000})
    spider = AccountNode()

    result = mp.run_job(job, ad, client, spider, submit_beat=1, tamper=True)

    assert not result.confirmed
    assert result.verifier_fee_per_member == 0
    assert ledger.tracked() == 0   # no verifier touched


@pytest.mark.property
def test_marketplace_no_verifier_reward_is_backward_compatible():
    from knitweb.ledger.node import AccountNode
    from knitweb.pouw.marketplace import ComputeJob, Marketplace, SpiderAd

    mp = Marketplace(committee_size=3)   # no verifier_reward

    verifiers = [f"did:key:v{i}" for i in range(5)]
    ad = SpiderAd(spider="did:key:spider", gpus=2, ram_mib=4096)
    job = ComputeJob(job_id="job-compat", seed=b"test-seed-compat", n_blocks=4)
    mp.advertise(ad, verifiers)

    client = AccountNode(genesis_balances={"PLS": 1000})
    spider = AccountNode()

    result = mp.run_job(job, ad, client, spider, submit_beat=1)
    assert result.confirmed
    assert result.verifier_fee_per_member == 0   # field present but zero
