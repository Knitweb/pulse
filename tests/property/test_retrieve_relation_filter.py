"""Tests for interpret.retrieve: relation_types filter and missing-node visibility (#274)."""

from __future__ import annotations

import pytest

from knitweb.core.canonical import cid as make_cid
from knitweb.fabric.web import Edge, Web
from knitweb.interpret.retrieve import retrieve


# ── Helpers ────────────────────────────────────────────────────────────────────

def _web_with_reactions() -> tuple[Web, str, str, str]:
    """Return (web, reaction_cid, element_cid, doc_cid)."""
    w = Web()
    r_rec = {"kind": "reaction", "name": "Haber-Bosch"}
    e_rec = {"kind": "element", "sym": "N"}
    d_rec = {"kind": "document", "title": "Ammonia review"}
    r = w.weave(r_rec)
    e = w.weave(e_rec)
    d = w.weave(d_rec)
    w.link(r, e, "reaction-knowledge", weight=1)
    w.link(r, d, "cites", weight=1)
    return w, r, e, d


# ── relation_types filter ──────────────────────────────────────────────────────

def test_relation_types_restricts_traversal():
    """Only edges matching relation_types are followed."""
    w, r, e, d = _web_with_reactions()
    cs = retrieve({"seed": r}, None, w, relation_types=["reaction-knowledge"])
    # element is reachable via 'reaction-knowledge'; document only via 'cites'
    assert e in cs.cids
    assert d not in cs.cids


def test_relation_types_none_follows_all():
    """None (default) follows all edge types — backwards-compatible."""
    w, r, e, d = _web_with_reactions()
    cs = retrieve({"seed": r}, None, w)
    assert e in cs.cids
    assert d in cs.cids


def test_relation_types_empty_set_follows_nothing():
    """Empty list means no edge type is allowed — only seed itself returned."""
    w, r, e, d = _web_with_reactions()
    cs = retrieve({"seed": r}, None, w, relation_types=[])
    assert r in cs.cids
    assert e not in cs.cids
    assert d not in cs.cids


def test_relation_types_rejects_str_not_iterable():
    """Passing a bare str instead of list[str] raises TypeError."""
    w, r, *_ = _web_with_reactions()
    with pytest.raises(TypeError):
        retrieve({"seed": r}, None, w, relation_types="reaction-knowledge")


def test_relation_types_overrides_query_rel():
    """relation_types kwarg takes precedence over query['rel']."""
    w, r, e, d = _web_with_reactions()
    # query says 'cites', kwarg says 'reaction-knowledge' — kwarg wins
    cs = retrieve({"seed": r, "rel": "cites"}, None, w,
                  relation_types=["reaction-knowledge"])
    assert e in cs.cids
    assert d not in cs.cids


def test_relation_types_multiple_allowed():
    """Two allowed relation types both traverse their edges."""
    w, r, e, d = _web_with_reactions()
    cs = retrieve({"seed": r}, None, w,
                  relation_types=["reaction-knowledge", "cites"])
    assert e in cs.cids
    assert d in cs.cids


# ── missing-node visibility ────────────────────────────────────────────────────

def _web_with_dangling_edge() -> tuple[Web, str, str]:
    """Return (web, present_cid, absent_cid) where present has an edge to absent."""
    w = Web()
    present_rec = {"kind": "reaction", "name": "CO2 reduction"}
    absent_cid = make_cid({"kind": "element", "sym": "C"})  # not woven
    p = w.weave(present_rec)
    # Simulate a partial sync: edge exists, target node does not
    w._out.setdefault(p, []).append(
        Edge(src=p, dst=absent_cid, rel="reaction-knowledge", weight=1)
    )
    return w, p, absent_cid


def test_missing_node_sentinel_in_records():
    """A CID referenced by an edge but absent from web gets a missing sentinel."""
    w, present, absent = _web_with_dangling_edge()
    cs = retrieve({"seed": present}, None, w)
    records = cs.records(w)
    assert absent in records
    assert records[absent] == {"kind": "missing", "cid": absent}


def test_present_node_not_marked_missing():
    """CIDs that are in web.nodes are never returned as missing sentinels."""
    w, present, _ = _web_with_dangling_edge()
    cs = retrieve({"seed": present}, None, w)
    records = cs.records(w)
    assert records[present].get("kind") != "missing"


def test_missing_node_does_not_appear_in_cids():
    """The absent node is surfaced only in records(), not in CandidateSet.cids."""
    w, present, absent = _web_with_dangling_edge()
    cs = retrieve({"seed": present}, None, w)
    assert absent not in cs.cids


def test_no_missing_when_all_nodes_present():
    """When all edge targets are in web, no missing sentinels are produced."""
    w, r, e, d = _web_with_reactions()
    cs = retrieve({"seed": r}, None, w)
    records = cs.records(w)
    assert all(v.get("kind") != "missing" for v in records.values())
