#!/usr/bin/env python3
"""Deploy the PHP store-and-forward relay to the 5mart.ml fallback host.

Fixes https://github.com/Knitweb/pulse/issues/337: RelayTransport
(src/knitweb/p2p/relay.py) posts to https://5mart.ml/api/relay/{send,fetch}
but nothing was ever published under that path, so NAT'd nodes got a 404 and
fell back to HTTPS feed bootstrap only.

Publishes:

    https://5mart.ml/api/relay/send    <- relay/send.php
    https://5mart.ml/api/relay/fetch   <- relay/fetch.php
    https://5mart.ml/api/relay/health  <- relay/health.php

Also provisions the mailbox queue directory OUTSIDE the web docroot
(`WEBROOT/../relay_queues`) so queued frames are never reachable by a direct
URL guess.

Credentials are NOT stored here. Set them in the environment before running
(same convention as sha-fail-akash-hosting/fallback-5mart/deploy_to_5mart.py):

    export FIVEMART_HOST=5martm.ssh.transip.me
    export FIVEMART_USER=5martml
    export FIVEMART_PASS='...'        # rotate after use; never commit
    python3 deploy_relay_to_5mart.py

Requires: paramiko  (pip install --user paramiko)
"""
import os
import sys
from pathlib import Path

import paramiko

WEBROOT = "/data/sites/web/5martml/www"
QUEUE_ROOT = "/data/sites/web/5martml/relay_queues"
HERE = Path(__file__).resolve().parent
RELAY_SRC = HERE / "relay"
RELAY_FILES = ["send.php", "fetch.php", "health.php", "_common.php", ".htaccess"]


def main():
    host = os.environ["FIVEMART_HOST"]
    user = os.environ["FIVEMART_USER"]
    pw = os.environ["FIVEMART_PASS"]

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=pw, timeout=25,
              look_for_keys=False, allow_agent=False)
    sftp = c.open_sftp()

    def ensure(d):
        try:
            sftp.stat(d)
        except IOError:
            sftp.mkdir(d)

    # Queue directory: private, outside the docroot.
    ensure(QUEUE_ROOT)
    print(f"OK queue root <- {QUEUE_ROOT}")

    dest = f"{WEBROOT}/api"
    ensure(dest)
    dest = f"{WEBROOT}/api/relay"
    ensure(dest)
    for f in RELAY_FILES:
        lp = RELAY_SRC / f
        if not lp.exists():
            print(f"  SKIP missing {f}")
            continue
        sftp.put(str(lp), f"{dest}/{f}")
        print(f"  put api/relay/{f} ({lp.stat().st_size} B)")
    print(f"OK relay <- {RELAY_SRC}")

    sftp.close()
    c.close()

    print("\nVerify with:")
    print("  curl -s https://5mart.ml/api/relay/health")


if __name__ == "__main__":
    if len(sys.argv) != 1:
        sys.exit("usage: FIVEMART_HOST/USER/PASS=... python3 deploy_relay_to_5mart.py")
    main()
