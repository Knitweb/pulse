# Classification memo — PLS & PAR under MiCA

Working analysis for counsel review; not legal advice. Facts are drawn from
the shipped protocol (`src/knitweb/token/mint.py`, `token/par.py`,
`pouw/compute_grant.py`, `deploy/5mart/api/faucet/`).

## 1. Both coins are "other crypto-assets" (Title II), not ART or EMT

| Test | PLS | PAR |
|---|---|---|
| E-money token (Art. 3(1)(7)): purports to maintain a stable value by referencing one official currency | No — no value reference, no redemption claim at par | No — same |
| Asset-referenced token (Art. 3(1)(6)): purports to maintain a stable value by referencing another value/right or combination | No — free-floating protocol reward | No — same |
| Crypto-asset (Art. 3(1)(5)): digital representation of value/rights transferable via DLT | Yes — integer balances moved by Knits on the Pulse ledger | Yes — second symbol on the same ledger |

Conclusion: Title II is the relevant regime; DNB's ART/EMT gatekeeping does
not apply; the AFM is the competent authority.

Neither coin is a financial instrument under MiFID II on the current design
(no share-like rights, no debt claim, no derivative payoff): PLS is a
pay-token for verified compute/validation work; PAR rewards verified physical
observations. **[COUNSEL CHECK]** — confirm no MiFID II re-qualification,
esp. if future staking/yield features are added.

## 2. Why the current phase needs no white paper yet

Three independent postures, deliberately stacked so no single one is
load-bearing:

1. **Reward exclusion (Art. 4(3))** — PLS and PAR come into existence only
   as protocol rewards for verified useful work (sampled re-execution PoUW)
   and verified observations. There is no premine, no admin mint, no primary
   sale by an offeror: issuance is "automatically created as a reward for
   the maintenance of the DLT or the validation of transactions" in
   substance. **[COUNSEL CHECK]** — proof-of-observation is a novel fact
   pattern; confirm it reads as "validation of transactions/DLT maintenance"
   or treat PAR under postures 2–3 only.
2. **Free offer (Art. 4(3))** — the launch faucet charges nothing and, by
   construction, collects no personal data (address + ISO country code +
   timestamp only; IPs only as salted hashes for rate-limiting, never
   stored raw). MiCA deems an offer *not* free where purchasers provide
   personal data or the offeror receives fees/commissions — the zero-PII
   design was chosen to keep this route clean.
3. **Small-circle exemption (Art. 4(2)(a))** — even if the faucet were an
   offer, grants are capped per country in code, with everyone beyond the
   cap on a waitlist that receives nothing. Counters are per
   (faucet, country) ledger files, auditable.
   **⚠ Precision point:** the exemption covers offers "to *fewer than* 150
   persons per Member State" — i.e. **at most 149**. The faucet grants
   exactly **150** places per country. For the 150th grant in an EU/EEA
   country this posture therefore does not apply on its own; postures 1–2
   still cover it. **[DECISION NEEDED]**: either (a) lower the cap to 149
   for EU/EEA countries (one-constant change in `faucet.php`) so all three
   postures hold for every grant, or (b) keep the user-specified 150 and
   rely on the reward-exclusion + free-offer postures.

Residual duties even while exempt: marketing communications must stay fair
and non-misleading, and none of the above helps once **admission to
trading** (Art. 5) is sought — a listing re-opens the full white-paper path,
which is what the M1–M4 timeline prepares.

## 3. Services check (Title V / CASP)

The protocol itself (P2P ledger, self-custody wallets, PoUW marketplace
seams) is not operated as a custodial or exchange service by any Knitweb
entity today. No CASP authorization is therefore required *yet*. Triggers to
watch (each requires AFM authorization before operating, NL transition
already over):

- running a trading platform or exchange function for PLS/PAR;
- custody of client crypto-assets (a hosted wallet);
- placing/reception-transmission style services around the coins;
- operating the faucet in a way that takes consideration.

The 49% ComputeGrant (`pouw/compute_grant.py`) is a *consent capability* for
the device owner's own hardware — it moves compute, not client funds, and is
not itself a crypto-asset service. **[COUNSEL CHECK]** on the marketplace
escrow flows once third parties operate spiders at scale.

## 4. Sustainability indicators (Art. 6(1)(j))

The white papers must include consensus-mechanism energy/climate indicators
per the ESMA RTS. Facts to disclose: proof-of-useful-work on *existing
consumer GPUs* bounded to ≤ 49% duty by revocable ComputeGrants — the energy
spent is the useful computation itself (vision inference, quantum path
sampling, chemistry validation), not a lottery; figures to be produced from
`scripts/business_model.py` and monitor telemetry per workload class.
`[DATA NEEDED: measured Wh per job class on reference hardware]`

## 5. Decisions needed before M3

- **[DECISION NEEDED]** Offeror legal person (Art. 4 requires one for any
  public offer beyond the exemptions): VirtualV Holding B.V., Slag B.V., or
  a new dedicated entity.
- **[DECISION NEEDED]** Host Member States list for the Art. 8 notification
  (which EU/EEA countries the M4 offer actually targets).
- **[DECISION NEEDED]** White-paper language: English is accepted by the
  AFM and matches the repo; confirm.
