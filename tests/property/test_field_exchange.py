"""Proofs for glass-to-glass field-observation exchange.

Covers:
  * pack → unpack round trip preserves CIDs and verifies every entry;
  * verify-before-trust is all-or-nothing: one tampered byte, one forged
    signature, or one malformed record refuses the whole bundle;
  * spatial acceptance on the observation's own geohash (no side channel);
  * dedupe on re-receive;
  * received observations weave into a local Web and surface through the
    standard SpatialIndex / overlay_near path;
  * resource bound on bundle size.
"""

from __future__ import annotations

import pytest

from knitweb.core import canonical, crypto
from knitweb.edge.exchange import (
    MAX_BUNDLE_OBSERVATIONS,
    ExchangeVerifyError,
    FieldGlass,
    pack_observations,
    unpack_observations,
)
from knitweb.edge.observer import GlassObserver, overlay_near
from knitweb.edge.recognize import MarkerBackend, recognize
from knitweb.fabric.attest import Attestation
from knitweb.fabric.observation import FieldObservation
from knitweb.fabric.spatial import geohash
from knitweb.fabric.spatial_index import SpatialIndex
from knitweb.fabric.web import Web

_POT_CID = "bafyreilp001"
_AMS = (52.3702, 4.8952)
_PARIS = (48.8566, 2.3522)


def _attested(lat: float, lon: float, marker: str = "qr:pot-7"):
    """One committed, attested observation at (lat, lon)."""
    priv, _pub = crypto.generate_keypair()
    glass = GlassObserver(priv, lat, lon, precision=9)
    result = recognize(marker, MarkerBackend({marker: _POT_CID}))
    glass.observe(result, label=marker, beat=1)
    [(_obs_cid, _anchor_cid, attestation)] = glass.commit(Web())
    return attestation


# --- round trip -----------------------------------------------------------

@pytest.mark.property
def test_pack_unpack_round_trip():
    attestation = _attested(*_AMS)
    data = pack_observations([attestation])
    [(observation, received)] = unpack_observations(data)
    assert canonical.cid(received.record) == canonical.cid(attestation.record)
    assert observation.cid == canonical.cid(attestation.record)
    assert received.verify(author_field="observer")


@pytest.mark.property
def test_pack_refuses_empty_and_unverifiable():
    with pytest.raises(ValueError):
        pack_observations([])
    attestation = _attested(*_AMS)
    other_priv, other_pub = crypto.generate_keypair()
    forged = Attestation(
        record=attestation.record, author_pub=other_pub, sig=attestation.sig
    )
    with pytest.raises(ExchangeVerifyError):
        pack_observations([forged])


# --- all-or-nothing verification ------------------------------------------

@pytest.mark.property
def test_one_tampered_byte_refuses_whole_bundle():
    data = pack_observations([_attested(*_AMS), _attested(*_AMS, marker="qr:pot-8")])
    tampered = bytearray(data)
    tampered[len(tampered) // 2] ^= 0xFF
    with pytest.raises(ExchangeVerifyError):
        unpack_observations(bytes(tampered))


@pytest.mark.property
def test_one_forged_entry_poisons_the_bundle():
    good = _attested(*_AMS)
    victim = _attested(*_AMS, marker="qr:pot-8")
    # forge: victim's record re-signed by an attacker's unrelated key
    attacker_priv, attacker_pub = crypto.generate_keypair()
    sig = crypto.sign(attacker_priv, canonical.encode(victim.record))
    entries = [
        {"record": good.record, "observer_pub": good.author_pub, "sig": good.sig},
        {"record": victim.record, "observer_pub": attacker_pub, "sig": sig},
    ]
    data = canonical.encode(
        {"kind": "field-observation-bundle", "observations": entries}
    )
    with pytest.raises(ExchangeVerifyError):
        unpack_observations(data)


@pytest.mark.property
def test_wrong_kind_and_malformed_records_refused():
    with pytest.raises(ExchangeVerifyError):
        unpack_observations(canonical.encode({"kind": "something-else"}))
    attestation = _attested(*_AMS)
    smuggled = dict(attestation.record)
    smuggled["extra_field"] = "sneaky"
    entries = [{
        "record": smuggled,
        "observer_pub": attestation.author_pub,
        "sig": attestation.sig,
    }]
    data = canonical.encode(
        {"kind": "field-observation-bundle", "observations": entries}
    )
    with pytest.raises(ExchangeVerifyError):
        unpack_observations(data)


@pytest.mark.property
def test_bundle_size_is_bounded():
    attestation = _attested(*_AMS)
    entry = {
        "record": attestation.record,
        "observer_pub": attestation.author_pub,
        "sig": attestation.sig,
    }
    data = canonical.encode({
        "kind": "field-observation-bundle",
        "observations": [entry] * (MAX_BUNDLE_OBSERVATIONS + 1),
    })
    with pytest.raises(ExchangeVerifyError):
        unpack_observations(data)


# --- spatial acceptance + dedupe ------------------------------------------

@pytest.mark.property
def test_receiver_keeps_nearby_drops_faraway():
    ams = _attested(*_AMS)
    paris = _attested(*_PARIS, marker="qr:tour-1")
    data = pack_observations([ams, paris])

    receiver = FieldGlass(*_AMS, precision=5)
    assert receiver.receive(data) == 1
    [entry] = receiver.overlays()
    assert entry["cid"] == canonical.cid(ams.record)

    # same bundle again: everything already known or elsewhere
    assert receiver.receive(data) == 0
    assert receiver.accepted_count == 1


@pytest.mark.property
def test_forged_bundle_leaves_receiver_untouched():
    receiver = FieldGlass(*_AMS, precision=5)
    data = pack_observations([_attested(*_AMS)])
    tampered = bytearray(data)
    tampered[-1] ^= 0x01
    with pytest.raises(ExchangeVerifyError):
        receiver.receive(bytes(tampered))
    assert receiver.accepted_count == 0


@pytest.mark.property
def test_received_observations_serve_through_spatial_index():
    sender = _attested(*_AMS)
    receiver = FieldGlass(*_AMS, precision=5)
    receiver.receive(pack_observations([sender]))

    web = Web()
    [(obs_cid, anchor_cid)] = receiver.weave_into(web)
    assert obs_cid in web.nodes and anchor_cid in web.nodes

    index = SpatialIndex.from_web(web)
    [entry] = overlay_near(web, index, geohash(*_AMS, 9), 6)
    assert entry["cid"] == obs_cid
    assert entry["target"] == _POT_CID


# --- strict from_record ----------------------------------------------------

@pytest.mark.property
def test_from_record_round_trip_and_strictness():
    attestation = _attested(*_AMS)
    rebuilt = FieldObservation.from_record(attestation.record)
    assert rebuilt.to_record() == attestation.record
    with pytest.raises(ValueError):
        FieldObservation.from_record({**attestation.record, "kind": "other"})
    incomplete = dict(attestation.record)
    del incomplete["geohash"]
    with pytest.raises(ValueError):
        FieldObservation.from_record(incomplete)
