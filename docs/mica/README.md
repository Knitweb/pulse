# MiCA dossier — PLS & PAR (Regulation (EU) 2023/1114)

Working documentation preparing the dual-coin launch (PLS + PAR, see
`../DUAL_COIN_IPO_PLAN.md`) for the EU Markets in Crypto-Assets Regulation.

| File | What |
|---|---|
| `MICA_TIMELINE.md` | The filings/request timeline toward the AFM (Dutch NCA), M0–M5 |
| `CLASSIFICATION_MEMO.md` | Why PLS/PAR are "other crypto-assets" (not ART/EMT) and which Art. 4 exemptions the launch design relies on |
| `WHITE_PAPER_PLS_DRAFT.md` | Crypto-asset white paper draft for PLS, structured per MiCA Annex I |
| `WHITE_PAPER_PAR_DRAFT.md` | Crypto-asset white paper draft for PAR, structured per MiCA Annex I |

**Status: preparation only.** These documents are engineering-side working
drafts assembled from the protocol's actual properties. They are **not legal
advice**; every position (classification, exemption reliance, entity choice,
timeline) requires review and sign-off by qualified Dutch/EU crypto counsel
before any notification, publication, or offer. `[DATA NEEDED]` and
`[DECISION NEEDED]` markers flag what only the owners/counsel can supply.

Key design↔regulation couplings already in the shipped code:

- The launch faucets cap grants at **150 persons per country** with a FIFO
  waitlist (`deploy/5mart/api/faucet/`), mirroring the Art. 4(2)(a)
  fewer-than-150-persons-per-Member-State offer exemption — the cap is
  *enforced technically*, not just promised.
- The faucet stores **zero personal data** (address + country code +
  timestamp), which is what keeps a free offer actually "free" in the MiCA
  sense (an offer is not for free where personal data is exchanged).
- PLS and PAR are minted **only** as protocol rewards for verified work /
  verified observations (no premine, no admin mint — `token/mint.py`,
  `token/par.py`), the fact pattern of the Art. 4(3) exclusion for
  crypto-assets automatically created as rewards for maintenance of the DLT
  or validation of transactions.
