"""MOLGANG epoch settlement — bridge P2 (plan, verify, never mint).

Consumes the signed epoch export produced by molgang-web's
``GET /api/bridge/epoch/{YYYYMMDD}`` (P1) and turns it into an idempotent,
integer-only settlement plan:

  1. **Verify** the Ed25519 signature over the canonical JSON payload. The
     attestation format follows the weave-core did:key identity pattern
     (Ed25519, raw-hex public key) — deliberately *not* this package's native
     secp256k1 (`core.crypto`), because the game server is an external
     attester, not a ledger node.
  2. **Apportion** a caller-supplied integer budget (PLS base units, decided
     by the Treasury's demand gate — never by gameplay volume) across players
     with positive net receipts, using pure integer largest-remainder
     arithmetic: no float enters this package, and the parts sum EXACTLY to
     the budget.
  3. **Anti-replay**: the plan carries the payload's canonical digest; a
     ``settled`` set makes planning the same epoch twice a refusal, mirroring
     the Treasury's ``_rewarded_digests`` discipline.

The plan is the hand-off artifact to P3: actually paying it out requires the
Treasury's gated path plus the MOLGANG-015 review gates. There is no code
path from here to a mint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

__all__ = [
    "EpochSettlementPlan",
    "apportion_integer",
    "plan_epoch_settlement",
    "verify_epoch_export",
]

SCHEMA = "molgang.bridge-epoch.v1"


def _canonical_bytes(payload: dict) -> bytes:
    # Must match molgang-web api/routes/bridge.py::_canonical exactly.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def verify_epoch_export(export: dict) -> dict:
    """Verify a P1 epoch export; return its payload or raise ``ValueError``."""
    payload = export.get("payload")
    signature_hex = export.get("signature")
    pub_hex = export.get("publicKeyHex")
    if not isinstance(payload, dict) or not signature_hex or not pub_hex:
        raise ValueError("export must carry payload, signature and publicKeyHex")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"unexpected schema: {payload.get('schema')!r}")
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        key.verify(bytes.fromhex(signature_hex), _canonical_bytes(payload))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError(f"epoch export signature invalid: {exc}") from exc

    players = payload.get("players", [])
    totals = payload.get("totals", {})
    net_sum = sum(int(p["net"]) for p in players)
    if net_sum != int(totals.get("net", -1)) or len(players) != int(totals.get("players", -1)):
        raise ValueError("epoch export violates conservation (totals != sum of players)")
    return payload


def apportion_integer(weights: list[int], total_units: int) -> list[int]:
    """Largest-remainder split in pure integer arithmetic.

    Exact remainders are compared by cross-multiplication (``w * total % wsum``),
    so no float participates — the same conservation invariants as
    ``knitweb_vank.apportion`` (its float-accepting sibling) and molgang-web's
    ``ledger.ts``, proven here without ever leaving ℤ.
    """
    if not isinstance(total_units, int) or isinstance(total_units, bool):
        raise TypeError("total_units must be int")
    if total_units < 0:
        raise ValueError("total_units must be non-negative")
    n = len(weights)
    if n == 0:
        if total_units:
            raise ValueError("cannot apportion non-zero total over zero parties")
        return []
    wsum = 0
    for i, w in enumerate(weights):
        if not isinstance(w, int) or isinstance(w, bool):
            raise TypeError(f"weights[{i}] must be int")
        if w < 0:
            raise ValueError(f"weights[{i}] must be non-negative")
        wsum += w
    if total_units == 0:
        return [0] * n
    if wsum == 0:
        base, extra = divmod(total_units, n)
        return [base + (1 if i < extra else 0) for i in range(n)]

    parts = [(w * total_units) // wsum for w in weights]
    remainders = [(w * total_units) % wsum for w in weights]
    leftover = total_units - sum(parts)
    order = sorted(range(n), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        parts[i] += 1
    return parts


@dataclass(frozen=True)
class EpochSettlementPlan:
    """Integer-only, replay-protected hand-off artifact for the gated payout."""

    epoch: str
    digest: str
    budget_units: int
    shares: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.shares.values())


def plan_epoch_settlement(
    export: dict,
    budget_units: int,
    *,
    settled: set[str] | None = None,
) -> EpochSettlementPlan:
    """Verify ``export`` and apportion ``budget_units`` over positive nets.

    ``settled`` is the caller's anti-replay registry (digests of already
    planned epochs); planning a digest twice raises. Players with net <= 0
    receive no share (a polluter's burn is not a payout weight).
    """
    payload = verify_epoch_export(export)
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    if settled is not None:
        if digest in settled:
            raise ValueError(f"epoch {payload['epoch']} ({digest[:12]}…) already settled")
        settled.add(digest)

    earners = [(p["player"], int(p["net"])) for p in payload["players"] if int(p["net"]) > 0]
    parts = apportion_integer([net for _, net in earners], budget_units)
    shares = {player: part for (player, _), part in zip(earners, parts) if part > 0}
    plan = EpochSettlementPlan(
        epoch=str(payload["epoch"]), digest=digest, budget_units=budget_units, shares=shares
    )
    assert plan.total == (budget_units if earners else 0)
    return plan
