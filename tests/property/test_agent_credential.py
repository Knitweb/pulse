"""Proofs for the agent-credential schema (lens#14 identity requirement).

An agent credential is co-signed like a Knit (two named pubkeys, verified
directly against the signed bytes) rather than attested like a fabric item
(which binds an address field) — see the module docstring in
``knitweb.agents.credential`` for why. These tests pin: the deny-by-default
whitelist, that both signers must actually control the keys they claim, that
an agent cannot self-issue its own role grant, and that the record is
canonical-CBOR clean and content-addressable.
"""

import pytest

from knitweb.core import canonical, crypto
from knitweb.agents import credential as C


def _issued():
    """Return (agent_priv, issuer_priv, unsigned credential) for a well-formed grant."""
    agent_priv, agent_pub = crypto.generate_keypair()
    issuer_priv, issuer_pub = crypto.generate_keypair()
    cred = C.build(
        agent_pub=agent_pub,
        role=C.ROLE_CURATOR,
        issuer_pub=issuer_pub,
        issued_at=1_000,
    )
    return agent_priv, issuer_priv, cred


@pytest.mark.property
def test_fully_signed_credential_verifies():
    agent_priv, issuer_priv, cred = _issued()
    cred = C.sign_by_agent(cred, agent_priv)
    cred = C.sign_by_issuer(cred, issuer_priv)
    assert cred.is_fully_signed()
    assert cred.verify()
    # signatures live outside the content id
    assert cred.cid == canonical.cid(cred.to_record())
    assert cred.role_name == "curator"


@pytest.mark.property
def test_unsigned_or_half_signed_credential_does_not_verify():
    _, _, cred = _issued()
    assert not cred.verify()
    agent_priv, _, cred2 = _issued()
    cred2 = C.sign_by_agent(cred2, agent_priv)
    assert not cred2.is_fully_signed()
    assert not cred2.verify()


@pytest.mark.property
def test_agent_cannot_sign_with_a_key_it_does_not_control():
    _, _, cred = _issued()
    other_priv, _ = crypto.generate_keypair()
    with pytest.raises(C.AgentCredentialError):
        C.sign_by_agent(cred, other_priv)


@pytest.mark.property
def test_issuer_cannot_sign_with_a_key_it_does_not_control():
    _, _, cred = _issued()
    other_priv, _ = crypto.generate_keypair()
    with pytest.raises(C.AgentCredentialError):
        C.sign_by_issuer(cred, other_priv)


@pytest.mark.property
def test_agent_cannot_self_issue_its_own_credential():
    priv, pub = crypto.generate_keypair()
    cred = C.build(agent_pub=pub, role=C.ROLE_TUTOR, issuer_pub=pub, issued_at=1)
    cred = C.sign_by_agent(cred, priv)
    cred = C.sign_by_issuer(cred, priv)
    # Same key signed both roles: the same-key-both-roles guard must reject this,
    # even though each individual signature is technically valid.
    assert not cred.verify()


@pytest.mark.property
def test_swapped_signatures_do_not_verify():
    agent_priv, issuer_priv, cred = _issued()
    # Deliberately swap: agent signs into issuer_sig's slot and vice versa.
    swapped = cred.__class__(
        **{**cred.__dict__, "agent_sig": crypto.sign(issuer_priv, cred.signing_bytes)}
    )
    swapped = swapped.__class__(
        **{**swapped.__dict__, "issuer_sig": crypto.sign(agent_priv, cred.signing_bytes)}
    )
    assert not swapped.verify()


@pytest.mark.property
@pytest.mark.parametrize("role", sorted(C.KNOWN_ROLES))
def test_all_known_roles_are_buildable(role):
    _, pub = crypto.generate_keypair()
    _, issuer_pub = crypto.generate_keypair()
    cred = C.build(agent_pub=pub, role=role, issuer_pub=issuer_pub, issued_at=0)
    assert cred.role == role


@pytest.mark.property
def test_unknown_role_rejected():
    _, pub = crypto.generate_keypair()
    _, issuer_pub = crypto.generate_keypair()
    with pytest.raises(C.AgentCredentialError):
        C.build(agent_pub=pub, role=99, issuer_pub=issuer_pub, issued_at=0)


@pytest.mark.property
def test_shape_rejects_disallowed_field():
    _, _, cred = _issued()
    record = cred.to_record()
    record["full_name"] = "leaked"
    with pytest.raises(C.AgentCredentialError):
        C.assert_credential_shape(record)


@pytest.mark.property
def test_shape_rejects_missing_field():
    _, _, cred = _issued()
    record = cred.to_record()
    del record["issued_at"]
    with pytest.raises(C.AgentCredentialError):
        C.assert_credential_shape(record)


@pytest.mark.property
def test_shape_rejects_malformed_pubkey():
    _, _, cred = _issued()
    record = cred.to_record()
    record["agent_pub"] = "not-hex"
    with pytest.raises(C.AgentCredentialError):
        C.assert_credential_shape(record)


@pytest.mark.property
def test_record_is_canonical_and_content_bound():
    agent_priv, issuer_priv, cred = _issued()
    encoded = canonical.encode(cred.to_record())
    assert isinstance(encoded, (bytes, bytearray))
    same_role = C.build(
        agent_pub=cred.agent_pub, role=cred.role, issuer_pub=cred.issuer_pub, issued_at=cred.issued_at
    )
    assert same_role.cid == cred.cid
    different = C.build(
        agent_pub=cred.agent_pub, role=C.ROLE_ARBITER, issuer_pub=cred.issuer_pub, issued_at=cred.issued_at
    )
    assert different.cid != cred.cid
