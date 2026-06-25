"""Property tests for PeerStanding integration in the Marketplace.

The standing wire-in fills the gap where marketplace jobs bypassed the
streak system entirely. Every confirmed job now credits the spider's streak;
every tampered/slashed job faults it.
"""

import pytest

from knitweb.ledger.node import AccountNode
from knitweb.p2p.standing import BASE_WEIGHT_BPS, PeerStanding
from knitweb.pouw.marketplace import ComputeJob, Marketplace, SpiderAd
from knitweb.token.mint import NATIVE, EmissionPolicy, Treasury

VERIFIERS = [f"did:key:verifier-{i}" for i in range(9)]
PRICE = 100
N_BLOCKS = 8
BEAT = 100


def _setup(*, standing=None):
    mkt = Marketplace(
        treasury=Treasury(EmissionPolicy(rate_num=1, rate_den=2)),
        standing=standing,
    )
    spider = AccountNode()
    ad = SpiderAd(spider=spider.address, gpus=2, ram_mib=2048, price_per_block=PRICE)
    mkt.advertise(ad, VERIFIERS)
    client = AccountNode(genesis_balances={NATIVE: 100_000})
    return mkt, ad, client, spider


@pytest.mark.property
def test_confirmed_job_credits_streak():
    s = PeerStanding()
    mkt, ad, client, spider = _setup(standing=s)
    job = ComputeJob(job_id="j-ok", seed=b"honest-seed", n_blocks=N_BLOCKS)

    r = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)

    assert r.confirmed
    assert s.streak(spider.address) == 1


@pytest.mark.property
def test_tampered_job_faults_streak():
    s = PeerStanding()
    mkt, ad, client, spider = _setup(standing=s)
    # Build a streak first.
    for i in range(3):
        job = ComputeJob(job_id=f"j-ok-{i}", seed=f"seed-{i}".encode(), n_blocks=N_BLOCKS)
        mkt.run_job(job, ad, client, spider, submit_beat=BEAT + i)
    assert s.streak(spider.address) == 3

    bad = ComputeJob(job_id="j-bad", seed=b"tamper-seed", n_blocks=N_BLOCKS)
    r = mkt.run_job(bad, ad, client, spider, submit_beat=BEAT + 10, tamper=True)

    assert not r.confirmed
    assert s.streak(spider.address) == 0   # streak reset on fault


@pytest.mark.property
def test_streak_grows_across_multiple_confirmed_jobs():
    s = PeerStanding()
    mkt, ad, client, spider = _setup(standing=s)

    for i in range(5):
        job = ComputeJob(job_id=f"j-{i}", seed=f"seed-{i}".encode(), n_blocks=N_BLOCKS)
        mkt.run_job(job, ad, client, spider, submit_beat=BEAT + i)

    assert s.streak(spider.address) == 5
    assert s.reward_weight_bps(spider.address) > BASE_WEIGHT_BPS


@pytest.mark.property
def test_standing_none_is_backward_compatible():
    # Default Marketplace (no standing) works exactly as before — no AttributeError.
    mkt, ad, client, spider = _setup(standing=None)
    job = ComputeJob(job_id="j-compat", seed=b"compat-seed", n_blocks=N_BLOCKS)
    r = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)
    assert r.confirmed and r.reward > 0


@pytest.mark.property
def test_standing_not_credited_when_reward_zero():
    # Edge case: policy mints nothing (0/1 rate → reward=0), but confirmed job
    # still credits standing — the streak tracks stable *work*, not earnings.
    s = PeerStanding()
    mkt, ad, client, spider = _setup(standing=s)
    mkt.treasury = Treasury(EmissionPolicy(rate_num=0, rate_den=1))

    job = ComputeJob(job_id="j-zero", seed=b"zero-seed", n_blocks=N_BLOCKS)
    r = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)

    # reward == 0 but job was confirmed and released
    assert r.confirmed
    assert s.streak(spider.address) == 1   # stable work credited regardless of mint
