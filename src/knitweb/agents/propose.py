"""propose_knit() — an agent's gated entry point into the distill PoUW pipeline.

LENS agentic-player-loop (lens#14) acceptance: "an NPC agent joins the bar,
proposes a knit, is verified by quorum, and earns PLS — held to the same rules
as a human." This module is deliberately thin: it adds nothing new to
consensus, settlement, or value transfer. It only:

  1. requires a fully verified :class:`knitweb.agents.credential.AgentCredential`
     (so only a credentialed, key-controlling agent can propose at all);
  2. enforces the calibrated-confidence + abstention reliability gate (AC of
     lens#14 — "so agents can't poison the canonical Web") by refusing to
     propose when the caller-supplied reliability verdict says abstain;
  3. builds the *existing* ``distill`` SPLIT-verified PoUW manifest
     (:class:`knitweb.pouw.job.DistillManifest`, IL-105) from the agent's
     already-computed :class:`knitweb.interpret.retrieve.CandidateSet` and
     :class:`knitweb.interpret.distill.Selection`;
  4. signs that manifest with the agent's own key via the *existing*
     :mod:`knitweb.fabric.attest` envelope — the same mechanism every other
     fabric item uses, treating ``DistillManifest.originator`` as an address
     field exactly like ``attest``'s other author fields.

Everything downstream of the returned :class:`ProposedKnit` — committee
selection (``pouw.committee``), quorum tallying (``pouw.quorum``), the
dispute-window settlement decision (``pouw.dispute`` / ``job.split_settles``),
and the PLS reward transfer (``ledger.knit``) — is the same, originator-
agnostic machinery a human-authored distill job already goes through. This
module does not call any of that itself: at the time of writing, the IL-106
(deterministic structural re-check) and IL-107 (challenge-window) *producers*
that feed ``split_settles`` are not yet assembled into a single end-to-end
orchestrator for ANY originator, human or agent (see ``pouw/job.py``'s own
"still-evolving producers" note) — that gap is shared infrastructure, not
agent-specific, and is out of scope here.

The reliability verdict is accepted as a small structural protocol (needs
``.abstained: bool`` and ``.confidence: int``) rather than importing
``knitweb_lens.reliability.ReliabilityReport`` directly, so ``pulse`` does not
gain a dependency on ``lens`` — the same "no upward import" rule
``lens.capabilities`` documents from the other side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core import crypto
from ..fabric.attest import Attestation, attest
from ..pouw.job import DistillManifest, bundle_cid
from ..synaptic.bytecode import compile_bundle
from .credential import AgentCredential

__all__ = [
    "ReliabilityVerdict",
    "CandidateSetLike",
    "SelectionLike",
    "ProposeKnitError",
    "ProposedKnit",
    "propose_knit",
]


class ReliabilityVerdict(Protocol):
    """Structural stand-in for ``knitweb_lens.reliability.ReliabilityReport``."""

    abstained: bool
    confidence: int


class CandidateSetLike(Protocol):
    """Structural stand-in for ``knitweb.interpret.retrieve.CandidateSet``."""

    web_state_cid: str
    query: object
    subscription: object


class SelectionLike(Protocol):
    """Structural stand-in for ``knitweb.interpret.distill.Selection``."""

    relations: object


class ProposeKnitError(ValueError):
    """Raised when an agent's proposal is refused before it reaches consensus."""


@dataclass(frozen=True)
class ProposedKnit:
    """A signed, ready-to-submit distill proposal from a credentialed agent."""

    manifest: DistillManifest
    attestation: Attestation
    agent_role: int

    @property
    def cid(self) -> str:
        return self.manifest.cid()


def propose_knit(
    candidate_set: CandidateSetLike,
    selection: SelectionLike,
    credential: AgentCredential,
    agent_priv: str,
    reliability: ReliabilityVerdict,
) -> ProposedKnit:
    """Build and sign a distill manifest on behalf of a credentialed agent.

    Raises :class:`ProposeKnitError` if the credential does not verify, the
    signing key does not match the credential, ``reliability.abstained`` is
    true, or ``reliability.confidence`` is not a positive int — the
    calibrated-confidence gate lens#14 requires so an unconfident agent
    proposal can never reach the canonical Web.

    The actual confidence *threshold* is the caller's responsibility (e.g.
    ``knitweb_lens.reliability.evaluate_session``'s ``min_confidence``, which
    is what sets ``abstained`` in the first place) — this function does not
    re-derive or second-guess that threshold. What it does enforce is
    consistency: a verdict claiming ``abstained=False`` must carry a
    ``confidence`` that actually supports that claim (a positive int), so a
    malformed or degenerate verdict object can't slip a proposal through on a
    default/zero confidence value.
    """
    if not credential.verify():
        raise ProposeKnitError("agent credential does not verify (unsigned or tampered)")
    if crypto.public_from_private(agent_priv) != credential.agent_pub:
        raise ProposeKnitError("agent_priv does not control the credential's agent_pub")
    if bool(getattr(reliability, "abstained", True)):
        raise ProposeKnitError(
            "reliability verdict abstained — refusing to propose (calibrated-confidence gate)"
        )
    confidence = getattr(reliability, "confidence", None)
    if not isinstance(confidence, int) or isinstance(confidence, bool) or confidence <= 0:
        raise ProposeKnitError(
            "reliability.confidence must be a positive int for a non-abstained verdict "
            f"(calibrated-confidence gate) — got {confidence!r}"
        )

    web_state_cid = getattr(candidate_set, "web_state_cid", None)
    if not isinstance(web_state_cid, str) or not web_state_cid:
        raise ProposeKnitError("candidate_set.web_state_cid must be a non-empty str")
    relations = list(getattr(selection, "relations", ()))
    if not relations:
        raise ProposeKnitError("selection has no relations to propose")

    originator_addr = crypto.address(credential.agent_pub)
    bytecode = compile_bundle(web_state_cid, originator_addr, relations)
    manifest = DistillManifest.from_distill(
        candidate_set, bundle_cid=bundle_cid(bytecode), originator=originator_addr
    )

    try:
        attestation = attest(manifest.to_record(), agent_priv, author_field="originator")
    except ValueError as exc:  # pragma: no cover - guarded by the address check above
        raise ProposeKnitError(str(exc)) from exc

    return ProposedKnit(manifest=manifest, attestation=attestation, agent_role=credential.role)
