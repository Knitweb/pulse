# MiCA request timeline — PLS & PAR toward the AFM

Scope: offers of PLS and PAR in the EU/EEA under Regulation (EU) 2023/1114
(MiCA), Title II ("crypto-assets other than asset-referenced tokens or
e-money tokens"). Fully applicable since 30 December 2024; the Dutch NCA is
the **AFM** (DNB only enters for ART/EMT, which PLS/PAR are not — see
`CLASSIFICATION_MEMO.md`). The Dutch CASP transitional regime ended
30 June 2025, so any future in-scope *service* needs authorization before it
operates.

Not legal advice; dates after M0 are planning targets, to be confirmed with
counsel. "wd" = working days.

## Regulatory ground rules driving the dates

| Rule | Source | Consequence |
|---|---|---|
| Offer to the public needs a legal person as offeror | Art. 4(1) | Entity decision is the critical path (M0) |
| Crypto-asset white paper per Annex I, incl. tech + risks + sustainability indicators | Art. 6, Annex I | Drafting effort M1; energy metrics needed for the PoUW consensus description |
| **Notify the NCA ≥ 20 wd before publication** (no prior approval) | Art. 8 | The AFM notification is the only hard external clock before publication |
| Publish white paper before the offer starts; AFM forwards to the ESMA register | Art. 9, Art. 109 | Publication gate M3→M4 |
| Marketing communications: fair, clear, consistent with the white paper, identified as marketing | Art. 7 | Comms policy must exist *before* any launch marketing |
| Retail right of withdrawal, 14 days, for paid offers not yet admitted to trading | Art. 13 | Only relevant once anything is *sold*; faucet grants are free |
| Modifications require an updated white paper + notification | Art. 12 | Ongoing obligation from M4 |
| Exemptions: **fewer than 150** persons per Member State (i.e. ≤149); ≤ €1,000,000 total consideration per 12 months; qualified investors only | Art. 4(2) | The faucet's 150/country cap sits one above this line — see memo §2 posture 3 for the 149-vs-150 decision |
| Title II does not apply to free offers (but "free" fails if personal data or fees flow back) and to crypto-assets automatically created as rewards for DLT maintenance / transaction validation | Art. 4(3) | Zero-PII faucet + no-premine PoUW/observation minting are the reliance facts |
| Admission to trading on a trading platform triggers white-paper duties regardless of offer exemptions | Art. 5 | Any future listing re-opens the full Title II path |

## Timeline

| Phase | Window | Requests / actions | Owner |
|---|---|---|---|
| **M0 — foundation** | Jul–Aug 2026 | Engage Dutch crypto counsel; counsel sign-off on `CLASSIFICATION_MEMO.md`; **[DECISION NEEDED]** offeror legal person (VirtualV Holding B.V. / Slag B.V. / new entity); confirm faucet operation stays inside Art. 4(2)(a)+4(3) (150/country enforced, zero-PII, free); inventory of every EU/EEA country the faucet serves | owners + counsel |
| **M1 — drafting** | Aug–Oct 2026 | Complete both Annex I white papers (`WHITE_PAPER_*.md` → counsel-reviewed documents); sustainability-indicator section for the PoUW consensus (consumer-GPU energy figures from `scripts/business_model.py` + monitor telemetry, per the ESMA sustainability RTS); marketing-communications policy; complaints + withdrawal-rights procedure design | eng + counsel |
| **M2 — sign-off** | Nov 2026 | Management-body approval and responsibility statements; machine-readable white-paper format per the ESMA ITS; final legal review; freeze offer parameters | owners |
| **M3 — AFM notification** | early Dec 2026 (**≥ 20 wd before publication**) | File the Art. 8 notification with the AFM for each white paper, incl. the list of host Member States where the offer will run; answer any AFM follow-ups | counsel |
| **M4 — publication & offer** | Jan 2027 | Publish white papers on 5mart.ml + knitweb.github.io (Art. 9); ESMA-register entries appear via the AFM; paid/broader offering beyond the Art. 4 exemptions may start; withdrawal-rights flow live for any paid retail offer | owners |
| **M5 — ongoing** | from Jan 2027 | Art. 12 white-paper updates on significant changes; Art. 7 marketing discipline; annual re-check of exemption headroom (150/MS counters, €1M/12m consideration); **CASP gate**: if any Knitweb service evolves into exchange/custody/platform functions, file an AFM CASP authorization application *before* operating (completeness check 25 wd + assessment 40 wd) | owners + counsel |

## Standing constraints while in the exempt phase (now → M4)

1. Faucet grant counters stay at the per-country cap (code enforces 150
   granted places; the waitlist is the compliance buffer). Note that Art.
   4(2)(a) covers "fewer than 150" = **max 149** — the 149-vs-150 decision
   for EU/EEA countries is with the owners (memo §2, posture 3); never
   raise the cap for EU countries without counsel.
2. The faucet keeps collecting **no personal data** and charging nothing —
   that is what keeps the free-offer route open.
3. No marketing that presents PLS/PAR as investment products; any
   communication stays consistent with the (future) white papers.
4. No admission to trading is sought before M4.
5. All issuance remains protocol-minted rewards (no premine, no direct
   sales), preserving the Art. 4(3) reward-exclusion posture.
