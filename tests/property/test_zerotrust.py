"""P7: Zero-Trust authorization policy.

Acceptance criteria
-------------------
AC1  default deny: low standing fails any action above its tier.
AC2  banned peer is refused every action (reputation wins first).
AC3  sensitive actions (COMPUTE/SETTLE/ADMIN) require a proven identity.
AC4  READ/WRITE allowed for an accepted-but-unproven peer with enough tier.
AC5  tier gating: peer_tier >= required => allowed; below => denied with reason.
AC6  min_tier_override raises (never lowers) the requirement.
AC7  Decision is truthy/falsey and carries the audit fields.
AC8  input validation (peer non-empty, action is Action).
"""

from __future__ import annotations

import pytest

from knitweb.privacy import (
    ACTION_MIN_TIER,
    Action,
    Decision,
    authorize,
)


class _FakeReputation:
    def __init__(self, banned: set[str]):
        self._banned = banned

    def is_banned(self, peer: str) -> bool:
        return peer in self._banned


class _FakeStanding:
    def __init__(self, tiers: dict[str, int]):
        self._tiers = tiers

    def tier(self, peer: str) -> int:
        return self._tiers.get(peer, 0)


def _auth(peer, action, *, banned=(), tiers=None, proven=True, override=None):
    return authorize(
        peer,
        action,
        reputation=_FakeReputation(set(banned)),
        standing=_FakeStanding(tiers or {}),
        identity_proven=proven,
        min_tier_override=override,
    )


# ── AC1 / AC5: tier gating ────────────────────────────────────────────────────
@pytest.mark.property
def test_low_tier_denied_for_high_action():
    d = _auth("p", Action.SETTLE, tiers={"p": 0})
    assert not d.allowed and "below required" in d.reason


@pytest.mark.property
def test_sufficient_tier_allowed():
    d = _auth("p", Action.SETTLE, tiers={"p": 2})
    assert d.allowed and d.reason == "authorized"


@pytest.mark.property
@pytest.mark.parametrize("action", list(Action))
def test_tier_zero_peer_allowed_only_up_to_its_tier(action):
    d = _auth("fresh", action, tiers={"fresh": 0})
    assert d.allowed == (ACTION_MIN_TIER[action] == 0)


# ── AC2: ban wins ─────────────────────────────────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("action", list(Action))
def test_banned_peer_refused_everything(action):
    d = _auth("bad", action, banned={"bad"}, tiers={"bad": 9}, proven=True)
    assert not d.allowed and d.reason == "peer is banned"


# ── AC3: proven identity for sensitive actions ────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("action", [Action.COMPUTE, Action.SETTLE, Action.ADMIN])
def test_sensitive_action_requires_proven_identity(action):
    d = _auth("p", action, tiers={"p": 9}, proven=False)
    assert not d.allowed and "identity not proven" in d.reason


# ── AC4: read/write tolerate unproven identity ────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("action", [Action.READ, Action.WRITE])
def test_read_write_allow_unproven_identity(action):
    d = _auth("p", action, tiers={"p": 0}, proven=False)
    assert d.allowed


# ── AC6: override raises, never lowers ────────────────────────────────────────
@pytest.mark.property
def test_override_raises_requirement():
    # READ normally needs tier 0; override to 2 should deny a tier-1 peer.
    d = _auth("p", Action.READ, tiers={"p": 1}, override=2)
    assert not d.allowed
    assert d.required_tier == 2


@pytest.mark.property
def test_override_cannot_lower_below_action_minimum():
    # SETTLE needs tier 2; override 0 must not weaken it.
    d = _auth("p", Action.SETTLE, tiers={"p": 1}, override=0)
    assert not d.allowed and d.required_tier == 2


# ── AC7: Decision shape ───────────────────────────────────────────────────────
@pytest.mark.property
def test_decision_is_boolean_and_audited():
    ok = _auth("p", Action.WRITE, tiers={"p": 1})
    assert bool(ok) is True
    assert isinstance(ok, Decision)
    assert ok.peer == "p" and ok.action == Action.WRITE
    assert ok.peer_tier == 1 and ok.required_tier == 0
    no = _auth("p", Action.ADMIN, tiers={"p": 0})
    assert bool(no) is False


# ── AC8: validation ───────────────────────────────────────────────────────────
@pytest.mark.property
def test_empty_peer_rejected():
    with pytest.raises(ValueError):
        _auth("", Action.READ)


@pytest.mark.property
def test_non_action_rejected():
    with pytest.raises(TypeError):
        _auth("p", "settle")  # type: ignore[arg-type]


# ── integration with the real standing/reputation primitives ──────────────────
@pytest.mark.property
def test_integrates_with_real_peer_modules():
    from knitweb.p2p.reputation import PeerReputation
    from knitweb.p2p.standing import PeerStanding

    rep = PeerReputation()
    standing = PeerStanding()
    # A fresh peer (tier 0, not banned, proven) may READ but not SETTLE.
    assert authorize(
        "alice", Action.READ, reputation=rep, standing=standing, identity_proven=True
    ).allowed
    assert not authorize(
        "alice", Action.SETTLE, reputation=rep, standing=standing, identity_proven=True
    ).allowed
