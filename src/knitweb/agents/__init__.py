"""Agents — LLM/NPC participants as first-class Knitweb peers (lens#14).

Scoped strictly to what is agent-specific: identity (:mod:`.credential`) and
the propose-and-gate glue (:mod:`.propose`) that turns a Lens-computed
candidate + reliability verdict into a ``distill`` PoUW manifest. Committee
selection, quorum tallying, dispute-window settlement, and value transfer are
NOT reimplemented here — they are the existing, originator-agnostic
``pouw``/``ledger`` machinery; an agent is just another valid originator.
"""

from __future__ import annotations

from . import credential, propose
from .credential import (
    AgentCredential,
    AgentCredentialError,
    KNOWN_ROLES,
    ROLE_ARBITER,
    ROLE_CHALLENGER,
    ROLE_CURATOR,
    ROLE_TUTOR,
    build as build_credential,
    sign_by_agent,
    sign_by_issuer,
)
from .propose import ProposedKnit, ProposeKnitError, propose_knit

__all__ = [
    "credential",
    "propose",
    "AgentCredential",
    "AgentCredentialError",
    "KNOWN_ROLES",
    "ROLE_ARBITER",
    "ROLE_CHALLENGER",
    "ROLE_CURATOR",
    "ROLE_TUTOR",
    "build_credential",
    "sign_by_agent",
    "sign_by_issuer",
    "ProposedKnit",
    "ProposeKnitError",
    "propose_knit",
]
