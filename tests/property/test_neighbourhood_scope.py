"""P5: optional neighbourhood-scoped knit visibility.

Acceptance criteria
-------------------
AC1  same-cell record visible; different-cell record hidden.
AC2  non-geo record visible iff include_non_geo.
AC3  off by default: scope=None / neighbourhood=None -> see everything.
AC4  monotone: visible at finer precision -> visible at every coarser precision.
AC5  validation: precision int >= 1, <= origin length; origin non-empty.
AC6  combined visible() ANDs subscription scope and neighbourhood scope.
AC7  neighbours() selects only same-cell geohashes.
"""

from __future__ import annotations

import pytest

from knitweb.fabric.neighbourhood import (
    NeighbourhoodScope,
    in_neighbourhood,
    neighbours,
    record_geohash,
    visible,
)
from knitweb.fabric.spatial import geohash

# Amsterdam-ish vs far away.
_AMS = geohash(52.3702, 4.8952, 9)
_AMS_NEAR = geohash(52.3705, 4.8950, 9)   # a few metres away -> shares prefix
_TOKYO = geohash(35.6762, 139.6503, 9)


# ── AC1: cell membership ──────────────────────────────────────────────────────
@pytest.mark.property
def test_same_cell_visible_other_hidden():
    scope = NeighbourhoodScope(origin_geohash=_AMS, precision=5)
    assert in_neighbourhood({"geohash": _AMS_NEAR}, scope) is True
    assert in_neighbourhood({"geohash": _TOKYO}, scope) is False


@pytest.mark.property
def test_exact_self_visible():
    scope = NeighbourhoodScope(origin_geohash=_AMS, precision=9)
    assert in_neighbourhood({"geohash": _AMS}, scope) is True


# ── AC2: non-geo records ──────────────────────────────────────────────────────
@pytest.mark.property
def test_non_geo_record_follows_include_flag():
    rec = {"kind": "note", "text": "hi"}
    assert in_neighbourhood(rec, NeighbourhoodScope(_AMS, 5, include_non_geo=True)) is True
    assert in_neighbourhood(rec, NeighbourhoodScope(_AMS, 5, include_non_geo=False)) is False


@pytest.mark.property
def test_nested_anchor_geohash_extracted():
    rec = {"kind": "x", "anchor": {"geohash": _AMS_NEAR}}
    assert record_geohash(rec) == _AMS_NEAR
    assert record_geohash({"kind": "x"}) is None


# ── AC3: opt-in / off by default ──────────────────────────────────────────────
@pytest.mark.property
def test_none_scope_sees_everything():
    assert in_neighbourhood({"geohash": _TOKYO}, None) is True
    assert visible({"geohash": _TOKYO}) is True  # no filters at all


# ── AC4: precision monotonicity ───────────────────────────────────────────────
@pytest.mark.property
def test_visible_at_fine_implies_visible_at_coarse():
    rec = {"geohash": _AMS_NEAR}
    visibilities = {
        p: in_neighbourhood(rec, NeighbourhoodScope(_AMS, p)) for p in range(1, 10)
    }
    # Once it turns False at some precision it must stay False for finer ones.
    last_true = max((p for p, v in visibilities.items() if v), default=0)
    for p in range(1, last_true + 1):
        assert visibilities[p] is True


# ── AC5: validation ───────────────────────────────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("bad", [0, -1])
def test_precision_must_be_positive(bad):
    with pytest.raises(ValueError):
        NeighbourhoodScope(_AMS, bad)


@pytest.mark.property
def test_precision_cannot_exceed_origin_length():
    with pytest.raises(ValueError):
        NeighbourhoodScope("u173", 9)


@pytest.mark.property
def test_empty_origin_rejected():
    with pytest.raises(ValueError):
        NeighbourhoodScope("", 1)


@pytest.mark.property
def test_non_int_precision_rejected():
    with pytest.raises(TypeError):
        NeighbourhoodScope(_AMS, 5.0)  # type: ignore[arg-type]


# ── AC6: combined gate ────────────────────────────────────────────────────────
@pytest.mark.property
def test_visible_ands_both_filters():
    scope = NeighbourhoodScope(_AMS, 5)
    near_chem = {"kind": "chemistry-node", "geohash": _AMS_NEAR}
    far_chem = {"kind": "chemistry-node", "geohash": _TOKYO}
    near_finance = {"kind": "finance-node", "geohash": _AMS_NEAR}
    # passes both
    assert visible(near_chem, subscription=("chemistry-node",), neighbourhood=scope) is True
    # right topic, wrong place
    assert visible(far_chem, subscription=("chemistry-node",), neighbourhood=scope) is False
    # right place, wrong topic
    assert visible(near_finance, subscription=("chemistry-node",), neighbourhood=scope) is False


# ── AC7: neighbour peer selection ─────────────────────────────────────────────
@pytest.mark.property
def test_neighbours_filters_to_cell():
    cands = [_AMS_NEAR, _TOKYO, _AMS]
    got = neighbours(_AMS, cands, precision=5)
    assert _AMS_NEAR in got and _AMS in got and _TOKYO not in got


@pytest.mark.property
def test_neighbours_rejects_bad_precision():
    with pytest.raises(ValueError):
        neighbours(_AMS, [_AMS], precision=0)
