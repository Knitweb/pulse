"""Property tests for interpret.backends (IL-116 — pluggable retrieve backend)."""

from __future__ import annotations

import pytest

from knitweb.interpret.backends import InMemoryBackend, RetrieveBackend
from knitweb.interpret.retrieve import CandidateSet, retrieve


# ---------------------------------------------------------------------------
# Minimal Web stub
# ---------------------------------------------------------------------------

class _StubWeb:
    """Minimal Web stub for backend tests."""

    def __init__(self, nodes: dict[str, dict], edges: list[tuple[str, str, str]] | None = None):
        self.nodes = dict(nodes)
        self._edges: list[tuple[str, str, str]] = edges or []

    def get(self, cid: str) -> dict | None:
        return self.nodes.get(cid)

    def traverse(self, cid: str, *, depth: int = 2, rels: set[str] | None = None):
        visited: set[str] = set()
        frontier = [cid]
        for _ in range(depth):
            next_frontier = []
            for src in frontier:
                for s, rel, dst in self._edges:
                    if s == src and (rels is None or rel in rels):
                        if dst not in visited:
                            visited.add(dst)
                            next_frontier.append(dst)
            frontier = next_frontier
        return list(visited)

    def outgoing_edges(self, cid: str):
        return [f"{s}:{r}:{d}" for s, r, d in self._edges if s == cid]

    def incoming_edges(self, cid: str):
        return [f"{s}:{r}:{d}" for s, r, d in self._edges if d == cid]

    def edge_metadata(self, edge: str) -> dict:
        return {}

    def neighbors(self, cid: str):
        return [d for s, _, d in self._edges if s == cid]


def _web(*records: dict, edges: list | None = None) -> _StubWeb:
    """Build a stub web from record dicts (each must have 'cid')."""
    nodes = {r["cid"]: {k: v for k, v in r.items() if k != "cid"} for r in records}
    return _StubWeb(nodes, edges)


# ---------------------------------------------------------------------------
# RetrieveBackend ABC
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_retrieve_backend_is_abstract():
    b = RetrieveBackend()
    with pytest.raises(NotImplementedError):
        b.select({}, None, _StubWeb({}))


@pytest.mark.property
def test_retrieve_backend_name():
    assert RetrieveBackend.name == "abstract"
    assert InMemoryBackend.name == "in-memory"


# ---------------------------------------------------------------------------
# InMemoryBackend.select — basic selection
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_in_memory_selects_by_seed():
    web = _web(
        {"cid": "A", "kind": "node"},
        {"cid": "B", "kind": "node"},
    )
    backend = InMemoryBackend()
    result = backend.select({"seed": "A"}, None, web)
    assert "A" in result
    assert "B" not in result


@pytest.mark.property
def test_in_memory_traverses_edges():
    web = _web(
        {"cid": "A", "kind": "node"},
        {"cid": "B", "kind": "node"},
        edges=[("A", "link", "B")],
    )
    backend = InMemoryBackend()
    result = backend.select({"seed": "A"}, None, web, depth=1)
    assert "A" in result
    assert "B" in result


@pytest.mark.property
def test_in_memory_filters_by_subscription():
    web = _web(
        {"cid": "A", "kind": "chemistry"},
        {"cid": "B", "kind": "finance"},
    )
    backend = InMemoryBackend()
    result = backend.select({"kind": "chemistry"}, ("chemistry",), web)
    assert "A" in result
    assert "B" not in result


@pytest.mark.property
def test_in_memory_none_subscription_passes_all():
    web = _web(
        {"cid": "A", "kind": "chemistry"},
        {"cid": "B", "kind": "finance"},
    )
    backend = InMemoryBackend()
    result = backend.select({}, None, web)
    assert "A" in result
    assert "B" in result


@pytest.mark.property
def test_in_memory_empty_web_returns_empty():
    web = _StubWeb({})
    backend = InMemoryBackend()
    result = backend.select({"text": "anything"}, None, web)
    assert result == []


# ---------------------------------------------------------------------------
# Re-validation gate in retrieve()
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_phantom_cid_dropped_by_revalidation():
    """A custom backend that returns a phantom CID gets it stripped."""

    class _PhantomBackend(RetrieveBackend):
        name = "phantom"

        def select(self, query, subscription, web, **kwargs) -> list[str]:
            return ["REAL", "PHANTOM-NOT-IN-WEB"]

    web = _StubWeb({"REAL": {"kind": "node"}})
    cs = retrieve("x", None, web, backend=_PhantomBackend())
    assert "REAL" in cs.cids
    assert "PHANTOM-NOT-IN-WEB" not in cs.cids


@pytest.mark.property
def test_all_phantom_returns_empty_candidate_set():
    class _AllPhantom(RetrieveBackend):
        name = "all-phantom"

        def select(self, query, subscription, web, **kwargs) -> list[str]:
            return ["GHOST1", "GHOST2"]

    web = _StubWeb({"REAL": {"kind": "node"}})
    cs = retrieve("x", None, web, backend=_AllPhantom())
    assert cs.cids == ()
    assert isinstance(cs, CandidateSet)


# ---------------------------------------------------------------------------
# retrieve() with explicit backend vs default
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_default_backend_matches_in_memory():
    web = _web(
        {"cid": "A", "kind": "chemistry"},
        {"cid": "B", "kind": "chemistry"},
        edges=[("A", "link", "B")],
    )
    cs_default = retrieve({"seed": "A"}, None, web)
    cs_explicit = retrieve({"seed": "A"}, None, web, backend=InMemoryBackend())
    assert cs_default.cids == cs_explicit.cids


@pytest.mark.property
def test_custom_backend_replaces_selection():
    """A backend that always returns a fixed CID overrides the default traversal."""

    class _FixedBackend(RetrieveBackend):
        name = "fixed"

        def select(self, query, subscription, web, **kwargs) -> list[str]:
            return ["fixed-cid"]

    web = _StubWeb({"fixed-cid": {"kind": "node"}, "other": {"kind": "node"}})
    cs = retrieve("anything", None, web, backend=_FixedBackend())
    assert cs.cids == ("fixed-cid",)


@pytest.mark.property
def test_backend_is_ephemeral_no_web_mutation():
    """Backend select() must not mutate the web's node dict."""
    web = _web({"cid": "A", "kind": "node"})
    original_nodes = dict(web.nodes)
    InMemoryBackend().select({}, None, web)
    assert web.nodes == original_nodes


# ---------------------------------------------------------------------------
# Backward compatibility — retrieve() without backend arg still works
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_retrieve_without_backend_arg_unchanged():
    web = _web({"cid": "A", "kind": "node"})
    cs = retrieve({"seed": "A"}, None, web)
    assert "A" in cs.cids
    assert isinstance(cs, CandidateSet)
