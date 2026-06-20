"""Co-signed personhood anchor — verifier RP *and* holder pairwise key both sign.

A ``personhood-anchor`` makes two distinct claims that need two distinct signers:

  * the **verifier** (an eIDAS Relying Party node) attests "I checked a valid, unique
    EU natural person via an accepted issuer", and
  * the **holder** attests, with their per-scope *pairwise* key, "I consent to this
    anchor binding my scope identity" — proving a human was in the loop.

Requiring both from day one is irreversible by design: a single-signed anchor could
never be upgraded to prove holder consent without re-anchoring everyone. Both
signatures are kept *outside* the record (each is a :class:`fabric.attest.Attestation`
over the same canonical bytes), so the anchor's CID stays a pure content hash.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import canonical
from ..fabric.attest import Attestation, attest
from ..fabric.web import Web
from . import records

__all__ = ["CoSignedAnchor", "co_sign_anchor"]


@dataclass(frozen=True)
class CoSignedAnchor:
    """A ``personhood-anchor`` record with both the verifier and holder signatures."""

    record: dict
    verifier_att: Attestation   # author_field="verifier"
    holder_att: Attestation     # author_field="holder_pairwise"

    @property
    def cid(self) -> str:
        """Content id of the record (signatures are not part of the identity)."""
        return canonical.cid(self.record)

    def verify(self) -> bool:
        """True iff both signatures are valid over the *same* record."""
        if self.verifier_att.record != self.record:
            return False
        if self.holder_att.record != self.record:
            return False
        return self.verifier_att.verify("verifier") and self.holder_att.verify(
            "holder_pairwise"
        )

    def weave(self, web: Web) -> str:
        """Weave the (already co-signed, shape-checked) anchor into ``web``; return CID."""
        return web.weave(self.record)


def co_sign_anchor(
    record: dict,
    verifier_priv: str,
    holder_pairwise_priv: str,
) -> CoSignedAnchor:
    """Validate the anchor shape, then co-sign it with the verifier and holder keys.

    ``fabric.attest.attest`` enforces that ``record['verifier']`` and
    ``record['holder_pairwise']`` each derive from the supplied signing key, so a
    party can only co-sign an anchor it actually claims.
    """
    records.assert_personhood_record_shape(record, kind=records.ANCHOR_KIND)
    verifier_att = attest(record, verifier_priv, author_field="verifier")
    holder_att = attest(record, holder_pairwise_priv, author_field="holder_pairwise")
    return CoSignedAnchor(
        record=record, verifier_att=verifier_att, holder_att=holder_att
    )
