"""Recursive distillation over a candidate set.

This stage consumes ``CandidateSet`` without concatenating relation content into a
single prompt. It performs bounded, deterministic loops and emits a minimal signed
artifact candidate for downstream bytecode compilation.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Iterable

from ..fabric import attest
from ..fabric.web import Web
from ..fabric import provenance
from ..synaptic import bytecode as _bc
from .retrieve import CandidateSet

__all__ = [
    "DistillIterationLog",
    "Selection",
    "distill",
    "gate_relations",
]


def _require_int(name: str, value: int, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def _relation_key(relation: _bc.Relation) -> tuple:
    return (
        relation.subject,
        relation.predicate,
        relation.obj,
        relation.source_type,
        relation.weight,
    )


@dataclass(frozen=True)
class DistillIterationLog:
    """Per-run metrics from a bounded distill loop."""

    iterations: int
    sub_calls: int
    elapsed_ms: int
    budget_exhausted: bool


@dataclass(frozen=True)
class Selection:
    """The distill output contract: selected relations + source coverage."""

    relations: tuple[_bc.Relation, ...]
    relation_sources: tuple[tuple[str, ...], ...]
    log: DistillIterationLog
    query: str | object

    @property
    def relation_count(self) -> int:
        return len(self.relations)


def _gate_relation(
    relation: _bc.Relation,
    web: Web,
) -> bool:
    """Deterministic attestation gate for a relation.

    Fabricated nodes are never emitted. We gate on ``attested`` graph membership for
    subject/predicate/object CIDs and on acyclic provenance.
    """
    if not all(isinstance(x, str) and x for x in (relation.subject, relation.predicate, relation.obj)):
        return False
    if relation.subject not in web.nodes or relation.predicate not in web.nodes or relation.obj not in web.nodes:
        return False

    # Re-check cycle safety so distill never emits cyclic provenance claims.
    if not provenance.is_acyclic(web, relation.subject):
        return False
    if not provenance.is_acyclic(web, relation.predicate):
        return False
    if not provenance.is_acyclic(web, relation.obj):
        return False

    # Reuse the attestation surface when available. If no explicit attestation is
    # attached (legacy records), this becomes a graph-membership + acyclicity gate.
    return (
        attest.node_is_attested(web, relation.subject)
        and attest.node_is_attested(web, relation.predicate)
        and attest.node_is_attested(web, relation.obj)
    )


def gate_relations(
    relations: Iterable[_bc.Relation],
    candidates: CandidateSet,
    web: Web,
) -> tuple[_bc.Relation, ...]:
    """Apply deterministic gate checks to a relation stream and drop fabricated tuples."""
    out: list[_bc.Relation] = []
    for relation in relations:
        if _gate_relation(relation, web):
            out.append(relation)
    return tuple(out)


def _relation_from_candidate(
    candidate_cid: str,
    web: Web,
    *,
    query: str | object,
) -> _bc.Relation:
    subject = candidate_cid
    obj = candidate_cid
    neighbors = []
    if web is not None:
        neighbors = web.neighbors(candidate_cid)
    predicate = neighbors[0] if neighbors else candidate_cid
    source_type = "Unknown"
    weight = 1

    if isinstance(query, dict):
        if isinstance(query.get("subject"), str):
            qs = str(query["subject"])  # type: ignore[index]
            subject = qs if qs in web.nodes else candidate_cid
        if isinstance(query.get("predicate"), str):
            qp = str(query["predicate"])  # type: ignore[index]
            predicate = qp if qp in web.nodes else predicate
        if isinstance(query.get("object"), str):
            qo = str(query["object"])  # type: ignore[index]
            obj = qo if qo in web.nodes else candidate_cid
        if isinstance(query.get("weight"), int) and query["weight"] >= 0:  # type: ignore[operator]
            weight = int(query["weight"])  # type: ignore[index]
        if isinstance(query.get("source_type"), str):
            source_type = str(query["source_type"])  # type: ignore[index]

    return _bc.Relation(
        subject=subject,
        predicate=predicate,
        obj=obj,
        source_type=source_type,
        weight=weight,
    )


def _candidate_signature(query: str | object, candidate: str, max_iters: int, mode: str) -> str:
    """Deterministic signature for a candidate's mined intermediate trace.

    The signature lets future callers cache sub-steps without serializing full
    records. It includes only primitives that matter for distillation output.
    """
    payload = {
        "candidate": candidate,
        "query": query,
        "max_iters": max_iters,
        "mode": mode,
    }
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def distill(
    candidates: CandidateSet,
    query: str | object,
    *,
    max_iters: int = 8,
    mode: str = "reflect",
    web: Web,
    max_prompt_bytes: int = 8 * 1024,
) -> Selection:
    """Select relations from a deterministic candidate frontier.

    The loop is strictly bounded by ``max_iters`` and emits relation-level metrics
    so callers can enforce mining budgets.
    """
    _require_int("max_iters", max_iters, minimum=1)
    if mode not in {"reflect", "recurse"}:
        raise ValueError("mode must be 'reflect' or 'recurse'")

    start = time.monotonic_ns()
    if mode == "recurse":
        # Keep recurse deterministic and bounded by explicit budget.
        max_iters = max(2, max_iters * 2)

    budget_exhausted = len(candidates.cids) > max_iters
    iters = min(len(candidates.cids), max_iters)

    collected: dict[tuple, _bc.Relation] = {}
    source_map: dict[tuple, tuple[str, ...]] = {}
    sub_calls = 0
    prompt_bytes = 0

    for candidate in candidates.cids[:iters]:
        sub_calls += 1
        # Every call produces an intermediate, deterministic relation signature. In
        # future passes this can cache/track mined sub-results. We still keep the
        # relation derivation pure and deterministic today.
        _ = _candidate_signature(query, candidate, max_iters, mode)
        rel = _relation_from_candidate(candidate, web, query=query)
        rel_key = _relation_key(rel)
        if rel_key in collected:
            # stable dedupe; preserve source union for reproducibility
            source_map[rel_key] += (candidate,)
            continue

        rel_bytes = (len(rel.subject) + len(rel.predicate) + len(rel.obj)).to_bytes(8, "big")
        prompt_bytes += len(rel_bytes)
        if prompt_bytes > max_prompt_bytes:
            break

        if _gate_relation(rel, web):
            collected[rel_key] = rel
            source_map[rel_key] = (candidate,)

    elapsed_ms = max(0, time.monotonic_ns() - start) // 1_000_000
    relations = tuple(collected.values())
    return Selection(
        relations=relations,
        relation_sources=tuple(source_map.get(_relation_key(r), ()) for r in relations),
        log=DistillIterationLog(
            iterations=iters,
            sub_calls=sub_calls,
            elapsed_ms=elapsed_ms,
            budget_exhausted=budget_exhausted,
        ),
        query=query,
    )
