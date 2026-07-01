"""PeerStanding integration for the PoUW marketplace."""

import pytest

from knitweb.ledger.node import AccountNode
from knitweb.p2p.standing import BASE_WEIGHT_BPS, PeerStanding
from knitweb.pouw.marketplace import ComputeJob, Marketplace, SpiderAd
from knitweb.token.mint import NATIVE, EmissionPolicy, Treasury

VERIFIERS = [f"did:key:verifier-{i}" for i in range(9)]
PRICE = 100
N_BLOCKS = 8
BEAT = 100


def _setup(*, standing: PeerStanding | None = None) -> tuple[Marketplace, SpiderAd, AccountNode, AccountNode]:
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
def test_confirmed_marketplace_job_credits_spider_standing() -> None:
    standing = PeerStanding()
    mkt, ad, client, spider = _setup(standing=standing)
    job = ComputeJob(job_id="j-ok", seed=b"honest-seed", n_blocks=N_BLOCKS)

    result = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)

    assert result.confirmed
    assert standing.streak(spider.address) == 1


@pytest.mark.property
def test_tampered_marketplace_job_faults_spider_standing() -> None:
    standing = PeerStanding()
    mkt, ad, client, spider = _setup(standing=standing)
    for i in range(3):
        job = ComputeJob(job_id=f"j-ok-{i}", seed=f"seed-{i}".encode(), n_blocks=N_BLOCKS)
        mkt.run_job(job, ad, client, spider, submit_beat=BEAT + i)
    assert standing.streak(spider.address) == 3

    bad = ComputeJob(job_id="j-bad", seed=b"tamper-seed", n_blocks=N_BLOCKS)
    result = mkt.run_job(bad, ad, client, spider, submit_beat=BEAT + 10, tamper=True)

    assert not result.confirmed
    assert standing.streak(spider.address) == 0


@pytest.mark.property
def test_marketplace_standing_grows_across_confirmed_jobs() -> None:
    standing = PeerStanding()
    mkt, ad, client, spider = _setup(standing=standing)

    for i in range(5):
        job = ComputeJob(job_id=f"j-{i}", seed=f"seed-{i}".encode(), n_blocks=N_BLOCKS)
        mkt.run_job(job, ad, client, spider, submit_beat=BEAT + i)

    assert standing.streak(spider.address) == 5
    assert standing.reward_weight_bps(spider.address) > BASE_WEIGHT_BPS


@pytest.mark.property
def test_marketplace_standing_none_is_backward_compatible() -> None:
    mkt, ad, client, spider = _setup(standing=None)
    job = ComputeJob(job_id="j-compat", seed=b"compat-seed", n_blocks=N_BLOCKS)

    result = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)

    assert result.confirmed
    assert result.reward > 0


@pytest.mark.property
def test_confirmed_zero_reward_marketplace_job_still_credits_standing() -> None:
    standing = PeerStanding()
    mkt, ad, client, spider = _setup(standing=standing)
    mkt.treasury = Treasury(EmissionPolicy(rate_num=0, rate_den=1))
    job = ComputeJob(job_id="j-zero", seed=b"zero-seed", n_blocks=N_BLOCKS)

    result = mkt.run_job(job, ad, client, spider, submit_beat=BEAT)

    assert result.confirmed
    assert result.reward == 0
    assert standing.streak(spider.address) == 1
