"""Zero-Trust authorization policy for the Knitweb.

"Never trust, always verify."  There is no ambient or session-level trust: every
action is authorized explicitly, and each :func:`authorize` call re-checks all
trust axes *now* against live state.  Nothing is cached as "already trusted".

This module does **not** invent new crypto — it composes the primitives the
engine already enforces into one auditable decision:

- **Identity** — was the peer's identity *proven* (not merely accepted)?  Comes
  from :class:`knitweb.p2p.peer_identity_gate.GateVerdict.proven`.
- **Reputation** — is the peer banned for misbehaviour?
  (:class:`knitweb.p2p.reputation.PeerReputation`)
- **Standing** — does the peer's earned tier meet the action's minimum?
  (:class:`knitweb.p2p.standing.PeerStanding`)

Actions are ordered by the trust they demand.  More sensitive actions require a
proven identity and a higher standing tier; reads are permissive, settlement and
admin are strict.  The default is **deny**.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol


class Action(IntEnum):
    """Capabilities, ordered by the trust they require (low -> high)."""

    READ = 0       # observe knits / fabric state
    WRITE = 1      # weave a knit / contribute data
    COMPUTE = 2    # accept a PoUW / interpret job
    SETTLE = 3     # move value / settle escrow
    ADMIN = 4      # privileged operations


# Minimum standing tier required per action.
ACTION_MIN_TIER: dict[Action, int] = {
    Action.READ: 0,
    Action.WRITE: 0,
    Action.COMPUTE: 1,
    Action.SETTLE: 2,
    Action.ADMIN: 3,
}

# Actions that require a *proven* identity (a merely accepted/unproven peer is
# refused).  Reads and writes tolerate an accepted identity; value-bearing and
# privileged actions do not.
ACTIONS_REQUIRING_PROVEN_ID: frozenset[Action] = frozenset(
    {Action.COMPUTE, Action.SETTLE, Action.ADMIN}
)


class _Reputation(Protocol):
    def is_banned(self, peer: str) -> bool: ...


class _Standing(Protocol):
    def tier(self, peer: str) -> int: ...


@dataclass(frozen=True)
class Decision:
    """The outcome of an authorization check."""

    allowed: bool
    peer: str
    action: Action
    reason: str
    required_tier: int
    peer_tier: int

    def __bool__(self) -> bool:
        return self.allowed


def authorize(
    peer: str,
    action: Action,
    *,
    reputation: _Reputation,
    standing: _Standing,
    identity_proven: bool,
    min_tier_override: int | None = None,
) -> Decision:
    """Authorize *peer* for *action* under the zero-trust policy.

    Checks, in order (first failure wins, default deny):

    1. reputation ban,
    2. proven-identity requirement for the action,
    3. standing-tier requirement.

    ``min_tier_override`` raises (never lowers) the required tier for this call.
    """
    if not isinstance(peer, str) or not peer:
        raise ValueError("peer must be a non-empty string")
    if not isinstance(action, Action):
        raise TypeError("action must be an Action")
    base_required = ACTION_MIN_TIER[action]
    required = base_required if min_tier_override is None else max(base_required, min_tier_override)

    peer_tier = standing.tier(peer)

    if reputation.is_banned(peer):
        return Decision(False, peer, action, "peer is banned", required, peer_tier)

    if action in ACTIONS_REQUIRING_PROVEN_ID and not identity_proven:
        return Decision(
            False, peer, action, "identity not proven for sensitive action", required, peer_tier
        )

    if peer_tier < required:
        return Decision(
            False,
            peer,
            action,
            f"standing tier {peer_tier} below required {required}",
            required,
            peer_tier,
        )

    return Decision(True, peer, action, "authorized", required, peer_tier)
