"""Field observations — signed, geohash-anchored recognition results.

An AR glass that recognizes a physical object (via :mod:`knitweb.edge.recognize`)
produces knowledge worth weaving: *"at this cell, this label resolved to this
Web node, with this confidence"*. A :class:`FieldObservation` is that fact as a
float-free, content-addressed fabric record.

Design rules (all inherited from the fabric):

  * **No floats in the record.** A recognition confidence is a float on the
    device; it crosses into the fabric as an integer ``confidence_milli``
    (``int(confidence * 1000)``) at one declared boundary —
    :meth:`FieldObservation.from_recognition` — mirroring ``quantize_weight``
    and the edge-metadata rule in :mod:`knitweb.fabric.web`.
  * **Raw captures never enter the fabric.** A camera frame or screenshot
    belongs in the wearer's personal data vault (e.g. a Solid pod). The record
    carries at most ``pod_ref`` (where the original lives, access-controlled by
    the wearer) and ``capture_digest`` (SHA-256 of the raw bytes) so a shared
    original is tamper-evident without ever being woven or gossiped.
  * **Authorship is attestable.** The record's ``observer`` field is a ``pls1``
    address; :func:`attest_observation` wraps the canonical bytes in the
    standard :class:`~knitweb.fabric.attest.Attestation` envelope, so peers can
    validate-at-read exactly like any other fabric item.
  * **Probabilistic recognition never binds durably on its own.** The
    ``requires_confirmation`` contract of
    :class:`~knitweb.edge.recognize.RecognitionResult` carries through:
    ``confidence_milli < 1000`` marks the observation as needing a user/agent
    confirmation step before it may be woven (enforced device-side by
    :class:`knitweb.edge.observer.GlassObserver`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import canonical, crypto
from .attest import Attestation, attest
from .spatial import SpatialAnchor

__all__ = [
    "FieldObservation",
    "attest_observation",
    "CONFIDENCE_MILLI_EXACT",
    "OBSERVATION_KIND",
    "RECOGNITION_BACKENDS",
]

OBSERVATION_KIND = "field-observation"
CONFIDENCE_MILLI_EXACT = 1000
RECOGNITION_BACKENDS = ("marker", "scene_semantic", "embedding")

_GEOHASH_ALPHABET = frozenset("0123456789bcdefghjkmnpqrstuvwxyz")


def _require_str(name: str, value: object, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not value and not allow_empty:
        raise ValueError(f"{name} must not be empty")


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True)
class FieldObservation:
    """One recognized thing at one physical cell, ready to weave.

    ``target`` is the Web node CID the recognition resolved to. ``label`` is the
    detector's class label (``scene_semantic``), the marker payload (``marker``),
    or a caller-chosen tag (``embedding``). ``beat`` is integer Pulse time.
    ``pod_ref`` / ``capture_digest`` are optional pointers to the wearer's
    private original — see the module docstring.
    """

    geohash: str
    alt_band: int
    label: str
    backend: str
    confidence_milli: int
    target: str
    observer: str          # pls1 address of the wearer's key
    beat: int
    pod_ref: str | None = None
    capture_digest: str | None = None

    def __post_init__(self) -> None:
        _require_str("geohash", self.geohash)
        if not set(self.geohash) <= _GEOHASH_ALPHABET:
            raise ValueError("geohash contains non-base32 characters")
        _require_int("alt_band", self.alt_band)
        _require_str("label", self.label)
        _require_str("backend", self.backend)
        if self.backend not in RECOGNITION_BACKENDS:
            raise ValueError(f"backend must be one of {RECOGNITION_BACKENDS}")
        _require_int("confidence_milli", self.confidence_milli)
        if not 0 <= self.confidence_milli <= CONFIDENCE_MILLI_EXACT:
            raise ValueError(
                f"confidence_milli must be in [0, {CONFIDENCE_MILLI_EXACT}]"
            )
        _require_str("target", self.target)
        _require_str("observer", self.observer)
        if not crypto.is_valid_address(self.observer):
            raise ValueError("observer must be a valid pls1 address")
        _require_int("beat", self.beat)
        if self.beat < 0:
            raise ValueError("beat must be non-negative")
        if self.pod_ref is not None:
            _require_str("pod_ref", self.pod_ref)
        if self.capture_digest is not None:
            _require_str("capture_digest", self.capture_digest)
            if not crypto.is_valid_hex(self.capture_digest, 32):
                raise ValueError("capture_digest must be 32 bytes of hex (SHA-256)")

    # -- the declared float -> integer boundary ----------------------------

    @classmethod
    def from_recognition(
        cls,
        result,
        *,
        geohash: str,
        alt_band: int,
        label: str,
        observer: str,
        beat: int,
        pod_ref: str | None = None,
        capture: bytes | None = None,
    ) -> "FieldObservation":
        """Build an observation from a :class:`RecognitionResult`.

        This is the one place a device-side float confidence becomes fabric
        state: ``confidence_milli = int(result.confidence * 1000)``. An
        unresolved result (``resolver_key is None``) is not an observation and
        raises ``ValueError`` — there is nothing to bind.

        ``capture``, when given, is digested to ``capture_digest`` here and the
        raw bytes are *dropped*: they stay wherever the wearer keeps them
        (their pod), never in the record.
        """
        if result.resolver_key is None:
            raise ValueError("cannot observe an unresolved recognition result")
        digest = crypto.sha256_hex(capture) if capture is not None else None
        return cls(
            geohash=geohash,
            alt_band=alt_band,
            label=label,
            backend=result.backend,
            confidence_milli=int(float(result.confidence) * 1000),
            target=result.resolver_key,
            observer=observer,
            beat=beat,
            pod_ref=pod_ref,
            capture_digest=digest,
        )

    # -- strict record round trip ------------------------------------------

    _RECORD_FIELDS = frozenset({
        "kind", "geohash", "alt_band", "label", "backend", "confidence_milli",
        "target", "observer", "beat", "pod_ref", "capture_digest",
    })

    @classmethod
    def from_record(cls, record: dict) -> "FieldObservation":
        """Rebuild an observation from a woven/received record — strictly.

        Anything that is not exactly a field-observation record is refused:
        wrong ``kind``, unknown fields, or missing required fields all raise.
        Every value constraint re-runs through ``__post_init__``, so a peer's
        record gets the same validation as a locally built one.
        """
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")
        if record.get("kind") != OBSERVATION_KIND:
            raise ValueError(f"record kind must be {OBSERVATION_KIND!r}")
        unknown = set(record) - cls._RECORD_FIELDS
        if unknown:
            raise ValueError(f"unknown record fields: {sorted(unknown)}")
        missing = {"geohash", "alt_band", "label", "backend", "confidence_milli",
                   "target", "observer", "beat"} - set(record)
        if missing:
            raise ValueError(f"missing record fields: {sorted(missing)}")
        return cls(
            geohash=record["geohash"],
            alt_band=record["alt_band"],
            label=record["label"],
            backend=record["backend"],
            confidence_milli=record["confidence_milli"],
            target=record["target"],
            observer=record["observer"],
            beat=record["beat"],
            pod_ref=record.get("pod_ref"),
            capture_digest=record.get("capture_digest"),
        )

    # -- confirmation contract ---------------------------------------------

    @property
    def requires_confirmation(self) -> bool:
        """True when a user/agent must confirm before this may be woven."""
        return self.confidence_milli < CONFIDENCE_MILLI_EXACT

    # -- canonical record ---------------------------------------------------

    def to_record(self) -> dict:
        """The float-free canonical record (optional fields omitted, not null)."""
        record = {
            "kind": OBSERVATION_KIND,
            "geohash": self.geohash,
            "alt_band": self.alt_band,
            "label": self.label,
            "backend": self.backend,
            "confidence_milli": self.confidence_milli,
            "target": self.target,
            "observer": self.observer,
            "beat": self.beat,
        }
        if self.pod_ref is not None:
            record["pod_ref"] = self.pod_ref
        if self.capture_digest is not None:
            record["capture_digest"] = self.capture_digest
        return record

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def anchor(self, precision: int | None = None) -> SpatialAnchor:
        """The spatial anchor binding this observation to its cell.

        The anchor's ``target`` is the observation's own CID, so a
        :class:`~knitweb.fabric.spatial_index.SpatialIndex` at the wearer's
        location surfaces the observation directly.
        """
        gh = self.geohash if precision is None else self.geohash[:precision]
        return SpatialAnchor(geohash=gh, target=self.cid, alt_band=self.alt_band)

    def weave(self, web) -> tuple[str, str]:
        """Weave record + spatial anchor into ``web``; return both CIDs."""
        obs_cid = web.weave(self.to_record())
        anchor_cid = self.anchor().weave(web)
        return obs_cid, anchor_cid


def attest_observation(observation: FieldObservation, observer_priv: str) -> Attestation:
    """Sign an observation with the wearer's key (standard attestation envelope).

    The record's ``observer`` address must derive from ``observer_priv`` — a
    glass can only attest what its own key claims, exactly like any other
    fabric item (see :func:`knitweb.fabric.attest.attest`).
    """
    return attest(observation.to_record(), observer_priv, author_field="observer")
