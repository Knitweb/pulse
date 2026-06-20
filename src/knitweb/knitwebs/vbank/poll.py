"""vBank poll lifecycle — authority-defined polls and signed, auditable results.

A raw :func:`knitweb.knitwebs.vbank.tally.tally` is anonymous and unbounded: anyone could
publish a "result" and a ballot could carry any integer choice. This adds the two pieces a
real poll needs, both content-addressed and signed:

  * **`vbank-poll`** — the poll definition: the option count and the voting window, signed by
    the poll **authority**. It declares what a valid ballot looks like (``choice`` in
    ``0..options-1``) and when voting is open.
  * **`vbank-result`** — the certified outcome: the deterministic :func:`tally` over a ballot
    set, embedded with a link (``poll_cid``) to the definition and signed by the same
    authority. So the result is attributable and tamper-evident, and the included-ballot
    Merkle ``ballot_root`` keeps it publicly auditable.

Only the authority that defined a poll can certify its result (the signing key must match the
definition's ``authority``). Choices are range-checked against the declared option count.

Note (deferred): per-ballot voting-window enforcement needs a cast timestamp on the ballot;
the window lives in the definition now, and enforcing it at tally time is a later increment.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core import canonical, crypto
from ...fabric.attest import Attestation, attest
from ...fabric.web import Web
from .tally import tally

__all__ = ["POLL_KIND", "RESULT_KIND", "Poll", "VbankPoll"]

POLL_KIND = "vbank-poll"
RESULT_KIND = "vbank-result"


@dataclass(frozen=True)
class Poll:
    """A poll definition: an option count and a voting window for one ``poll_id``."""

    scope: str
    poll_id: str
    options: int     # valid choices are the integers 0 .. options-1
    opens_at: int    # epoch seconds (inclusive)
    closes_at: int   # epoch seconds (exclusive)

    def __post_init__(self) -> None:
        for name, value in (("options", self.options), ("opens_at", self.opens_at),
                            ("closes_at", self.closes_at)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"poll {name} must be an int")
        if self.options < 2:
            raise ValueError("a poll needs at least 2 options")
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        if not self.poll_id:
            raise ValueError("poll_id must be non-empty")


class VbankPoll:
    """A poll authority: defines polls and certifies their deterministic results."""

    def __init__(self, authority_priv: str, scope: str) -> None:
        if not scope:
            raise ValueError("scope must be a non-empty string")
        self._priv = authority_priv
        self.authority_pub = crypto.public_from_private(authority_priv)
        self.authority = crypto.address(self.authority_pub)
        self.scope = scope

    def define(self, poll: Poll) -> Attestation:
        """Build and sign a ``vbank-poll`` definition record."""
        if poll.scope != self.scope:
            raise ValueError(f"poll scope {poll.scope!r} != authority scope {self.scope!r}")
        record = {
            "kind": POLL_KIND,
            "scope": poll.scope,
            "poll_id": poll.poll_id,
            "options": poll.options,
            "opens_at": poll.opens_at,
            "closes_at": poll.closes_at,
            "authority": self.authority,
        }
        canonical.encode(record)
        return attest(record, self._priv, author_field="authority")

    def certify_result(self, poll_record: dict, ballots: list[dict]) -> Attestation:
        """Validate ballots against the definition, tally them, and sign the result.

        ``poll_record`` is a ``vbank-poll`` definition this authority signed. Each ballot's
        ``choice`` must be in ``0..options-1``. Raises ``ValueError`` otherwise.
        """
        if poll_record.get("kind") != POLL_KIND:
            raise ValueError(f"not a {POLL_KIND}: {poll_record.get('kind')!r}")
        if poll_record.get("authority") != self.authority:
            raise ValueError("only the defining authority may certify this poll's result")
        scope = poll_record["scope"]
        poll_id = poll_record["poll_id"]
        options = poll_record["options"]
        opens_at = poll_record["opens_at"]
        closes_at = poll_record["closes_at"]

        # Only ballots cast inside the voting window count. Out-of-window ballots are
        # excluded (the fabric is append-only, so we cannot stop them being emitted — only
        # decline to count them); in-window ballots have their choice range-checked.
        in_window = []
        for ballot in ballots:
            cast_at = ballot.get("cast_at")
            if not isinstance(cast_at, int) or isinstance(cast_at, bool):
                raise ValueError("ballot cast_at must be an int")
            if not (opens_at <= cast_at < closes_at):
                continue
            choice = ballot.get("choice")
            if not isinstance(choice, int) or isinstance(choice, bool) or not (0 <= choice < options):
                raise ValueError(f"ballot choice {choice!r} out of range 0..{options - 1}")
            in_window.append(ballot)

        counted = tally(scope, poll_id, in_window)
        record = {
            "kind": RESULT_KIND,
            "scope": scope,
            "poll_id": poll_id,
            "poll_cid": canonical.cid(poll_record),
            "authority": self.authority,
            "total_voters": counted["total_voters"],
            "results": counted["results"],
            "ballot_root": counted["ballot_root"],
        }
        canonical.encode(record)
        return attest(record, self._priv, author_field="authority")

    def weave_result(self, poll_record: dict, ballots: list[dict], web: Web) -> tuple[str, Attestation]:
        """Certify and weave a result into ``web``; return (cid, attestation)."""
        att = self.certify_result(poll_record, ballots)
        return web.weave(att.record), att
