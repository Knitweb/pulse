"""Field-observation exchange — glass-to-glass sharing of verified sightings.

The producer side (:class:`~knitweb.edge.observer.GlassObserver`) ends with
attested observations. This module moves them between wearers: a compact,
canonical-CBOR **observation bundle** any carrier can ship — the BitChat BLE
seam for buren in the same street, a WebRTC DataChannel across the wider web,
or a plain file. The carrier stays opaque, exactly like every other frame in
the p2p layer; this module owns packing, verification, and spatial acceptance.

Trust model (verify-before-trust, all-or-nothing):

  * every entry carries its own :class:`~knitweb.fabric.attest.Attestation`
    (record + observer pubkey + signature over the canonical bytes);
  * :func:`unpack_observations` re-verifies **every** entry and refuses the
    **whole bundle** on the first failure — a peer that ships one forged
    sighting is not a peer whose other sightings deserve the benefit of the
    doubt (acting on a forged overlay is a safety problem, not a UI glitch);
  * records are rebuilt through the strict
    :meth:`~knitweb.fabric.observation.FieldObservation.from_record`, so a
    received record passes the same constraints as a locally built one.

Spatial acceptance differs from :class:`~knitweb.edge.arglass.ARGlass` in one
pleasant way: an observation *carries its own geohash*, so no side-channel
``anchor_geohash`` is needed — :class:`FieldGlass` filters on the record
itself.
"""

from __future__ import annotations

from ..core import canonical
from ..fabric.attest import Attestation
from ..fabric.observation import FieldObservation
from ..fabric.spatial import geohash as _geohash, proximate

__all__ = [
    "ExchangeVerifyError",
    "pack_observations",
    "unpack_observations",
    "FieldGlass",
    "BUNDLE_KIND",
    "MAX_BUNDLE_OBSERVATIONS",
]

BUNDLE_KIND = "field-observation-bundle"

# Resource bound, in the spirit of the capped serve paths in fabric/node.py:
# one bundle can never make a receiver verify an unbounded amount of ECDSA.
MAX_BUNDLE_OBSERVATIONS = 256


class ExchangeVerifyError(Exception):
    """Raised when a bundle fails verification and must not be used at all."""


def pack_observations(attestations: list[Attestation]) -> bytes:
    """Encode attested observations as one canonical, carrier-opaque bundle.

    Refuses to pack anything the sender could not verify itself — never ship a
    bundle you would reject on receipt.
    """
    if not attestations:
        raise ValueError("cannot pack an empty bundle")
    if len(attestations) > MAX_BUNDLE_OBSERVATIONS:
        raise ValueError(
            f"bundle exceeds {MAX_BUNDLE_OBSERVATIONS} observations"
        )
    entries: list[dict] = []
    for attestation in attestations:
        # from_record enforces record shape; verify enforces authorship.
        FieldObservation.from_record(attestation.record)
        if not attestation.verify(author_field="observer"):
            raise ExchangeVerifyError(
                "refusing to pack an observation that does not verify"
            )
        entries.append({
            "record": attestation.record,
            "observer_pub": attestation.author_pub,
            "sig": attestation.sig,
        })
    return canonical.encode({"kind": BUNDLE_KIND, "observations": entries})


def unpack_observations(
    data: bytes,
) -> list[tuple[FieldObservation, Attestation]]:
    """Decode + verify a bundle; refuse the whole thing on any bad entry."""
    try:
        decoded = canonical.decode(data)
    except Exception as exc:  # strict decoder: non-canonical bytes are refused
        raise ExchangeVerifyError(f"bundle is not canonical CBOR: {exc}") from exc
    if not isinstance(decoded, dict) or decoded.get("kind") != BUNDLE_KIND:
        raise ExchangeVerifyError(f"not a {BUNDLE_KIND!r}")
    entries = decoded.get("observations")
    if not isinstance(entries, list) or not entries:
        raise ExchangeVerifyError("bundle carries no observations")
    if len(entries) > MAX_BUNDLE_OBSERVATIONS:
        raise ExchangeVerifyError(
            f"bundle exceeds {MAX_BUNDLE_OBSERVATIONS} observations"
        )
    out: list[tuple[FieldObservation, Attestation]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ExchangeVerifyError("malformed bundle entry")
        try:
            observation = FieldObservation.from_record(entry["record"])
            attestation = Attestation(
                record=entry["record"],
                author_pub=entry["observer_pub"],
                sig=entry["sig"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExchangeVerifyError(f"malformed bundle entry: {exc}") from exc
        if not attestation.verify(author_field="observer"):
            raise ExchangeVerifyError(
                "observation signature invalid — refusing the whole bundle"
            )
        out.append((observation, attestation))
    return out


class FieldGlass:
    """A wearer's receiver for peer-shared observations near their position."""

    def __init__(self, lat: float, lon: float, precision: int = 7) -> None:
        self.precision = precision
        self.geohash = _geohash(lat, lon, precision)
        self._accepted: dict[str, tuple[FieldObservation, Attestation]] = {}

    # -- location ----------------------------------------------------------

    def move(self, lat: float, lon: float) -> None:
        """Update the wearer's position (floats transient, as in ARGlass)."""
        self.geohash = _geohash(lat, lon, self.precision)

    # -- ingest (verify + spatial filter + dedupe) -------------------------

    def receive(self, data: bytes) -> int:
        """Verify a bundle and keep the observations near the wearer.

        Raises :class:`ExchangeVerifyError` if the bundle fails verification
        (nothing is kept). Otherwise keeps only observations whose own geohash
        falls in the wearer's cell, deduplicated by CID, and returns how many
        were newly accepted.
        """
        accepted = 0
        for observation, attestation in unpack_observations(data):
            if not proximate(self.geohash, observation.geohash, self.precision):
                continue
            cid = observation.cid
            if cid in self._accepted:
                continue
            self._accepted[cid] = (observation, attestation)
            accepted += 1
        return accepted

    # -- projection --------------------------------------------------------

    def overlays(self) -> list[dict]:
        """Field-of-view entries for every accepted peer observation."""
        return [
            {
                "cid": cid,
                "label": observation.label,
                "target": observation.target,
                "backend": observation.backend,
                "confidence_milli": observation.confidence_milli,
                "observer": observation.observer,
                "pod_ref": observation.pod_ref,
            }
            for cid, (observation, _att) in sorted(self._accepted.items())
        ]

    def weave_into(self, web) -> list[tuple[str, str]]:
        """Weave accepted observations (+ anchors) into a local ``web``.

        After this, the standard :class:`~knitweb.fabric.spatial_index.SpatialIndex`
        / :func:`~knitweb.edge.observer.overlay_near` path serves peer sightings
        exactly like the wearer's own.
        """
        return [obs.weave(web) for obs, _att in self._accepted.values()]

    @property
    def accepted_count(self) -> int:
        return len(self._accepted)
