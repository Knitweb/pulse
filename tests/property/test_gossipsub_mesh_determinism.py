"""Mesh graft/prune selection is reproducible across processes — same seed, same mesh.

The module promises *"same seed -> same mesh"* and ``_select_graft`` claims its shuffle is
"deterministic via injected RNG". But the shuffled list was derived from a ``set``
(``_topic_peers - mesh`` for graft, ``list(mesh)`` for prune), and a ``set`` of strings
iterates in **PYTHONHASHSEED-randomised** order. ``random.shuffle`` permutes its input, so
its output depends on that initial order — meaning two processes with the same injected RNG
seed but different hash seeds picked *different* peers to graft/prune. The fix canonicalises
(``sorted``) the set-derived list before the shuffle, making selection a pure function of
``(seed, contents)``.

The cross-process test is the real proof; it spawns children under several hash seeds and
requires byte-identical selection. All integer/RNG, no wall-clock; touches no wire/CID path.
"""
import os
import random
import subprocess
import sys

from knitweb.p2p.mesh import Gossipsub

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC = os.path.join(_REPO_ROOT, "src")

# Exercises BOTH set-derived selection paths (graft candidates + prune members).
_SELECT_SCRIPT = """
import random
from knitweb.p2p.mesh import Gossipsub
gs = Gossipsub(rng=random.Random(1234))
topic = "web/demo"
peers = ["peer-%03d" % i for i in range(64)]
for p in peers:
    gs.add_peer(topic, p)
graft = gs._select_graft(topic, set(), want=16)
prune = gs._select_prune(set(peers), drop=16)
print(",".join(graft) + "|" + ",".join(prune))
"""


def _gs():
    return Gossipsub(rng=random.Random(0))


def _run_under_hashseed(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": _SRC}
    out = subprocess.run(
        [sys.executable, "-c", _SELECT_SCRIPT],
        env=env, cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_selection_is_identical_across_hash_seeds():
    # Same injected RNG seed, four different PYTHONHASHSEEDs -> identical selection.
    # Without the sorted() canonicalisation these diverge (set iteration order leaks).
    results = {h: _run_under_hashseed(h) for h in ("0", "1", "2", "12345")}
    distinct = set(results.values())
    assert len(distinct) == 1, f"selection diverged across hash seeds: {results}"
    # And it actually selected something (guards against a vacuous all-empty pass).
    graft, prune = next(iter(distinct)).split("|")
    assert len(graft.split(",")) == 16 and len(prune.split(",")) == 16


def test_eligible_candidates_returned_in_canonical_order():
    # Insertion order must not affect the candidate ordering handed to the RNG.
    names = [f"peer-{i:03d}" for i in range(64)]
    shuffled = names[:]
    random.Random(7).shuffle(shuffled)
    gs = _gs()
    for p in shuffled:
        gs.add_peer("t", p)
    assert gs._eligible_candidates("t", set()) == sorted(names)


def test_same_seed_same_mesh_in_process():
    # Two nodes, same injected seed, peers added in different orders -> same graft pick.
    names = [f"n{i:02d}" for i in range(40)]
    a, b = _gs(), _gs()
    for p in names:
        a.add_peer("t", p)
    for p in reversed(names):
        b.add_peer("t", p)
    assert a._select_graft("t", set(), want=8) == b._select_graft("t", set(), want=8)
