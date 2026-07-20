"""P3: FHE compute-time / cost estimator.

Acceptance criteria
-------------------
AC1  more nodes -> wall-time non-increasing, but never below the sequential floor.
AC2  nodes_available < 1 -> ValueError; non-int -> TypeError.
AC3  node_seconds (total work) is independent of node count; deterministic.
AC4  cost_pls is an integer (PLS settlement invariant).
AC5  unsupported scheme / ring degree -> ValueError.
AC6  bootstrap unsupported at small ring -> ValueError; dominates when present.
AC7  parallel_fraction must be in [0, 1]; f=1 + nodes=N gives linear speed-up.
AC8  op-count validation: negative / non-int rejected.
"""

from __future__ import annotations

import math

import pytest

from knitweb.privacy import (
    SCHEME_CKKS,
    Estimate,
    FHEParams,
    Workload,
    estimate,
    op_latencies_ms,
    serial_time_ms,
)

_PARAMS = FHEParams(ring_degree=32768)
_WORK = Workload(adds=1000, mults=500, rotations=200)


# ── AC1: monotone speed-up with a floor ───────────────────────────────────────
@pytest.mark.property
def test_more_nodes_never_slower():
    walls = [estimate(_WORK, _PARAMS, nodes_available=n).wall_time_s for n in range(1, 33)]
    assert walls == sorted(walls, reverse=True)  # non-increasing


@pytest.mark.property
def test_sequential_floor_respected():
    serial = serial_time_ms(_WORK, _PARAMS) / 1000.0
    f = 0.9
    floor = serial * (1.0 - f)
    huge = estimate(_WORK, _PARAMS, nodes_available=10_000, parallel_fraction=f)
    assert huge.wall_time_s > floor
    assert huge.wall_time_s == pytest.approx(floor, abs=floor)  # close to floor, above it


# ── AC2: node validation ──────────────────────────────────────────────────────
@pytest.mark.property
def test_zero_nodes_raises():
    with pytest.raises(ValueError):
        estimate(_WORK, _PARAMS, nodes_available=0)


@pytest.mark.property
def test_non_int_nodes_raises():
    with pytest.raises(TypeError):
        estimate(_WORK, _PARAMS, nodes_available=2.5)  # type: ignore[arg-type]


# ── AC3: total work invariant + determinism ───────────────────────────────────
@pytest.mark.property
def test_node_seconds_independent_of_node_count():
    e1 = estimate(_WORK, _PARAMS, nodes_available=1)
    e8 = estimate(_WORK, _PARAMS, nodes_available=8)
    assert e1.node_seconds == e8.node_seconds


@pytest.mark.property
def test_deterministic():
    a = estimate(_WORK, _PARAMS, nodes_available=4)
    b = estimate(_WORK, _PARAMS, nodes_available=4)
    assert a == b
    assert isinstance(a, Estimate)


# ── AC4: integer PLS ──────────────────────────────────────────────────────────
@pytest.mark.property
def test_cost_pls_is_integer():
    e = estimate(_WORK, _PARAMS, nodes_available=4, pls_per_node_second=3)
    assert isinstance(e.cost_pls, int) and not isinstance(e.cost_pls, bool)
    assert e.cost_pls == math.ceil(e.node_seconds * 3)


@pytest.mark.property
def test_negative_rate_raises():
    with pytest.raises(ValueError):
        estimate(_WORK, _PARAMS, nodes_available=1, pls_per_node_second=-1)


# ── AC5: scheme / ring validation ─────────────────────────────────────────────
@pytest.mark.property
def test_unsupported_scheme_raises():
    with pytest.raises(ValueError):
        FHEParams(ring_degree=32768, scheme="BFV")


@pytest.mark.property
def test_unsupported_ring_raises():
    with pytest.raises(ValueError):
        FHEParams(ring_degree=12345)


# ── AC6: bootstrap behaviour ──────────────────────────────────────────────────
@pytest.mark.property
def test_bootstrap_unsupported_at_small_ring():
    with pytest.raises(ValueError):
        serial_time_ms(Workload(bootstraps=1), FHEParams(ring_degree=8192))


@pytest.mark.property
def test_bootstrap_dominates_cost():
    no_boot = estimate(Workload(adds=100, mults=100), _PARAMS, nodes_available=1)
    with_boot = estimate(Workload(adds=100, mults=100, bootstraps=5), _PARAMS, nodes_available=1)
    bootstrap_share = with_boot.node_seconds - no_boot.node_seconds
    assert bootstrap_share > no_boot.node_seconds  # the 5 bootstraps dominate the rest
    assert any("bootstrap" in n for n in with_boot.notes)


# ── AC7: parallel fraction ────────────────────────────────────────────────────
@pytest.mark.property
def test_parallel_fraction_bounds():
    with pytest.raises(ValueError):
        estimate(_WORK, _PARAMS, nodes_available=2, parallel_fraction=1.5)
    with pytest.raises(ValueError):
        estimate(_WORK, _PARAMS, nodes_available=2, parallel_fraction=-0.1)


@pytest.mark.property
def test_fully_parallel_gives_linear_speedup():
    serial = serial_time_ms(_WORK, _PARAMS) / 1000.0
    e = estimate(_WORK, _PARAMS, nodes_available=10, parallel_fraction=1.0)
    assert e.wall_time_s == pytest.approx(serial / 10)


# ── AC8: workload validation ──────────────────────────────────────────────────
@pytest.mark.property
def test_negative_op_count_raises():
    with pytest.raises(ValueError):
        Workload(adds=-1)


@pytest.mark.property
def test_non_int_op_count_raises():
    with pytest.raises(TypeError):
        Workload(mults=3.0)  # type: ignore[arg-type]


@pytest.mark.property
def test_total_ops_and_latency_table():
    assert Workload(adds=1, mults=2, rotations=3, bootstraps=4).total_ops == 10
    lat = op_latencies_ms(_PARAMS)
    assert lat["mul"] > lat["add"]
    assert set(lat) == {"add", "mul", "rotate", "bootstrap"}
