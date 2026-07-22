# Quanta Milestone 1 — how `qua_node.py` works, and a code review

This document explains the reference implementation end to end, then records a
full review of it. It is the companion to [`README.md`](README.md) (status /
how-to-run) and to the concept paper
[`docs/research/09-quanta-series.md`](../../docs/research/09-quanta-series.md)
§12.1. The code is **reference-only**; the review below is what stands between
this prototype and anything that could enter `src/knitweb/`.

---

## 1. The one-sentence idea

Three peers watch the same physical world, each turns a detection into an
observation whose **identity is a pure function of _what_ + _where_**, and they
gossip those observations until every peer holds the same tamper-evident history
— with **no central database and no coordinator**. `3S = Sense → Spatial → Share`.

## 2. The data flow, layer by layer

```
 camera / YOLO (SensorInterface)
        │  (class, confidence, lat, lon, alt, heading)
        ▼
 SENSE   observe()                         qua_node.py:403
        │  build Observation, stamp observer + time + frame_hash
        ▼
 SPATIAL qua_id(class, lat, lon)           qua_node.py:87
        │  spatial_cell() quantises lat/lon → cell string → sha256 → qua:<class>:<hash8>
        │  → identical id on every node that saw the same thing in the same cell
        ▼
 LEDGER  LedgerField.append()              qua_node.py:196
        │  body={type,payload,author,ts}; hash=SHA256(prev‖canonical(body));
        │  sig=HMAC(node_key,hash); chain prev←hash
        ▼
 SHARE   _gossip_loop → _sync_with         qua_node.py:434 / 443
        │  HELLO(key) · HAVE(all hashes) · WANT(missing) · EVENT(envelope)
        ▼
 MERGE   _ingest → ingest_remote           qua_node.py:487 / 218
        │  dedup by hash · recompute hash · (verify HMAC if author key known)
        │  → _apply_observation rebuilds the QUASpatialObject + consensus
        ▼
 STATE   QUASpatialObject                  qua_node.py:124
           position = running mean of observations; consensus = f(confidence, #observers)
```

### Spatial layer (`spatial_cell`, `qua_id`)

`spatial_cell(lat, lon)` floors each coordinate to 4 decimals (~11 m × 7 m at NL
latitude) and formats it as a string like `"52.3740_4.8990"`. `chunk_of()` does
the same at 2 decimals (~1.1 km) for coarse cache/sync scoping. `qua_id` hashes
`"<class>|<cell>"` and keeps 8 hex characters, yielding e.g.
`qua:cow:eaf60f4a`. The whole milestone rests on this: two nodes computing it for
the same physical spot get byte-identical ids, so **sync only ever merges
histories — it never has to negotiate identity**.

### Ledger layer (`LedgerField`)

An append-only, per-author hash chain. Each node signs its *own* events with a
per-node HMAC key; `append()` chains `prev ← hash`, `ingest_remote()` stores
events from peers after a structural hash re-check (and an HMAC check when the
author's key is known). `verify_own_chain()` walks a node's own author-chain and
re-derives every hash and signature. Content-addressing by `hash` is what makes
the gossip a simple set-difference.

### P2P layer (`QUANode`, gossip)

One asyncio TCP server per node plus two background loops: `_sense_loop` polls
the sensor every 0.4 s, `_gossip_loop` dials every peer every 1.0 s. The wire
protocol is four newline-delimited JSON messages: `HELLO` (exchange node id +
key), `HAVE` (all my event hashes), `WANT` (the subset you're missing), `EVENT`
(one envelope). Offline peers raise `ConnectionRefusedError` and are silently
skipped, so the web is partition-tolerant by construction.

### Aggregation layer (`QUASpatialObject`)

Each distinct `qua_id` accumulates its observations into a living twin: position
is the running mean of observed lat/lon; `consensus = 0.6·avg_confidence +
0.4·min(#observers/3, 1)`, so confidence rises with **independent** observers,
not with repeated frames from one camera.

## 3. Why the demo's six acceptance checks pass

| Check | Mechanism |
|---|---|
| A and B derive the same cow id | `qua_id` is `f(class, cell)`; both GPS fixes floor to the same cell |
| C learns the cow via P2P only | C has no sensor; it only ever receives `EVENT`s over gossip |
| 2 independent observers everywhere | `observers` is a set of author ids; merge is order-independent |
| all ledgers converge | HAVE/WANT exchanges every missing hash; gossip repeats each second |
| all hash-chains verify | `verify_own_chain` re-derives hashes + HMAC per author-chain |
| consensus rises above single-obs | two observers push `observer_weight` from 1/3 to 2/3 |

---

## 4. Code review

Verified empirically against the code (see the probe script results quoted
inline). Severity is for a **hypothetical production port**, not for the demo,
which meets its stated goal. Nothing here needs changing in the reference file;
these are the gates for reuse, and they line up with
`docs/research/09-quanta-series.md` §15.

### Correctness / protocol

**C1 — Identity is brittle at cell boundaries (design limit, high for prod).**
Two observers of the *same* object whose GPS fixes straddle a cell edge derive
*different* ids. Probed: `cow @ 52.37399` → `qua:cow:5435dc82` but
`cow @ 52.37401` → `qua:cow:eaf60f4a` — a 2 cm latitude difference, well inside
GPS noise, splits one cow into two twins. Floor-quantisation has no overlap
tolerance, so the "same object → same id" guarantee holds only away from
boundaries. Real fusion needs overlapping cells (e.g. geohash neighbours) or a
post-hoc merge keyed on proximity + class, exactly the "claim-score conflict
resolution" the paper lists as an open gap. *Knitweb note:* the geohash-**string**
approach in `knitweb.edge.pulse_ar` is the pattern to port, with neighbour
lookup.

**C2 — Consensus/position use floats and are order-sensitive in principle.**
`add_observation` keeps a running mean in floats and `_update_consensus` mixes
float weights. For a demo that is fine; for the value path it violates the
no-floats-near-state rule. Because position is a *running* mean, the stored value
also depends on arrival order (the final set is the same across nodes, but any
intermediate snapshot differs). Port to integer micro-degrees and integer basis
points, and recompute from the full observation set rather than incrementally.

**C3 — No equivocation / fork detection.** A node can rewind its own
`prev_hash`, author two different events with the same `prev`, and a peer accepts
**both** (probed: `fork: both branches accepted by peer: True`). Each event is
individually valid, so nothing rejects a forked author-chain. The demo never does
this; a hostile node would. This is precisely what the repo's real
equivocation-report / dispute machinery exists for.

**C4 — Remote chains are not linkage-checked.** `ingest_remote` re-derives each
event's own hash but never checks that its `prev` already exists locally, nor
that an author's chain is gap-free — `verify_own_chain` walks only the *local*
author's chain. Verified by inspection: a peer can serve a mid-chain slice and it
is stored as if it were complete history. Convergence in the demo hides this
because gossip eventually delivers every event; under an adversary or lossy
transport it does not.

**C5 — Moving objects fragment.** Because identity is `f(class, cell)`, an object
that walks into the next cell acquires a *new* id, while the old id's
running-average position keeps dragging toward the edge it left. The static-world
assumption is fine for Milestone 1 but fatal for anything that moves (livestock,
vehicles); it compounds C1 and needs tracklet re-identification, not just cell
overlap.

### Security

**S1 — Unauthenticated events are trusted when the author key is unknown (high
for prod).** `ingest_remote(envelope, author_key=None)` skips the HMAC check
entirely and stores the event after only a hash re-check. Probed: a fully forged
envelope with `sig="not-a-real-signature"` from an unknown author `ghost` is
accepted (`forged event accepted when author unknown: True`). Since keys are only
learned from a `HELLO` (itself unauthenticated — anyone may claim any node id and
hand over any key), the HMAC adds no real authentication here. This is the
central reason the paper's §15 replaces node-key HMACs with per-account
**secp256k1 signatures over `core.canonical` bytes**: a signature binds the event
to a public identity a third party can verify without a prior handshake.

**S1b — `HELLO` discloses the signing *secret* itself (high for prod).** Worse
than S1: the key a node ships in `HELLO` (`"key": self.key.hex()`,
`qua_node.py:443`) is the very `self.key` (`:370`) the `LedgerField` uses as its
HMAC secret. Verified: the ledger is `LedgerField(node_id, self.key, …)` and the
same bytes go out on the wire. So any peer or eavesdropper who sees one `HELLO`
can forge events *as that node* even for a "known" author — a symmetric MAC whose
key is broadcast provides no authentication at all. Public-key signatures fix this
by construction: verification reveals nothing that lets you sign.

**S2 — `_ingest` crashes on a malformed payload (medium — remote DoS).**
`Observation(**body["payload"])` raises `TypeError` on missing/extra keys
(probed). A peer that sends one `EVENT` with a junk payload takes down the
receiver's connection handler. Needs a schema/allow-list validation step (or a
`try/except` that drops the event) before construction.

**S3 — No wire limits.** `readline()` has a 3 s timeout but no size cap, and
`HAVE` sends *every* hash each round. A peer can send an unbounded line
(memory) or a huge HAVE. Bound line length and paginate HAVE.

### Efficiency / scale

**E1 — O(N) full-set gossip every second.** `all_hashes()` ships the entire
ledger to every peer each cycle; sync cost grows with total history, not with the
delta. Fine for three nodes and a handful of events; quadratic in a real web. Use
a set reconciliation scheme (IBLT / range-hash / Merkle range proofs — the repo
already has feed range-multiproofs) or at least a since-cursor.

**E2 — New connection per gossip round.** `_sync_with` opens and closes a fresh
TCP connection to each peer every second; no connection reuse, no backoff on a
dead peer (it just retries at full rate). A persistent connection + exponential
backoff (the repo's rolling-upgrade doc has the pattern) scales better.

**E3 — Full file rewrite semantics are fine, but `_load` trusts the file.**
Persistence appends JSONL and reloads without re-verifying signatures on load;
a tampered ledger file is trusted. Re-run `verify_own_chain` (or the
signature-based successor) at load.

**E4 — Server binds `127.0.0.1` hard-coded (`qua_node.py:381`).** The CLI
advertises a multi-machine mode (`node --peers other-host:9002`), but the
listener binds localhost only, so it can never accept a remote connection —
verified by inspection. The docstring oversells the CLI; a one-line bind-address
parameter fixes it when anyone actually runs Milestone 1 across machines.

**E5 — Blocking inference stalls the event loop.** `try_real_yolo_sensor`'s
`detect()` runs the YOLO model and camera I/O synchronously, and `_sense_loop`
awaits it inline — so every frame blocks the gossip loop for its full inference
time (verified by inspection). Production needs `run_in_executor` or the
edge-node split from `docs/QUEST3S_AR.md` (thin headset, inference on a spider).

### Style / minor

- **M1** `chunk_of` and `haversine_m` are defined but unused in the demo path —
  they're API surface for later phases; keep, but note as intentional.
- **M2** `frame_hash` mixes `time.time()` and `secrets.token_hex` so it is
  non-deterministic; the docstring calls the frame "proof". In production the
  frame hash should be the actual content hash of the image bytes (a real
  evidence pointer), not a random nonce.
- **M3** Node identity, HMAC key, and `HELLO` are all self-asserted; there is no
  binding between the `observer`/`author` string and any key. The secp256k1 port
  (address = hash of pubkey) closes this by construction.

### What is genuinely good and should be ported

- Identity as `f(what, where)` so sync merges rather than negotiates — the core
  insight, and correct.
- Content-addressed events + HAVE/WANT delta gossip — the right minimal L2 shape.
- Observer-**set** weighting for consensus (independence, not repetition).
- Clean pluggable `SensorInterface` boundary (YOLO/Snap/Quest swap in unchanged).
- Partition tolerance by default (offline peers are a non-event).

## 5. Reuse checklist (the gate to `src/knitweb/`)

1. Signatures: node-key HMAC → per-account **secp256k1 ECDSA + SHA-256**; stop
   broadcasting the secret in `HELLO` and drop the shared-key trust (S1, S1b, M3).
2. Encoding: `json.dumps(sort_keys)` → `core.canonical.encode`; hashes →
   `core.canonical.cid` (CIDv1) (C2, general).
3. Numbers: float position/consensus/timestamps → integer micro-degrees, basis
   points, integer time; recompute from the full set (C2).
4. Identity: single floored cell → overlapping cells / neighbour merge + a
   claim-score tiebreak, plus tracklet re-id for movers (C1, C5).
5. Safety: validate `EVENT` payloads; bound line size and HAVE volume; check
   `prev` linkage on ingest; detect equivocation (S2, S3, C3, C4).
6. Scale/ops: delta reconciliation + persistent connections + backoff; verify on
   load; parameterise the bind address; move inference off the event loop
   (E1, E2, E3, E4, E5).
