# Features

Tracks shipped and planned capabilities by epic. Completed items reflect merged PRs as of 2026-06-24.
Requirements and constraints live in [REQUIREMENTS.md](REQUIREMENTS.md).

---

## Epic 1 — P2P Fabric

### Shipped
- Pure-Python `knitweb` package; `knitweb` / `pulse` CLI entry points (baseline)
- Canonical CBOR content addressing with CIDv1 and strict float/depth/length guards
- Fabric `Web` primitives: signed records, checkpoints, provenance, edge metadata
- Asyncio P2P node with AddrBook, PEX peer discovery, eclipse-resistance bucketing
- Gossipsub mesh: eager-push + lazy IHAVE/IWANT + integer peer-score (#67)
- Kademlia DHT core: k-buckets, XOR distance, iterative node lookup (#68)
- Erlay-style O(diff) inventory reconciliation on reconnect (#69, #96)
- k-bucket source-diversity cap to resist DHT keyspace eclipse (#238)
- Inv→getdata inventory relay replacing full-flood gossip (#64)
- Identity-keyed connection gate binding proofs to ban ledger (#62)
- Reputation/ban layer active on live TCP path (#57)
- WebRTC transport: browser DataChannel carrier for in-tab peers (#239)
- RelayPool: multi-relay fanout, BootstrapRegistry, STUN seamless fallback (#243)
- Self-hosted relay server + live monitor dashboard (#279)
- Wire WIRE_VERSION constant + version-byte negotiation (#250)
- Reputation decay per anti-entropy round (#177)
- Per-peer rate/byte budget on inv-getdata/IWANT serve path (#91)
- Gossipsub peer-score: cap first-message-delivery reward, P2-cap (#178)
- Lazy gossip gated on peer score — refuse IHAVE/IWANT from negative peers (#180)
- Equivocation reporting + reputation banning (#31)

### Planned
- Full WebRTC STUN/TURN integration for browser nodes behind symmetric NAT

---

## Epic 2 — Fabric: Web, Subscription & Provenance

### Shipped
- `in_subscription_scope` fabric-wide scope filter (IL-100) (#247)
- JSON-LD / OriginTrail-DKG export of the woven Web (#264)
- Edge metadata vocabulary: reputation / deploy-location / debug-score (IL-109) (#264)
- PII guard on edge metadata (rejects email/name/phone/IP/key fields)
- Float rejection at `Web.link()` layer (P1-8) (#252)
- Spatial index union with graph traversal (geohash + altitude band)
- Provenance ancestry walker; attestation gate

### Planned
- P2-7: MAX_STRING_LEN + MAX_ARRAY_SIZE guards in canonical encode/decode (#260)

---

## Epic 3 — Interpret / Lens (IL-100 → IL-120)

### Shipped
- Stage-tagging contract: Mining → Settlement boundary (IL-104) (#244)
- Distill as PoUW job class with split verification (IL-105) (#259)
- Distill re-execution check: retrieve + gate, deterministic halves (IL-106) (#259)
- Job-level audit selection for distill jobs (IL-106 sampling) (#259)
- Relevance challenge window + spider quality reputation (IL-107) (#261)
- Metered reflect/recurse mode config + bench harness (IL-108) (#262)
- JSON-LD metadata vocab + reputation ranking (IL-109) (#264)
- `relation_types` filter + missing-node visibility on `retrieve()` (#282)
- Pluggable recognition resolver: MarkerBackend / SceneSemanticBackend / EmbeddingBackend (IL-118) (#265)
- Verifiable AR overlays from distilled bundle (IL-119) (#266)
- Field observations: confidence-gated AR producer side — `FieldObservation` float-free record, `GlassObserver` confirmation gate, capture-digest/pod-ref vault pointers, spatial-index round trip (#342)
- GeoWeave (PAR) bridge: verify Ed25519 `did:key` finding envelopes from weave-core and re-express them as attested field observations; `did-link` identity record; MOLGANG label maps from woven knowledge (`edge/labelmap.py`); PAR maturity plan (`docs/PAR_MATURITY_PLAN.md`)
- Field-observation exchange: glass-to-glass bundles over any carrier — all-or-nothing attestation verify, spatial acceptance on the record's own geohash, dedupe, weave-through to SpatialIndex (#357)
- MeTTa-inspired atomspace adapter for virtualpc LLM agents (Lens) (#248)
- Fiber taxonomy for semantic bundle categorisation (#263)

### In Progress / Planned
- IL-111: provenance-ancestry distill gate
- IL-114: PoUW escrow flow with split-verify settlement
- IL-115: marketplace job submission + worker registration
- IL-117: canonical field-ordering freeze for CID stability
- IL-120: end-to-end Lens loop (marker → overlay → AR render)
- Subscription scope + provenance CID gate (#246 — open)

---

## Epic 4 — PoUW / Distill / SDK

### Shipped
- Quorum-aware settlement for useful work (#249)
- Distill_bundle ACs: verify/decode/content-address/regression (IL-102) (#258)
- Content-addressed intermediates + cache + provenance (IL-103) (#257)
- Token budget fix in distill: real token budget proxy (#255)
- Provenance-gate + compile_bundle format guard (IL-102) (#256)
- Spider PoUW compute-marketplace MVP (baseline)
- Split-verify: `SplitVerdict`, `split_settles`, `bundle_cid`
- Challenge window: `DisputeWindowLedger.dispute_by_quorum`

---

## Epic 5 — Ingest Pipeline (Phase 2)

### Shipped
- Source abstraction + format detection (P2-A): `IngestionSource`, `SourceFormat`, 9 property tests (#280)
- Ingest molgang reactions into pulse Web (P2-5) (#254)

### Planned
- P2-B: Text extraction adapters for PDF/HTML/JSON/TXT
- P2-C: Rule-based relation extraction
- P2-D: CID assignment + web weaving for extracted nodes
- P2-E: Incremental delta sync for repeated ingest runs

---

## Epic 6 — Ops & Developer Experience

### Shipped
- Self-hosted relay server (FastAPI drop-in for 5mart.ml) + live monitor dashboard (#279)
- Interactive chemistry knowledge graph widget (#241)
- Chemistry Lens Agent demo for knitweb.art homepage (#240)

### Planned
- Docker-compose bundle for self-hosted node + relay
- Prometheus metrics endpoint for relay/node

---

## Epic 7 — Docs & Architecture

### Shipped
- Architecture, P2P, PoUW, Identity, Personhood, CROWDFUNDING docs
- Lens export boundary, Lens/RLM contract, provenance contract
- Backlog: agent army + demo tasks (#269, #278)
- Migration mirror plan to public repo (#251)
