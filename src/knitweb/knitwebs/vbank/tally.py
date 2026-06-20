"""Deterministic, one-person-one-vote tally for vBank — the public audit-trail half.

The vBank guardrail (``docs/DOMAIN_KNITWEB_INTERFACE.md``) requires a *deterministic tally and
public audit trail*. This computes a result that is byte-for-byte reproducible by any peer from
the same ballot set, regardless of order:

  * **One person, one vote.** Ballots are deduped by ``scope_nullifier``. A voter may re-vote;
    the ballot with the highest ``seq`` wins, ties broken by the smallest ballot CID — both
    fully deterministic and order-independent (no timestamps, no trust in arrival order).
  * **Integer-only result.** Counts are integers; the result is a canonical, content-addressed
    ``vbank-tally`` record with a Merkle ``ballot_root`` over the *included* ballot CIDs, so the
    exact set of counted ballots is publicly auditable and tamper-evident.

This does NOT verify ballot signatures or personhood tickets — that is the gate's job at emit
time (:func:`knitweb.personhood.gate.require_personhood`). The tally operates on records already
admitted to the fabric; it only decides which of them count and produces the auditable result.
"""

from __future__ import annotations

from typing import Iterable, List

from ...core import canonical, crypto

__all__ = ["BALLOT_KIND", "TALLY_KIND", "tally"]

BALLOT_KIND = "vbank-ballot"
TALLY_KIND = "vbank-tally"


def tally(scope: str, poll_id: str, ballots: Iterable[dict]) -> dict:
    """Return the deterministic ``vbank-tally`` record for ``ballots`` in one poll.

    ``ballots`` are ``vbank-ballot`` records (dicts). Every ballot must match ``scope`` and
    ``poll_id`` and carry an integer ``seq`` (the re-vote counter). Raises ``ValueError`` on a
    foreign-kind / wrong-scope / wrong-poll ballot.
    """
    if not scope or not poll_id:
        raise ValueError("scope and poll_id must be non-empty")

    # nullifier -> (seq, cid, choice) of the winning ballot for that voter
    winners: dict[str, tuple] = {}
    for ballot in ballots:
        if ballot.get("kind") != BALLOT_KIND:
            raise ValueError(f"not a {BALLOT_KIND}: {ballot.get('kind')!r}")
        if ballot.get("scope") != scope or ballot.get("poll_id") != poll_id:
            raise ValueError("ballot scope/poll_id does not match the tally")
        nullifier = ballot["scope_nullifier"]
        seq = ballot["seq"]
        choice = ballot["choice"]
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise ValueError("ballot seq must be an int")
        cid = canonical.cid(ballot)
        current = winners.get(nullifier)
        # Highest seq wins; ties broken by the smallest CID (deterministic, order-independent).
        if current is None or seq > current[0] or (seq == current[0] and cid < current[1]):
            winners[nullifier] = (seq, cid, choice)

    counts: dict[int, int] = {}
    for _seq, _cid, choice in winners.values():
        counts[choice] = counts.get(choice, 0) + 1
    results: List[List[int]] = [[choice, counts[choice]] for choice in sorted(counts)]

    included_cids = sorted(cid for _seq, cid, _choice in winners.values())
    ballot_root = crypto.merkle_root(
        [crypto.sha256(cid.encode("utf-8")) for cid in included_cids]
    ).hex()

    record = {
        "kind": TALLY_KIND,
        "scope": scope,
        "poll_id": poll_id,
        "total_voters": len(winners),
        "results": results,
        "ballot_root": ballot_root,
    }
    canonical.encode(record)  # fail fast on any non-canonical content
    return record
