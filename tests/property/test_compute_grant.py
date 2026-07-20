"""Proofs for the 49% GPU wallet consent: bounded, scoped, revocable, verified.

The invariants: no grant ever yields a majority of a device (protocol cap
4900 bps), a scheduler can only assign inside consent (clamp), consent dies at
expiry or on a revocation signed by the *same* device key, and a registry fed
hostile envelopes admits nothing.
"""

import pytest

from knitweb.ledger.node import AccountNode
from knitweb.pouw.compute_grant import (
    ALLOWED_SCOPES,
    MAX_GRANT_BPS,
    ComputeGrant,
    ComputeRevocation,
    GrantRegistry,
    attest_grant,
    attest_revocation,
)


def _grant(device: AccountNode, **over) -> ComputeGrant:
    spec = dict(device=device.address, max_gpu_bps=4900,
                scopes=("vision", "pq"), beat_granted=0, beat_expiry=100)
    spec.update(over)
    return ComputeGrant(**spec)


@pytest.mark.property
def test_majority_grants_are_invalid_by_protocol():
    device = AccountNode()
    assert _grant(device).max_gpu_bps == MAX_GRANT_BPS  # 4900 itself is legal
    with pytest.raises(ValueError):
        _grant(device, max_gpu_bps=4901)   # 49.01% would be a majority path
    with pytest.raises(ValueError):
        _grant(device, max_gpu_bps=0)      # an empty grant is no grant
    with pytest.raises(TypeError):
        _grant(device, max_gpu_bps=True)


@pytest.mark.property
def test_scope_and_window_validation():
    device = AccountNode()
    with pytest.raises(ValueError):
        _grant(device, scopes=("mining",))
    with pytest.raises(TypeError):
        _grant(device, scopes=())
    with pytest.raises(ValueError):
        _grant(device, scopes=("pq", "pq"))
    with pytest.raises(ValueError):
        _grant(device, beat_expiry=-1)
    assert set(ALLOWED_SCOPES) == {"vision", "pq", "chem-validate"}


@pytest.mark.property
def test_registry_clamps_assignment_to_consent():
    device = AccountNode()
    reg = GrantRegistry()
    grant = _grant(device, max_gpu_bps=3000)
    assert reg.admit(grant, attest_grant(grant, device.priv))

    assert reg.allowed_bps(device.address, 50, "vision") == 3000
    assert reg.clamp(device.address, 50, "vision", 10_000) == 3000  # consent wins
    assert reg.clamp(device.address, 50, "vision", 1_000) == 1_000  # request wins
    assert reg.clamp(device.address, 50, "chem-validate", 1_000) == 0  # unscoped
    assert reg.clamp(device.address, 101, "vision", 1_000) == 0       # expired
    assert reg.clamp(AccountNode().address, 50, "vision", 1_000) == 0  # stranger


@pytest.mark.property
def test_grants_do_not_stack_past_the_protocol_cap():
    device = AccountNode()
    reg = GrantRegistry()
    for bps in (2000, 4900):
        g = _grant(device, max_gpu_bps=bps)
        assert reg.admit(g, attest_grant(g, device.priv))
    # Two live grants: the answer is the largest single one, never their sum.
    assert reg.allowed_bps(device.address, 10, "pq") == 4900


@pytest.mark.property
def test_revocation_zeroes_consent_from_its_beat():
    device = AccountNode()
    reg = GrantRegistry()
    grant = _grant(device)
    assert reg.admit(grant, attest_grant(grant, device.priv))
    rev = ComputeRevocation(device=device.address, grant_cid=grant.cid, beat=60)
    assert reg.revoke(rev, attest_revocation(rev, device.priv))

    assert reg.allowed_bps(device.address, 59, "vision") == 4900  # before: intact
    assert reg.allowed_bps(device.address, 60, "vision") == 0     # from beat on: gone
    assert reg.allowed_bps(device.address, 99, "pq") == 0


@pytest.mark.property
def test_only_the_granting_key_can_revoke():
    device, attacker = AccountNode(), AccountNode()
    reg = GrantRegistry()
    grant = _grant(device)
    assert reg.admit(grant, attest_grant(grant, device.priv))

    hostile = ComputeRevocation(device=attacker.address, grant_cid=grant.cid, beat=0)
    assert not reg.revoke(hostile, attest_revocation(hostile, attacker.priv))
    assert reg.allowed_bps(device.address, 10, "vision") == 4900  # untouched


@pytest.mark.property
def test_registry_rejects_tampered_envelopes():
    device = AccountNode()
    reg = GrantRegistry()
    grant = _grant(device, max_gpu_bps=1000)
    att = attest_grant(grant, device.priv)

    # Envelope over a different (greedier) record than the claimed grant.
    greedy = _grant(device, max_gpu_bps=4900)
    assert not reg.admit(greedy, att)
    # Signature by a key that does not own the device address.
    other = AccountNode()
    forged = type(att)(record=att.record, author_pub=other.pub, sig=att.sig)
    assert not reg.admit(grant, forged)
    assert reg.allowed_bps(device.address, 10, "vision") == 0  # nothing admitted
