"""Knitweb chemistry record schema — canonical field set, version, and CID stability.

All field orderings here are FROZEN.  Adding fields, reordering, or renaming
any key in :func:`chemistry_node_record` or :func:`bond_edge_record` WILL change
CIDs for all downstream records and break peer-sync byte-identity.  Gate changes
through a schema migration note (see :data:`SCHEMA_VERSION`).
"""
from .schema import (
    SCHEMA_VERSION,
    chemistry_node_record,
    bond_edge_record,
    GOLDEN_CIDS,
)

__all__ = [
    "SCHEMA_VERSION",
    "chemistry_node_record",
    "bond_edge_record",
    "GOLDEN_CIDS",
]
