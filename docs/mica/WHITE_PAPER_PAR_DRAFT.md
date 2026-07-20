# Crypto-asset white paper — PAR (DRAFT, not published)

Draft structured per MiCA (EU) 2023/1114 Annex I, prepared for counsel
review (timeline M1). Not notified, not published, not an offer. Shares the
offeror, technology base and process sections with the PLS draft; stated
here in full where PAR differs.

> **Mandatory statement (Art. 6(3)):** This crypto-asset white paper has not
> been approved by any competent authority in any Member State of the
> European Union. The offeror of the crypto-asset is solely responsible for
> the content of this crypto-asset white paper.

> **Responsibility statement (Art. 6(5)):** `[DECISION NEEDED: management
> body of the offeror entity]` declares that the information presented in
> this white paper is fair, clear and not misleading and that there are no
> omissions likely to affect its import.

> **Risk warning (Art. 6(6)):** PAR may lose its value in part or in full,
> may not always be transferable and may not be liquid. PAR is not covered
> by the investor compensation schemes or the deposit guarantee schemes of
> Directive 97/9/EC or 2014/49/EU.

## Summary (Art. 6(7))

PAR ("Pulse Augmented Reality") is the observation coin of the Pulse
ledger. PAR is minted exclusively when a **confirmed, cryptographically
attested field observation** of the physical world — produced by an AR
headset, phone or browser — passes independent peer validation and settles
a PLS-funded observation bounty. The mint is bounded by that settled escrow;
there is no premine and no administrative mint. Raw camera captures never
enter the ledger: records carry only signed, float-free facts with a
tamper-evident digest, and originals stay in the wearer's personal pod.

## Part A / Part B — offeror and issuer

As in the PLS draft: `[DECISION NEEDED: offeror entity]`; there is no
corporate issuer — PAR units are created by the protocol
(`token/par.py`, `ObservationTreasury`) against verified observations only.

## Part C — operator of the trading platform

Not applicable — no admission to trading is sought in this white paper.

## Part D — the crypto-asset project

Pulse AR: consumers (games, explorers, chemistry bounties) escrow PLS on
observation bounties (a geohash cell, an object class, a beat window);
wearers answer them with confirmed observations through one documented
path: device detection → signed mesh envelope (verify-before-trust) →
canonical FieldObservation → attestation → peer validation → settlement.
Clients: Meta Quest 3/3S (Unity), browser (WebGPU vision), BLE mesh for
offline propagation. Chemistry scans feed the MOLGANG learning game and the
public ChemField knowledge field.

## Part E — the offer to the public

- Current phase: free faucet reservations only, capped at 150 persons per
  country with a FIFO waitlist, zero personal data — relying on the Art.
  4(2)(a) and free-offer exclusions (see `CLASSIFICATION_MEMO.md`).
- Total consideration: zero during the faucet phase.
- Future paid offers, if any: `[DECISION NEEDED at M2]` with the Art. 13
  withdrawal right honoured for retail purchasers.

## Part F — the crypto-asset

- Symbol PAR; integer base units on the same ledger as PLS (symbol-typed
  Knit transfers; independent monetary policy — the PLS heartbeat cap is
  deliberately not consulted for PAR).
- Functionality: reward for verified physical-world observations;
  reputation-free, work-backed acquisition path for AR participants.
- Supply: proof-of-observation issuance, mint ≤ the PLS escrow that funded
  the bounty, optional hard cap and per-epoch policy ceilings.

## Part G — rights and obligations

- PAR conveys no claim on any entity, no dividend, no governance right, no
  redemption right; it is a transferable protocol reward.
- Observation records referenced by an issuance are public fabric items;
  the underlying captures remain the wearer's private property in their
  pod, access-controlled by the wearer alone.

## Part H — the underlying technology

As the PLS draft (deterministic integer stack, PoUW), plus the observation
pipeline: geohash-anchored float-free records with `confidence_milli`
(device confidence crosses one declared integer boundary; only true full
confidence counts as confirmed), Ed25519/secp256k1 device keys, sampled
re-execution of vision inference against digest-committed frames, and the
49%-capped, revocable ComputeGrant consent layer for contributed GPU time.

## Part I — risks

- **Value & liquidity**: as PLS — free-floating, no promised listing.
- **Observation integrity**: adversarial physical-world claims are bounded
  by attestation, confirmation, geohash/bounty matching, sampled
  re-execution and slashing — but novel attack surfaces (staged scenes,
  sensor spoofing) remain research areas.
- **Privacy**: the design keeps captures off-ledger; a wearer who
  voluntarily shares pod contents changes their own exposure.
- **Regulatory**: proof-of-observation issuance is a novel fact pattern
  under Art. 4(3); posture may need to shift to the exemption/white-paper
  path entirely (see memo §2).
- `[COUNSEL CHECK: complete against Annex I risk taxonomy]`

## Sustainability indicators (Art. 6(1)(j))

Observation validation consumes consumer-device GPU time under the same
≤49% consent regime as PLS work; per-observation energy is dominated by a
single vision inference pass.
`[DATA NEEDED: measured Wh per observation validation on reference
hardware — produce at M1]`.
