# Crypto-asset white paper — PLS (DRAFT, not published)

Draft structured per MiCA (EU) 2023/1114 Annex I, prepared for counsel
review (timeline M1). Not notified, not published, not an offer.

> **Mandatory statement (Art. 6(3)):** This crypto-asset white paper has not
> been approved by any competent authority in any Member State of the
> European Union. The offeror of the crypto-asset is solely responsible for
> the content of this crypto-asset white paper.

> **Responsibility statement (Art. 6(5)):** `[DECISION NEEDED: management
> body of the offeror entity]` declares that the information presented in
> this white paper is fair, clear and not misleading and that there are no
> omissions likely to affect its import.

> **Risk warning (Art. 6(6)):** PLS may lose its value in part or in full,
> may not always be transferable and may not be liquid. PLS is not covered
> by the investor compensation schemes or the deposit guarantee schemes of
> Directive 97/9/EC or 2014/49/EU.

## Summary (Art. 6(7))

PLS ("Pulse") is the native pay-token of the Pulse ledger, a pure-Python
peer-to-peer web for verifiable compute and traceable knowledge. PLS is
created exclusively as a bounded protocol reward when independently verified
useful work settles (proof-of-useful-work with sampled re-execution). There
is no premine and no administrative mint. Balances are integers; every
client reproduces identical state byte-for-byte. This offer `[DECISION
NEEDED: describe the concrete M4 offer, if any]`.

## Part A — the offeror

- Name / legal form / LEI: `[DECISION NEEDED: offeror entity]`
- Registered office: `[DATA NEEDED]`
- Contact: `[DATA NEEDED]` (responses within the Art. 6 service levels)

## Part B — the issuer (where different from the offeror)

PLS has no issuer in the corporate sense: units are created by the protocol
itself as verified-work rewards (`token/mint.py`, no privileged genesis
allocation). The offeror does not control issuance beyond the published
emission policy parameters.

## Part C — operator of the trading platform (where applicable)

Not applicable — no admission to trading is sought in this white paper.

## Part D — the crypto-asset project

- Project: Knitweb / Pulse — a credibly-neutral P2P web where "spiders"
  perform funded useful work: GPU vision inference, quantum path sampling
  (PQ), chemistry-record validation, relay and storage.
- Repository of record: github.com/Knitweb/pulse (public, reviewed PRs).
- Key participants: `[DATA NEEDED: named natural/legal persons per Annex I]`
- Milestones achieved: ledger + PoUW + sampled re-execution live; PAR
  observation coin (separate white paper); ComputeGrant consent layer;
  launch faucets. Planned: see `../DUAL_COIN_IPO_PLAN.md` §9.

## Part E — the offer to the public

- Nature: `[DECISION NEEDED — current phase relies on the Art. 4
  exemptions: free faucet grants, ≤150 persons per Member State]`
- Total consideration: zero during the faucet phase.
- Withdrawal right (Art. 13): applicable to any future paid retail offer
  for 14 calendar days; procedure: `[DATA NEEDED at M2]`.

## Part F — the crypto-asset

- Symbol PLS; smallest unit: integer "PLS-wei" base units.
- Functionality: payment for verified useful work inside the web; escrow
  collateral in the PoUW marketplace; funding of observation bounties (PAR).
- Supply: demand-gated issuance, reward ≤ escrow actually spent, optional
  hard `max_supply` cap and per-epoch (heartbeat-gated) ceilings.

## Part G — rights and obligations attached to the crypto-asset

- PLS conveys **no** claim on any entity, no dividend, no interest, no
  governance right over the offeror, no redemption right.
- It is transferable peer-to-peer (Knit transfers) and spendable inside the
  protocol (escrow, bounties, fees to workers).
- Future protocol changes follow public review; vBank-based polling may
  inform parameters but creates no enforceable holder rights.

## Part H — the underlying technology

- Pure-Python deterministic stack: canonical CBOR, secp256k1 ECDSA +
  SHA-256, content-addressed records (CIDv1), integer-only state ("no
  floats near the hash"); deterministic float kernel isolated in
  Knitweb/vank for PQ workloads.
- Consensus/settlement: proof-of-useful-work with sampled re-execution and
  slashing of fraudulent proofs; account Braids with spent-knit replay
  protection; P2P signed-feed sync with mailbox relays for NAT'd peers.
- Device participation is consent-based: revocable ComputeGrants cap any
  device's contribution at 49% (4900 bps) of its GPU.

## Part I — risks

- **Value**: PLS floats freely; demand depends on usage of the compute web.
- **Technology**: novel protocol; despite reviewed PRs and 2000+ tests,
  defects may exist; deterministic-execution assumptions could be violated
  by hostile implementations.
- **Counterparty**: PoUW verification is sampled — collusion above the
  sampling/slashing economics could temporarily reward bad work.
- **Liquidity**: no listing exists or is promised; transferability may stay
  peer-to-peer only.
- **Regulatory**: MiCA interpretations (esp. of reward-based issuance) may
  evolve; future services could require CASP authorization.
- `[COUNSEL CHECK: complete against Annex I risk taxonomy]`

## Sustainability indicators (Art. 6(1)(j))

Consensus is useful computation on existing consumer hardware, duty-cycled
to ≤ 49% per consenting device; no dedicated mining fleets, no
hash-lottery. Energy per job class:
`[DATA NEEDED: measured Wh per vision/PQ/chem-validate job on reference
hardware — produce at M1 from business_model.py + monitor telemetry]`.
