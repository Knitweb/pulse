"""Pluggable candidate-selection backends for ``interpret.retrieve`` (IL-116).

The backend is the *trap-1* stage of the interpret pipeline: given a query
and a subscription scope it selects a list of candidate CIDs from the Web.
All CIDs a backend returns are re-validated against the live Web inside
``retrieve()`` — a backend can accelerate selection (vector index, DAS) but
can never introduce a CID absent from the current Web.

Only the selection step is pluggable. Reputation scoring, provenance ancestry
and CandidateSet assembly remain in ``retrieve()`` so the settlement-layer
determinism guarantee is unchanged.

Shipped backends
----------------
``InMemoryBackend`` (default)
    Pure graph traversal from query seeds using ``Web.traverse``; identical
    to the original inlined logic in ``retrieve()``.  Dependency-free.

Optional backends (not shipped; shown for spec reference)
----------------------------------------------------------
``DASBackend``
    Queries a Distributed-Atom-Space / Hyperon MeTTa space for candidates.
    Must import ``hyperon`` lazily; should never be imported at module level.

``VectorBackend``
    ANN index (FAISS, hnswlib, …).  Must be lazy-imported.

Both optional backends must implement the same ``select()`` signature and
their output is re-validated before use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Mapping

if TYPE_CHECKING:
    from ...fabric.spatial_index import SpatialIndex
    from ...fabric.web import Web

__all__ = ["RetrieveBackend", "InMemoryBackend"]


# ---------------------------------------------------------------------------
# Scope helpers (inline copy so this module is import-independent from PR #247)
# ---------------------------------------------------------------------------

_SCOPE_FIELDS: tuple[str, ...] = ("kind", "scope", "domain", "namespace")


def _in_scope(record: dict, subscription: tuple[str, ...] | None) -> bool:
    if subscription is None:
        return True
    for field in _SCOPE_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value in subscription:
            return True
    tags = record.get("tags")
    if isinstance(tags, (list, tuple, set)):
        sub_set = set(subscription)
        for tag in tags:
            if isinstance(tag, str) and tag in sub_set:
                return True
    return False


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class RetrieveBackend:
    """Abstract candidate-selection backend.

    Subclasses implement :meth:`select`.  They MAY hold ephemeral/session
    state (e.g. a vector index built from recent Web snapshots) but MUST NOT
    write back to the fabric or ``store.py`` — the Web is the sole durable
    source of truth.

    Class attribute :attr:`name` is a short identifier used in diagnostics.
    """

    name: str = "abstract"

    def select(
        self,
        query: Mapping[str, object],
        subscription: tuple[str, ...] | None,
        web: "Web",
        *,
        depth: int = 2,
        rel_filter: set[str] | None = None,
        spatial_index: "SpatialIndex | None" = None,
    ) -> list[str]:
        """Return candidate CIDs matching *query* within *subscription*.

        Parameters
        ----------
        query:
            Structured query dict (already normalised by ``retrieve``).
        subscription:
            Scope filter.  ``None`` means no restriction.
        web:
            The live Web.  Backends may read it but must not mutate it.
        depth:
            Graph traversal depth hint.  Backends may ignore it.
        rel_filter:
            Optional relation-type whitelist for graph traversal.
        spatial_index:
            Optional spatial index.  May be ``None`` if not available.

        Returns
        -------
        list[str]
            Candidate CIDs.  Every returned CID is re-validated against the
            Web inside ``retrieve()``; phantom CIDs are silently dropped.
        """
        raise NotImplementedError  # pragma: no cover


# ---------------------------------------------------------------------------
# Default: in-memory graph traversal
# ---------------------------------------------------------------------------

class InMemoryBackend(RetrieveBackend):
    """Default backend — pure graph traversal over the in-process Web.

    Mirrors the original inlined logic in ``retrieve()``: seed CIDs are
    derived from the query, traversed with ``Web.traverse``, optionally
    unioned with a ``SpatialIndex``, then filtered by subscription scope.
    No external dependency; no session state.
    """

    name: str = "in-memory"

    def select(
        self,
        query: Mapping[str, object],
        subscription: tuple[str, ...] | None,
        web: "Web",
        *,
        depth: int = 2,
        rel_filter: set[str] | None = None,
        spatial_index: "SpatialIndex | None" = None,
    ) -> list[str]:
        seed_cids = _derive_seeds(query, web)

        discovered: list[str] = []
        for sid in seed_cids:
            if sid in web.nodes and sid not in discovered:
                discovered.append(sid)
            for cid in sorted(web.traverse(sid, depth=depth, rels=rel_filter)):
                if cid not in discovered:
                    discovered.append(cid)

        if spatial_index is not None and "geohash" in query and "precision" in query:
            precision = query.get("precision")
            if not isinstance(precision, int):
                raise TypeError("query['precision'] must be int when spatial query is used")
            near = spatial_index.near(
                str(query["geohash"]), precision, alt_band=query.get("alt_band")
            )
            for cid in near:
                if cid not in discovered:
                    discovered.append(cid)

        return [cid for cid in discovered if _in_scope(web.nodes.get(cid, {}), subscription)]


# ---------------------------------------------------------------------------
# Seed derivation (extracted from retrieve.py; shared by InMemoryBackend)
# ---------------------------------------------------------------------------

def _derive_seeds(query: Mapping[str, object], web: "Web") -> tuple[str, ...]:
    """Derive seed CIDs from a normalised query dict."""
    if "seed" in query:
        seeds = query["seed"]
        if isinstance(seeds, str):
            return (seeds,)
        if not isinstance(seeds, (list, tuple, set)):
            raise TypeError("query['seed'] must be str, list, tuple, or set")
        out: list[str] = []
        for sid in seeds:
            if not isinstance(sid, str) or not sid:
                raise TypeError("seed values must be non-empty str")
            out.append(sid)
        return tuple(out)

    text = query.get("text")
    if isinstance(text, str) and text in web.nodes:
        return (text,)

    kinds: tuple[str, ...] = ()
    if "kind" in query:
        k = query["kind"]
        if isinstance(k, str):
            kinds = (k,)
        elif isinstance(k, Iterable):
            kinds = tuple(str(i) for i in k)

    out_list: list[str] = []
    for cid, record in sorted(web.nodes.items(), key=lambda kv: kv[0]):
        if kinds and str(record.get("kind", "")) not in kinds:
            continue
        if isinstance(text, str):
            haystack = " ".join(str(v) for v in record.values())
            if text.lower() not in haystack.lower():
                continue
        out_list.append(cid)
    return tuple(out_list)
