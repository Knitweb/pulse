#!/usr/bin/env python3
"""Publish a relay-status record into the signed FinField *ops feed*.

Closes the last relay-roadmap item (docs/RELAY_COMPETITIVE_NOTES.md #4):
relay health becomes itself P2P-distributed. Every run appends one
``relay-status`` record — a reduced, integer-only snapshot of the 5mart.ml
relay's ``status.php`` — to an append-only feed under ``ops/`` in the
``FinField/feed`` repo, alongside the main data feed under ``feed/``. Any
knitweb node can bootstrap ``ops/`` over HTTPS (GitHub raw, or the 5mart.ml
mirror's ``/api/feed/ops/…``), verify the head signature and every record
against ``knitweb.fabric.feed``, and replicate it onward.

The ops feed has its OWN publisher identity (``~/.finfield/ops_publisher.key``,
minted on first run, chmod 600) — deliberately not the main FinField data
publisher, whose key lives only on the ingest machine. Different feeds,
different keys, same verification path.

Layout published (mirrors the main feed's shape so any feed client
bootstraps it identically):

    ops/records-00001.jsonl   append-only records
    ops/head.json             signed FeedHead {feed, root, length, fork, sig}
    ops/MANIFEST.json         shard list + publisher address

The whole history is rebuilt from the shard on every run and the rebuilt
Merkle root is checked against the stored head BEFORE appending, so a
corrupted or foreign shard aborts loudly instead of being blindly re-signed.
After writing, the new head + entries are verified reader-side
(``verify_head`` / ``verify_entries``) before anything is pushed.

Environment (defaults fit the 96-core box):
    KW_PULSE_SRC       pulse ``src/`` for knitweb imports
    FINFIELD_FEED_DIR  working clone of FinField/feed
    FINFIELD_OPS_KEY   ops publisher key file
    KW_RELAY_STATUS    status endpoint to snapshot

Cron (every 30 min):
    */30 * * * * python3 …/deploy/5mart/tools/publish_ops_feed.py >> ~/logs/ops_feed.log 2>&1
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PULSE_SRC = os.environ.get("KW_PULSE_SRC", "/media/knight2/EDS2/projects/radicle-knitweb/pulse/src")
sys.path.insert(0, PULSE_SRC)

from knitweb.core import crypto  # noqa: E402
from knitweb.fabric.feed import Feed, FeedHead, verify_entries, verify_head  # noqa: E402

FEED_DIR = Path(os.environ.get("FINFIELD_FEED_DIR", "/media/knight2/EDS2/projects/finfield-feed"))
KEY_FILE = Path(os.environ.get("FINFIELD_OPS_KEY", Path.home() / ".finfield/ops_publisher.key"))
STATUS_URL = os.environ.get("KW_RELAY_STATUS", "https://5mart.ml/api/relay/status.php")
REPO_SSH = "git@github.com:FinField/feed.git"


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def load_or_mint_key() -> str:
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    priv, _ = crypto.generate_keypair()
    KEY_FILE.write_text(priv + "\n")
    KEY_FILE.chmod(0o600)
    print(f"minted ops publisher key -> {KEY_FILE}")
    return priv


def fetch_status() -> dict:
    with urllib.request.urlopen(STATUS_URL, timeout=20) as resp:
        s = json.loads(resp.read().decode("utf-8"))
    # Reduced, integer/string-only record: knitweb canonical encoding is
    # float-free by design, and the P2P-interesting part is the counters.
    return {
        "kind": "relay-status",
        "host": str(s.get("host", "?")),
        "t": int(time.time()),
        "ok": 1 if s.get("ok") else 0,
        "node_count": int(s.get("node_count", 0)),
        "mailboxes": int(s.get("mailboxes", 0)),
        "frames_total": int(s.get("frames_total", 0)),
        "queue_bytes": int(s.get("queue_bytes", 0)),
        "peer_reachable": 1 if (s.get("peer") or {}).get("reachable") else 0,
    }


def main() -> None:
    if not FEED_DIR.exists():
        sh("git", "clone", "--depth", "50", REPO_SSH, str(FEED_DIR))
    sh("git", "-C", str(FEED_DIR), "pull", "--ff-only")

    ops = FEED_DIR / "ops"
    ops.mkdir(exist_ok=True)
    shard = ops / "records-00001.jsonl"
    head_file = ops / "head.json"

    priv = load_or_mint_key()
    feed = Feed(priv)

    existing: list[dict] = []
    if shard.exists():
        with shard.open() as f:
            existing = [json.loads(line) for line in f if line.strip()]
    feed.extend(existing)

    # Guard: the rebuilt history must match the committed head before we
    # append — a mismatch means corruption or a foreign publisher; abort.
    if head_file.exists():
        stored = json.loads(head_file.read_text())
        if stored["feed"] != feed.feed:
            sys.exit("ops feed head belongs to a different publisher key — refusing")
        if stored["length"] != feed.length or stored["root"] != feed.root():
            sys.exit("ops shard does not reproduce the committed head — refusing")

    record = fetch_status()
    head = feed.append(record)

    # Reader-side verification before anything leaves this machine.
    assert verify_head(head), "freshly-minted head failed verification"
    assert verify_entries(head, feed.entries), "entries failed verification against head"

    with shard.open("a") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
    head_file.write_text(json.dumps(
        {"feed": head.feed, "root": head.root, "length": head.length,
         "fork": head.fork, "sig": head.sig}, indent=1) + "\n")
    (ops / "MANIFEST.json").write_text(json.dumps(
        {"publisher": feed.address, "shards": ["records-00001.jsonl"],
         "records": feed.length}, indent=1) + "\n")

    sh("git", "-C", str(FEED_DIR), "add", "ops")
    sh("git", "-C", str(FEED_DIR), "commit", "-m",
       f"ops: relay-status {record['host']} n={head.length} (signed)")
    sh("git", "-C", str(FEED_DIR), "push")
    print(f"published ops record #{head.length}: {record}")


if __name__ == "__main__":
    main()
