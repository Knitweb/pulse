# Gap-closure backlog — derived from the Crypto Landscape Analysis

> Source: `Knitweb_Crypto_Landscape_Analysis_20260618.pdf` (Febuz, v1.0, 18 Jun 2026).
> The report inspected this repo (`febuz/pulse`) at its 17–18 Jun 2026 snapshot. Several
> gaps it lists have since been partly addressed — each row below re-checks the report's
> claim against the **current** module tree and proposes a concrete next action.
> Vocabulary follows `CLAUDE.md` (P2P **web** / **fabric**, never "network"; the seven
> primitives are Blob · Fiber · Knitweb · Knit · Braid · Web · Pulse).

## Functional gaps → actions

| ID | Reported gap | Current reality (this tree) | Proposed next action | Priority |
|----|--------------|-----------------------------|----------------------|----------|
| G1 | GPU compute is mostly a spec; deterministic-pulse contract unresolved; no scheduler | `pouw/scheduler.py` exists; `pouw/{challenge,digest,dispute,committee,collateral,escrow}.py` present | Ship a **determinism proof**: two independent runs of one real kernel producing identical output CIDs via `pouw/digest.py`; record in `experiments/ledger.py` | P1 |
| G2 | Economic loop incomplete; per-epoch caps + 1-pulse access payment pending | `token/mint.py` (280 LOC) demand-gated bounded mint; dispute (486 LOC), collateral, escrow present | Close the **per-epoch emission cap + per-bundle PLS access payment** with a property test; adversarially stress the k-of-n quorum in `pouw/committee.py` | P1 |
| G3 | Real-world OriginTrail integration missing (stubs only) | `anchor/origintrail.py` has an HTTP path; `synaptic/origintrail.py` resolution helpers | Prove **one live Knowledge Asset resolution** end-to-end (resolve → compile via `synaptic/bytecode.py` → load), gated behind a network flag; best-effort offline fallback | P2 |
| G4 | P2P transport minimal (static-peer asyncio; DHT deferred) | **Already partly closed**: `p2p/dht_discovery.py`, `p2p/bluetooth_transport.py`, `p2p/anti_entropy.py`, `p2p/bootstrap.py` | Add a **NAT-traversal + churn** integration test over `dht_discovery`; document the open-internet transport story in `docs/` | P2 |
| G5 | No edge deployment path; `edge/` ~190 LOC stubs | **Outdated**: `edge/{arglass,recognize,runtime}.py` ≈ 420 LOC | Wire an **end-to-end edge demo**: compiled bundle → `edge/runtime.py` execution with a signed-output check; capture a proof run | P2 |
| G6 | Governance & Sybil resistance under-specified | reputation via fabric attestation; notary looms optional | Draft a **Sybil-resistance note** (web-of-trust bounds + notary quorum) under `docs/`; no protocol change until reviewed | P3 |
| G7 | MOLGANG is not a live game | `knitwebs/` domain plugins incl. chemistry (L5) | Out of scope for this backlog — track separately; keep as a demo target | P3 |

## Recommendations (report §07) → tracked items

| ID | Recommendation | Concrete first step |
|----|----------------|---------------------|
| R1 | Prove GPU determinism first | Same as **G1** — public two-spider identical-CID benchmark on a real kernel |
| R2 | Ship a minimal live OriginTrail integration | Same as **G3** — one real asset resolved + compiled + edge-loaded |
| R3 | Replace static-peer asyncio with libp2p/DHT | Build on the existing **G4** `dht_discovery` — add discovery + NAT-traversal coverage |
| R4 | Find one paying workload | Product/BD action, not code — note only; the compute path must be demand-gated (`token/mint.py`) |
| R5 | Build a contributor community | Repo hygiene: issues from G1–G5, `CONTRIBUTING`, good-first-issue labels |

## Notes
- Each engineering item (G1–G5, R1–R3) must end with a runnable proof + an
  `experiments/ledger.py` record, per the proofs-first culture.
- GPU work goes through `pouw/scheduler.py`; keep single experiments bounded (minutes).
- This file is an internal backlog, not front-door product prose; keep Knitweb framed as a
  peer-to-peer web / fabric.
