# Quanta Milestone 1 — 3-node shared-identity demo (reference-only)

`qua_node.py` is the **Milestone 1 reference implementation** from the Quanta
series (`docs/research/09-quanta-series.md`), reconstructed from the lost
`pulse-ar-series-FULL.bundle` / `claude/pulse-ar-yolo-llm-bluetooth-rpqwvm`
branch. It is preserved **verbatim as a standalone reference prototype** — like
the earlier JS prototype: read it for semantics, do not port it byte-for-byte
into the knitweb value path.

What it proves (3S = Sense → Spatial → Share), stdlib-only:

- **Deterministic identity from the world:** `qua_id = f(object class, spatial
  cell)` — two nodes independently observing the same cow in the same ~11 m
  cell derive the *same* QUA id with zero coordination; sync only merges
  histories, never negotiates identity.
- **Tamper-evident local logs without mining:** per-node append-only,
  hash-chained, HMAC-signed event logs ("LedgerField").
- **Central-database-free convergence:** HELLO/HAVE/WANT/EVENT gossip over
  asyncio TCP; a third node that never saw the cow learns of it purely via P2P.
- **Consensus from independent observers:** confidence grows with distinct
  observers, not repeated frames.

Run it:

```bash
python3 qua_node.py demo          # 3-node acceptance demo (6 criteria)
python3 qua_node.py node --id a --port 9001 --peers 127.0.0.1:9002
```

Verified in this repo: all six acceptance criteria PASS (see the
`quanta-m1-3node-sync` record in `experiments/`).

## Status w.r.t. the non-negotiables

This prototype deliberately predates the project rules and is **not** value-path
code. Before any concept here lands in `src/knitweb/`, apply
`docs/research/09-quanta-series.md` §15: HMAC node keys → per-account secp256k1
ECDSA + SHA-256 signatures; ad-hoc sorted-JSON hashing → `core.canonical.encode`
(float-free CBOR) + `core.canonical.cid`; float `time.time()` timestamps and
float confidences in hashed payloads → integer time and basis points (the
geohash-string trick in `knitweb.edge.pulse_ar` shows the pattern for the
lat/lon cell key); running-average position and consensus scores → integer
arithmetic. The deterministic spatial-cell identity and the HAVE/WANT delta
gossip are the ideas worth porting.
