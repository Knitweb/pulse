"""Proofs for the Solid pod-vault seam and the WebID link record.

Covers:
  * honest refusal without a bridge (PodUnavailable, never a silent no-op);
  * content-addressed capture storage: pod_ref path IS the digest, and the
    stored pair plugs straight into GlassObserver.observe / FieldObservation;
  * tamper-evident retrieval (corrupted vault bytes are caught at read);
  * canonical observation archive round trip (CID re-checked on fetch);
  * WebIdLink: float-free record, validation, self-link-only signing,
    tamper refusal, latest-beat-wins lookup, and observers_for.
"""

from __future__ import annotations

import pytest

from knitweb.core import canonical, crypto
from knitweb.edge.observer import GlassObserver
from knitweb.edge.recognize import MarkerBackend, recognize
from knitweb.fabric.web import Web
from knitweb.solid.pod import (
    CAPTURES_CONTAINER,
    MemoryPodBridge,
    PodError,
    PodUnavailable,
    PodVault,
)
from knitweb.solid.webid import (
    WebIdLink,
    link_webid,
    observers_for,
    verify_link,
    webid_for,
)

_POT_CID = "bafyreilp001"
_AMS = (52.3702, 4.8952)
_FRAME = b"\x89PNG-fake-frame-bytes"


# --- vault seam ------------------------------------------------------------

@pytest.mark.property
def test_no_bridge_refuses_honestly():
    vault = PodVault()
    with pytest.raises(PodUnavailable):
        vault.store_capture(_FRAME)
    with pytest.raises(PodUnavailable):
        vault.fetch_capture("00" * 32)


@pytest.mark.property
def test_capture_path_is_its_digest():
    bridge = MemoryPodBridge()
    vault = PodVault(bridge)
    pod_ref, digest = vault.store_capture(_FRAME)
    assert digest == crypto.sha256_hex(_FRAME)
    assert pod_ref == bridge.base_url + CAPTURES_CONTAINER + digest
    assert vault.fetch_capture(digest) == _FRAME
    assert vault.verify_capture(digest)


@pytest.mark.property
def test_tampered_vault_is_caught_at_read():
    bridge = MemoryPodBridge()
    vault = PodVault(bridge)
    _pod_ref, digest = vault.store_capture(_FRAME)
    bridge.corrupt(CAPTURES_CONTAINER + digest)
    with pytest.raises(PodError):
        vault.fetch_capture(digest)
    assert not vault.verify_capture(digest)


@pytest.mark.property
def test_vault_pair_plugs_into_observation_flow():
    """store_capture's (pod_ref, digest) matches what the record derives itself."""
    vault = PodVault(MemoryPodBridge())
    pod_ref, digest = vault.store_capture(_FRAME)

    priv, _pub = crypto.generate_keypair()
    glass = GlassObserver(priv, *_AMS, precision=9)
    result = recognize("qr:pot-7", MarkerBackend({"qr:pot-7": _POT_CID}))
    observation = glass.observe(
        result, label="qr:pot-7", beat=1, pod_ref=pod_ref, capture=_FRAME
    )
    record = observation.to_record()
    assert record["capture_digest"] == digest       # both sides agree by construction
    assert record["pod_ref"] == pod_ref
    # the original is retrievable from the vault by exactly that digest
    assert vault.fetch_capture(record["capture_digest"]) == _FRAME


@pytest.mark.property
def test_observation_archive_round_trip_and_cid_check():
    vault = PodVault(MemoryPodBridge())
    priv, _pub = crypto.generate_keypair()
    glass = GlassObserver(priv, *_AMS, precision=9)
    result = recognize("qr:pot-7", MarkerBackend({"qr:pot-7": _POT_CID}))
    observation = glass.observe(result, label="qr:pot-7", beat=1)

    vault.store_observation(observation)
    fetched = vault.fetch_observation(observation.cid)
    assert fetched == observation.to_record()
    assert canonical.cid(fetched) == observation.cid


# --- WebID link -------------------------------------------------------------

@pytest.mark.property
def test_webid_link_record_is_float_free_and_validated():
    priv, _pub = crypto.generate_keypair()
    link, _att = link_webid("https://alice.pod.example/profile/card#me", priv, beat=3)
    canonical.encode(link.to_record())          # float-free by construction
    with pytest.raises(ValueError):
        WebIdLink(webid="ftp://nope", observer=link.observer, beat=1)
    with pytest.raises(ValueError):
        WebIdLink(webid="https://ok.example/#me", observer="not-an-address", beat=1)
    with pytest.raises(ValueError):
        WebIdLink(webid="https://ok.example/#me", observer=link.observer, beat=-1)


@pytest.mark.property
def test_link_signs_only_its_own_key_and_tamper_fails():
    priv, pub = crypto.generate_keypair()
    link, attestation = link_webid("https://alice.pod.example/#me", priv, beat=1)
    assert verify_link(attestation.record, attestation.author_pub, attestation.sig)

    # tampered webid: signature no longer covers the record
    tampered = dict(attestation.record)
    tampered["webid"] = "https://mallory.pod.example/#me"
    assert not verify_link(tampered, attestation.author_pub, attestation.sig)

    # a different key cannot attest this record at all
    other_priv, _other_pub = crypto.generate_keypair()
    from knitweb.fabric.attest import attest
    with pytest.raises(ValueError):
        attest(link.to_record(), other_priv, author_field="observer")


@pytest.mark.property
def test_webid_lookup_latest_beat_wins():
    priv, _pub = crypto.generate_keypair()
    web = Web()
    old, _ = link_webid("https://old.pod.example/#me", priv, beat=1)
    new, _ = link_webid("https://new.pod.example/#me", priv, beat=7)
    old.weave(web)
    new.weave(web)
    assert webid_for(web, old.observer) == "https://new.pod.example/#me"
    assert webid_for(web, "pls1qqqqqqqq") is None
    assert observers_for(web, "https://old.pod.example/#me") == [old.observer]
