"""The single observation path: pulse_ar device claims → fabric FieldObservation.

Epic E14 of the dual-coin plan (``docs/DUAL_COIN_IPO_PLAN.md`` §9): after the
repo consolidation there must be exactly **one** ledger-facing observation
canon. That canon is :class:`~knitweb.fabric.observation.FieldObservation`
(float-free, geohash-anchored, attested, and what
:class:`~knitweb.token.par.ObservationTreasury` mints PAR against). The
pulse_ar edge stack keeps its richer device-side record
(:class:`.observation.ObjectObservation` — WHAT/WHO/WHERE/HOW/DEVICE, BLE
mesh, ``verify()``-before-trust), and this bridge is the one place the two
meet:

    Quest/glass detection → ObjectObservation → (BLE mesh, signature verify)
        → :func:`to_field_observation` → attest → weave → PAR bounty

Mapping rules:

  * ``confidence_bps`` (0..10000) → ``confidence_milli`` (0..1000) by **floor**
    division: the bridge never rounds a device up into the confirmed band, so
    only a true 10000 bps claim crosses as ``CONFIDENCE_MILLI_EXACT`` and
    everything else keeps the fabric's requires-confirmation contract.
  * ``target`` prefers the woven knowledge fiber (``fiber_cid``) and falls back
    to the taxonomy id; an observation that resolves to neither has nothing to
    bind and is refused.
  * ``observer`` is the device's PLS address — the same key that signed the
    mesh envelope, so provenance is one identity end-to-end.
  * :func:`signed_to_field_observation` refuses an envelope whose signature
    does not verify — a forged mesh claim never even becomes a candidate
    fabric record.
"""

from __future__ import annotations

from ...fabric.observation import FieldObservation
from .observation import ObjectObservation, SignedObservation

__all__ = ["to_field_observation", "signed_to_field_observation"]

_BPS_PER_MILLI = 10  # 10000 bps == 1000 milli == certainty


def to_field_observation(
    observation: ObjectObservation,
    *,
    beat: int | None = None,
    pod_ref: str | None = None,
    capture_digest: str | None = None,
) -> FieldObservation:
    """Map a device-side observation onto the ledger-facing canon.

    ``beat`` defaults to the observation's ``observed_at`` (already integer
    Pulse time by contract). ``pod_ref``/``capture_digest`` pass through to the
    fabric record untouched — raw captures stay in the wearer's pod either way.
    """
    target = observation.fiber_cid or observation.taxonomy
    if not target:
        raise ValueError(
            "observation resolves to no Web node (fiber_cid and taxonomy empty)"
        )
    return FieldObservation(
        geohash=observation.geohash,
        alt_band=observation.alt_band,
        label=observation.label,
        backend="scene_semantic",
        confidence_milli=observation.confidence_bps // _BPS_PER_MILLI,
        target=target,
        observer=observation.device,
        beat=observation.observed_at if beat is None else beat,
        pod_ref=pod_ref,
        capture_digest=capture_digest,
    )


def signed_to_field_observation(
    signed: SignedObservation,
    *,
    beat: int | None = None,
    pod_ref: str | None = None,
    capture_digest: str | None = None,
) -> FieldObservation:
    """Bridge a mesh envelope, verifying its signature first.

    Verify, don't trust: an envelope that does not verify is refused outright —
    it must never surface as a candidate fabric record, however plausible its
    payload looks.
    """
    if not signed.verify():
        raise ValueError("signed observation does not verify — refusing to bridge")
    return to_field_observation(
        signed.observation, beat=beat, pod_ref=pod_ref, capture_digest=capture_digest
    )
