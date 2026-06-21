"""Proofs for the stable Lens provenance query contract.

Covers relation-filtered ancestry and origins, deterministic ordering (across repeated
calls and across different insertion orders), and dangling-reference (missing-node)
visibility — a referenced ancestor whose node record is absent must surface in the
result, never be silently dropped.
"""

import pytest

from knitweb.fabric.provenance_contract import (
    ProvenanceQueryResult,
    provenance_query,
)
from knitweb.fabric.web import Web


def _chain():
    # ore (origin) -> smelting -> ingot -> machining -> part (product)
    # each derived record links to what it came from via "derived-from".
    web = Web()
    ore = web.weave({"kind": "material", "sku": "IRON-ORE"})
    smelt = web.weave({"kind": "process", "op": "smelting"})
    ingot = web.weave({"kind": "material", "sku": "IRON-INGOT"})
    mach = web.weave({"kind": "process", "op": "machining"})
    part = web.weave({"kind": "material", "sku": "GEAR"})
    web.link(smelt, ore, "derived-from")
    web.link(ingot, smelt, "derived-from")
    web.link(mach, ingot, "derived-from")
    web.link(part, mach, "derived-from")
    return web, dict(ore=ore, smelt=smelt, ingot=ingot, mach=mach, part=part)


@pytest.mark.property
def test_relation_filtered_ancestry_present_to_full_depth():
    web, n = _chain()
    # an unrelated edge type must not widen the present set when rels is restricted
    web.link(n["part"], n["ore"], "mentions")
    res = provenance_query(web, n["part"], rels={"derived-from"})
    assert isinstance(res, ProvenanceQueryResult)
    assert res.root == n["part"]
    assert res.rels == ("derived-from",)
    # full chain back to the ore, all present, start excluded, sorted
    assert set(res.present) == {n["mach"], n["ingot"], n["smelt"], n["ore"]}
    assert n["part"] not in res.present
    assert res.missing == ()
    assert not res.has_dangling


@pytest.mark.property
def test_relation_filter_scopes_origins():
    web, n = _chain()
    # an unrelated "mentions" leaf must not be counted as a provenance origin
    extra = web.weave({"kind": "note", "txt": "see also"})
    web.link(n["part"], extra, "mentions")
    res = provenance_query(web, n["part"], rels={"derived-from"})
    assert res.origin_present == (n["ore"],)          # only the raw-material leaf
    assert extra not in res.present                   # mentions edge not followed
    # following every edge type does pull the mentions leaf in as an origin
    res_all = provenance_query(web, n["part"], rels=None)
    assert res_all.rels is None
    assert extra in res_all.origin_present


@pytest.mark.property
def test_deterministic_across_repeated_calls():
    web, n = _chain()
    a = provenance_query(web, n["part"], rels={"derived-from"})
    b = provenance_query(web, n["part"], rels={"derived-from"})
    assert a == b                                     # frozen dataclass value-equality
    # every reported list is sorted by CID
    for field in (a.present, a.missing, a.origin_present, a.origin_missing):
        assert list(field) == sorted(field)


@pytest.mark.property
def test_deterministic_across_insertion_orders():
    # Build the same DAG two ways: weave/link in different orders, same content.
    records = {
        "ore": {"kind": "material", "sku": "IRON-ORE"},
        "smelt": {"kind": "process", "op": "smelting"},
        "ingot": {"kind": "material", "sku": "IRON-INGOT"},
        "part": {"kind": "material", "sku": "GEAR"},
    }
    links = [("smelt", "ore"), ("ingot", "smelt"), ("part", "ingot")]

    def build(weave_order, link_order):
        web = Web()
        cids = {name: web.weave(records[name]) for name in weave_order}
        for src, dst in link_order:
            web.link(cids[src], cids[dst], "derived-from")
        return web, cids

    web1, c1 = build(["ore", "smelt", "ingot", "part"], links)
    web2, c2 = build(["part", "ingot", "smelt", "ore"], list(reversed(links)))
    assert c1 == c2                                   # CIDs are content-derived
    r1 = provenance_query(web1, c1["part"], rels={"derived-from"})
    r2 = provenance_query(web2, c2["part"], rels={"derived-from"})
    assert r1 == r2                                   # identical despite insertion order


@pytest.mark.property
def test_missing_node_is_visible_not_dropped():
    web, n = _chain()
    # Drop a mid-chain ancestor's node record while its edges remain: a dangling
    # reference (e.g. a peer-fed edge whose target node has not synced yet).
    web.nodes.pop(n["ingot"])
    res = provenance_query(web, n["part"], rels={"derived-from"})
    # the dangling CID is surfaced in `missing`, not silently dropped
    assert n["ingot"] in res.missing
    assert n["ingot"] not in res.present
    assert res.has_dangling
    # present ancestors still resolve; the missing/present split is exhaustive
    assert set(res.present) == {n["mach"], n["smelt"], n["ore"]}
    assert set(res.present) | set(res.missing) == {
        n["mach"], n["ingot"], n["smelt"], n["ore"]
    }


@pytest.mark.property
def test_missing_leaf_reported_as_dangling_origin():
    web, n = _chain()
    # Drop the raw-material origin's record: its leaf reference must surface as a
    # missing origin, never be mistaken for a clean (present) root of the chain.
    web.nodes.pop(n["ore"])
    res = provenance_query(web, n["part"], rels={"derived-from"})
    assert res.origin_missing == (n["ore"],)
    assert n["ore"] not in res.origin_present
    assert n["ore"] in res.missing
