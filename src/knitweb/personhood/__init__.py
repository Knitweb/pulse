"""Personhood — the sybil-resistance foundation for Votebank (voting + crowdfunding).

This layer (L3.5, between the L3 fabric and the L5 domain knitwebs) turns an off-fabric
eIDAS / EUDI-Wallet personhood check into a **revocable, privacy-preserving proof** that
voting and crowdfunding consume as their one-person-one-scope gate. It stores *only* a
proof — never PII — so the privacy model is built in from day one rather than retrofitted
onto an append-only fabric (which is impossible).

Dependency rule: domain apps import ``personhood``; ``personhood`` never imports an app.
It depends only on ``core``, ``fabric.attest``/``fabric.feed``, and ``knitwebs.base``
constants.
"""

from __future__ import annotations

from . import anchor, records
from .anchor import CoSignedAnchor, co_sign_anchor
from .records import (
    ANCHOR_KIND,
    CRED_TYPE,
    PersonhoodSchemaError,
    REVOKE_KIND,
    assert_personhood_record_shape,
    build_anchor_record,
    build_revoke_record,
)

__all__ = [
    "records",
    "anchor",
    "PersonhoodSchemaError",
    "ANCHOR_KIND",
    "REVOKE_KIND",
    "CRED_TYPE",
    "assert_personhood_record_shape",
    "build_anchor_record",
    "build_revoke_record",
    "CoSignedAnchor",
    "co_sign_anchor",
]
