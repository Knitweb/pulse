"""Proofs for PAR issuance: proof-of-observation, demand-gated, no-premine.

The economic loop: a confirmed, attested field observation that answers a funded
bounty settles the consumer's PLS escrow to the observer AND mints bounded PAR.
Unconfirmed, unattested, tampered, or non-answering observations mint nothing.
Issuance never exceeds the escrow consumed nor the supply cap, and is replay-proof.
"""

import pytest

from knitweb.fabric.observation import FieldObservation, attest_observation
from knitweb.ledger.node import AccountNode
from knitweb.token.mint import NATIVE, EmissionPolicy
from knitweb.token.par import PAR, ObservationBounty, ObservationTreasury


def _observation(observer: AccountNode, *, confidence: int = 1000, label: str = "hydrant",
                 geohash: str = "u173zq", beat: int = 50) -> FieldObservation:
    return FieldObservation(
        geohash=geohash,
        alt_band=0,
        label=label,
        backend="scene_semantic",
        confidence_milli=confidence,
        target="bafy-target-node",
        observer=observer.address,
        beat=beat,
    )


def _bounty(consumer: AccountNode, *, escrow: int = 100) -> ObservationBounty:
    return ObservationBounty(
        consumer=consumer.address,
        geohash_prefix="u173",
        label="hydrant",
        escrow=escrow,
        beat_open=0,
        beat_close=100,
    )


def _pls_total(*nodes) -> int:
    return sum(n.balance(NATIVE) for n in nodes)


@pytest.mark.property
def test_no_premine():
    t = ObservationTreasury()
    assert t.total_minted == 0 and t.issuances == []


@pytest.mark.property
def test_confirmed_observation_settles_escrow_and_mints_bounded_par():
    consumer = AccountNode(genesis_balances={"PLS": 100})
    observer = AccountNode()
    obs = _observation(observer)
    att = attest_observation(obs, observer.priv)
    bounty = _bounty(consumer, escrow=100)
    t = ObservationTreasury(EmissionPolicy(rate_num=1, rate_den=2))

    pls_before = _pls_total(consumer, observer)
    issuance = t.reward_verified_observation(consumer, observer, bounty, obs, att, 1)

    assert issuance is not None and issuance.amount == 50  # escrow/2
    assert consumer.balance(NATIVE) == 0                   # escrow left the consumer
    assert observer.balance(NATIVE) == 100                 # ...and reached the observer
    assert observer.balance(PAR) == 50                     # plus the PAR coinbase
    assert _pls_total(consumer, observer) == pls_before    # PLS is conserved
    assert t.total_minted == 50
    assert issuance.observation_cid == obs.cid and issuance.bounty_cid == bounty.cid


@pytest.mark.property
def test_replay_of_the_same_observation_mints_nothing():
    consumer = AccountNode(genesis_balances={"PLS": 200})
    observer = AccountNode()
    obs = _observation(observer)
    att = attest_observation(obs, observer.priv)
    bounty = _bounty(consumer, escrow=100)
    t = ObservationTreasury(EmissionPolicy(rate_num=1, rate_den=2))

    assert t.reward_verified_observation(consumer, observer, bounty, obs, att, 1) is not None
    assert t.reward_verified_observation(consumer, observer, bounty, obs, att, 2) is None
    assert t.total_minted == 50 and consumer.balance(NATIVE) == 100  # settled once


@pytest.mark.property
def test_unconfirmed_observation_binds_no_value():
    consumer = AccountNode(genesis_balances={"PLS": 100})
    observer = AccountNode()
    obs = _observation(observer, confidence=900)  # requires confirmation
    att = attest_observation(obs, observer.priv)
    t = ObservationTreasury()

    assert t.reward_verified_observation(consumer, observer, _bounty(consumer), obs, att, 1) is None
    assert consumer.balance(NATIVE) == 100 and t.total_minted == 0


@pytest.mark.property
def test_attestation_must_match_and_verify():
    consumer = AccountNode(genesis_balances={"PLS": 100})
    observer = AccountNode()
    other = AccountNode()
    obs = _observation(observer)
    t = ObservationTreasury()

    # Attestation over a *different* record than the claimed observation.
    decoy = _observation(observer, beat=51)
    att_decoy = attest_observation(decoy, observer.priv)
    assert t.reward_verified_observation(consumer, observer, _bounty(consumer), obs, att_decoy, 1) is None

    # Attestation signed by a key that does not own the observer address.
    att = attest_observation(obs, observer.priv)
    forged = type(att)(record=att.record, author_pub=other.pub, sig=att.sig)
    assert t.reward_verified_observation(consumer, observer, _bounty(consumer), obs, forged, 1) is None
    assert consumer.balance(NATIVE) == 100 and t.total_minted == 0


@pytest.mark.property
def test_observation_must_actually_answer_the_bounty():
    consumer = AccountNode(genesis_balances={"PLS": 100})
    observer = AccountNode()
    t = ObservationTreasury()
    bounty = _bounty(consumer)

    for wrong in (
        _observation(observer, label="bench"),          # wrong label
        _observation(observer, geohash="v99xxx"),       # outside the cell prefix
        _observation(observer, beat=101),               # after the window closed
    ):
        att = attest_observation(wrong, observer.priv)
        assert t.reward_verified_observation(consumer, observer, bounty, wrong, att, 1) is None
    assert consumer.balance(NATIVE) == 100 and t.total_minted == 0


@pytest.mark.property
def test_structural_errors_raise_before_any_state_change():
    consumer = AccountNode(genesis_balances={"PLS": 100})
    observer = AccountNode()
    stranger = AccountNode(genesis_balances={"PLS": 100})
    obs = _observation(observer)
    att = attest_observation(obs, observer.priv)
    bounty = _bounty(consumer)
    t = ObservationTreasury()

    with pytest.raises(ValueError):   # bounty funded by someone else
        t.reward_verified_observation(stranger, observer, bounty, obs, att, 1)
    with pytest.raises(ValueError):   # observer node does not own the observation
        t.reward_verified_observation(consumer, stranger, bounty, obs, att, 1)
    with pytest.raises(TypeError):    # bool timestamp violates integer-only
        t.reward_verified_observation(consumer, observer, bounty, obs, att, True)
    underfunded = AccountNode(genesis_balances={"PLS": 5})
    poor_bounty = ObservationBounty(
        consumer=underfunded.address, geohash_prefix="u173", label="hydrant",
        escrow=100, beat_open=0, beat_close=100,
    )
    with pytest.raises(ValueError):   # escrow beyond the consumer's balance
        t.reward_verified_observation(underfunded, observer, poor_bounty, obs, att, 1)
    assert consumer.balance(NATIVE) == 100 and t.total_minted == 0


@pytest.mark.property
def test_supply_cap_and_escrow_bound_hold():
    consumer = AccountNode(genesis_balances={"PLS": 400})
    observer = AccountNode()
    # Aggressive 3/2 rate: policy must still clamp mint to the escrow itself.
    t = ObservationTreasury(EmissionPolicy(rate_num=3, rate_den=2, max_supply=150))

    obs1 = _observation(observer, beat=10)
    i1 = t.reward_verified_observation(
        consumer, observer, _bounty(consumer, escrow=100), obs1,
        attest_observation(obs1, observer.priv), 1,
    )
    assert i1 is not None and i1.amount == 100  # clamped to escrow, not 150

    obs2 = _observation(observer, beat=20)
    i2 = t.reward_verified_observation(
        consumer, observer, _bounty(consumer, escrow=100), obs2,
        attest_observation(obs2, observer.priv), 2,
    )
    assert i2 is not None and i2.amount == 50   # clamped to remaining max_supply
    assert t.total_minted == 150 == t.policy.max_supply


@pytest.mark.property
def test_bounty_validation():
    consumer = AccountNode()
    with pytest.raises(ValueError):
        ObservationBounty(consumer=consumer.address, geohash_prefix="u173",
                          label="hydrant", escrow=0, beat_open=0, beat_close=1)
    with pytest.raises(ValueError):
        ObservationBounty(consumer=consumer.address, geohash_prefix="aiol",
                          label="hydrant", escrow=1, beat_open=0, beat_close=1)
    with pytest.raises(ValueError):
        ObservationBounty(consumer=consumer.address, geohash_prefix="u173",
                          label="hydrant", escrow=1, beat_open=5, beat_close=1)
