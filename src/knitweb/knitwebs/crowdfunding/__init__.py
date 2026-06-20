"""Crowdfunding (minimal stub) — a pledge requires a personhood ticket, but allows repeats.

The second consumer of the personhood foundation, proving the same revocable proof anchors
**both** voting and crowdfunding (the owner's mandate). It reuses the identical gate as
``votebank``: ``CrowdfundingKnitweb.emit`` refuses a pledge unless handed a
:class:`~knitweb.personhood.gate.PersonhoodTicket` matching the campaign scope, pledger, and
nullifier.

The deliberate contrast with voting: a vote is **deduped** on the nullifier (one person, one
vote), but a pledge is **not** — the same verified person may pledge repeatedly in a campaign.
The nullifier is still carried so the campaign can prove every pledge came from a distinct
verified EU natural person (the anti-sybil / light-KYC property required by EU crowdfunding
rules) and aggregate per-person totals — all without any identity on the fabric.

Scope note: this models a **donation/reward** pledge (an integer ``amount`` in PLS-wei, no
equity or return). Investment/lending flows need regulatory review (Reg. (EU) 2020/1503) and
are out of scope for this stub.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core import canonical, crypto
from ...fabric.attest import Attestation, attest
from ...fabric.web import Web
from ...personhood.gate import PersonhoodTicket

__all__ = ["Pledge", "CrowdfundingKnitweb"]


@dataclass(frozen=True)
class Pledge:
    """One donation/reward pledge of an integer ``amount`` (PLS-wei) to a campaign."""

    scope: str            # campaign id
    amount: int           # PLS-wei, integer-only, strictly positive
    pledger: str          # pls1 address of the holder's pairwise key
    scope_nullifier: str  # which verified person (no identity); NOT deduped for pledges

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise TypeError("pledge amount must be an int (PLS-wei)")
        if self.amount <= 0:
            raise ValueError("pledge amount must be strictly positive")


class CrowdfundingKnitweb:
    """Emits signed pledges — but only against a valid personhood ticket."""

    KIND = "crowdfunding-pledge"

    def __init__(self, scope: str) -> None:
        if not scope:
            raise ValueError("scope must be a non-empty string")
        self.scope = scope

    def _check_ticket(self, pledge: Pledge, ticket: PersonhoodTicket) -> None:
        if pledge.scope != self.scope:
            raise ValueError(f"pledge scope {pledge.scope!r} != knitweb scope {self.scope!r}")
        if not isinstance(ticket, PersonhoodTicket):
            raise TypeError("a PersonhoodTicket is required to pledge")
        if ticket.scope != pledge.scope:
            raise ValueError("ticket scope does not match the pledge")
        if ticket.scope_nullifier != pledge.scope_nullifier:
            raise ValueError("ticket nullifier does not authorise this pledge")
        if ticket.holder_pairwise != pledge.pledger:
            raise ValueError("ticket holder does not match the pledger")

    def to_record(self, pledge: Pledge, ticket: PersonhoodTicket) -> dict:
        """Build the integer-only pledge record (gated on a matching ticket)."""
        self._check_ticket(pledge, ticket)
        record = {
            "kind": self.KIND,
            "scope": pledge.scope,
            "amount": pledge.amount,
            "actor": pledge.pledger,
            "scope_nullifier": pledge.scope_nullifier,
        }
        # Fixed key set (no caller-supplied keys); the load-bearing checks are a valid PLS
        # author address + canonical encodability (rejects floats). Self-contained on core.
        if not crypto.is_valid_address(record["actor"]):
            raise ValueError("pledger must be a current PLS address")
        canonical.encode(record)
        return record

    def emit(self, pledge: Pledge, ticket: PersonhoodTicket, pledger_priv: str) -> Attestation:
        """Validate the ticket, then sign the pledge with the holder's pairwise key."""
        record = self.to_record(pledge, ticket)
        return attest(record, pledger_priv, author_field="actor")

    def weave(
        self, pledge: Pledge, ticket: PersonhoodTicket, pledger_priv: str, web: Web
    ) -> tuple[str, Attestation]:
        """Emit a gated pledge and weave it into ``web``; return (cid, attestation)."""
        att = self.emit(pledge, ticket, pledger_priv)
        return web.weave(att.record), att
