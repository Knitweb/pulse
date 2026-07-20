"""Proofs for field observations — the confidence-gated producer side of AR.

Covers:
  * float-free canonical records with deterministic CIDs;
  * the declared float→integer confidence boundary (``confidence_milli``);
  * the confirmation gate: probabilistic recognitions never bind durably
    unconfirmed, exact (marker) recognitions bind immediately;
  * raw captures reduced to digests — bytes never enter the record;
  * attestation validate-at-read (tamper ⇒ refuse);
  * spatial round trip: a woven observation is discoverable by a wearer's
    SpatialIndex at the same cell, and not from far away.
"""

from __future__ import annotations

import pytest

from knitweb.core import canonical, crypto
from knitweb.edge.observer import GlassObserver, overlay_near
from knitweb.edge.recognize import (
    EmbeddingBackend,
    MarkerBackend,
    SceneSemanticBackend,
    recognize,
)
from knitweb.fabric.attest import verify_record
from knitweb.fabric.observation import (
    CONFIDENCE_MILLI_EXACT,
    FieldObservation,
    attest_observation,
)
from knitweb.fabric.spatial import geohash
from knitweb.fabric.spatial_index import SpatialIndex
from knitweb.fabric.web import Web

_POT_CID = "bafyreilp001"

# Amsterdam and Paris, well apart; float coords are transient only.
_AMS = (52.3702, 4.8952)
_PARIS = (48.8566, 2.3522)


def _observer(lat: float = _AMS[0], lon: float = _AMS[1]) -> GlassObserver:
    priv, _pub = crypto.generate_keypair()
    return GlassObserver(priv, lat, lon, precision=9)


def _marker_result():
    backend = MarkerBackend({"qr:pot-7": _POT_CID})
    return recognize("qr:pot-7", backend)


def _semantic_result(confidence: float = 0.87):
    backend = SceneSemanticBackend({"leaching_pot": (_POT_CID, confidence)})
    return recognize("leaching_pot", backend)


# --- canonical record -----------------------------------------------------

@pytest.mark.property
def test_observation_record_is_float_free_and_deterministic():
    glass = _observer()
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=5)
    record = observation.to_record()
    # canonical.encode rejects floats — encoding must succeed as-is
    canonical.encode(record)
    assert isinstance(record["confidence_milli"], int)
    assert observation.cid == FieldObservation(**{
        f: getattr(observation, f)
        for f in ("geohash", "alt_band", "label", "backend", "confidence_milli",
                  "target", "observer", "beat", "pod_ref", "capture_digest")
    }).cid


@pytest.mark.property
def test_optional_fields_omitted_not_null():
    glass = _observer()
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    record = observation.to_record()
    assert "pod_ref" not in record
    assert "capture_digest" not in record


@pytest.mark.property
def test_confidence_milli_is_the_declared_boundary():
    glass = _observer()
    observation = glass.observe(_semantic_result(0.87), label="leaching_pot", beat=1)
    assert observation.confidence_milli == 870          # int(0.87 * 1000)
    exact = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    assert exact.confidence_milli == CONFIDENCE_MILLI_EXACT


@pytest.mark.property
def test_unresolved_result_cannot_become_observation():
    backend = MarkerBackend({})
    result = recognize("qr:unknown", backend)
    glass = _observer()
    with pytest.raises(ValueError):
        glass.observe(result, label="qr:unknown", beat=1)


@pytest.mark.property
def test_confidence_milli_rejects_floats_and_out_of_range():
    glass = _observer()
    base = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    kwargs = {
        f: getattr(base, f)
        for f in ("geohash", "alt_band", "label", "backend", "target",
                  "observer", "beat")
    }
    with pytest.raises(TypeError):
        FieldObservation(confidence_milli=0.87, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        FieldObservation(confidence_milli=1001, **kwargs)


# --- confirmation gate ----------------------------------------------------

@pytest.mark.property
def test_exact_marker_binds_without_confirmation():
    glass = _observer()
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    assert not observation.requires_confirmation
    assert glass.pending() == []
    web = Web()
    woven = glass.commit(web)
    assert len(woven) == 1


@pytest.mark.property
def test_probabilistic_observation_held_until_confirmed():
    glass = _observer()
    observation = glass.observe(_semantic_result(), label="leaching_pot", beat=1)
    assert observation.requires_confirmation
    assert [o.cid for o in glass.pending()] == [observation.cid]

    web = Web()
    assert glass.commit(web) == []          # nothing confirmed -> nothing woven
    assert web.nodes == {}

    glass.confirm(observation.cid)
    woven = glass.commit(web)
    assert len(woven) == 1
    obs_cid, _anchor_cid, _attestation = woven[0]
    assert obs_cid == observation.cid


@pytest.mark.property
def test_rejected_observation_never_weaves():
    glass = _observer()
    observation = glass.observe(_semantic_result(), label="leaching_pot", beat=1)
    glass.reject(observation.cid)
    assert glass.pending() == []
    with pytest.raises(KeyError):
        glass.confirm(observation.cid)
    assert glass.commit(Web()) == []


@pytest.mark.property
def test_embedding_backend_always_requires_confirmation():
    backend = EmbeddingBackend([([1.0, 0.0], _POT_CID)], threshold=0.5)
    result = recognize([1.0, 0.0], backend)
    glass = _observer()
    observation = glass.observe(result, label="pot-embedding", beat=1)
    assert observation.requires_confirmation


# --- captures stay in the wearer's vault ----------------------------------

@pytest.mark.property
def test_capture_reduced_to_digest_and_pod_ref():
    glass = _observer()
    frame = b"\x89PNG-fake-frame-bytes"
    observation = glass.observe(
        _marker_result(),
        label="qr:pot-7",
        beat=1,
        pod_ref="https://pod.example/field/captures/42",
        capture=frame,
    )
    record = observation.to_record()
    assert record["capture_digest"] == crypto.sha256_hex(frame)
    assert record["pod_ref"] == "https://pod.example/field/captures/42"
    # the raw bytes appear nowhere in the canonical record
    assert frame not in canonical.encode(record)


# --- attestation ----------------------------------------------------------

@pytest.mark.property
def test_attestation_verifies_and_tamper_is_refused():
    priv, pub = crypto.generate_keypair()
    glass = GlassObserver(priv, *_AMS)
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    attestation = attest_observation(observation, priv)
    assert attestation.verify(author_field="observer")

    tampered = dict(attestation.record)
    tampered["label"] = "somebody_elses_pot"
    assert not verify_record(
        tampered, attestation.author_pub, attestation.sig, author_field="observer"
    )


@pytest.mark.property
def test_attestation_requires_the_observers_own_key():
    priv, _ = crypto.generate_keypair()
    other_priv, _ = crypto.generate_keypair()
    glass = GlassObserver(priv, *_AMS)
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    with pytest.raises(ValueError):
        attest_observation(observation, other_priv)


# --- spatial round trip ---------------------------------------------------

@pytest.mark.property
def test_woven_observation_is_discoverable_at_the_same_cell():
    glass = _observer(*_AMS)
    observation = glass.observe(_marker_result(), label="qr:pot-7", beat=1)
    web = Web()
    [(obs_cid, anchor_cid, _att)] = glass.commit(web)
    assert obs_cid in web.nodes and anchor_cid in web.nodes

    index = SpatialIndex.from_web(web)
    here = geohash(*_AMS, 9)
    far = geohash(*_PARIS, 9)
    assert obs_cid in index.near(here, 6)
    assert obs_cid not in index.near(far, 6)

    [entry] = overlay_near(web, index, here, 6)
    assert entry["cid"] == obs_cid
    assert entry["label"] == "qr:pot-7"
    assert entry["target"] == _POT_CID
    assert entry["confidence_milli"] == CONFIDENCE_MILLI_EXACT


@pytest.mark.property
def test_overlay_near_skips_non_observation_anchors():
    web = Web()
    knowledge = web.weave({"kind": "knowledge", "title": "pot"})
    from knitweb.fabric.spatial import bind
    bind(*_AMS, target=knowledge, precision=9).weave(web)
    index = SpatialIndex.from_web(web)
    assert overlay_near(web, index, geohash(*_AMS, 9), 6) == []
