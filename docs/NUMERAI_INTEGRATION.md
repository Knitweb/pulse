# Numerai Signals/Crypto Integration with Knitweb P2P

## Overview

This document describes how Numerai submission data (CORR, MMC, percentile, feature metadata) is published to the Knitweb P2P network as signed, append-only Feeds. This enables:

- **Peer Discovery:** Any Knitweb node can query for Numerai submission data via P2P gossip
- **Data Integrity:** All entries are cryptographically signed using secp256k1
- **Auditability:** Feed history is immutable; readers can verify data hasn't been tampered with
- **Knowledge Graphs:** Submission data is linked to feature lifecycle and asset metadata via LightRAG

## Architecture

### Components

1. **Numerai Feed Integrator** (`/media/knight2/EDS2/projects/numerai-signals/scripts/numerai_feed_integrator.py`)
   - Fetches latest Numerai submission from `competition_feedback.sqlite`
   - Creates canonical entries (wei-scaled integers for floats)
   - Appends to persistent Knitweb Feed using secp256k1 signing
   - Exports signed heads for P2P broadcast

2. **Cloud Routine** (scheduled hourly via Claude Code)
   - Runs integrator every hour at 00-minute mark
   - Fetches fresh submission data from Numerai API
   - Publishes to Knitweb Feed
   - Replicates via Radicle/gither P2P git

3. **Knowledge Graph Integration** (`knowledge_pit/gitnexus`)
   - Feed entries linked to feature families
   - Asset/sector relationships captured
   - Evidence chain: submission → features → RMSE/CORR/MMC proofs

### Data Flow

```
Numerai API / Local Feedback Database
        ↓
Numerai Feed Integrator
    (secp256k1 sign)
        ↓
Knitweb Feed (append-only log)
        ↓
    ┌─────┴─────┐
    ↓           ↓
P2P Broadcast  Knowledge Graph
(DHT gossip)  (gitnexus/LightRAG)
    ↓           ↓
Peer Discovery  Feature Linking
```

## Feed Entry Schema

### Canonical Encoding (wei-scaled)

```json
{
  "tournament": "signals",          // "signals" | "crypto"
  "round": 1291,                    // int (round number)
  "model": "sctr_hdg_mine_tech",    // string (model name)
  "timestamp": "2026-07-13T01:30:00Z", // ISO 8601 UTC
  "corr": 4790000000,               // int (CORR × 10^8, wei-scaled)
  "corr_percentile": 979000000,     // int (percentile × 10^8)
  "mmc": 67754000,                  // int (MMC × 10^8)
  "mmc_percentile": 972600000       // int (percentile × 10^8)
}
```

### Why Wei-Scaling?

Knitweb's canonical encoding forbids floating-point numbers to ensure:
- Deterministic hashing (no floating-point rounding variance)
- Cross-platform compatibility (no IEEE 754 quirks)
- Exact reproducibility for cryptographic verification

Scaling by 10^8 preserves 8 decimal places of precision (sufficient for most financial metrics).

## Feed Identity

Each Numerai Feed has a persistent identity:

- **Feed Public Key (hex):** `02ee0b99af581a0f72e8243e4c6723b140eb99e0b465db12122e42f8b4407d0ac1` (secp256k1 compressed)
- **PLS Address:** `pls1ad5rrppfvzrtyzuuc2pch5pngangw573lu`
- **Keypair File:** `/media/knight2/EDS2/projects/numerai-signals/data/knowledge/numerai_feed_keypair.json`

The keypair is persistent; all entries are signed by the same author across time.

## Verification

Peers can verify Numerai Feed entries using the author's public key:

```python
from knitweb.fabric.feed import verify_entries, FeedHead

# Retrieve entries and signed head from P2P network
head = FeedHead(...)  # from gossip or DHT query
entries = [...]       # entries received from peer

# Verify: signature is valid AND entries reproduce the committed root
if verify_entries(head, entries):
    print("✓ Data is authentic and unmodified")
```

## Cloud Routine

### Scheduling

- **Service:** Claude Code Managed Agents
- **Routine ID:** `trig_0137jUCtDXXsvtTLf2eVa5JZ`
- **Cron:** `0 * * * *` (every hour on the hour, UTC)
- **Repositories:** 
  - `github.com/febuz/knitweb-pulse`
  - `github.com/febuz/knitweb-gither`
  - `github.com/febuz/numerai-signals`

### Execution

The routine:
1. Clones all three repos into the cloud session
2. Runs `numerai_feed_integrator.py`
3. Queries `competition_feedback.sqlite` for latest round feedback
4. Publishes to Numerai Feed
5. (Future) Replicates via gither P2P git

### Monitoring

Latest export: `/media/knight2/EDS2/projects/numerai-signals/data/knowledge_pit/gitnexus/numerai_feed_latest.json`

```json
{
  "head": {
    "feed": "02ee0b99af581a0f72e8243e4c6723b140eb99e0b465db12122e42f8b4407d0ac1",
    "root": "4d84a13c3bf5cfff912c75d9c9338963d6a4e4d18b295b894ebe21502582852d",
    "length": 1,
    "fork": 0,
    "sig": "3045022100e66139cf2b0fac8b66d46ffc4946b757b567d19ab4f70b876610a8d87addca10..."
  },
  "exported_at": "2026-07-13T01:30:00Z",
  "format": "knitweb-feed-v1"
}
```

## Knowledge Graph Linking

### Current Implementation

Entries are logged to:
- **GitNexus:** `/knowledge_pit/gitnexus/numerai_feed_latest.json` (Feed head export)
- **LightRAG:** `/knowledge_pit/lightrag/numerai_feed_facts.jsonl` (Feature linking facts)

### Future Enhancement

Integrate with knitweb's LightRAG + Obsidian knowledge viewers to:
1. Query "Which models have CORR > 0.05?" → resolve to submissions
2. Drill into feature importance by submission
3. Cross-link to RMSE proofs + feature lifecycle entries
4. Timeline view: submission → feedback resolution → next round

## Use Cases

### 1. Peer Discovery of Strong Models

A knitweb node receives the Numerai Feed via DHT and queries:
- "Latest CORR ≥ 0.04?" → Returns sctr_hdg_mine_tech round 1291
- "Top 5 models by MMC?" → Ranks by mmc_percentile

### 2. Feature Importance Tracking

Feature researchers monitor which features are used by top Numerai models:
- Link features_used (from Feed entry) to proof_artifact (RMSE/CORR/MMC)
- Identify correlations: "Crypto dispersion features → 97%ile?" → Prioritize similar work

### 3. Cross-Tournament Comparison

Numerai Signals vs. Crypto tournament performance:
- Same model performance across tournaments
- Feature transfer insights
- Ensemble weighting strategies

### 4. Stake Decision Support

Vbank (sybil-resistant identity) polls: "Should we increase NMR stake in `<model>` given its latest round score?"
- Poll is backed by Numerai Feed data (verifiable)
- Voting weight based on vbank personhood (Sybil-resistant)
- Decision outcome recorded in vbank ledger

## Deployment Checklist

- [x] Feed integrator implemented & tested
- [x] Hourly cloud routine scheduled
- [x] Persistent keypair created
- [x] First entry published to Numerai Feed
- [x] Feed export file generated (gitnexus)
- [ ] P2P replication via gither (pending gither/libp2p wire)
- [ ] LightRAG knowledge graph linking (pending)
- [ ] Vbank poll integration (pending)

## Integration Points

### Knitweb Ecosystem

- **Pulse:** Numerai Feed is a first-class Feed in the Pulse network
- **Gither:** Use P2P git to replicate Feed manifest and proof artifacts
- **Vbank:** Anchor stake decisions to Numerai performance data
- **Lens:** Query interface for "show me all submissions for model X across rounds"
- **Monitor:** Dashboard widget showing latest Numerai round results

### Numerai Ecosystem

- **Signals/Crypto:** Submission data flows out via Knitweb P2P
- **ML Experiments:** Feature proofs link back to model performance (feedback loop)
- **Scoring:** Round_model_performances are ingested + published P2P

## References

- [Knitweb Feed Design](../src/knitweb/fabric/feed.py)
- [Numerai Feed Integrator](../../numerai-signals/scripts/numerai_feed_integrator.py)
- [Knowledge Pit Layout](../data/knowledge_pit/)
- [Canonical Encoding](../src/knitweb/core/canonical.py)
