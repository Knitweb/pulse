"""Liquid (delegated) voting for vBank — a voter may delegate their weight to another.

A delegation is a signed record (gated by the delegator's personhood ticket, like a ballot)
naming the delegate by scope nullifier. At tally time, weight flows along delegation chains to
whoever actually voted:

  * **direct vote overrides delegation** — if you cast a ballot, your weight goes to your choice
    regardless of any delegation you also made;
  * **transitive** — A→B→C resolves to C's choice if C voted;
  * **cycle / dead-end abstains** — a chain that loops, or ends at someone who never voted, does
    not count (its weight is dropped).

This composes with fixed-point weights: each participant (anyone who voted or delegated) carries
their weight to the choice their chain resolves to. Authenticity comes from the signed
delegation record (only the delegator can delegate their own nullifier).

Note: this module computes a liquid result; wiring it into ``poll.certify_result`` (so an
authority signs a delegated result) is a thin follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ...core import canonical, crypto
from ...fabric.attest import Attestation, attest
from ...fabric.web import Web
from ...personhood.gate import PersonhoodTicket
from .tally import BALLOT_KIND

__all__ = [
    "DELEGATION_KIND",
    "LIQUID_RESULT_KIND",
    "Delegation",
    "emit_delegation",
    "collect_delegations",
    "delegation_map",
    "resolve_liquid",
    "liquid_results",
]

DELEGATION_KIND = "vbank-delegation"
LIQUID_RESULT_KIND = "vbank-liquid-result"


@dataclass(frozen=True)
class Delegation:
    """One delegation: ``delegator`` hands their voting weight to ``delegate_nullifier``."""

    scope: str
    poll_id: str
    delegator: str            # pls1 pairwise address of the delegator (signs)
    delegator_nullifier: str  # the delegator's scope nullifier
    delegate_nullifier: str   # the nullifier they delegate to
    seq: int = 0              # re-delegation counter (highest seq wins)

    def __post_init__(self) -> None:
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq < 0:
            raise ValueError("delegation seq must be a non-negative int")
        if self.delegator_nullifier == self.delegate_nullifier:
            raise ValueError("cannot delegate to yourself")


def emit_delegation(delegation: Delegation, ticket: PersonhoodTicket, delegator_priv: str) -> Attestation:
    """Build and sign a ``vbank-delegation`` record, gated by the delegator's ticket."""
    if not isinstance(ticket, PersonhoodTicket):
        raise TypeError("a PersonhoodTicket is required to delegate")
    if ticket.scope != delegation.scope:
        raise ValueError("ticket scope does not match the delegation")
    if ticket.scope_nullifier != delegation.delegator_nullifier:
        raise ValueError("ticket nullifier does not authorise this delegation")
    if ticket.holder_pairwise != delegation.delegator:
        raise ValueError("ticket holder does not match the delegator")
    record = {
        "kind": DELEGATION_KIND,
        "scope": delegation.scope,
        "poll_id": delegation.poll_id,
        "actor": delegation.delegator,
        "scope_nullifier": delegation.delegator_nullifier,
        "delegate_nullifier": delegation.delegate_nullifier,
        "seq": delegation.seq,
    }
    if not crypto.is_valid_address(record["actor"]):
        raise ValueError("delegator must be a current PLS address")
    canonical.encode(record)
    return attest(record, delegator_priv, author_field="actor")


def collect_delegations(web: Web, scope: str, poll_id: str) -> List[dict]:
    """Read every ``vbank-delegation`` record for ``(scope, poll_id)`` from a woven Web."""
    found = [
        record
        for record in web.nodes.values()
        if record.get("kind") == DELEGATION_KIND
        and record.get("scope") == scope
        and record.get("poll_id") == poll_id
    ]
    found.sort(key=canonical.cid)
    return found


def _direct_choices(ballots: List[dict]) -> Dict[str, int]:
    """Deduped {scope_nullifier: choice} from ballot records (highest seq, tie smallest CID)."""
    winners: Dict[str, tuple] = {}
    for ballot in ballots:
        if ballot.get("kind") != BALLOT_KIND:
            raise ValueError(f"not a {BALLOT_KIND}: {ballot.get('kind')!r}")
        nullifier = ballot["scope_nullifier"]
        seq = ballot["seq"]
        cid = canonical.cid(ballot)
        current = winners.get(nullifier)
        if current is None or seq > current[0] or (seq == current[0] and cid < current[1]):
            winners[nullifier] = (seq, cid, ballot["choice"])
    return {nf: choice for nf, (_seq, _cid, choice) in winners.items()}


def delegation_map(delegations: List[dict]) -> Dict[str, str]:
    """Deduped {delegator_nullifier: delegate_nullifier} (highest seq, tie smallest CID)."""
    winners: Dict[str, tuple] = {}
    for record in delegations:
        if record.get("kind") != DELEGATION_KIND:
            raise ValueError(f"not a {DELEGATION_KIND}: {record.get('kind')!r}")
        delegator = record["scope_nullifier"]
        seq = record["seq"]
        cid = canonical.cid(record)
        current = winners.get(delegator)
        if current is None or seq > current[0] or (seq == current[0] and cid < current[1]):
            winners[delegator] = (seq, cid, record["delegate_nullifier"])
    return {nf: target for nf, (_seq, _cid, target) in winners.items()}


def resolve_liquid(direct_choices: Dict[str, int], delegations: Dict[str, str],
                   weights: Dict[str, int] | None = None) -> Dict[int, int]:
    """Resolve liquid-democracy weight flow to ``{choice: total_weight}``.

    Each participant (anyone who voted or delegated) carries their weight to the choice their
    delegation chain resolves to; voting directly wins; cycles/dead-ends abstain.
    """
    participants = set(direct_choices) | set(delegations)
    counts: Dict[int, int] = {}
    for participant in participants:
        if weights is None:
            weight = 1
        else:
            weight = weights.get(participant, 0)
            if not isinstance(weight, int) or isinstance(weight, bool) or weight < 0:
                raise ValueError("weights must be non-negative integers")
        if weight == 0:
            continue
        # follow the chain to a direct voter (with cycle detection)
        seen = set()
        cursor = participant
        choice = None
        while cursor is not None and cursor not in seen:
            if cursor in direct_choices:
                choice = direct_choices[cursor]
                break
            seen.add(cursor)
            cursor = delegations.get(cursor)
        if choice is not None:
            counts[choice] = counts.get(choice, 0) + weight
    return counts


def liquid_results(scope: str, poll_id: str, ballots: List[dict], delegations: List[dict],
                   weights: Dict[str, int] | None = None) -> dict:
    """Compute a deterministic liquid-voting result record from ballots + delegations."""
    direct = _direct_choices(ballots)
    deleg = delegation_map(delegations)
    counts = resolve_liquid(direct, deleg, weights)
    results = [[choice, counts[choice]] for choice in sorted(counts)]
    record = {
        "kind": LIQUID_RESULT_KIND,
        "scope": scope,
        "poll_id": poll_id,
        "results": results,
        "direct_voters": len(direct),
        "delegations": len(deleg),
        "total_weight": sum(counts.values()),
    }
    canonical.encode(record)
    return record
