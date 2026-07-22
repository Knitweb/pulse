"""Proofs for the GeoWeave (PAR) bridge and the label-map builder.

A weave-core finding envelope — canonical JSON body, SHA-256 id, Ed25519
signature, did:key observer — is rebuilt here byte-compatibly (using the
``cryptography`` library the ledger already requires) and imported into the
fabric as an attested FieldObservation.

Covers:
  * envelope verification (good, tampered body, wrong id, foreign did);
  * the crossing: float confidence/lat/lon → confidence_milli/geohash at the
    declared boundary; image_sha256 carried as capture_digest;
  * unmapped labels and failing envelopes refuse the import;
  * MOLGANG connection: a chemistry web's titled nodes become the target map,
    and the imported observation lands on the molecule/apparatus CID;
  * did-link record: self-link-only signing, tamper refusal, validation;
  * label_map_from_web: deterministic CID choice + confidence boundary.
"""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from knitweb.core import canonical, crypto
from knitweb.edge.labelmap import label_map_from_web, target_map_from_web
from knitweb.edge.recognize import SceneSemanticBackend, recognize
from knitweb.fabric.spatial import geohash
from knitweb.fabric.spatial_index import SpatialIndex
from knitweb.fabric.web import Web
from knitweb.geoweave.bridge import (
    BridgeVerifyError,
    DidLink,
    canonical_finding_bytes,
    finding_to_observation,
    link_did,
    verify_did_link,
    verify_finding,
)

_AMS = (52.370216, 4.895168)

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58_ALPHABET[r] + out
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + out


def _ed25519_identity() -> tuple[Ed25519PrivateKey, str]:
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return key, "did:key:z" + _b58encode(b"\xed\x01" + raw)


def _envelope(
    label: str = "leaching_pot",
    confidence: float = 0.87,
    lat: float = _AMS[0],
    lon: float = _AMS[1],
    h: float = 6.5,
) -> dict:
    """A byte-compatible weave-core finding envelope, freshly signed."""
    key, did = _ed25519_identity()
    body = {
        "kind": "geoweave.finding", "v": 1,
        "label": label,
        "confidence": round(float(confidence), 4),
        "geopose": {"position": {"lat": lat, "lon": lon, "h": h},
                    "angles": {"yaw": 90.0, "pitch": 0.0, "roll": 0.0}},
        "observer_pose": {"position": {"lat": lat, "lon": lon, "h": 1.6},
                          "angles": {"yaw": 90.0, "pitch": 0.0, "roll": 0.0}},
        "bbox": [100.0, 80.0, 220.0, 190.0],
        "image_sha256": hashlib.sha256(b"fake-frame").hexdigest(),
        "source": "unity-sentis",
        "observed_at": "2026-07-20T12:00:00+00:00",
    }
    data = canonical_finding_bytes(body)
    return {
        "type": "geoweave.finding.announce", "v": 1,
        "id": hashlib.sha256(data).hexdigest(),
        "body": body,
        "did": did,
        "sig": key.sign(data).hex(),
    }


def _molgang_web() -> tuple[Web, str]:
    """A MOLGANG-style chemistry web with one apparatus node."""
    web = Web()
    pot = web.weave({
        "kind": "knowledge",
        "title": "leaching_pot",
        "scope": "public",
        "tags": ["feedstock:Fe-slag", "pH:4.5"],
    })
    web.weave({"kind": "knowledge", "scope": "public"})          # untitled: skipped
    return web, pot


# --- envelope verification ---------------------------------------------------

@pytest.mark.property
def test_envelope_verifies_and_tamper_fails():
    envelope = _envelope()
    assert verify_finding(envelope)

    tampered = {**envelope, "body": {**envelope["body"], "label": "gold_bar"}}
    assert not verify_finding(tampered)          # id no longer matches

    wrong_id = {**envelope, "id": "00" * 32}
    assert not verify_finding(wrong_id)

    _key, other_did = _ed25519_identity()
    swapped = {**envelope, "did": other_did}
    assert not verify_finding(swapped)           # signature from another key


# --- the crossing --------------------------------------------------------------

@pytest.mark.property
def test_finding_becomes_attested_observation_on_the_molgang_target():
    web, pot_cid = _molgang_web()
    targets = target_map_from_web(web)
    priv, _pub = crypto.generate_keypair()

    observation, attestation = finding_to_observation(
        _envelope(), target_map=targets, importer_priv=priv, beat=5
    )
    assert observation.target == pot_cid
    assert observation.backend == "scene_semantic"
    assert observation.confidence_milli == 870            # int(0.87 * 1000)
    assert observation.geohash == geohash(*_AMS, 9)
    assert observation.alt_band == 2                      # 6.5m // 3m bands
    assert observation.capture_digest == hashlib.sha256(b"fake-frame").hexdigest()
    assert observation.requires_confirmation              # probabilistic stays gated
    canonical.encode(observation.to_record())             # float-free record
    assert attestation.verify(author_field="observer")

    # woven observation is discoverable at the finding's cell
    obs_cid, _anchor = observation.weave(web)
    index = SpatialIndex.from_web(web)
    assert obs_cid in index.near(geohash(*_AMS, 9), 6)


@pytest.mark.property
def test_failing_envelope_and_unmapped_label_refuse_import():
    web, _pot = _molgang_web()
    targets = target_map_from_web(web)
    priv, _pub = crypto.generate_keypair()

    bad = _envelope()
    bad["sig"] = "00" * 64
    with pytest.raises(BridgeVerifyError):
        finding_to_observation(bad, target_map=targets, importer_priv=priv, beat=1)

    unmapped = _envelope(label="bicycle")                  # COCO class, not woven
    with pytest.raises(BridgeVerifyError):
        finding_to_observation(unmapped, target_map=targets, importer_priv=priv, beat=1)


# --- did-link -------------------------------------------------------------------

@pytest.mark.property
def test_did_link_self_sign_and_tamper_refusal():
    _key, did = _ed25519_identity()
    priv, _pub = crypto.generate_keypair()
    link, attestation = link_did(did, priv, beat=3)
    assert verify_did_link(attestation.record, attestation.author_pub, attestation.sig)

    _key2, other_did = _ed25519_identity()
    tampered = {**attestation.record, "did": other_did}
    assert not verify_did_link(tampered, attestation.author_pub, attestation.sig)

    with pytest.raises(ValueError):
        DidLink(did="did:web:nope.example", observer=link.observer, beat=1)
    with pytest.raises(ValueError):
        DidLink(did=did, observer="not-an-address", beat=1)
    canonical.encode(link.to_record())                     # float-free record


# --- label maps ------------------------------------------------------------------

@pytest.mark.property
def test_label_map_feeds_scene_semantic_backend():
    web, pot_cid = _molgang_web()
    backend = SceneSemanticBackend(label_map_from_web(web, class_confidence_milli=900))
    result = recognize("leaching_pot", backend)
    assert result.resolver_key == pot_cid
    assert result.requires_confirmation                    # 0.9 < 1.0 keeps the gate
    assert recognize("unknown_thing", backend).resolver_key is None


@pytest.mark.property
def test_target_map_is_deterministic_on_title_collisions():
    web = Web()
    a = web.weave({"kind": "knowledge", "title": "pot", "n": 1})
    b = web.weave({"kind": "knowledge", "title": "pot", "n": 2})
    assert target_map_from_web(web)["pot"] == min(a, b)    # smallest CID, every peer agrees

    with pytest.raises(ValueError):
        label_map_from_web(web, class_confidence_milli=1001)
    with pytest.raises(TypeError):
        label_map_from_web(web, class_confidence_milli=0.9)  # type: ignore[arg-type]


# --- SDK facade -------------------------------------------------------------

@pytest.mark.property
def test_sdk_import_geoweave_findings_one_call():
    from knitweb.sdk import import_geoweave_findings

    web, pot_cid = _molgang_web()
    priv, _pub = crypto.generate_keypair()
    result = import_geoweave_findings(
        [_envelope(), _envelope(label="bicycle")],   # one mapped, one not
        web=web, importer_priv=priv, beat=7,
    )
    assert result["skipped_unmapped"] == ["bicycle"]
    [(obs_cid, anchor_cid, attestation)] = result["imported"]
    assert obs_cid in web.nodes and anchor_cid in web.nodes
    assert web.nodes[obs_cid]["target"] == pot_cid
    assert attestation.verify(author_field="observer")

    forged = _envelope()
    forged["sig"] = "00" * 64
    with pytest.raises(BridgeVerifyError):
        import_geoweave_findings([forged], web=web, importer_priv=priv, beat=8)
