"""Solid data-vault seam — the wearer's personal pod behind an injectable bridge.

The fabric carries digests; the wearer's pod carries originals. This package
binds the two: :mod:`knitweb.solid.pod` is the injectable vault seam (no HTTP
client in core — a real Solid implementation is supplied by an optional
backend, exactly like the Bluetooth radio and the WebRTC shell), and
:mod:`knitweb.solid.webid` is the signed record linking a pod's WebID to a
``pls1`` key so peers can validate-at-read who a vault belongs to.
"""
