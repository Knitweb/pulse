"""Agent credential — the identity record that makes an LLM a first-class peer.

LENS agentic-player-loop (lens#14): an NPC agent must "knit the same records,
sign with the same keys, pass the same gates" as a human. That starts with an
identity record binding a secp256k1 keypair to a declared **role archetype**
(Tutor / Curator / Challenger / Arbiter — see :mod:`knitweb.agents.roles`),
co-signed by the agent (proving it controls the key it claims) and an issuer
(a human operator or bar-admin key vouching the agent may join at all).

This mirrors :mod:`knitweb.ledger.knit` (two named signers over one canonical
record, verified directly against the pubkeys the record itself carries) rather
than :mod:`knitweb.fabric.attest` (which binds an *address* field), because a
credential's whole point is publishing the agent's usable pubkey — the same key
it will later sign proposed knits and PoUW manifests with — not just an address
commitment.

An agent is explicitly NOT a person: this module intentionally does not import
or extend :mod:`knitweb.personhood` (which is scoped to eIDAS-verified unique
natural persons and must never carry a synthetic/agentic entry).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..core import canonical, crypto

__all__ = [
    "AgentCredentialError",
    "KIND",
    "ROLE_TUTOR",
    "ROLE_CURATOR",
    "ROLE_CHALLENGER",
    "ROLE_ARBITER",
    "KNOWN_ROLES",
    "ROLE_NAMES",
    "WHITELIST",
    "AgentCredential",
    "build",
    "sign_by_agent",
    "sign_by_issuer",
    "assert_credential_shape",
]


class AgentCredentialError(ValueError):
    """Raised when an agent credential violates its shape or signature contract."""


KIND = "agent-credential/v1"

# Role archetypes (lens#14 scope). Plain ints so the record stays canonical-CBOR
# clean; a role governs what :class:`knitweb.agents.policy.AgentPolicy` (lens-side)
# lets the agent attempt, not what pulse itself enforces beyond identity.
ROLE_TUTOR = 0
ROLE_CURATOR = 1
ROLE_CHALLENGER = 2
ROLE_ARBITER = 3
KNOWN_ROLES = frozenset({ROLE_TUTOR, ROLE_CURATOR, ROLE_CHALLENGER, ROLE_ARBITER})
ROLE_NAMES = {
    ROLE_TUTOR: "tutor",
    ROLE_CURATOR: "curator",
    ROLE_CHALLENGER: "challenger",
    ROLE_ARBITER: "arbiter",
}

# Deny-by-default whitelist (mirrors personhood.records' anti-drift discipline):
# any field outside this set is a hard error, so a credential can never grow a
# free-form/PII-shaped field by accident.
WHITELIST = frozenset({"kind", "agent_pub", "role", "issuer_pub", "issued_at", "key_scheme"})


@dataclass(frozen=True)
class AgentCredential:
    """A role-scoped identity credential for one agent, co-signed by its issuer."""

    agent_pub: str          # compressed secp256k1 pubkey (hex) — the agent's own key
    role: int                # one of ROLE_TUTOR/ROLE_CURATOR/ROLE_CHALLENGER/ROLE_ARBITER
    issuer_pub: str          # compressed secp256k1 pubkey (hex) of the vouching issuer
    issued_at: int           # beat/timestamp the credential was issued at
    key_scheme: int = crypto.SCHEME_SECP256K1_ECDSA
    agent_sig: str | None = None   # agent's signature, proving it controls agent_pub
    issuer_sig: str | None = None  # issuer's signature, vouching for the role grant

    def to_record(self) -> dict:
        """The signed payload — signatures are NOT part of the signed bytes."""
        return {
            "kind": KIND,
            "agent_pub": self.agent_pub,
            "role": self.role,
            "issuer_pub": self.issuer_pub,
            "issued_at": self.issued_at,
            "key_scheme": self.key_scheme,
        }

    @property
    def signing_bytes(self) -> bytes:
        return canonical.encode(self.to_record())

    @property
    def cid(self) -> str:
        """Content id over the signed record (excludes signatures)."""
        return canonical.cid(self.to_record())

    @property
    def role_name(self) -> str:
        return ROLE_NAMES.get(self.role, "unknown")

    def is_fully_signed(self) -> bool:
        return self.agent_sig is not None and self.issuer_sig is not None

    def verify(self) -> bool:
        """True iff both the agent and the issuer validly signed this exact record."""
        agent_sig, issuer_sig = self.agent_sig, self.issuer_sig
        if agent_sig is None or issuer_sig is None:
            return False
        if self.agent_pub == self.issuer_pub:
            # An agent cannot vouch for its own role grant — that would let any
            # process mint itself a credential with no external issuer in the loop.
            return False
        message = self.signing_bytes
        return crypto.verify(self.agent_pub, message, agent_sig) and crypto.verify(
            self.issuer_pub, message, issuer_sig
        )


def assert_credential_shape(record: dict) -> None:
    """Validate an agent-credential record's shape (deny-by-default whitelist).

    Guards: it is a dict; no field outside :data:`WHITELIST`; ``kind`` matches;
    ``role``/``key_scheme`` are known enum values; ``agent_pub``/``issuer_pub``
    are valid compressed secp256k1 hex; ``issued_at`` is a non-negative int.
    """
    if not isinstance(record, dict):
        raise AgentCredentialError("agent credential record must be a dict")
    extra = set(record) - WHITELIST
    if extra:
        raise AgentCredentialError(f"agent credential carries disallowed fields: {sorted(extra)}")
    missing = WHITELIST - set(record)
    if missing:
        raise AgentCredentialError(f"agent credential missing required fields: {sorted(missing)}")
    if record["kind"] != KIND:
        raise AgentCredentialError(f"kind must be {KIND!r}")
    role = record["role"]
    if not isinstance(role, int) or isinstance(role, bool) or role not in KNOWN_ROLES:
        raise AgentCredentialError(f"role={role!r} not in {sorted(KNOWN_ROLES)}")
    key_scheme = record["key_scheme"]
    if key_scheme not in crypto.KNOWN_SCHEMES:
        raise AgentCredentialError(f"key_scheme={key_scheme!r} not a blessed crypto scheme")
    for field in ("agent_pub", "issuer_pub"):
        value = record[field]
        if not isinstance(value, str) or not crypto.is_valid_hex(value, 33):
            raise AgentCredentialError(f"{field!r} must be a 33-byte compressed pubkey hex")
    issued_at = record["issued_at"]
    if not isinstance(issued_at, int) or isinstance(issued_at, bool) or issued_at < 0:
        raise AgentCredentialError("issued_at must be a non-negative int")


def build(
    agent_pub: str,
    role: int,
    issuer_pub: str,
    issued_at: int,
    *,
    key_scheme: int = crypto.SCHEME_SECP256K1_ECDSA,
) -> AgentCredential:
    """Construct an unsigned :class:`AgentCredential`, validating its shape."""
    credential = AgentCredential(
        agent_pub=agent_pub,
        role=role,
        issuer_pub=issuer_pub,
        issued_at=issued_at,
        key_scheme=key_scheme,
    )
    assert_credential_shape(credential.to_record())
    return credential


def sign_by_agent(credential: AgentCredential, agent_priv: str) -> AgentCredential:
    """Attach the agent's own signature, proving control of ``agent_pub``.

    Refuses to sign if ``agent_priv`` does not actually control the pubkey the
    credential names, so a credential can never be self-signed under a borrowed key.
    """
    if crypto.public_from_private(agent_priv) != credential.agent_pub:
        raise AgentCredentialError("agent_priv does not control the credential's agent_pub")
    sig = crypto.sign(agent_priv, credential.signing_bytes)
    return replace(credential, agent_sig=sig)


def sign_by_issuer(credential: AgentCredential, issuer_priv: str) -> AgentCredential:
    """Attach the issuer's signature, vouching for the role grant."""
    if crypto.public_from_private(issuer_priv) != credential.issuer_pub:
        raise AgentCredentialError("issuer_priv does not control the credential's issuer_pub")
    sig = crypto.sign(issuer_priv, credential.signing_bytes)
    return replace(credential, issuer_sig=sig)
