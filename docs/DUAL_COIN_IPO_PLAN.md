# Dual-Coin Public Launch Plan — PLS & PAR (with PQ, chemistry, and the 49% GPU wallet grant)

Status: v1.0 (2026-07-20) · Owner: febuz · Canonical repo: `Knitweb/pulse`
Supersedes the scattered per-repo roadmaps; extends the GeoWeave report v1.0
(`/media/knight2/EDS2/XR/geoweave/docs/rapport/`, epics E-numbering continued here).

## 1. Goal

Launch **two coins simultaneously** on the Pulse ledger:

| Symbol | Name | Nature | Issuance |
|---|---|---|---|
| **PLS** | Pulse | native pay-token for verified useful work (GPU compute, validation, relay, storage) | already implemented: `token/mint.py` — no premine, demand-gated, escrow-bounded, `max_supply` cap |
| **PAR** | Pulse Augmented Reality | observation coin: rewards verified, confirmed AR field observations of the physical world | new: same Treasury pattern, minted only against verified `FieldObservation` chains |

**PQ (Pulse Quantum)** is an *application*, not a coin: distributed quantum
computation (Feynman path sampling) paid in PLS, with its deterministic float
kernel in `Knitweb/vank`.

## 2. Naming reality (checked 2026-07-20)

The top-level GitHub names `pulse`, `vank`, `par`, and `pls` are **all taken**
by unrelated accounts (org "Pulse" since 2015; users VANK, Par, Pls). Canonical
homes therefore stay inside the Knitweb org:

- Protocol + coins + AR + quantum + chemistry: **`Knitweb/pulse`**
- Deterministic numeric core ("vank floats") + voting domain: **`Knitweb/vank`**
- Public web entry points: **`5mart.ml/pls`** and **`5mart.ml/par`** (already-working TransIP host with the `api/relay` PHP endpoint, PR #343).

## 3. Repo review outcome & consolidation map

Review of all `febuz/*` and `Knitweb/*` repos (2026-07-20):

**Migrate into `Knitweb/pulse` (this PR):** from `febuz/pulse` — the only
material unique to that older fork: `src/knitweb/edge/pulse_ar/` (observation,
vision, BLE bitchat mesh, glass service; 13 property tests green against this
codebase), `clients/quest3s/` (Unity C# PulseARClient), `docs/PULSE_AR.md`,
`docs/QUEST3S_AR.md`, `examples/pulse_ar_web/`. After merge, `febuz/pulse` is
archived with description `MIGRATED → Knitweb/pulse` (same pattern as
`febuz/votebank → Knitweb/vank`).

**Publish (GeoWeave epic E13, approved):** the four split repos staged in
`/media/knight2/EDS2/XR/splits/` become public Knitweb repos:
`weave-core` (GeoPose + Ed25519 finding ledger + YOLO vision — 10/10 tests),
`weave-node` (FastAPI server + viewer), `weave-client-web` (WebGPU in-browser
YOLO), `weave-client-unity` (Quest 3/3S capture client).

**Keep active:** `pulse`, `vank`, `knitfield` (**runtime dependency** of the
PoUW layer — `knitweb_knitfield` decision layer; do *not* archive), `molgang`,
`virtualpc`, `gither` + `gither.github.io`, `monitor`, `node.knitweb.art`,
`chemfield`, `news`, `docs`, `knitweb.github.io`, `sha256.fail` (PQ benchmark
workload feed).

**Archive (integrated into pulse / migrated back to febuz):**

| Repo | Reason |
|---|---|
| `Knitweb/lens` | integrated as `src/knitweb/lens` + `interpret/` + `quantum/lens_gateway` |
| `Knitweb/vein` | integrated as `pouw/vein_bridge.py` + `pouw/vein_register.py` |
| `Knitweb/bt` | DEX research absorbed by the ledger (`ledger/knit`, CRYPTO_CORPUS_STUDY) |
| `Knitweb/knitweb` | field-kit monorepo spec superseded by pulse + the field orgs |
| `Knitweb/k.nitweb.art` | gallery content superseded by `web/` in pulse + knitweb.github.io |
| `Knitweb/Numer_crypto`, `Knitweb/numerai-crypto-signals` | stale copies; active development is `febuz/numerai-crypto-signals` |
| `Knitweb/agent-mesh-whitepapers` | stale copy; active at `febuz/agent-mesh-whitepapers` |
| `febuz/pulse` | after this PR merges (see above) |

There must be exactly **one** AR stack after this consolidation: capture/vision
engine = `weave-core`; ledger-facing record canon = `fabric/observation.py`
(`FieldObservation`, float-free, geohash-anchored, attested); device layer =
`edge/` (`arglass`, `recognize`, `observer`, `runtime`, and now `pulse_ar` for
the Quest3S/BLE path). Unifying `pulse_ar.service` with `edge/observer` is epic
E14 (below).

## 4. PAR — proof-of-observation issuance

PAR reuses the PLS treasury machinery with one different verification hook:

1. A consumer (game, explorer, chemfield bounty) escrows **PLS** on an
   observation bounty (geohash cell + label class + expiry).
2. A wearer produces a `FieldObservation`; `confidence_milli < 1000` requires
   explicit user/agent confirmation before weaving (existing rule).
3. Peer validation: sampled re-execution of the vision inference on the
   `capture_digest`-committed frame (raw frame stays in the wearer's pod;
   verifier receives it only via the wearer's access grant), plus geohash
   proximity checks (`fabric/spatial.py`).
4. On verification: escrowed PLS settles to the observer, and the Treasury
   mints **PAR ≤ settled escrow** as the observation coinbase — no premine, no
   admin mint, `max_supply` cap, identical audit surface as PLS.

Implementation: generalize `token/mint.py` `NATIVE` to a per-treasury symbol,
add `token/par.py` (ObservationProof adapter implementing the `verify` seam).
Ledger needs no change — `Knit` transfers are already symbol-based integers.

## 5. PQ — Pulse Quantum (Feynman paths) and "vank floats"

Existing: `quantum/simulator.py` is a deterministic statevector simulator
(≤16 qubits, integer counts) used for PoUW verification. PQ adds a **Feynman
path-integral engine** for larger/physical problems: amplitudes as sums over
sampled paths — embarrassingly parallel, ideal for the spider swarm and WebGPU.

Floats are banned from the fabric, but path amplitudes need them. Resolution —
the **vank float kernel** becomes the core of `Knitweb/vank`:

- Deterministic software floats: fixed-format (binary64-emulated, or fixed-point
  128.128) arithmetic with canonically specified rounding, so every peer
  reproduces bit-identical amplitude sums — pure Python, no numpy, mirroring
  `core/canonical`.
- One declared boundary (the `confidence_milli` pattern): amplitudes cross into
  ledger records only as integers (`amplitude_micro`, probability milli-counts).
- vBank voting weights adopt the same kernel — one numeric truth for both
  domains, which is why vank (not pulse) hosts it.

PQ job classes register through the existing `quantum/pouw_register.py`;
verification = sampled path-batch re-execution (same fraud/slash economics as
GPU jobs). `sha256.fail` circuits and molgang quantum chemistry (Aufbau,
valence consistency) are the first two workload feeds. Results are queryable
through `quantum/lens_gateway.py`.

## 6. Shared WebGPU compute — the 49% wallet grant

**By using the Pulse wallet, the user consents to contribute up to 49% of
their GPU to the web.** Design rules:

- **49%, never a majority:** the device owner always keeps priority; mirrors
  the no-privileged-genesis ethos. The number is a *cap*, not a duty cycle —
  contribution only runs when the wallet is open/idle per user setting.
- **Consent is a signed, revocable capability grant** (personhood/anchor
  pattern): `ComputeGrant{device_did, max_gpu_bps: 4900, scopes:[vision, pq,
  chem-validate], expiry}` — woven as a fabric record, revocable like a vBank
  anchor. Wallet UI shows the grant and a one-tap revoke.
- **Enforcement is two-sided:** scheduler-side (`pouw/scheduler.py` caps
  assignment per grant to 4900 bps of the device's benchmark) and client-side
  (WebGPU frame-budget slicing in `weave-client-web` / onnxruntime-web —
  yield to the render loop, hard duty-cycle at 49%).
- **Workloads on the grant:** YOLO vision inference (PAR observations), PQ
  path-batch sampling, chemistry record validation. All paid in PLS via the
  normal PoUW escrow→verify→settle→mint loop.

## 7. Elemental chemical recording × MOLGANG

The chemistry lane makes PLS/PAR carry *knowledge*, not only compute:

- Record canon: `chemistry/schema.py` + `docs/CHEMISTRY_RECORD_SCHEMA.md` —
  elements, bonds, molecules as content-addressed, float-free fabric records
  (energies/masses via the milli/micro integer boundary; vank kernel for any
  derived computation).
- MOLGANG mapping (already the game's vocabulary): **bonds are Knits, molecules
  are Fibers, peers validate with pulses**. A validated in-game synthesis
  becomes a chemistry record; consistency is checked against the quantum
  chemistry module (molgang's Aufbau/valence work) — heavier checks route to PQ.
- PAR × chemistry: scan a real object through the Quest/phone client →
  recognized material/element → confirmed `FieldObservation` with a
  `chem_ref` to the element/molecule node → PAR for the observation, PLS for
  validators. Chemfield aggregates these into the public knowledge field.
- Education loop: molgang players earn starting silk + pulses (free tier), then
  real PLS only through validated chemistry — learning is the faucet's sybil
  cost.

## 8. Public launch: faucets, waitlists, and the web pages

**Two faucets — one per coin — capped at 150 people per country, waitlist
beyond that.**

- Pages: **`5mart.ml/pls`** and **`5mart.ml/par`** (static HTML + a small PHP
  endpoint next to the proven `api/relay/relay.php`; deployed from
  `deploy/5mart/` via the existing `deploy.sh`).
- Flow: visitor generates or pastes a `pls1` address → picks country
  (self-declared at v1) → server counts confirmed grants per (faucet, country);
  slots 1–150 get a claim voucher, later entrants join the waitlist (FIFO,
  position shown). No PII stored: address + country code + timestamp only.
- Sybil hardening (phase 2): a faucet claim requires a vBank personhood anchor
  (zero-PII, pairwise DIDs, revocable) — country then comes from the
  eIDAS/EUDI trusted-RP seam instead of self-declaration, which is what makes
  "per country" honest. v1 ships self-declared + one-address-per-mailbox rate
  limits; v2 upgrades to anchors before any real value moves.
- Faucet grants are **bounded starter amounts** minted through a dedicated
  faucet escrow funded by treasury-verified work — the no-premine rule holds:
  faucet PLS/PAR is real worked value, throttled (150/country) to spread it.

## 9. Phasing (continues GeoWeave epic numbering)

| Phase | Epics | Content | Exit gate |
|---|---|---|---|
| 0 (now) | E13, E15 | repo consolidation: pulse_ar PR, weave-* published, archives, this plan | PR merged; archives done |
| 1 | E16 | PAR treasury (`token/par.py`), multi-symbol Treasury, ComputeGrant record + wallet consent UI | property tests; PAR mint ≤ escrow invariant |
| 2 | E17 | vank float kernel; PQ path-integral module + PoUW job class; WebGPU job format | cross-platform bit-identical amplitude test |
| 3 | E18 | chemistry loop: molgang → chemistry records → PQ validation; chemfield ingest | one full synthesis→record→validate→reward round-trip |
| 4 | E19 | faucet pages live on 5mart.ml (/pls, /par), waitlist, monitoring; launch comms via knitweb.github.io + news | 2×150-cap + waitlist verified; health checks green |
| 5 | E14 | AR stack unification (pulse_ar.service ↔ edge/observer; weave-core GeoPose ↔ geohash boundary) | single documented observation path |

## 10. Non-negotiables carried over

Integer-only fabric (floats only inside the vank kernel and at declared
boundaries) · no premine / no admin mint · raw captures never leave the
wearer's pod · zero-PII identity (anchors, pairwise DIDs) · no synthetic data
in any proof · one canonical repo per component · every phase lands as a
reviewed PR with tests.
