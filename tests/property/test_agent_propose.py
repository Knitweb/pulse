"""Proofs for ``agents.propose_knit`` (lens#14 propose-and-gate glue).

These tests pin the three refusal gates (unverified credential, wrong signing
key, abstained reliability verdict) and that a clean proposal produces a
correctly-signed, content-addressable :class:`ProposedKnit` reusing the
existing ``distill``/``fabric.attest`` machinery unmodified.
"""

import pytest

from knitweb.agents import credential as C
from knitweb.agents.propose import ProposeKnitError, propose_knit
from knitweb.core import crypto
from knitweb.pouw.job import VERIFICATION_SPLIT
from knitweb.synaptic.bytecode import Relation


class _FakeCandidateSet:
    """Duck-typed stand-in for ``interpret.retrieve.CandidateSet``."""

    def __init__(self, web_state_cid="bafy-state-1", query="q", subscription=("chem",)):
        self.web_state_cid = web_state_cid
        self.query = query
        self.subscription = subscription


class _FakeSelection:
    """Duck-typed stand-in for ``interpret.distill.Selection``."""

    def __init__(self, relations):
        self.relations = relations


class _Reliability:
    def __init__(self, abstained, confidence=800):
        self.abstained = abstained
        self.confidence = confidence


def _credentialed_agent(role=C.ROLE_CURATOR):
    agent_priv, agent_pub = crypto.generate_keypair()
    issuer_priv, issuer_pub = crypto.generate_keypair()
    cred = C.build(agent_pub=agent_pub, role=role, issuer_pub=issuer_pub, issued_at=1)
    cred = C.sign_by_agent(cred, agent_priv)
    cred = C.sign_by_issuer(cred, issuer_priv)
    return agent_priv, cred


def _selection():
    return _FakeSelection(
        (Relation(subject="H2O", predicate="is-a", obj="molecule"),)
    )


@pytest.mark.property
def test_clean_proposal_is_signed_and_content_addressable():
    agent_priv, cred = _credentialed_agent()
    proposed = propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(False))
    assert proposed.manifest.verification == VERIFICATION_SPLIT
    assert proposed.manifest.originator == crypto.address(cred.agent_pub)
    assert proposed.attestation.author_pub == cred.agent_pub
    assert proposed.attestation.verify(author_field="originator")
    assert proposed.cid == proposed.manifest.cid()
    assert proposed.agent_role == C.ROLE_CURATOR


@pytest.mark.property
def test_unverified_credential_is_refused():
    agent_priv, cred = _credentialed_agent()
    unsigned = cred.__class__(**{**cred.__dict__, "issuer_sig": None})
    with pytest.raises(ProposeKnitError):
        propose_knit(_FakeCandidateSet(), _selection(), unsigned, agent_priv, _Reliability(False))


@pytest.mark.property
def test_wrong_signing_key_is_refused():
    _, cred = _credentialed_agent()
    other_priv, _ = crypto.generate_keypair()
    with pytest.raises(ProposeKnitError):
        propose_knit(_FakeCandidateSet(), _selection(), cred, other_priv, _Reliability(False))


@pytest.mark.property
def test_abstained_reliability_verdict_is_refused():
    agent_priv, cred = _credentialed_agent()
    with pytest.raises(ProposeKnitError):
        propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(True))


@pytest.mark.property
@pytest.mark.parametrize("bad_confidence", [0, -1, -500])
def test_non_positive_confidence_is_refused_even_when_not_abstained(bad_confidence):
    agent_priv, cred = _credentialed_agent()
    with pytest.raises(ProposeKnitError):
        propose_knit(
            _FakeCandidateSet(), _selection(), cred, agent_priv,
            _Reliability(False, confidence=bad_confidence),
        )


@pytest.mark.property
def test_non_int_confidence_is_refused():
    agent_priv, cred = _credentialed_agent()
    with pytest.raises(ProposeKnitError):
        propose_knit(
            _FakeCandidateSet(), _selection(), cred, agent_priv,
            _Reliability(False, confidence="high"),
        )


@pytest.mark.property
def test_empty_selection_is_refused():
    agent_priv, cred = _credentialed_agent()
    empty = _FakeSelection(())
    with pytest.raises(ProposeKnitError):
        propose_knit(_FakeCandidateSet(), empty, cred, agent_priv, _Reliability(False))


@pytest.mark.property
def test_missing_web_state_cid_is_refused():
    agent_priv, cred = _credentialed_agent()
    bad_candidates = _FakeCandidateSet(web_state_cid="")
    with pytest.raises(ProposeKnitError):
        propose_knit(bad_candidates, _selection(), cred, agent_priv, _Reliability(False))


@pytest.mark.property
@pytest.mark.parametrize("role", sorted(C.KNOWN_ROLES))
def test_every_role_can_produce_a_proposal(role):
    agent_priv, cred = _credentialed_agent(role=role)
    proposed = propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(False))
    assert proposed.agent_role == role


@pytest.mark.property
def test_identical_inputs_produce_the_same_manifest_cid():
    agent_priv, cred = _credentialed_agent()
    a = propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(False))
    b = propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(False))
    assert a.cid == b.cid


@pytest.mark.property
def test_different_relations_produce_a_different_bundle_cid():
    agent_priv, cred = _credentialed_agent()
    a = propose_knit(_FakeCandidateSet(), _selection(), cred, agent_priv, _Reliability(False))
    other = _FakeSelection((Relation(subject="NaCl", predicate="is-a", obj="salt"),))
    b = propose_knit(_FakeCandidateSet(), other, cred, agent_priv, _Reliability(False))
    assert a.manifest.bundle_cid != b.manifest.bundle_cid
    assert a.cid != b.cid
