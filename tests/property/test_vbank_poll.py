"""Proofs for the vBank poll lifecycle: signed definitions + authority-certified results."""

import pytest

from knitweb.core import canonical, crypto
from knitweb.fabric.attest import attest, verify_record
from knitweb.fabric.web import Web
from knitweb.knitwebs.vbank import (
    BALLOT_KIND,
    POLL_KIND,
    RESULT_KIND,
    Poll,
    VbankPoll,
)

SCOPE = "vbank"
POLL_ID = "referendum-1"


def _authority():
    priv, _ = crypto.generate_keypair()
    return priv, VbankPoll(priv, SCOPE)


def _nf(i: int) -> str:
    return crypto.sha256(f"voter-{i}".encode()).hex()


def _ballot(nullifier: str, choice: int, seq: int = 0, cast_at: int = 1500) -> dict:
    # default cast_at 1500 is inside the test poll window [1000, 2000)
    return {
        "kind": BALLOT_KIND, "scope": SCOPE, "poll_id": POLL_ID, "choice": choice,
        "actor": "pls1" + nullifier[:16], "scope_nullifier": nullifier, "seq": seq,
        "cast_at": cast_at,
    }


def _poll(authority: VbankPoll, options: int = 3):
    return authority.define(Poll(scope=SCOPE, poll_id=POLL_ID, options=options,
                                 opens_at=1000, closes_at=2000))


@pytest.mark.property
@pytest.mark.parametrize("bad", [
    {"options": 1, "opens_at": 0, "closes_at": 10},   # too few options
    {"options": 3, "opens_at": 10, "closes_at": 10},  # window not positive
    {"options": 3, "opens_at": 10, "closes_at": 5},   # closes before opens
])
def test_invalid_poll_definitions_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        Poll(scope=SCOPE, poll_id=POLL_ID, **bad)


@pytest.mark.property
def test_poll_definition_is_signed_and_well_formed():
    priv, authority = _authority()
    att = _poll(authority)
    assert att.verify(author_field="authority")
    assert att.record["kind"] == POLL_KIND
    assert att.record["options"] == 3
    assert att.record["authority"] == authority.authority


@pytest.mark.property
def test_certified_result_counts_and_links_to_definition():
    priv, authority = _authority()
    poll_att = _poll(authority, options=3)
    ballots = [_ballot(_nf(0), 0), _ballot(_nf(1), 2), _ballot(_nf(2), 0)]
    res = authority.certify_result(poll_att.record, ballots)
    assert res.verify(author_field="authority")
    assert res.record["kind"] == RESULT_KIND
    assert res.record["total_voters"] == 3
    assert res.record["results"] == [[0, 2], [2, 1]]
    assert res.record["poll_cid"] == canonical.cid(poll_att.record)


@pytest.mark.property
def test_choice_out_of_range_is_rejected():
    priv, authority = _authority()
    poll_att = _poll(authority, options=3)
    with pytest.raises(ValueError):
        authority.certify_result(poll_att.record, [_ballot(_nf(0), 3)])  # 3 not in 0..2


@pytest.mark.property
def test_only_defining_authority_can_certify():
    _, authority_a = _authority()
    _, authority_b = _authority()
    poll_att = _poll(authority_a, options=2)
    with pytest.raises(ValueError):
        authority_b.certify_result(poll_att.record, [_ballot(_nf(0), 1)])


@pytest.mark.property
def test_result_is_deterministic_and_order_independent():
    priv, authority = _authority()
    poll_att = _poll(authority, options=3)
    ballots = [_ballot(_nf(i), i % 3) for i in range(6)]
    a = authority.certify_result(poll_att.record, ballots)
    b = authority.certify_result(poll_att.record, list(reversed(ballots)))
    assert a.cid == b.cid  # content id is independent of ballot order


@pytest.mark.property
def test_ballots_outside_voting_window_are_excluded():
    priv, authority = _authority()
    poll_att = _poll(authority, options=3)  # window [1000, 2000)
    ballots = [
        _ballot(_nf(0), 0, cast_at=1500),   # in window  -> counts
        _ballot(_nf(1), 1, cast_at=999),    # before opens_at -> excluded
        _ballot(_nf(2), 2, cast_at=2000),   # == closes_at (exclusive) -> excluded
        _ballot(_nf(3), 0, cast_at=2500),   # after close -> excluded
    ]
    res = authority.certify_result(poll_att.record, ballots)
    assert res.record["total_voters"] == 1
    assert res.record["results"] == [[0, 1]]


@pytest.mark.property
def test_out_of_window_revote_does_not_override_in_window_vote():
    priv, authority = _authority()
    poll_att = _poll(authority, options=3)
    # same voter: in-window seq0 choice0, then a LATER (higher-seq) but out-of-window choice2
    ballots = [
        _ballot(_nf(0), 0, seq=0, cast_at=1500),
        _ballot(_nf(0), 2, seq=1, cast_at=2500),  # higher seq but outside window -> ignored
    ]
    res = authority.certify_result(poll_att.record, ballots)
    assert res.record["total_voters"] == 1
    assert res.record["results"] == [[0, 1]]  # the in-window choice 0 stands


@pytest.mark.property
def test_weave_result_into_web():
    priv, authority = _authority()
    poll_att = _poll(authority, options=2)
    web = Web()
    cid, att = authority.weave_result(poll_att.record, [_ballot(_nf(0), 1), _ballot(_nf(1), 0)], web)
    assert att.verify(author_field="authority")
    assert cid == att.cid
