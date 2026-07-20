"""CID-stability sign-off for the chemistry record schema (pulse #210).

These tests are the HARD GATE: any change to the canonical field set,
field ordering, value types, or encoder that alters a golden CID means a
breaking schema migration and must be reviewed.

Golden CIDs were computed once from the canonical encoder and are now
pinned.  A failing test here is NOT a test bug — it is evidence of a
byte-identity break that MUST be resolved before this branch merges.
"""

from __future__ import annotations

import pytest

from knitweb.chemistry.schema import (
    GOLDEN_CIDS,
    SCHEMA_VERSION,
    bond_edge_record,
    chemistry_node_record,
)
from knitweb.core.canonical import cid as canonical_cid, encode as canonical_encode


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_schema_version_is_integer():
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


# ---------------------------------------------------------------------------
# chemistry_node_record: field set and types
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_chemistry_node_record_field_set():
    rec = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    assert set(rec.keys()) == {"formula", "kind", "name_en", "name_nl", "schema_version"}


@pytest.mark.property
def test_chemistry_node_record_no_float():
    rec = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    for v in rec.values():
        assert not isinstance(v, float), f"float in chemistry-node record: {v!r}"


@pytest.mark.property
def test_chemistry_node_record_kind():
    rec = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    assert rec["kind"] == "chemistry-node"
    assert rec["schema_version"] == SCHEMA_VERSION


@pytest.mark.property
def test_chemistry_node_record_invalid_raises():
    with pytest.raises(ValueError):
        chemistry_node_record(formula="", name_en="Water", name_nl="Water")
    with pytest.raises(ValueError):
        chemistry_node_record(formula="H2O", name_en=123, name_nl="Water")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# bond_edge_record: field set and types
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_bond_edge_record_field_set():
    rec = bond_edge_record(from_formula="H2O", to_formula="CO2", relation="reacts-with")
    assert set(rec.keys()) == {
        "from_formula", "kind", "relation", "schema_version", "to_formula", "weight"
    }


@pytest.mark.property
def test_bond_edge_weight_is_integer():
    rec = bond_edge_record(from_formula="H2O", to_formula="CO2", relation="reacts-with", weight=3)
    assert isinstance(rec["weight"], int) and not isinstance(rec["weight"], bool)
    assert rec["weight"] == 3


@pytest.mark.property
def test_bond_edge_weight_no_float():
    with pytest.raises(ValueError):
        bond_edge_record(from_formula="H2O", to_formula="CO2", relation="r", weight=1.5)  # type: ignore[arg-type]


@pytest.mark.property
def test_bond_edge_negative_weight_raises():
    with pytest.raises(ValueError):
        bond_edge_record(from_formula="H2O", to_formula="CO2", relation="r", weight=-1)


# ---------------------------------------------------------------------------
# CID round-trip: same input → same CID (content-addressing idempotency)
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_chemistry_node_cid_stable_across_calls():
    rec1 = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    rec2 = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    assert canonical_cid(rec1) == canonical_cid(rec2)


@pytest.mark.property
def test_bond_edge_cid_stable_across_calls():
    rec1 = bond_edge_record(from_formula="H2O", to_formula="CO2", relation="reacts-with")
    rec2 = bond_edge_record(from_formula="H2O", to_formula="CO2", relation="reacts-with")
    assert canonical_cid(rec1) == canonical_cid(rec2)


@pytest.mark.property
def test_cid_changes_when_field_changes():
    rec_en = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    rec_nl = chemistry_node_record(formula="H2O", name_en="H2O", name_nl="Water")
    assert canonical_cid(rec_en) != canonical_cid(rec_nl)


# ---------------------------------------------------------------------------
# GOLDEN CID VECTORS — the hard gate
#
# If any of these fail, a byte-identity break has occurred.
# This is a schema migration requiring an explicit review.
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_golden_cid_chemistry_node_h2o():
    rec = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
    computed = canonical_cid(rec)
    pinned = GOLDEN_CIDS["chemistry-node:H2O"]
    assert computed == pinned, (
        f"BYTE-IDENTITY BREAK: chemistry-node:H2O CID changed!\n"
        f"  expected (pinned): {pinned}\n"
        f"  computed now:      {computed}\n"
        f"This is a schema migration — review before merging."
    )


@pytest.mark.property
def test_golden_cid_chemistry_node_nacl():
    rec = chemistry_node_record(formula="NaCl", name_en="Table salt", name_nl="Keukenzout")
    computed = canonical_cid(rec)
    pinned = GOLDEN_CIDS["chemistry-node:NaCl"]
    assert computed == pinned, (
        f"BYTE-IDENTITY BREAK: chemistry-node:NaCl CID changed!\n"
        f"  expected (pinned): {pinned}\n"
        f"  computed now:      {computed}"
    )


@pytest.mark.property
def test_golden_cid_bond_edge_h2o_co2():
    rec = bond_edge_record(
        from_formula="H2O", to_formula="CO2", relation="reacts-with", weight=1
    )
    computed = canonical_cid(rec)
    pinned = GOLDEN_CIDS["bond-edge:H2O->CO2:reacts-with"]
    assert computed == pinned, (
        f"BYTE-IDENTITY BREAK: bond-edge:H2O->CO2:reacts-with CID changed!\n"
        f"  expected (pinned): {pinned}\n"
        f"  computed now:      {computed}"
    )


@pytest.mark.property
def test_all_golden_cids_present():
    """Every entry in GOLDEN_CIDS is reachable and non-empty."""
    assert len(GOLDEN_CIDS) >= 3
    for key, cid_val in GOLDEN_CIDS.items():
        assert isinstance(cid_val, str) and cid_val.startswith("b"), (
            f"golden CID for {key!r} has unexpected format: {cid_val!r}"
        )


@pytest.mark.property
def test_canonical_encode_is_deterministic():
    """Same chemistry-node record encodes to identical bytes every call."""
    rec = chemistry_node_record(formula="CO2", name_en="Carbon dioxide", name_nl="Koolstofdioxide")
    b1 = canonical_encode(rec)
    b2 = canonical_encode(rec)
    assert b1 == b2


# ---------------------------------------------------------------------------
# Cross-version identity: schema_version is bound into the CID, so a v2 record
# can never collide with a v1 record (#210 — cross-version byte-identity).
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_schema_version_is_bound_into_cid():
    v1 = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water",
                               schema_version=1)
    v2 = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water",
                               schema_version=2)
    assert canonical_cid(v1) != canonical_cid(v2), (
        "schema_version must change the CID — otherwise a migrated record could "
        "collide with a v1 record."
    )
    # the pinned golden is the v1 (current SCHEMA_VERSION) value
    assert canonical_cid(v1) == GOLDEN_CIDS["chemistry-node:H2O"]
