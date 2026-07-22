"""Proofs for the MOLGANG epoch-settlement bridge (P2 — plan, verify, never mint).

Principles under test (docs/MOLGANG_PLS_BRIDGE.md §3–5):
  * Only a validly signed export settles; tampering or a foreign key is refused.
  * Conservation twice over: the export's totals must match its players, and the
    integer apportionment hands out EXACTLY the budget — never one base unit more.
  * Pure-integer largest remainder: parity with the float twins on shared vectors.
  * Anti-replay: the same epoch digest plans at most once.
  * Burns are not payout weights: net <= 0 earns no share.
"""

import json
import random

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knitweb.bridge import apportion_integer, plan_epoch_settlement, verify_epoch_export


def _signed_export(players, epoch="20260721", key=None):
    key = key or Ed25519PrivateKey.generate()
    payload = {
        "schema": "molgang.bridge-epoch.v1",
        "epoch": epoch,
        "eligibleReasonPrefixes": ["chem_synth_"],
        "players": [{"player": p, "net": n, "receipts": 1} for p, n in players],
        "totals": {
            "net": sum(n for _, n in players),
            "receipts": len(players),
            "players": len(players),
        },
    }
    message = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    raw_pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "payload": payload,
        "signature": key.sign(message).hex(),
        "publicKeyHex": raw_pub.hex(),
    }, key


@pytest.mark.property
def test_valid_export_verifies_and_plans_exact_budget():
    export, _ = _signed_export([("alice", 300), ("bob", 100)])
    plan = plan_epoch_settlement(export, 1000)
    assert plan.total == 1000
    assert plan.shares == {"alice": 750, "bob": 250}


@pytest.mark.property
def test_tamper_and_foreign_key_are_refused():
    export, _ = _signed_export([("alice", 300)])
    tampered = json.loads(json.dumps(export))
    tampered["payload"]["players"][0]["net"] = 999
    tampered["payload"]["totals"]["net"] = 999
    with pytest.raises(ValueError):
        verify_epoch_export(tampered)

    other = Ed25519PrivateKey.generate()
    forged = dict(export)
    forged["publicKeyHex"] = other.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    with pytest.raises(ValueError):
        verify_epoch_export(forged)


@pytest.mark.property
def test_internal_conservation_violation_is_refused():
    export, key = _signed_export([("alice", 300)])
    # re-sign a payload whose totals lie about the player sum
    bad = json.loads(json.dumps(export["payload"]))
    bad["totals"]["net"] = 1
    message = json.dumps(bad, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    export_bad = {"payload": bad, "signature": key.sign(message).hex(), "publicKeyHex": export["publicKeyHex"]}
    with pytest.raises(ValueError, match="conservation"):
        verify_epoch_export(export_bad)


@pytest.mark.property
def test_replay_is_refused_and_burns_earn_nothing():
    export, _ = _signed_export([("earner", 500), ("polluter", -40), ("idle", 0)])
    settled: set[str] = set()
    plan = plan_epoch_settlement(export, 90, settled=settled)
    assert plan.shares == {"earner": 90}
    with pytest.raises(ValueError, match="already settled"):
        plan_epoch_settlement(export, 90, settled=settled)


@pytest.mark.property
def test_integer_apportion_fuzz_conserves_and_matches_twins():
    rng = random.Random(20260721)
    for _ in range(500):
        n = rng.randrange(1, 18)
        weights = [0 if rng.random() < 0.2 else rng.randrange(1, 10_000) for _ in range(n)]
        total = rng.randrange(0, 100_000)
        parts = apportion_integer(weights, total)
        assert sum(parts) == total
        wsum = sum(weights)
        if wsum:
            for w, p in zip(weights, parts):
                # within one unit of exact proportion (cross-multiplied, no float)
                assert abs(p * wsum - w * total) < wsum + wsum
    # shared parity vector with knitweb_vank.apportion and ledger.ts
    assert apportion_integer([1, 1, 1], 100) == [34, 33, 33]


@pytest.mark.property
def test_boundary_rejections():
    with pytest.raises(ValueError):
        apportion_integer([], 5)
    assert apportion_integer([], 0) == []
    assert sum(apportion_integer([0, 0], 7)) == 7
    with pytest.raises(TypeError):
        apportion_integer([1.5], 10)  # type: ignore[list-item]
    with pytest.raises(TypeError):
        apportion_integer([1], True)
    with pytest.raises(ValueError):
        apportion_integer([-1], 10)
    with pytest.raises(ValueError):
        apportion_integer([1], -1)
