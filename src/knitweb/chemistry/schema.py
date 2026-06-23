"""Canonical record types for chemistry knit nodes and bond edges.

FIELD ORDERING IS FROZEN.  The canonical CBOR encoder sorts map keys
lexicographically, so the orderings in the docstrings below are what
the encoder actually produces.  Pinned golden CIDs in :data:`GOLDEN_CIDS`
ensure any drift fails loudly in tests.

Schema version: 1.  Bump ONLY with a migration note.
"""

from __future__ import annotations

from knitweb.core.canonical import cid as _cid

__all__ = [
    "SCHEMA_VERSION",
    "chemistry_node_record",
    "bond_edge_record",
    "GOLDEN_CIDS",
]

SCHEMA_VERSION: int = 1


def chemistry_node_record(
    *,
    formula: str,
    name_en: str,
    name_nl: str,
    kind: str = "chemistry-node",
    schema_version: int = SCHEMA_VERSION,
) -> dict:
    """Return the canonical map for a ChemistryNode record.

    Canonical field set (lexicographic key order from CBOR encoder):
        formula, kind, name_en, name_nl, schema_version

    All values are strings or integers — no floats, no booleans on the
    identity path.  ``kind`` MUST remain ``"chemistry-node"`` for all v1
    records; a changed kind yields a different CID (intended).
    """
    if not isinstance(formula, str) or not formula:
        raise ValueError("formula must be a non-empty string")
    if not isinstance(name_en, str):
        raise ValueError("name_en must be a string")
    if not isinstance(name_nl, str):
        raise ValueError("name_nl must be a string")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("schema_version must be an integer")
    return {
        "formula": formula,
        "kind": kind,
        "name_en": name_en,
        "name_nl": name_nl,
        "schema_version": schema_version,
    }


def bond_edge_record(
    *,
    from_formula: str,
    to_formula: str,
    relation: str,
    weight: int = 1,
    kind: str = "bond-edge",
    schema_version: int = SCHEMA_VERSION,
) -> dict:
    """Return the canonical map for a BondEdge record.

    Canonical field set (lexicographic key order from CBOR encoder):
        from_formula, kind, relation, schema_version, to_formula, weight

    ``weight`` MUST be a non-negative integer (never a float) so the CID is
    stable regardless of how the weight was computed.
    """
    if not isinstance(from_formula, str) or not from_formula:
        raise ValueError("from_formula must be a non-empty string")
    if not isinstance(to_formula, str) or not to_formula:
        raise ValueError("to_formula must be a non-empty string")
    if not isinstance(relation, str) or not relation:
        raise ValueError("relation must be a non-empty string")
    if not isinstance(weight, int) or isinstance(weight, bool) or weight < 0:
        raise ValueError("weight must be a non-negative integer")
    return {
        "from_formula": from_formula,
        "kind": kind,
        "relation": relation,
        "schema_version": schema_version,
        "to_formula": to_formula,
        "weight": weight,
    }


# ---------------------------------------------------------------------------
# Golden CID vectors (schema_version=1)
#
# These are computed ONCE from the canonical encoder and then PINNED here.
# Any encoder or field change that alters these values indicates a breaking
# schema migration and must be reviewed before merging.
# ---------------------------------------------------------------------------

_WATER_NODE = chemistry_node_record(formula="H2O", name_en="Water", name_nl="Water")
_SALT_NODE = chemistry_node_record(formula="NaCl", name_en="Table salt", name_nl="Keukenzout")
_H2O_CO2_BOND = bond_edge_record(
    from_formula="H2O", to_formula="CO2", relation="reacts-with", weight=1
)

GOLDEN_CIDS: dict[str, str] = {
    "chemistry-node:H2O": _cid(_WATER_NODE),
    "chemistry-node:NaCl": _cid(_SALT_NODE),
    "bond-edge:H2O->CO2:reacts-with": _cid(_H2O_CO2_BOND),
}
