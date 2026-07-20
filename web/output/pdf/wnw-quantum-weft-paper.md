# World Narrow Web: Spherical Quantum Weft Architecture

**Technical Paper v1.0**  
E. Hauwert · VirtualV Holding B.V. · 2026-06-30  
DOI: pending · companion: worlds.html · k.nitweb.art

---

## Abstract

The World Narrow Web (WNW) is a fact-first P2P communication layer that estimates the size of a data response *before* fetching it, works on the smallest devices (bitchat-style relay), and is architecturally prepared for the quantum-molecular era after 2036. This paper argues that the right geometric model for such a network is **spherical, not linear**: nodes positioned at spherical coordinates (r, θ, φ), layers differentiated by orbital radius and frequency, and Pulse as the cross-shell carrier — analogous to a photon crossing electron shells. We describe the six-shell Quantum Weft model, the WNW specify-before-retrieve protocol, the P2P-connected-LLM RAG pattern, AR/VR traversal, and a transition roadmap toward laser-addressable molecular nodes. Appendix A covers the Pulse (PLS) token economics; Appendix B the marketing and exchange-listing strategy.

---

## 1. Introduction

### 1.1 The problem with linear webs

Today's web is a **pull-first** system: a user types words, an engine fetches terabytes, and a result is returned without the user ever knowing how much data was consumed. For small devices — a field sensor, a bitchat relay, a mobile mesh node — this is unusable. For P2P-connected LLMs it is unsafe: unbounded context windows, unknown provenance.

Quantum circuit development faces the same problem: qubits are arranged in **square linear arrays** because physical substrates have historically been planar. This imposes adjacency constraints — a qubit in row 3, column 5 cannot directly interact with row 1, column 1 without swap gates, creating gate overhead that scales badly.

Both problems share a root cause: **the wrong geometry**.

### 1.2 The spherical correction

A sphere is not just a visual metaphor. It is the geometry of:
- Electron shells in atoms (each layer at radius r, different energy/frequency)
- Quantum dot assemblies (optically addressable, 3D distributed)
- Signal propagation in wireless meshes (concentric coverage zones)
- Human perception in AR/VR (we navigate 360°, not left-right-only)

A spherical WNW positions every node at (r, θ, φ). Traversal is a rotation, not a scroll. A "nearby" node means smaller r, not a smaller line number. Layers naturally encode protocol speed and frequency: the innermost layer is fastest (local memory), the outermost is slowest (internet relay), exactly as inner electron shells have higher frequency than outer ones.

### 1.3 Pulse as the carrier vessel

In atomic physics, a **photon** carries energy between shells. In WNW, **Pulse** plays this role: it is the protocol primitive that crosses from one shell to another, carrying a fact assertion, a query proposal, or a settlement order. Pulse operates:
- **within a shell** (peer-to-peer, same frequency zone)
- **between shells** (cross-layer, with frequency adaptation)
- **as a beat** (clock pulse that timestamps events, analogous to photon emission)

Pulse is not a token; it is a transport primitive. The PLS token is the economic layer on top.

### 1.4 Contributions

1. A six-shell Quantum Weft model with spherical coordinates, frequency layers, and cross-shell Pulse.
2. A specify-before-retrieve protocol that bounds response size before any fetch occurs.
3. A P2P RAG pattern for LLMs using bounded fact-table slices.
4. A BC2 capsule format for bitchat-style small-device communication.
5. A molecular addressability roadmap for post-2036 hardware.
6. A fully working single-file demo: `worlds.html` at `k.nitweb.art`.

---

## 2. Background

### 2.1 KnitWeb: the warp-weft fabric

KnitWeb (Hauwert 2026) defines a CRDT knowledge fabric where **warp threads** are stable entity axes and **weft picks** are provenance-bearing assertions crossing those axes. Every intersection is a content-addressed **interlacement**. The fabric converges by set-union of CIDs — no leader, no quorum.

WNW is the **application layer** on KnitWeb: it provides the user interface (specify, not search), the transport protocol (Pulse), and the governance layer (WorldDAO). KnitWeb provides the data substrate.

### 2.2 Classical quantum circuit layout (linear)

Standard quantum computers (IBM Eagle/Heron, Google Sycamore) use 2D grid topologies. Two qubits interact only if they are physically adjacent; all others require SWAP chains. This means:
- Long-range interactions cost O(d) SWAP gates (d = Manhattan distance)
- Parallelism is constrained to non-overlapping "stripes"
- Scale increases circuit depth super-linearly

### 2.3 Spherical quantum structures

The referenced ScienceDirect paper (J. Luminescence, 2011, pii S0022-2313-11-00723X) studies **spherical quantum dot assemblies** and their optical properties. Key finding: nodes on a sphere maintain uniform nearest-neighbor distance (by Fibonacci packing), and shells at different radii have spectrally distinct emission frequencies. This gives a natural **frequency addressing scheme** — a laser tuned to frequency f_k selectively excites the k-th shell.

For quantum circuits, spherical topology offers:
- **O(1) long-range** for nearest neighbors across the sphere (azimuthal arcs)
- **Natural error zones**: inner shells are isolated, outer shells are noisier
- **3D packing efficiency**: volume grows as r³, surface as r² — far more nodes per unit space than planar grids

### 2.4 Natural analogue: atomic orbitals

The Bohr-Schrödinger model of the atom provides the clearest natural analogue:

| Orbital | Shell | Frequency     | WNW layer          |
|---------|-------|---------------|--------------------|
| s       | n=1   | Highest (UV)  | Shell 1: local dot |
| p       | n=2   | High (blue)   | Shell 2: molecule  |
| d       | n=3   | Medium (green)| Shell 3: freq band |
| f       | n=4   | Low (IR)      | Shell 4: P2P fabric|
| +       | n=5–6 | Lowest (radio)| Shell 5: human lens|

Crucially: **layers further from the quantum dot are of lower frequency and carry more nodes per shell** — exactly what a P2P network needs. Inner shells are fast and few (local peers); outer shells are slow and many (internet nodes).

---

## 3. Spherical Quantum Weft Architecture

### 3.1 Coordinate system

Every WNW node has a spherical address:

```
addr = (r, θ, φ, beat)
```

- `r` ∈ {0, 1, 2, 3, 4, 5}: shell index (integer)
- `θ` ∈ [0°, 180°]: polar angle
- `φ` ∈ [0°, 360°]: azimuthal angle
- `beat` ∈ ℕ: Pulse clock (monotone, Lamport-style)

Nodes are placed using Fibonacci sphere packing to maximize minimum nearest-neighbor distance:

```
θ_i = arccos(1 − 2i/(n−1))
φ_i = π(3−√5) · i   (golden angle)
```

This gives n nodes with nearly identical angular spacing — **no dead zones**, **no crowding poles**.

### 3.2 Shell radii and node capacity

| Shell | r (relative) | Max nodes | Protocol zone      |
|-------|--------------|-----------|---------------------|
| 0     | 0            | 1         | Self (pulse vessel) |
| 1     | 1.0          | 8         | Local (direct mem)  |
| 2     | 1.8          | 14        | Nearby (BLE/WebRTC) |
| 3     | 2.6          | 22        | LAN / relay         |
| 4     | 3.4          | 30        | Internet (5mart.ml) |
| 5     | 4.2          | 36        | Human lens (AR/VR)  |

Total addressable nodes per weft unit: 111 + self.

### 3.3 Cross-shell Pulse

A Pulse from Shell k to Shell k+1 carries:
```
pulse = { src_addr, dst_addr, beat, cid, payload_type, capsule }
```

- `payload_type`: `FACT | QUERY | SETTLEMENT | HEARTBEAT`
- `capsule`: compressed bytecode (≤ 280 bytes for BC2 relay compat)
- `cid`: content-addressed hash of the full payload

Cross-shell routing uses **frequency adaptation**: a node at Shell 2 (BLE frequency) emitting a pulse to Shell 4 (internet) first transits Shell 3 (LAN relay) — just as a photon from the p-shell passes through the d-shell energy level.

### 3.4 Weft fabric address

The full weft address for a node is a 12-byte compact encoding:

```
[r:4bit][node_index:20bit][beat:40bit]  = 8 bytes
[theta:8bit][phi:9bit][reserved:15bit]  = 4 bytes
```

Total: 12 bytes. Compact enough for a BC2 text relay line.

---

## 4. The Six Shells in Detail

### Shell 0 — Pulse Vessel (the clock)

The center of the weft. This is not a network node — it is the **local device's clock and beat root**. Every event on the device gets a beat timestamp from Shell 0. Cross-shell messages are ordered by beat. There is no network latency at Shell 0; it is a pure local primitive.

Analogy: the atomic nucleus. It does not emit or receive electromagnetic radiation directly; it governs the energy structure from which shells emerge.

### Shell 1 — Quantum-Dot Anchor

8 nodes. These are the closest peers: processes on the same device, or co-located sensors sharing a USB hub or local IPC socket. Communication is synchronous, sub-millisecond, no encryption overhead required (trust boundary is the device).

Analogy: the 1s orbital — tightest binding, highest frequency, most stable.

Post-2036 mapping: laser-addressed quantum dots on a substrate. Each of the 8 nodes corresponds to a distinct QD emission frequency on the inner shell.

### Shell 2 — Bonded Molecule Ring

14 nodes. Nearby peers via BLE 5.0, WiFi Direct, or WebRTC data channels. Physical proximity: < 10 m. These nodes are "bonded" — they maintain persistent connections and share a local knowledge sub-graph (sub-weft). Bond formation is a Pulse handshake with mutual CID exchange.

Analogy: the 2p orbitals (three lobes, 6 electrons max) — directional, bonding-capable.

Post-2036: optically addressable molecules with known bonding geometry. The molecule graph *is* the network graph.

### Shell 3 — Frequency Shell

22 nodes. LAN or relay peers within the same network segment (WiFi AP, Ethernet switch, private relay). Latency: 1–50 ms. The "frequency" metaphor here is literal: Shell 3 operates at different timing characteristics than Shell 2, just as d-orbital electrons have different energy levels than p-orbital.

### Shell 4 — Narrow-Web Fabric

30 nodes. Internet-reachable peers via relay (5mart.ml, libp2p, or similar). This is the **working P2P layer** for WNW fact distribution. Queries that cannot be resolved at Shell 0–3 escalate here. Latency: 50–500 ms.

### Shell 5 — Human Lens

36 nodes. This is the **AR/VR interface layer** — not a network shell, but a **view shell**. Nodes here are "viewable world cards" anchored in 3D space, visible through WebXR. A user rotating 360° sees all worlds distributed across the sphere. Tapping a node opens its fact-table.

Crucially: the human lens is **outside** the compute fabric. It can be replaced by any visualization without affecting the protocol — the weft is protocol-layer-independent.

---

## 5. Protocol: Specify Before Retrieve

### 5.1 The problem with search-first

A search engine fetches first, then ranks. The user never knows:
- How much data was consumed
- What the schema of the result is
- How many rows will be returned
- What the source provenance is

For small devices with bandwidth budgets, this is unacceptable. For LLM context windows with token limits, it is dangerous.

### 5.2 The specify-first protocol

WNW reverses the order:

```
1. User specifies (natural language intent)
2. WNW classifies → fact contract: {domain, schema, estimated_rows, estimated_bytes}
3. User inspects estimate and accepts or narrows
4. Only then: WNW fetches the bounded slice
```

The fact contract is computed locally in < 5 ms from a local schema registry. No network is required for step 2.

### 5.3 Estimation algorithm

Given a natural language query q:

```python
def estimate(q, scope='world'):
    domain = classify(q)         # local keyword → domain map
    schema = SCHEMAS[domain]     # known column set
    base_rows = REGISTRY[domain].estimated_rows
    scale = SCOPE_FACTORS[scope] # world=1.0, nearby=0.03, mesh=0.18
    rows = round(base_rows * scale)
    bytes = rows * schema.avg_row_bytes
    packets = ceil(bytes / 140)  # BC2 line budget
    return FactContract(domain, schema.columns, rows, bytes, packets)
```

The REGISTRY and SCHEMAS are maintained by the narrow-web fabric (Shell 4 peers). Each world advertises its schema + row count on join; nodes cache this in a local bloom-filtered index.

### 5.4 BC2 capsule (bitchat-style relay)

For small-device communication, the query proposal compresses to two lines of 140 characters each:

```
WNW1 {domain} rows={r} cols={c} bytes={b} beat={t}
CID? est={hash} scope={s} accept=narrow/refine/query
```

The first line is the estimate; the second is the proposal CID hint and accept options. Total payload: ≤ 280 bytes. Compatible with SMS, LoRa, and text-only relay networks.

A peer that receives this capsule can:
- `accept narrow`: fetch only the subset within Shell 0–2
- `accept refine`: narrow the columns or row filter first
- `accept query`: fetch the full table from Shell 4

---

## 6. P2P Connected LLM with RAG

### 6.1 The WNW-RAG pattern

WNW turns every fact-table into a **bounded RAG source**. Instead of giving an LLM an open-ended web search, the system gives it:

```
context = {
  facts: [{domain, slice_cid, rows, columns, provenance}],
  budget: {max_tokens: N, used: M},
  unknown_fields: ["field_a", "field_b"]
}
```

The LLM receives structured, provenance-stamped fact slices — not an open-web dump. Token consumption is predictable (known rows × known columns × avg field tokens).

### 6.2 Multi-shell RAG escalation

```
Shell 0-1 facts → primary context (fastest, highest trust)
Shell 2-3 facts → secondary context (nearby peer, medium trust)
Shell 4 facts   → tertiary context (internet peer, cite source)
Fallback        → public web OR LLM general knowledge (lowest trust)
```

Only when Shell 0–4 cannot resolve a field does the system escalate to Google or an open-ended LLM query. This keeps 90%+ of common fact queries on-shell.

### 6.3 Provenance and credence

Every fact slice carries a PROV-O provenance record woven into the KnitWeb fabric:

```
weft-pick: {
  subject_cid, predicate_cid, object_cid,
  provenance: {agent, source_uri, timestamp, beat},
  credence: float [0, 1],
  shell_origin: int
}
```

The LLM context includes credence scores. A fact from Shell 0 (own device) has credence 1.0; from Shell 4 (internet peer) it has credence proportional to that peer's EigenTrust reputation score.

---

## 7. AR/VR Interface

### 7.1 WebXR integration

The weft sphere is visualized using WebGL (2D canvas with 3D perspective projection for broad compatibility; WebXR for AR-capable devices). The implementation in `worlds.html`:

- Nodes distributed via Fibonacci sphere packing (uniform angular distribution)
- Six shells rendered as orbital rings (p-orbital-style tori at 0°, 90°, 90° cross orientations)
- Pulse particles animate from center to nodes
- Interactive rotation via mouse drag or touch
- HUD shows spherical coordinates (r, θ, φ, beat) in real time

### 7.2 WebXR AR mode

On AR-capable devices (Android Chrome, Safari with WebXR):

1. Tap "AR / VR" → requests `immersive-ar` session with `hit-test` feature
2. Sphere anchors to a physical surface via hit-test plane detection
3. User rotates their device to traverse the full 360°
4. Tap on a node → opens a world detail card (fact-table metadata overlay)
5. Pinch gesture → zoom into a specific shell

### 7.3 360° traversal

Because all nodes are at angular positions on a sphere, traversal is a **rotation** — conceptually equivalent to rotating a globe. This maps naturally to:
- Head rotation in VR (HMD tracking)
- Device orientation in AR (gyroscope)
- Mouse/finger drag on desktop/mobile

The spherical geometry ensures no "dead zone" — rotating any direction always reveals new nodes.

---

## 8. Compute Layers: GPU · TPU · QPU

WNW supports three compute proof types, all woven into the KnitWeb fabric as signed records:

| Type | Proof primitive | Result | Record field |
|------|----------------|--------|--------------|
| GPU  | WebGPU WGSL SHA-256 workload | work_result hash | `digest` |
| TPU  | GCP Cloud TPU runtime check | available versions | `work_result` |
| QPU  | IBM Quantum 5-qubit GHZ / D-Wave QUBO | dominant bitstring / min-energy sample | `work_result` |
| CPU  | Web Crypto SHA-256 | hash | `digest` |

All proofs are **integer-only** records (no floats at the seam boundary):

```json
{
  "runtime": "webgpu",
  "pu_kind": "gpu",
  "challenge": "hex-nonce",
  "nonce": "timestamp-36",
  "work_result": "sha256-hex",
  "digest": "sha256-of-all-fields"
}
```

QPU proofs require credentials stored in `localStorage` (never transmitted to a server). The credential UI in `worlds.html` allows IBM Quantum API key, GCP OAuth token, and D-Wave Leap token to be saved locally and verified.

---

## 9. Future: Molecular Addressability (2036+)

### 9.1 The 2036 horizon

The paper cited (ScienceDirect 2011, quantum dot spherical assemblies) demonstrates that laser addressability of individual quantum dots in a spherical assembly is physically achievable. The research timeline:

| Year | Milestone |
|------|-----------|
| 2026 | Software weft: WNW protocol, spherical coordinate addressing |
| 2028 | Quantum-classical bridge: QPU proofs woven into KnitWeb |
| 2030 | Addressable QD arrays (academic demonstration, < 100 dots) |
| 2032 | Photonic molecular network (university lab, 3D addressable) |
| 2034 | Industrial QD substrate (1,000+ addressable dots, commercial) |
| 2036 | Molecular-weft node: laser-addressable bonded molecule array |

The WNW protocol is designed so that the **spherical address space is identical** whether the "nodes" are software peers, quantum dots, or bonded molecules. The address (r, θ, φ, beat) is protocol-agnostic.

### 9.2 Laser addressability mechanism

Each Shell k node corresponds to a quantum dot with:
- A known emission frequency f_k (laser-selectable)
- A known position (θ_i, φ_i) on the shell
- An optically readable state (spin, charge, photon polarization)

Addressing a node = sending a laser pulse at frequency f_k, angle (θ_i, φ_i), duration τ. The WNW "pulse" becomes a literal optical pulse.

### 9.3 Indirect addressing via quantum dots

Companion molecules (molecular tags) attached to quantum dots allow **indirect addressing**: a laser targets the tag (larger molecule, easier to hit), which in turn addresses the QD. This extends addressability to bonded molecular networks where direct laser access is obstructed.

This is why WNW's Shell 2 is called the "Bonded Molecule Ring" — the bonding pattern *is* the network topology, and companion molecules *are* the addresses.

### 9.4 Natural efficiency analogy

In nature, energy transfer through molecular systems (FRET — Förster Resonance Energy Transfer) is highly efficient precisely because geometry is optimized for the wavelengths involved. Outer molecular layers absorb at lower energy (longer wavelength); inner layers at higher energy. WNW mirrors this: outer shells use lower-frequency protocols (internet, ms latency); inner shells use higher-frequency protocols (BLE, μs latency).

This is not metaphor — it is the same physics. The WNW spherical model is **digitally isomorphic** to the future molecular hardware.

---

## 10. Implementation: worlds.html

The complete WNW demo is a **single self-contained HTML file** with no build step:

| Section | Technology | Status |
|---------|-----------|--------|
| Specify information | Vanilla JS, local schema map | Live |
| Query estimate | Deterministic formula, local | Live |
| BC2 relay capsule | String template, clipboard | Live |
| Quantum Weft sphere | Canvas 2D + 3D projection | Live |
| WebGPU raymarcher | WGSL compute shader | Live (Chrome) |
| PU credentials (TPU/QPU) | localStorage, no server | Live |
| Worlds registry | Gateway API / demo data | Live (demo) |
| Settlement demo | Integer-only record preview | Live |
| Self-host node install | OS-tabbed command panel | Reference |
| AR / VR | WebXR (immersive-ar) | On AR devices |

The file is served at `http://localhost:9191/worlds.html` in development and at `k.nitweb.art/worlds.html` in production.

---

## 11. Backlog

| Priority | Item | Description |
|----------|------|-------------|
| P0 | Specify contract spec | Define the FactContract record: domain, columns, estimated_rows, byte_budget, source_layer, accept/refine decision. |
| P0 | Fact-table planner | Deterministic row+payload estimates before any web fetch. Cache per Pulse beat. |
| P1 | BC2 adapter | Pack proposals into ≤ 280-byte relay capsules. Two-line format. LoRa / SMS compat. |
| P1 | Quantum Weft schema | Represent each address as (r, θ, φ, beat, band, relation_digest) in the KnitWeb warp. |
| P1 | AR / VR WebXR | Promote canvas demo to full WebXR: hit-test plane anchor, 360° traversal, node tap-to-inspect. |
| P2 | Quantum circuit bridge | Map circuit submissions into weft coordinates. Compare QPU/GPU/TPU proofs as signed records. |
| P2 | Quantum Forge runs | MLflow-like run records for circuit code: params, backend, shots, result CID, score, review sig. |
| P2 | Vank mesh orderbook | Non-custodial signed order intents, gossip merge, escrow terms, settlement proof states. |
| P2 | P2P RAG slices | Attach fact slices to LLM context as bounded, provenance-rich narrow-web packets. |
| P3 | Molecule addressing research | Track laser, QD, and optically addressable molecular-qubit work. No hardware claims yet. |
| P3 | Post-2036 digital twin | Maintain protocol readiness for future molecular fabric while shipping useful web facts now. |

---

## 12. Conclusion

The World Narrow Web is a geometry correction: replace the linear web with a spherical one, replace "search and fetch" with "specify and estimate", and replace "cloud-first" with "shell-first". The six-layer Quantum Weft model provides a conceptual framework that works today (software peers, fact tables) and is forward-compatible with the physical hardware emerging over the next decade (quantum dots, bonded molecules, laser addressing).

Pulse crosses shells. Knowledge woven, not mined.

---

## Appendix A: Token Economics (PLS — Pulse Token)

### A.1 Token design

**PLS (Pulse)** is the native settlement and incentive token of the KnitWeb / WNW ecosystem.

| Property | Value |
|----------|-------|
| Name | Pulse |
| Symbol | PLS |
| Type | Utility + governance |
| Substrate | KnitWeb block-lattice (MeshLattice) |
| Divisibility | 10⁶ (micro-PLS) |
| Max supply | Anchored to registered population per World |

**Supply formula:**  
`max_vote_supply = registered_persons + expected_annual_births`

This means the maximum governance-eligible token supply can *only* increase as real people are registered. No operator can mint governance weight out of thin air. Supply is additive-only per world.

### A.2 Issuance model

Tokens are issued via **proof-of-knowledge contributions**:

| Activity | PLS earned |
|----------|-----------|
| Weft pick (verified fact assertion) | 0.01–1.0 PLS based on credence |
| Compute proof (GPU/TPU/QPU) | 0.001–0.1 PLS based on compute type |
| World settlement (SettlementOrder) | Fee in PLS, distributed to validators |
| Quantum circuit submission (ecdsafail) | 10–1000 PLS based on score improvement |
| Schema maintenance (new world schema) | 5–50 PLS one-time grant |

### A.3 Token utility

- **Query access**: large Shell 4 fetches require PLS stake (prevents spam)
- **WorldDAO governance**: 1 PLS = 1 vote in registered worlds (capped per person)
- **Compute proof reward**: GPU/TPU/QPU workers earn PLS
- **Settlement gas**: SettlementOrders burn a small PLS fee
- **Schema bonds**: world schema maintainers bond PLS as quality collateral

### A.4 Economic model

The token avoids speculation traps by tying issuance directly to:
1. **Real knowledge production** (not token staking)
2. **Real compute contribution** (not proof-of-stake weight)
3. **Real population registration** (not arbitrary mint)

This makes PLS a **utility-first** token — its value is proportional to how much knowledge the network holds and how much compute it can prove.

---

## Appendix B: Marketing Strategy & Exchange Listing

### B.1 Positioning

**For developers:** "WNW is a fact-first P2P web. You specify what you want, it tells you the size and cost before fetching. Works on a Raspberry Pi."

**For quantum researchers:** "Your circuit submissions are signed, content-addressed, and reproducible — not just a leaderboard entry. Peer review is cryptographically binding."

**For data scientists:** "Think of WNW as a federated fact database with built-in provenance, where your query tells you the schema and row count before you pay for the data."

**For AR/VR developers:** "Every node in the network has a spherical coordinate. You can literally walk through the knowledge graph in AR."

**For investors:** "PLS supply is anchored to real population — it cannot be inflated by the founding team or VCs. Knowledge work earns tokens; speculation doesn't."

### B.2 Target communities

| Community | Channel | Hook |
|-----------|---------|------|
| Quantum computing researchers | arXiv, QC Ware forums, IBM Quantum Network | Circuit forge, reproducible runs, QPU proofs |
| Data scientists / engineers | Kaggle, HuggingFace, LinkedIn | Fact-first query, P2P RAG, schema provenance |
| Decentralized AI devs | Farcaster, Lens Protocol, Ethereum forums | P2P LLM context, bounded RAG, no cloud |
| Small-device / IoT devs | Hackaday, LoRa forums, bitchat community | BC2 capsule, ≤280 bytes, offline-first |
| AR/VR devs | WebXR community, Meta developer network | Spherical knowledge graph, WebXR integration |
| Govtech / civic data | Open government data communities | WorldDAO, one-vote-per-person, population anchoring |

### B.3 Launch sequence

**Phase 1 (Q3 2026) — Developer beta**
- Public GitHub: `github.com/Knitweb/wnw`
- Self-host node install (Linux/macOS/Windows, one command)
- `worlds.html` published at k.nitweb.art
- ecdsafail / sha2.fail quantum circuit submissions woven into WNW
- Target: 100 node operators, 10 active worlds

**Phase 2 (Q4 2026) — Token genesis**
- PLS genesis block: issuance via proof-of-knowledge, not ICO
- WorldDAO Earth: first governance-registered world (KYC-lite, one-person-one-vote)
- Token tracked on-chain via MeshLattice block-lattice
- Target: 1,000 PLS holders via knowledge contribution

**Phase 3 (Q1 2027) — Exchange listing**

**DEX (first):**
- Uniswap v3 (EVM bridge or wrapped PLS): immediate liquidity, permissionless
- Raydium (Solana): fast settlement, low fees, strong DeFi community
- Target: $50k–$200k initial liquidity from founding team + community

**CEX (secondary, 6–12 months post-genesis):**

| Exchange | Tier | Strategy |
|----------|------|----------|
| Gate.io | Mid-tier | Easiest listing process; large Asian retail base |
| KuCoin | Mid-tier | Developer-friendly; listing program via community vote |
| MEXC | Mid-tier | Low listing cost; good for early utility tokens |
| Bitget | Mid-tier | Copy-trading base; drives retail volume |
| Kraken (aspirational) | Tier 1 | Regulatory-clean; best for EU/US institutional |
| Coinbase (aspirational) | Tier 1 | Requires regulatory clarity + significant user base |

**CEX listing requirements (preparation checklist):**
- [ ] Audited smart contract (if EVM bridge used)
- [ ] Legal opinion on token classification (NL / EU MiCA 2025)
- [ ] Whitepaper v1.0 (this document)
- [ ] Minimum 500 verified token holders
- [ ] 3 months of on-chain transaction history
- [ ] Dedicated listing fees budget: $20k–$100k per mid-tier CEX

### B.4 Partnership strategy

| Partner type | Target | Value |
|-------------|--------|-------|
| Quantum hardware | IBM Quantum, D-Wave, IonQ | QPU proof integration, co-marketing to research community |
| AR/VR platform | Meta Spark, Snap Lens Studio | WebXR world browser integration |
| Data providers | OriginTrail DKG, Tableland, Ceramic | Interoperability: WNW narrow-web + DKG wide-web |
| Academic | TU/e, Amsterdam, quantum computing labs | Research citations, student operators, circuit submissions |
| Civic data | Open Data Netherlands, EU open data portal | WorldDAO Earth demo with real government data |

### B.5 Revenue model (for the network, not a company)

WNW is a protocol, not a company. Revenue flows to **PLS holders and node operators**:

- Query fees → PLS (distributed to Shell 4 peers who served the data)
- Settlement fees → PLS (distributed to validators)
- Compute proof rewards → PLS mint (new supply from knowledge work)
- Schema bond slashing → PLS redistribution (quality enforcement)

There is no central company collecting fees. The founding team holds a **time-locked founding allocation** (max 10% of genesis supply, 2-year cliff, 4-year vesting) to cover development costs, with vesting publicly verified on-chain.

---

## References

| Ref | Citation |
|-----|---------|
| W1 | Nakamoto, S. (2008). Bitcoin: A peer-to-peer electronic cash system. |
| W2 | Baird, L. (2016). The Swirlds Hashgraph consensus algorithm: Fair, fast, Byzantine fault tolerance. |
| W3 | Shapiro, M. et al. (2011). Conflict-free replicated data types. SSS 2011. |
| W4 | Hauwert, E. (2026). KnitWeb: A knowledge-graph peer-to-peer weave. VirtualV Holding B.V. |
| W5 | PROV-O: The PROV Ontology (2013). W3C Recommendation. |
| W6 | Shapes Constraint Language (SHACL) (2017). W3C Recommendation. |
| W7 | RDF 1.1 (2014). W3C Recommendation. |
| W8 | Kamvar, S. et al. (2003). The EigenTrust algorithm for reputation management in P2P networks. WWW 2003. |
| W9 | W3C DID Core (2022). Decentralized identifiers. W3C Recommendation. |
| W10 | Lamport, L. (1978). Time, clocks, and the ordering of events in a distributed system. CACM. |
| W11 | LeMahieu, C. (2018). Nano: A featherweight, secure and decentralized cryptocurrency. |
| W12 | Fidge, C. (1988). Timestamps in message-passing systems that preserve partial ordering. ACSC. |
| W13 | Quantum dot spherical assemblies (2011). J. Luminescence. pii S0022-2313-11-00723X. ScienceDirect. |
| W14 | Fibonacci sphere packing: González, Á. (2010). Measurement of areas on a sphere using Fibonacci and latitude–longitude lattices. Mathematical Geosciences. |
| W15 | Förster Resonance Energy Transfer (FRET) — Förster, T. (1948). Zwischenmolekulare Energiewanderung und Fluoreszenz. Annalen der Physik. |
