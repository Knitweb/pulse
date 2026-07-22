# Paper 9 — The Quanta Series: qua-core to the Browser-Native Node

**Subtitle:** *A module-by-module design conversation — reconstructed — that grows a P2P
world from a single asyncio cell into a browser that is itself an edge node.*

**Status:** Design-conversation capture v0.1 (reconstructed)
**Language:** English capture of a Dutch source conversation
**Scope:** The eleven-step "qua-*" module ladder; the gap analysis (ten missing pieces);
the browser-native node; the ≤49% GPU covenant; the crosswalk onto the Knitweb layers
and the reconciliation with the project non-negotiables.

> **Provenance.** The original series lived on branch
> `claude/pulse-ar-yolo-llm-bluetooth-rpqwvm`, carried in `pulse-ar-series-FULL.bundle`.
> That bundle was lost with its ephemeral session container before it reached the
> remote. This paper reconstructs the series from the owner's design conversation
> (Dutch, July 2026), restored to chronological order (the surviving transcript was
> newest-first). Where the source sketches code, this paper keeps the *shape* —
> directory trees, envelopes, invariants — not the throwaway prototype bodies.

> **Vocabulary rule.** This project is a **web**, never a "network"/"net". The source
> conversation freely used the Dutch *netwerk*; this capture writes **web / fabric**
> throughout and flags every other divergence in §12. The brand terms remain
> **Web · Knit · Pulse · Fiber · knitweb**; a peer node is a **spider**.

> **Normative note (read before the narrative).** This is a *concept capture*; the code
> in `src/knitweb/` is authoritative where they differ. The source prototypes chose
> Ed25519, blake3, HMAC shared secrets, float timestamps and float balances. None of
> those survive contact with the non-negotiables (secp256k1 ECDSA + SHA-256, integer
> money/state, float-free canonical CBOR via `core.canonical`). §12 gives the full
> reconciliation table; every module below must be read through it.

---

## 1. The module ladder

The source builds the world bottom-up, one repository-shaped module at a time, each
snapping onto the previous ones:

```
 1. qua-core         asyncio P2P cell, EHMAC envelopes, Quanta object ids
 2. qua-vank         cryptographic identity, claims, signatures
 3. qua-ledgerfield  append-only event field, hash chain, P2P merge
 4. qua-pulse        wallets, jobs, resource market, settlement
 5. qua-torrent      chunked asset distribution, manifests, swarms
 6. qua-ar           camera → YOLO → located, claimable Quanta object
 7. qua-molgang      world / entity / player / inventory / economy
 8. qua-quantum      circuits, IR, simulator, shot results as assets
 9. quanta-web       React + Three.js user layer over all of it
10. qua-node         the runtime that finally hosts the modules as one process
11. browser node     the pivot: every browser IS the node
```

Steps 1–9 build capabilities; step 10 notices they still lack a *body*; step 11
concludes the body was in front of us all along — the browser.

## 2. qua-core — the first cell

A pure-Python asyncio node: peers exchange JSON packets wrapped in **EHMAC**, a
context-aware HMAC envelope:

```
{ "envelope": { "payload": …, "context": …, "timestamp": … },
  "signature": HMAC-SHA256(secret, canonical(envelope)) }
```

Objects are minted as `qua:<uuid>` with a type, metadata and creation time. Messages
are a tiny action vocabulary (`CREATE_OBJECT`, `PING`, `SYNC`). No central database —
each node keeps what it knows.

```
qua-core/qua_core/
├── node.py       # asyncio server, verifies every inbound packet first
├── peer.py       # connections
├── protocol.py   # message actions
├── ehmac.py      # envelope + verify
├── identity.py   # node identity
└── object.py     # qua:<uuid> objects
```

*Knitweb reading:* this is L2 — signed-feed sync between spiders. The shared-secret
EHMAC is the placeholder the source itself schedules for replacement ("EHMAC key
exchange, public/private keys" in v0.2); in Knitweb the envelope is a signed `Knit`
(secp256k1 + SHA-256) and *verify-before-trust* is already the standing rule.

### 2.1 EHMAC clarified — a context layer, not a new primitive

A later turn of the conversation sharpens the design with an explicit security
stance: **EHMAC must not be positioned as a replacement for HMAC.** HMAC is a
well-studied, widely analysed construction; a homegrown variant would be a new
protocol demanding extensive analysis before any security-critical use. The safe
split:

```
                 QUA Protocol
                      │
        ┌─────────────┴─────────────┐
   HMAC-SHA-256                   EHMAC
 (transport security)     (metadata / provenance)
        └─────────────┬─────────────┘
                      │
                Signed Packet
```

EHMAC is then *defined as* standard HMAC over a **standardised context envelope**:

```
EHMAC = HMAC + protocol version + Quanta object id + VANK identity
       + timestamp + node id + nonce + ledger sequence + capability flags
```

yielding packets of the shape:

```
{ "packet": { … },
  "ehmac": { "algorithm": "EHMAC-v1",
             "context": { "node": "qua-node-001", "object": "qua:asset:12345",
                          "ledger": 58231, "timestamp": 1784729200, "nonce": "…" },
             "signature": "…" } }
```

Intended uses: P2P message authentication, object-claim validation, GPU job
assignment, quantum-shot requests, torrent manifests, Quanta object mutations. The
source's own advice: keep HMAC-SHA-256/512 as the cryptographic core; EHMAC is a
protocol layer that signs extra, standardised context — never a new hash function —
so the construction inherits HMAC's proven security and stays externally reviewable.

*Knitweb reading:* the split maps cleanly. A keyed transport MAC over an
established session is legitimate at L2; but everything on the list that *changes
state* — claims, mutations, job assignments, manifests — is value-path and therefore
carries a secp256k1 ECDSA + SHA-256 signature from a per-account key, not a shared
secret (a MAC cannot prove *who* to a third party; provenance requires signatures).
The context envelope itself is the good idea to keep: version, object CID, address,
integer timestamp, nonce and ledger sequence belong in the signed body, encoded via
`core.canonical.encode` — replay protection via nonce + the hash-critical `network`
id field a signed `Knit` already carries.

## 3. qua-vank — identity

Every participant derives a `vank:<base58(sha256(pubkey)[:20])>` id from a local
keypair; identity lives on the device, never on a server. On top of the keys:
**claims** (`ownership`, `observation`) binding a VANK id to a Quanta object id, and
detached signatures over canonically-serialized JSON. The source plans WebID / Solid /
DID bridges later.

```
qua-vank/qua_vank/
├── identity.py   # vank:<id> from pubkey hash
├── keys.py       # local keypair
├── claim.py      # ownership / observation claims
└── signature.py  # sign / verify canonical JSON
```

*Knitweb reading:* this is the account layer — an address is already a hash of a
secp256k1 public key, and the `vank` repository carries the account tooling. The
source's Ed25519 choice is replaced wholesale (§12); the *claim* object maps onto a
signed, content-addressed record whose CID lands in the fabric.

## 4. qua-ledgerfield — the event field

Deliberately **not** a database and not a blockchain: an **append-only event field**.
Each event (`CREATE`, `CLAIM`, `TRANSFER`, …) names an object, an actor and data; the
field chains events by hashing `{previous, event}` so history is tamper-evident; sync
is a set-merge of events a peer hasn't seen (CRDT-shaped, refinement deferred).

```
qua-ledgerfield/qua_ledgerfield/
├── event.py      # type, object_id, actor, data, timestamp, hash
├── ledger.py     # append-only chain from "GENESIS"
├── hash.py       # content hash of canonical JSON
└── sync.py       # merge remote events by hash novelty
```

The first full chain the source celebrates:

```
VANK ── signs ──▶ QUA Object ── creates ──▶ LedgerField event ── syncs ──▶ P2P web
```

*Knitweb reading:* the event field is the L1 ledger seen from provenance's side —
`Braid` links of content-addressed records, hashed through `core.canonical.cid`
(CIDv1 dag-cbor sha2-256), never ad-hoc JSON hashing. The bookkeeping-flavoured
sibling lives in the `ledgerfield/ledgerfield` repository.

## 5. qua-pulse — the economy

Wallets bound to VANK ids; `reserve` fails on insufficient funds; transactions carry
sender, receiver, amount, purpose; **compute jobs** carry a task and a reward;
a **resource market** matches capability queries against registered nodes; and
**settlement** pays the provider only when the job completes. Every movement is
recorded as a LedgerField event.

The source is explicit about restraint: *"this is first a protocol credit system for
the web. A real publicly-traded currency requires later work on regulation, consensus
and security."* The worked example: a researcher budgets 500 Pulse for 100 000 quantum
shots; the market picks among GPU-simulator / NMR / QPU nodes on price + reputation +
history; result → LedgerField event → settlement.

```
qua-pulse/qua_pulse/
├── wallet.py      # balance, deposit, reserve
├── transaction.py # pulse:<uuid> transfers with purpose
├── market.py      # capability search over nodes
├── job.py         # OPEN → DONE compute jobs
└── settlement.py  # pay on completion
```

*Knitweb reading:* this is PLS activity accounting (L6) plus the pouw escrow /
settlement path. Amounts are **integer base units** — the prototype's bare numbers are
read as integers, never floats. The "protocol credit, not a speculative asset" stance
is exactly the owner-direction guard.

## 6. qua-torrent — heavy assets off-ledger

Large files (3D models, FBX/glTF, renders, MP4, diffusion datasets, YOLO weights,
simulation output) never enter the event field. Only the **manifest** does: content
hash, owner, chunk table (1 MiB chunks), metadata. Distribution is a P2P swarm; the
ledger records `ASSET_PUBLISHED { quanta_id, torrent_hash, owner }` — identity, not
bytes.

```
qua-torrent/qua_torrent/
├── manifest.py   # asset identity + chunk table
├── chunk.py      # 1 MiB splitting
├── hash.py       # whole-file content hash
├── swarm.py      # who holds which chunk
└── client.py     # publish / fetch
```

*Knitweb reading:* this is the fabric `Blob` layer and the OriginTrail interlock from
Paper 8 — light signed records in the web, heavy artifacts beside it, joined by CIDs.
Hashing goes through SHA-256 CIDs, not blake3.

## 7. qua-ar — the observation layer

The chain the whole game stands on:

```
Camera ─▶ YOLO detect ─▶ geo + time stamp ─▶ qua:ar:<id> object ─▶ VANK claim ─▶ LedgerField ─▶ P2P world
```

Detector wraps ultralytics YOLO (label, confidence, bbox per frame); GeoStamp fixes
latitude/longitude/time; the AR object binds detection + location under a fresh id; a
client publishes it. Planned extensions: a Lens/RLM enrichment layer (web search,
materials, history), 3D model matching (detection → glTF/FBX), a first-observer claim
mechanism with conflict resolution, LiDAR point-cloud fingerprints, and MOLGANG
adoption of the objects as playable assets.

```
qua-ar/qua_ar/
├── camera.py     # frames in
├── detector.py   # YOLO interface
├── tracker.py    # pose estimation (stub)
├── object.py     # detection + location → qua:ar:<id>
├── geo.py        # lat / lon / time
└── client.py     # publish into the web
```

*Knitweb reading:* **already implemented, better, in
`knitweb.edge.pulse_ar`** — the YOLO→CNN→LLM `VisionPipeline`, the
WHAT/WHO/WHERE/HOW/DEVICE `ObjectObservation` (integer basis-point confidence,
integer millimetres, geohash strings — no floats near the hash), secp256k1-signed
observations exchanged over the **bitchat BLE mesh** (`docs/PULSE_AR.md`,
`docs/QUEST3S_AR.md`). The source's float lat/lon + `time.time()` are exactly what the
implementation already refuses. The Lens/RLM enrichment idea maps onto the existing
Lens contracts (`docs/LENS_RLM_CONTRACT.md`).

## 8. qua-molgang — the first game layer

Quanta objects become game entities: `MolEntity` (id, name, category, owner,
position), `Player` (a VANK id with an inventory), `MolWorld` (spawn/get), an
`AssetLoader` over the torrent cache, and a first `Market.buy`. First playable core:
*a world in which every object has a digital identity, a history and an owner.*
Sketched on top: the chemistry lab (reactor, glassware, elements, molecules, quantum
computer), an RTS loop (resource → factory → machine → product → trade), and the AR
loop (YOLO object → qua-ar → MOLGANG entity → claim).

```
qua-molgang/qua_molgang/
├── world.py      # world state
├── entity.py     # game objects bound to Quanta ids
├── player.py     # VANK-identified players
├── inventory.py  # holdings
├── economy.py    # Pulse purchases
└── assets.py     # torrent-backed assets
```

*Knitweb reading:* MOLGANG is the standing L5 domain knitweb (never in core). The
`Market.buy` sketch is superseded by the real MOLGANG↔PLS bridge
(`docs/MOLGANG_PLS_BRIDGE.md`): epoch settlement over the conserving integer
quantizer — verify, apportion, **never mint**.

## 9. qua-quantum — circuits as assets

Circuits are Quanta objects (`qua:circuit:<id>`, qubit count, gate list) compiled
through a small IR to interchangeable backends (local simulator now; GPU/CUDA/WebGPU
simulators and real QPUs later). A run yields a `qua:shot:<id>` **shot result**
(counts histogram + timestamp) — itself a tradable, provenance-carrying asset:

```
Si-28 material → quantum chip → circuit → compiler → simulator/QPU
   → shot result → LedgerField event → Pulse settlement
```

```
qua-quantum/qua_quantum/
├── circuit.py    # qua:circuit:<id> gate lists
├── ir.py         # intermediate representation
├── compiler.py   # optimisation passes
├── simulator.py  # local backend
├── shots.py      # qua:shot:<id> results
└── backend.py    # backend abstraction
```

Planned next: `qua-compiler` — PyTorch graph → quantum IR, Qiskit/Cirq/OpenQASM
import, hardware-aware optimisation, per-shot settlement.

*Knitweb reading:* a pouw **job family**. Scheduling and payment belong to
`pouw/scheduler.py` (bounded experiments) and the escrow path; the shot result is a
content-addressed record like any other useful-work output.

## 10. quanta-web — the user layer

A pure web client (HTML5, TypeScript, React, Three.js, WebXR, WebGPU hooks,
WebSocket/WebRTC to Python nodes): a wallet panel (VANK id + Pulse balance), a 3D
world canvas, object cards (id, owner, Claim button), a Quantum Lab (available
backends, "run 1000 shots", cost in Pulse), and an AR scanner stub. The source's
closing remark is the hinge: a backend gateway would make the website *"actually a
node in the web instead of only an interface"* — which step 11 then makes literal.

```
quanta-web/src/
├── app/App.tsx                          # wallet + world + quantum lab
├── components/{World,ObjectCard,Wallet,QuantumLab,ARScanner}.tsx
├── network/p2p.ts                       # socket to a node
└── api/quanta.ts                        # object fetch
```

*Knitweb reading:* the ecosystem seats for this are `weave-client-web` /
`molgang-web` / `clients/`.

## 11. The gap analysis — ten missing pieces

Half-way through, the source stops building and audits. With qua-core…quanta-web
standing, a *working* game still lacks:

1. **qua-node** — the runtime that binds all modules into one process (the single
   most important gap).
2. **Consensus / conflict resolution** — no blockchain, so "which truth holds?"
   needs claim ranking. Two players claim the same tree; the sketch:

   ```
   claim score = time + GPS + LiDAR match + AI confidence + reputation
   ```

   plus observation proof and cryptographic history. (Knitweb note: any such score
   is computed over **integers** — basis points, millimetres, ranks.)
3. **qua-compute** — the GPU economy: offer capacity → Pulse job → WebGPU/CUDA
   execution → result hash → payment; for diffusion, YOLO, Blender, quantum
   simulation, AI training.
4. **Contract / policy engine** — not blockchain smart contracts but a small policy
   language: `IF gpu available AND price < 10 PLS AND reputation > 95% THEN execute`.
5. **Security layer** — key rotation, node trust, anti-sybil, sandboxing, encrypted
   transport, permissions; critical because arbitrary nodes execute jobs.
6. **Asset pipeline** — scan → YOLO → 3D reconstruction → glTF/FBX → LOD → torrent →
   game asset; Blender pipeline, mesh compression, texture streaming.
7. **WebGPU renderer** — WGSL shaders, ray tracing, physics, AI upscaling; the
   difference with existing games.
8. **Geospatial engine** — world coordinates, 3D tiles, point clouds, object
   anchoring (GIS / digital-twin / SLAM adjacent).
9. **LLM/Lens layer** — YOLO says "reactor"; Lens enriches: type, material
   (stainless steel 316), historical matches, maker, 3D model — with provenance and
   confidence. (Maps onto the existing Lens contracts.)
10. **Developer SDK** — `import quanta; object.claim(); object.trade()`.

And a discipline: don't build everything at once. The **minimal vertical demo**:

```
smartphone AR → YOLO → QUA object → VANK identity → LedgerField event
   → torrent asset → MOLGANG world → PLS claim
then:  GPU node → diffusion render → WebGPU display
then:  quantum circuit → compute marketplace → shot-result ownership
```

## 12. qua-node v0.1 — the runtime

The first body: one asyncio process that loads a VANK identity, a ledger handle and
a wallet; keeps a service registry (`ledger`, `pulse`, `compute`); accepts
`QuantaJob`s (id, type, payload, reward, OPEN→DONE); ticks a loop reserved for P2P
sync / job discovery / heartbeat; and exposes a tiny web API (`GET /status` → node
name, identity, job count). A node introduces itself to the market as:

```
{ "node": "3090-render-node",
  "services": ["diffusion", "yolo", "blender", "quantum-sim"],
  "payment": "pulse", "identity": "vank:xyz" }
```

v0.2 plan: real qua-core coupling, EHMAC handshake, peer discovery, LedgerField
sync, Pulse settlement, GPU worker daemon — "a real distributed compute node instead
of only a local runtime."

*Knitweb reading:* qua-node **is the spider**. The service registry and job loop are
the pouw scheduler's job; the status API mirrors the existing node tooling.

## 13. The browser-native pivot

The closing move discards `qua-node-server` in favour of **qua-browser-runtime**:
the browser is not a client of the web — it is an **edge node**, because the platform
already ships the whole stack:

| Browser API | Node capability |
|---|---|
| WebGPU | GPU compute + rendering (WGSL jobs) |
| WebRTC / WebTransport | P2P transport |
| IndexedDB / Cache API | local asset cache (`reactor.glb`, textures, animations, diffusion cache, YOLO model, quantum results) |
| WebXR | AR observation |
| Service Workers | background work |

```
                Browser Node
                     │
          ┌──────────┴──────────┐
       WebGPU               WebRTC
          │                     │
     AI / render            P2P web
          │                     │
     asset cache         EHMAC messages
          │                     │
       torrent              qua-core
          │
    LedgerField sync
```

Every MOLGANG player's browser is simultaneously **client + server + GPU node +
cache + peer**: it plays, renders effects, re-seeds assets it downloaded, runs YOLO,
helps diffusion renders, validates objects — and earns PLS for the useful capacity. A
laptop contributes a little; an RTX 3090 owner becomes a compute provider
automatically; a smartphone becomes an AR/LiDAR observation node. This, the source
notes, is truer to the original idea than any server: *a P2P world without central
infrastructure.*

### The ≤49% covenant

One governance rule rides along: **a node contracts with the ledger to offer at most
49% of its GPU to the compute market.** The device's owner keeps the majority of
their own machine, by construction — the game/browser experience can never be starved
by the market, and no fleet of contributed GPUs is ever majority-committed to an
external workload. In Knitweb terms this is a signed capacity covenant recorded like
any other agreement and *enforced* where compute is actually dispatched:
`pouw/scheduler.py`, which already owns the "bounded experiments" guardrail. The cap
is stored in integer basis points (4900), like every other bound.

## 14. Crosswalk — Quanta vocabulary to Knitweb

| Quanta (source) | Knitweb (normative) |
|---|---|
| Quanta / QUA object, `qua:<id>` | content-addressed record; CIDv1 via `core.canonical.cid` |
| VANK identity, `vank:<id>` | account address (hash of secp256k1 pubkey); `vank` repo |
| EHMAC envelope (shared secret) | signed `Knit` — secp256k1 ECDSA + SHA-256; verify-before-trust |
| LedgerField event field | L1 ledger (`Braid`/`Fiber` commitments) + provenance fabric; `ledgerfield` repo for bookkeeping |
| Pulse credit / "protocoltoken" | **PLS** activity accounting (L6); integer base units; proof-of-useful-work |
| qua-torrent manifest/swarm | fabric `Blob` layer + OriginTrail heavy-artifact interlock |
| qua-ar | `knitweb.edge.pulse_ar` — implemented (YOLO→CNN→LLM, bitchat BLE mesh) |
| qua-molgang | MOLGANG L5 knitweb; MOLGANG↔PLS bridge (never mint) |
| qua-quantum | pouw job family under `pouw/scheduler.py` |
| qua-node / spider process | the spider runtime |
| qua-browser-runtime | browser spider: `weave-client-web` / `clients/` seat |
| "netwerk" (Dutch prose) | **web / fabric** — always |

## 15. Reconciliation with the non-negotiables

Every prototype choice below is *overridden* by the standing rules; this table is the
contract for any code that grows out of this paper:

| Source prototype chose | Knitweb requires |
|---|---|
| Ed25519 signatures (`qua-vank`) | secp256k1 ECDSA + SHA-256 (`knitweb.core.crypto`) — no Ed25519 in the value path |
| blake3 hashing (`qua-torrent`, `qua-ledgerfield`) | SHA-256 CIDs via `core.canonical.cid` — no BLAKE2b/blake3 in the value path |
| ad-hoc `json.dumps(sort_keys=True)` canonicalisation | `core.canonical.encode` — float-free deterministic CBOR, the only signing/hashing path |
| `time.time()` float timestamps in hashed records | integer time only; floats are rejected near hashing/balances |
| float-capable balances / bare `reward` numbers | integer base units (wei-style) everywhere money moves |
| shared-secret HMAC (EHMAC) as message auth | HMAC-SHA-256 acceptable as transport MAC only (§2.1); all state-changing records signed with per-account secp256k1 keys, verified before trust |
| "protocoltoken", coin-flavoured framing | activity accounting (PLS); owner-direction guard applies to front-door prose |
| privileged node roles implied by "server" | no privileged genesis / founder allocation; spiders are peers |
| unbounded GPU market participation | `pouw/scheduler.py` guardrail + the ≤49% covenant (integer basis points) |

## 16. What this paper adds beyond Paper 8

Paper 8 fixed the data model, the compute layer and the OriginTrail interlock. The
Quanta series contributes, on top:

1. **The browser as a first-class spider** — WebGPU/WebRTC/WebXR/IndexedDB/Service
   Workers as the complete node stack, no install step between a player and the web.
2. **The ≤49% GPU covenant** — an owner-protective, ledger-signed capacity bound.
3. **Claim-score conflict resolution** for first-observer disputes (time + GPS +
   LiDAR fingerprint + detection confidence + reputation, integer-scored).
4. **The minimal vertical demo** as build discipline: one thin end-to-end thread
   (AR scan → claim → asset → world → settlement) before any layer widens.
5. **Quantum shot results as owned, tradable useful-work artifacts.**
