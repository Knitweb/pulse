"""ComputeGrant — the 49% GPU wallet consent, as a signed revocable record.

Using the Pulse wallet opts a device in to contribute GPU capacity to the web
(``docs/DUAL_COIN_IPO_PLAN.md`` §6). Consent is not a checkbox in an app — it
is a **fabric record**: signed by the device's own key, bounded by protocol,
revocable at any beat, and enforceable by any scheduler that reads it.

Protocol rules:

  * **49%, never a majority.** ``MAX_GRANT_BPS = 4900`` is a *protocol* cap,
    not a default: a grant asking for more is invalid everywhere. The device
    owner always keeps priority — the same ethos as no-privileged-genesis.
  * **Scoped.** A grant names the workload classes it covers (vision inference
    for PAR observations, PQ path sampling, chemistry validation). A scheduler
    may only assign work inside the granted scopes.
  * **Revocable, one-tap.** A :class:`ComputeRevocation` signed by the same
    device key zeroes the grant from its beat onward. Expiry does the same
    passively (``beat_expiry``).
  * **Enforcement is two-sided.** This module is the *assignment* side: a
    :class:`GrantRegistry` verifies envelopes and answers "how many bps may
    this device be assigned for this scope at this beat" —
    :meth:`GrantRegistry.clamp` is the number a marketplace/scheduler must
    respect. The *device* side (WebGPU frame-budget slicing in the client)
    keeps the duty cycle honest locally; :class:`.scheduler.GpuScheduler`
    remains the local concurrency gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import canonical, crypto
from ..fabric.attest import Attestation, attest, verify_record

__all__ = [
    "MAX_GRANT_BPS",
    "ALLOWED_SCOPES",
    "ComputeGrant",
    "ComputeRevocation",
    "GrantRegistry",
    "attest_grant",
    "attest_revocation",
]

MAX_GRANT_BPS = 4900  # 49.00% — a granted device never yields a majority
ALLOWED_SCOPES = ("vision", "pq", "chem-validate")

GRANT_KIND = "compute-grant"
REVOCATION_KIND = "compute-revocation"


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True)
class ComputeGrant:
    """One device's bounded, scoped, expiring GPU consent."""

    device: str            # pls1 address of the granting wallet/device key
    max_gpu_bps: int       # basis points of the device GPU, 1..MAX_GRANT_BPS
    scopes: tuple[str, ...]
    beat_granted: int
    beat_expiry: int       # last beat (inclusive) the grant is valid for

    def __post_init__(self) -> None:
        if not isinstance(self.device, str) or not crypto.is_valid_address(self.device):
            raise ValueError("device must be a valid pls1 address")
        _require_int("max_gpu_bps", self.max_gpu_bps)
        if not 0 < self.max_gpu_bps <= MAX_GRANT_BPS:
            raise ValueError(f"max_gpu_bps must be in 1..{MAX_GRANT_BPS} — "
                             "a grant never yields a majority of the device")
        if not isinstance(self.scopes, tuple) or not self.scopes:
            raise TypeError("scopes must be a non-empty tuple")
        for scope in self.scopes:
            if scope not in ALLOWED_SCOPES:
                raise ValueError(f"unknown scope {scope!r}; allowed: {ALLOWED_SCOPES}")
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("scopes must not repeat")
        _require_int("beat_granted", self.beat_granted)
        _require_int("beat_expiry", self.beat_expiry)
        if self.beat_granted < 0 or self.beat_expiry < self.beat_granted:
            raise ValueError("need 0 <= beat_granted <= beat_expiry")

    def to_record(self) -> dict:
        return {
            "kind": GRANT_KIND,
            "device": self.device,
            "max_gpu_bps": self.max_gpu_bps,
            "scopes": sorted(self.scopes),
            "beat_granted": self.beat_granted,
            "beat_expiry": self.beat_expiry,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


@dataclass(frozen=True)
class ComputeRevocation:
    """The one-tap withdrawal: zeroes ``grant_cid`` from ``beat`` onward."""

    device: str      # must match the grant's device — only the granter revokes
    grant_cid: str
    beat: int

    def __post_init__(self) -> None:
        if not isinstance(self.device, str) or not crypto.is_valid_address(self.device):
            raise ValueError("device must be a valid pls1 address")
        if not isinstance(self.grant_cid, str) or not self.grant_cid:
            raise TypeError("grant_cid must be a non-empty str")
        _require_int("beat", self.beat)
        if self.beat < 0:
            raise ValueError("beat must be non-negative")

    def to_record(self) -> dict:
        return {
            "kind": REVOCATION_KIND,
            "device": self.device,
            "grant_cid": self.grant_cid,
            "beat": self.beat,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


def attest_grant(grant: ComputeGrant, device_priv: str) -> Attestation:
    """Sign a grant with the device's own key (standard attestation envelope)."""
    return attest(grant.to_record(), device_priv, author_field="device")


def attest_revocation(revocation: ComputeRevocation, device_priv: str) -> Attestation:
    """Sign a revocation with the device's own key."""
    return attest(revocation.to_record(), device_priv, author_field="device")


class GrantRegistry:
    """Validate-at-admit registry answering "how much may this device carry?".

    Verify, don't trust: :meth:`admit` and :meth:`revoke` re-verify the
    attestation envelope locally and silently reject anything that does not
    hold (returning ``False``), so a registry fed from gossip can never be
    poisoned into over-assigning a device.
    """

    def __init__(self) -> None:
        self._grants: dict[str, ComputeGrant] = {}          # grant cid -> grant
        self._revoked_from: dict[str, int] = {}             # grant cid -> beat

    def admit(self, grant: ComputeGrant, attestation: Attestation) -> bool:
        """Accept a signed grant into the registry. False = invalid envelope."""
        if attestation.record != grant.to_record():
            return False
        if not verify_record(attestation.record, attestation.author_pub,
                             attestation.sig, author_field="device"):
            return False
        self._grants[grant.cid] = grant
        return True

    def revoke(self, revocation: ComputeRevocation, attestation: Attestation) -> bool:
        """Apply a signed revocation. False = unknown grant or invalid envelope."""
        grant = self._grants.get(revocation.grant_cid)
        if grant is None:
            return False
        if revocation.device != grant.device:
            return False  # only the granting device may revoke its own grant
        if attestation.record != revocation.to_record():
            return False
        if not verify_record(attestation.record, attestation.author_pub,
                             attestation.sig, author_field="device"):
            return False
        beat = self._revoked_from.get(revocation.grant_cid)
        self._revoked_from[revocation.grant_cid] = (
            revocation.beat if beat is None else min(beat, revocation.beat)
        )
        return True

    def allowed_bps(self, device: str, beat: int, scope: str) -> int:
        """The bps this device may be assigned for ``scope`` at ``beat`` (0 = none).

        Multiple live grants for one device do not stack: the answer is the
        single largest applicable grant, and never exceeds ``MAX_GRANT_BPS``.
        """
        _require_int("beat", beat)
        best = 0
        for cid, grant in self._grants.items():
            if grant.device != device or scope not in grant.scopes:
                continue
            if not grant.beat_granted <= beat <= grant.beat_expiry:
                continue
            revoked_at = self._revoked_from.get(cid)
            if revoked_at is not None and beat >= revoked_at:
                continue
            best = max(best, grant.max_gpu_bps)
        return min(best, MAX_GRANT_BPS)

    def clamp(self, device: str, beat: int, scope: str, requested_bps: int) -> int:
        """The assignment a scheduler may actually make: min(request, consent)."""
        _require_int("requested_bps", requested_bps)
        if requested_bps < 0:
            raise ValueError("requested_bps must be non-negative")
        return min(requested_bps, self.allowed_bps(device, beat, scope))
