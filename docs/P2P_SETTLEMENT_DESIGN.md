# Design — P2P-distributed crowdfunding settlement

Status: **design / RFC** (no code). The merged crowdfunding stack produces a signed, audited
`crowdfunding-settlement` instruction and a *local* executor (`execute_settlement`) that moves
PLS escrow→payee when **both accounts are in one process**. This document designs the
**distributed** execution — escrow and payees on different nodes — which is the remaining real
piece. It needs owner decisions on the custody/liveness model before implementation.

## The constraint that shapes everything

knitweb `Knit` transfers are **dual-signed** (sender proposes + receiver accepts; see
`ledger/node.py` `propose`/`accept`/`apply_sent`/`apply_received`) and applied **per-account in
nonce order**. Two consequences:

1. An escrow **cannot unilaterally push** funds to a payee — the payee must co-sign acceptance.
   So settlement is inherently a set of two-party handshakes, not a batch the escrow applies alone.
2. All payouts from one escrow share a single nonce sequence — the escrow must apply them in a
   **deterministic order, one at a time** (the settlement's sorted entries give that order).

Together these mean a robust distributed settlement must tolerate **payees being offline** and
must be **idempotent/resumable**.

## Two models

### Model A — escrow-push (both online, simplest)
The escrow drives, in settlement-entry order:
1. Authority publishes the signed `crowdfunding-settlement` (already built) to the fabric.
2. For entry *i* (payee, amount), escrow `propose`s a sender-signed Knit at its current nonce and
   sends it to the payee over the wire (`p2p/node.py`).
3. The payee **validates the proposal against the published settlement** — the Knit's
   `(to_pub, amount)` must match a settlement entry whose `payee == self`, and the settlement must
   `audit_settlement` — then `accept`s (receiver-signs) and returns it.
4. Escrow `apply_sent`, advances nonce, payee `apply_received`; move to entry *i+1*.

Idempotency: the escrow persists `(settlement_cid → next_entry_index)`; on restart it resumes.
A payee accepts a given `(settlement_cid, entry)` at most once (dedup). This generalizes the
in-process `applied`-set guard already shipped.

**Weakness:** a single offline/unresponsive payee stalls its entry. Acceptable for release
(one beneficiary, presumably online) but poor for refunds (many pledgers, often offline).

### Model B — payee-pull / claim (robust to offline payees) — recommended for refunds
Invert the handshake: the **payee initiates**.
1. Authority publishes the settlement; escrow funds remain in the escrow account.
2. Any payee, whenever online, builds a **claim**: it `propose`s the *receive* by presenting the
   settlement + its entry, and the **escrow** (a service that stays online) verifies the entry,
   co-signs as sender, and the transfer completes. The escrow enforces **claim-once** per
   `(settlement_cid, entry_cid)`.
3. Unclaimed funds sit in escrow until claimed (or a documented expiry/forfeiture policy fires).

This removes the "all payees online at once" requirement and matches how real crowdfunding
refunds work (claim/refund-on-demand). Release (goal met) can use Model A (single beneficiary).

## Safety properties (both models)

- **Conservation** — enforced by the ledger (dual-signed Knits, no overdraft); the published
  settlement bounds the total, and per-entry amounts are committed in `settlement_root`.
- **No double-pay** — `(settlement_cid, entry)` is applied at most once (escrow-side dedup, the
  distributed form of the shipped `applied` set); the ledger's per-account nonce prevents Knit
  replay.
- **Auditable** — anyone can reconcile the applied Knits' Braids against the signed settlement
  (`settlement_entries` recomputes the expected `(payee, amount)` set; `settlement_root` commits it).
- **Authorisation** — a payee only ever co-signs/claims an entry addressed to itself in a settlement
  that `audit_settlement` passes; the escrow only signs entries present in the audited settlement.

## Reuses (no new heavy deps)

`ledger/node.py` (propose/accept/apply, two-party transfer), `p2p/node.py` + `p2p/wire.py`
(signed-frame transport), `fabric/feed.py` (publish the settlement as a signed feed entry),
`crowdfunding/campaign.py` (`settlement_entries`, `audit_settlement`). The escrow's
`(settlement_cid → progress)` and `claimed` sets persist via `store.py`.

## Owner decisions needed before building

1. **Custody** — is the escrow a protocol account the campaign authority controls, a multi-sig, or
   a neutral service? (Determines who can co-sign payouts.)
2. **Refund model** — Model B (payee-pull/claim) vs Model A (escrow-push) for refunds.
3. **Liveness/forfeiture** — what happens to unclaimed refunds after the window (indefinite claim,
   expiry to a pool, return-to-treasury)?
4. **Fees** — does settlement deduct a protocol/relayer fee per payout?

## Phasing

- **Phase 1** — Model A escrow-push with a persisted resume cursor + claim-once dedup, tested with
  in-process nodes simulating the two phases separately (extends the current executor tests).
- **Phase 2** — Model B claim endpoint + wire messages over `p2p`, with an offline-payee test.
- **Phase 3** — forfeiture/expiry policy + fees, per the owner decisions above.
