"""Cross-repo contract: verify the committed weave-core fixture byte-for-byte.

`Knitweb/weave-core` commits a fully deterministic signed finding envelope
(`tests/fixtures/pulse_contract_finding.json`, regenerated only intentionally
by `scripts/make_pulse_contract_fixture.py`); this suite carries the same
bytes as `tests/fixtures/geoweave_pulse_contract.json`. If either repo changes
its canonical serialization, signing, or envelope shape, one of the two suites
goes red instead of the repos drifting apart silently. (PAR maturity plan, M0.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knitweb.core import crypto
from knitweb.edge.recognize import CONFIDENCE_EXACT
from knitweb.fabric.spatial import geohash
from knitweb.geoweave.bridge import finding_to_observation, verify_finding

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "geoweave_pulse_contract.json"


def _envelope() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.mark.property
def test_weave_core_fixture_verifies_here():
    envelope = _envelope()
    assert verify_finding(envelope), (
        "weave-core's committed contract fixture no longer verifies — the two "
        "repos' canonical forms have drifted; fix the bridge or sync the fixture"
    )
    tampered = {**envelope, "body": {**envelope["body"], "label": "gold_bar"}}
    assert not verify_finding(tampered)


@pytest.mark.property
def test_fixture_crosses_into_the_expected_observation():
    envelope = _envelope()
    priv, _pub = crypto.generate_keypair()
    observation, attestation = finding_to_observation(
        envelope,
        target_map={"leaching_pot": "bafyreilp001"},
        importer_priv=priv,
        beat=5,
    )
    body = envelope["body"]
    position = body["geopose"]["position"]
    assert observation.geohash == geohash(position["lat"], position["lon"], 9)
    assert observation.alt_band == int(position["h"] // 3)
    assert observation.confidence_milli == int(body["confidence"] * 1000) == 870
    assert observation.confidence_milli < int(CONFIDENCE_EXACT * 1000)  # gate stays on
    assert observation.capture_digest == body["image_sha256"]
    assert observation.label == "leaching_pot"
    assert attestation.verify(author_field="observer")
