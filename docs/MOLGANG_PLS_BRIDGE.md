# MOLGANG ↔ PLS bridge — design (P0)

Status: v0.1 design (2026-07-21) · extends `DUAL_COIN_IPO_PLAN.md` ("Keep active: molgang")
· TS twin of the settlement core: `febuz/molgang-web/shared/economy/ledger.ts`
· Python core: `Knitweb/vank` `knitweb_vank.apportion` (PR #7, merged)

## 1. Why

MOLGANG is the launch plan's public showcase: a playable chemistry game whose in-game economy
already runs on the pulse doctrine — floats for analytics, **one** quantisation crossing, integer
settlement that provably conserves. This document specifies how in-game value (molCoins) becomes
a **PLS sink/source** without violating the plan's hard rules: no premine, demand-gated mint,
escrow-bounded, and **no chain-writes before the MOLGANG-015 security review** (Athena) and
explicit merge authorization (Alexander).

## 2. What already exists (verified live, 2026-07-21)

| Piece | Where | State |
|---|---|---|
| Hash-chained client journal (`molgang.pulse.journal.v1`) | `frontend/public/lab3d/lab.js`, `frontend/lib/pulseJournal` | live; integrity-verified in browser smokes |
| Server-authoritative economy events | `game-server` ArenaRoom: `collect_result`, `craft_result`, `pollution_charge` | live; identity server-stamped; integer amounts |
| Conserving quantizer (TS) | `shared/economy/ledger.ts` — 32 tests | live (pollution levy, e2e smoke) |
| Conserving quantizer (Python) | `knitweb_vank.apportion` — parity vectors with TS | merged |
| PLS mint | `token/mint.py` (this repo) | implemented; demand-gated, `max_supply` cap |

## 3. Bridge model

**molCoins stay a soft in-game currency.** The bridge settles **per epoch** (e.g. daily), not per
event, and only over *server-authoritative* receipts:

1. **Receipt classes** (whitelist): `session_completed` (quota reached), `craft_result` (ok),
   `pollution_charged` (negative — burns before any mint). Client-only events (e.g.
   `manual_demo_event`) are **never** bridge-eligible.
2. **Epoch close (float lane):** the game server aggregates net earned molCoins per player and
   computes the epoch's PLS budget from the Treasury's demand gate — never from gameplay volume
   alone (anti-farm: gameplay earns a *share of a bounded budget*, not an open faucet).
3. **Quantisation (the single crossing):** `quantize_conserving(weights=net_molCoins,
   total_units=epoch_budget_PLS_base_units)` — conservation proofs guarantee the epoch never
   mints one base unit more than the budget.
4. **Settlement order (integer lane):** per player a `SettlementOrder`-shaped record
   (see `knitweb_vank.settle`): integer base units, pairwise address (personhood doctrine —
   **no identity, no PII**), epoch id, journal-root.

## 4. Verifiability & security preconditions (gates, not options)

- **Signed export:** the game server exposes `GET /bridge/epoch/<id>` returning the receipt batch,
  the client-journal roots involved, and an Ed25519 signature (did:key pattern from `weave-core`).
- **Replay/duplication:** epoch id + journal hash-chain root make batches idempotent; a receipt
  may appear in exactly one epoch.
- **Sybil:** PLS payout addresses require a personhood ticket (vank vBank gate) — one player, one
  stream; unticketed players keep molCoins but accrue no PLS share.
- **Gate P2→P3:** Athena's MOLGANG-015 review (key management, gas/abuse budget, threat model) and
  Alexander's authorization are prerequisites for any non-testnet mint. Until then the bridge runs
  **off-chain verifiable** only.

## 5. Phasing (each phase independently shippable/resumable)

| Phase | Deliverable | Proof |
|---|---|---|
| P0 | this design (review in PR) | — |
| P1 | signed epoch-export endpoint in molgang-web (off-chain) | smoke in the `run-*-smoke.mjs` style: fetch epoch, verify signature + conservation |
| P2 | testnet mint against verified receipts via `token/mint.py` | property test: Σ minted == quantised budget; idempotent replays rejected |
| P3 | mainnet enablement | Athena review artifact + Alexander authorization recorded in repo |

## 6. Out of scope

Direct molCoin↔PLS exchange/trading, client-initiated mints, and any PAR coupling (PAR rewards
FieldObservations via GeoWeave — separate pipeline; see `weave-core`).
