"""GlassObserver — the device-side confirmation gate for field observations.

:mod:`knitweb.edge.recognize` ends with a contract: *"the durable binding
(anchor → knit-id) is a separate settlement-class operation handled upstream"*,
and a probabilistic result "MUST surface confidence so the caller can gate
durable binding on a user/agent confirmation step". This module is that
upstream handler.

A :class:`GlassObserver` pairs with :class:`~knitweb.edge.arglass.ARGlass`:
where ``ARGlass`` is the *consumer* side (verify + filter what others shared),
``GlassObserver`` is the *producer* side — it turns the wearer's recognition
results into :class:`~knitweb.fabric.observation.FieldObservation` records and
enforces the confirmation gate before anything is woven:

  * exact results (marker, confidence 1.0) are staged for weaving immediately;
  * probabilistic results (scene_semantic / embedding) are held **pending**
    until :meth:`confirm` — an unconfirmed observation can never reach
    :meth:`commit`;
  * raw captures are digested and dropped on ingest — the bytes stay in the
    wearer's personal data vault (pod); the fabric only ever sees
    ``pod_ref`` + ``capture_digest``.

Like ``ARGlass``, position floats are transient: only the geohash string and
the integer altitude band are kept.
"""

from __future__ import annotations

from ..fabric.attest import Attestation
from ..fabric.observation import FieldObservation, attest_observation
from ..fabric.spatial import altitude_band, geohash
from ..core import crypto

__all__ = ["GlassObserver", "overlay_near"]


class GlassObserver:
    """Produce confirmed, attestable field observations from a wearer's glass."""

    def __init__(
        self,
        observer_priv: str,
        lat: float,
        lon: float,
        precision: int = 9,
        altitude_m: float | None = None,
    ) -> None:
        self.precision = precision
        self._priv = observer_priv
        self._pub = crypto.public_from_private(observer_priv)
        self.observer = crypto.address(self._pub)
        self.geohash = geohash(lat, lon, precision)
        self.alt_band = altitude_band(altitude_m) if altitude_m is not None else 0
        self._pending: dict[str, FieldObservation] = {}
        self._confirmed: list[FieldObservation] = []

    # -- location ----------------------------------------------------------

    def move(self, lat: float, lon: float, altitude_m: float | None = None) -> None:
        """Update the wearer's position (floats are transient, as in ARGlass)."""
        self.geohash = geohash(lat, lon, self.precision)
        self.alt_band = altitude_band(altitude_m) if altitude_m is not None else 0

    # -- ingest (confidence gate) ------------------------------------------

    def observe(
        self,
        result,
        label: str,
        beat: int,
        *,
        pod_ref: str | None = None,
        capture: bytes | None = None,
    ) -> FieldObservation:
        """Turn a recognition result into an observation at the current cell.

        Returns the observation either way; whether it went to the pending
        queue or straight to the confirmed stage is visible on
        ``observation.requires_confirmation`` / :meth:`pending`.
        """
        observation = FieldObservation.from_recognition(
            result,
            geohash=self.geohash,
            alt_band=self.alt_band,
            label=label,
            observer=self.observer,
            beat=beat,
            pod_ref=pod_ref,
            capture=capture,
        )
        if observation.requires_confirmation:
            self._pending[observation.cid] = observation
        else:
            self._confirmed.append(observation)
        return observation

    def pending(self) -> list[FieldObservation]:
        """Observations awaiting the user/agent confirmation step."""
        return list(self._pending.values())

    def confirm(self, observation_cid: str) -> FieldObservation:
        """The user/agent confirmation step: promote a pending observation."""
        try:
            observation = self._pending.pop(observation_cid)
        except KeyError:
            raise KeyError(f"no pending observation {observation_cid}") from None
        self._confirmed.append(observation)
        return observation

    def reject(self, observation_cid: str) -> None:
        """Drop a pending observation (the recognition was wrong)."""
        try:
            del self._pending[observation_cid]
        except KeyError:
            raise KeyError(f"no pending observation {observation_cid}") from None

    # -- durable binding ---------------------------------------------------

    def commit(self, web) -> list[tuple[str, str, Attestation]]:
        """Weave every *confirmed* observation (+ its spatial anchor) into ``web``.

        Pending observations are untouched — an unconfirmed probabilistic
        recognition can never bind durably. Returns
        ``(observation_cid, anchor_cid, attestation)`` per woven observation;
        the attestations are what a glass shares with peers so they can
        validate-at-read.
        """
        out: list[tuple[str, str, Attestation]] = []
        for observation in self._confirmed:
            obs_cid, anchor_cid = observation.weave(web)
            out.append((obs_cid, anchor_cid, attest_observation(observation, self._priv)))
        self._confirmed = []
        return out


def overlay_near(
    web,
    index,
    wearer_geohash: str,
    precision: int,
    alt_band: int | None = None,
) -> list[dict]:
    """Field-of-view entries for observations anchored near the wearer.

    ``index`` is a :class:`~knitweb.fabric.spatial_index.SpatialIndex` built
    over ``web`` (e.g. ``SpatialIndex.from_web(web)``). Returns one dict per
    nearby ``field-observation`` record — the producer-side complement of
    :meth:`knitweb.edge.arglass.ARGlass.overlays`.
    """
    entries: list[dict] = []
    for target_cid in index.near(wearer_geohash, precision, alt_band):
        record = web.nodes.get(target_cid)
        if not record or record.get("kind") != "field-observation":
            continue
        entries.append({
            "cid": target_cid,
            "label": record["label"],
            "target": record["target"],
            "backend": record["backend"],
            "confidence_milli": record["confidence_milli"],
            "observer": record["observer"],
            "pod_ref": record.get("pod_ref"),
        })
    return entries
