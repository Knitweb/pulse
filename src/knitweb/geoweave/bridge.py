"""Verify GeoWeave finding envelopes and re-express them as field observations.

A GeoWeave *finding envelope* is the P2P wire format of `Knitweb/weave-core`::

    {
      "type": "geoweave.finding.announce", "v": 1,
      "id":   "<sha256-hex of canonical JSON body>",
      "body": {
        "kind": "geoweave.finding", "v": 1,
        "label": "bicycle", "confidence": 0.87,
        "geopose": {"position": {"lat": .., "lon": .., "h": ..}, "angles": {...}},
        "observer_pose": {...}, "bbox": [..],
        "image_sha256": "<sha256-hex of the frame (frame stays local)>",
        "source": "server-yolo" | "client-webgpu" | "unity-sentis",
        "observed_at": "<iso8601>"
      },
      "did": "did:key:z...",   # ed25519-pub multicodec
      "sig": "<ed25519 signature hex over the canonical body bytes>"
    }

Three explicit boundaries are honored on import:

  * **verify-before-trust** — :func:`verify_finding` re-derives the id and
    checks the Ed25519 signature against the ``did:key`` (using the same
    ``cryptography`` library the ledger already requires; no new dependency).
    A failing envelope refuses the import, always.
  * **float → integer** — the finding's float confidence and float lat/lon
    exist only in the *foreign* JSON. They cross into fabric state as
    ``confidence_milli`` and a geohash string, the same declared boundary
    every observation uses.
  * **label → target CID** — a YOLO class name is not a Web node. The caller
    supplies a ``target_map`` (label → CID), typically built from woven
    knowledge with :func:`knitweb.edge.labelmap.target_map_from_web` — e.g.
    MOLGANG chemistry nodes, so a lab finding lands on the molecule/apparatus
    node the game already weaves. An unmapped label refuses the import
    (nothing to bind is not an error to paper over).

The importing wearer signs the resulting observation with their own ``pls1``
key; :func:`link_did` weaves the record that says *"this did:key and this
address are the same observer"*, so the original Ed25519 identity stays
resolvable from the fabric side.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..core import canonical, crypto
from ..fabric.attest import Attestation, attest, verify_record
from ..fabric.observation import FieldObservation
from ..fabric.spatial import altitude_band, geohash

__all__ = [
    "BridgeVerifyError",
    "FINDING_BODY_KIND",
    "DID_LINK_KIND",
    "canonical_finding_bytes",
    "did_to_ed25519_public",
    "verify_finding",
    "finding_to_observation",
    "DidLink",
    "link_did",
    "verify_did_link",
]

FINDING_BODY_KIND = "geoweave.finding"
DID_LINK_KIND = "did-link"

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_MULTICODEC = b"\xed\x01"


class BridgeVerifyError(Exception):
    """Raised when a GeoWeave envelope fails verification — never import it."""


# -- did:key (ed25519-pub multicodec, base58btc) ----------------------------

def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        try:
            n = n * 58 + _B58_ALPHABET.index(ch)
        except ValueError:
            raise ValueError(f"invalid base58 character {ch!r}") from None
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


def did_to_ed25519_public(did: str) -> Ed25519PublicKey:
    """Resolve a ``did:key:z...`` (ed25519-pub) to a verifying key."""
    if not isinstance(did, str) or not did.startswith("did:key:z"):
        raise ValueError("unsupported did (expected did:key:z...)")
    raw = _b58decode(did[len("did:key:z"):])
    if raw[:2] != _ED25519_MULTICODEC:
        raise ValueError("did:key is not ed25519-pub")
    return Ed25519PublicKey.from_public_bytes(raw[2:])


# -- foreign canonical form --------------------------------------------------

def canonical_finding_bytes(body: dict) -> bytes:
    """weave-core's canonical JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_finding(envelope: dict) -> bool:
    """True iff the envelope's id and Ed25519 signature both check out."""
    try:
        body = envelope["body"]
        if not isinstance(body, dict) or body.get("kind") != FINDING_BODY_KIND:
            return False
        data = canonical_finding_bytes(body)
        if hashlib.sha256(data).hexdigest() != envelope["id"]:
            return False
        public = did_to_ed25519_public(envelope["did"])
        public.verify(bytes.fromhex(envelope["sig"]), data)
        return True
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False


# -- the crossing -------------------------------------------------------------

def finding_to_observation(
    envelope: dict,
    *,
    target_map: dict[str, str],
    importer_priv: str,
    beat: int,
    precision: int = 9,
    pod_ref: str | None = None,
) -> tuple[FieldObservation, Attestation]:
    """Verify a finding and re-express it as an attested field observation.

    ``target_map`` maps detector labels to Web node CIDs (see
    :func:`knitweb.edge.labelmap.target_map_from_web`). The importing wearer
    signs with ``importer_priv``; the finding's ``image_sha256`` becomes the
    observation's ``capture_digest`` (the frame itself stays wherever the
    capturing device kept it — vault-first survives the crossing).

    Raises :class:`BridgeVerifyError` on a failing envelope or unmapped label.
    """
    if not verify_finding(envelope):
        raise BridgeVerifyError("finding envelope failed verification — refusing import")
    body = envelope["body"]
    label = body["label"]
    target = target_map.get(label)
    if target is None:
        raise BridgeVerifyError(f"no target CID mapped for label {label!r}")

    position = body["geopose"]["position"]
    observation = FieldObservation(
        geohash=geohash(float(position["lat"]), float(position["lon"]), precision),
        alt_band=altitude_band(float(position.get("h", 0.0))),
        label=label,
        backend="scene_semantic",
        confidence_milli=int(float(body["confidence"]) * 1000),
        target=target,
        observer=crypto.address(crypto.public_from_private(importer_priv)),
        beat=beat,
        pod_ref=pod_ref,
        capture_digest=body["image_sha256"],
    )
    return observation, attest(observation.to_record(), importer_priv,
                               author_field="observer")


# -- did:key <-> pls1 identity link -------------------------------------------

@dataclass(frozen=True)
class DidLink:
    """A signed claim: this did:key and this pls1 address are the same observer."""

    did: str
    observer: str   # pls1 address of the linking key
    beat: int       # integer Pulse time; latest beat wins on re-link

    def __post_init__(self) -> None:
        # resolving validates the multicodec + base58 payload in one step
        did_to_ed25519_public(self.did)
        if not isinstance(self.observer, str) or not crypto.is_valid_address(self.observer):
            raise ValueError("observer must be a valid pls1 address")
        if isinstance(self.beat, bool) or not isinstance(self.beat, int):
            raise TypeError("beat must be an integer")
        if self.beat < 0:
            raise ValueError("beat must be non-negative")

    def to_record(self) -> dict:
        return {
            "kind": DID_LINK_KIND,
            "did": self.did,
            "observer": self.observer,
            "beat": self.beat,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def weave(self, web) -> str:
        return web.weave(self.to_record())


def link_did(did: str, observer_priv: str, beat: int) -> tuple[DidLink, Attestation]:
    """Create + sign a did-link with the wearer's own pls1 key."""
    observer = crypto.address(crypto.public_from_private(observer_priv))
    link = DidLink(did=did, observer=observer, beat=beat)
    return link, attest(link.to_record(), observer_priv, author_field="observer")


def verify_did_link(record: dict, author_pub: str, sig: str) -> bool:
    """True iff ``record`` is a well-formed did-link the key really signed."""
    if not isinstance(record, dict) or record.get("kind") != DID_LINK_KIND:
        return False
    try:
        DidLink(did=record.get("did"), observer=record.get("observer"),
                beat=record.get("beat"))
    except (TypeError, ValueError):
        return False
    return verify_record(record, author_pub, sig, author_field="observer")
