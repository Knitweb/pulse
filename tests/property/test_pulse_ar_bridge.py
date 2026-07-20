"""E14 bridge proofs: one observation path from device claim to PAR mint.

The invariants: floor-mapped confidence never rounds a device up into the
confirmed band, unresolvable targets are refused, forged mesh envelopes never
become candidate records, and a bridged full-confidence observation flows
end-to-end through attestation into an ObservationTreasury PAR mint.
"""

import pytest

from knitweb.edge.pulse_ar.bridge import (
    signed_to_field_observation,
    to_field_observation,
)
from knitweb.edge.pulse_ar.observation import (
    CONF_FULL,
    ObjectObservation,
    SignedObservation,
)
from knitweb.fabric.observation import CONFIDENCE_MILLI_EXACT, attest_observation
from knitweb.ledger.node import AccountNode
from knitweb.token.mint import NATIVE
from knitweb.token.par import PAR, ObservationBounty, ObservationTreasury


def _device_obs(device: AccountNode, *, bps: int = CONF_FULL, **over) -> ObjectObservation:
    spec = dict(label="hydrant", taxonomy="wn:03560161", confidence_bps=bps,
                geohash="u173zq", device=device.address, observed_at=50)
    spec.update(over)
    return ObjectObservation(**spec)


@pytest.mark.property
def test_bridge_maps_fields_and_floors_confidence():
    device = AccountNode()
    field = to_field_observation(_device_obs(device, bps=9999))
    assert field.geohash == "u173zq" and field.label == "hydrant"
    assert field.observer == device.address and field.beat == 50
    assert field.target == "wn:03560161"
    # floor: 9999 bps -> 999 milli — NOT confirmed; only true certainty crosses.
    assert field.confidence_milli == 999 and field.requires_confirmation
    confirmed = to_field_observation(_device_obs(device, bps=CONF_FULL))
    assert confirmed.confidence_milli == CONFIDENCE_MILLI_EXACT
    assert not confirmed.requires_confirmation


@pytest.mark.property
def test_fiber_cid_outranks_taxonomy_and_empty_target_is_refused():
    device = AccountNode()
    with_fiber = to_field_observation(_device_obs(device, fiber_cid="bafy-fiber"))
    assert with_fiber.target == "bafy-fiber"
    with pytest.raises(ValueError):
        to_field_observation(_device_obs(device, taxonomy="", fiber_cid=""))


@pytest.mark.property
def test_forged_mesh_envelopes_never_bridge():
    device, attacker = AccountNode(), AccountNode()
    obs = _device_obs(device)
    good = SignedObservation.sign(obs, device.priv, device.pub)
    assert signed_to_field_observation(good).observer == device.address
    forged = SignedObservation(observation=obs, pubkey=attacker.pub,
                               signature=good.signature)
    with pytest.raises(ValueError):
        signed_to_field_observation(forged)


@pytest.mark.property
def test_bridged_observation_flows_end_to_end_into_a_par_mint():
    # Quest detection -> mesh envelope -> bridge -> attest -> bounty -> PAR.
    consumer = AccountNode(genesis_balances={"PLS": 100})
    device = AccountNode()
    signed = SignedObservation.sign(_device_obs(device), device.priv, device.pub)
    field = signed_to_field_observation(signed)
    att = attest_observation(field, device.priv)
    bounty = ObservationBounty(consumer=consumer.address, geohash_prefix="u173",
                               label="hydrant", escrow=100, beat_open=0, beat_close=100)
    treasury = ObservationTreasury()
    issuance = treasury.reward_verified_observation(
        consumer, device, bounty, field, att, 1
    )
    assert issuance is not None and issuance.amount == 50
    assert device.balance(NATIVE) == 100 and device.balance(PAR) == 50
