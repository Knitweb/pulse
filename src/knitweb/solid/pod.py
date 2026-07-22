"""Pod vault seam — store originals in the wearer's Solid pod, keep digests here.

A :class:`~knitweb.fabric.observation.FieldObservation` carries at most a
``pod_ref`` (where the original lives) and a ``capture_digest`` (SHA-256 of the
raw bytes). This module is the device-side half that makes those pointers real:
a **vault layout** over an injectable :class:`PodBridge`.

This is a **seam, not an HTTP client.** Real Solid access needs Solid-OIDC
authentication and an LDP/Solid protocol client, which the dependency-free core
cannot provide. So the actual pod lives behind an injectable bridge — exactly
the pattern :mod:`knitweb.p2p.bluetooth_transport` uses for the BLE radio and
:mod:`knitweb.p2p.webrtc_transport` uses for the JS shell. With **no bridge
installed the vault refuses honestly** (:class:`PodUnavailable`); it never
pretends bytes were stored in a pod that isn't there. A
:class:`MemoryPodBridge` is provided for in-process testing and is clearly
labelled as *not* a real pod.

Vault layout (paths relative to the wearer's pod container)::

    field/captures/<sha256-hex>          raw camera frames / screenshots
    field/observations/<cid>.cbor        canonical observation records (audit trail)

Two properties matter:

  * **content-addressed capture paths** — the path IS the digest, so a
    ``pod_ref`` and its record's ``capture_digest`` corroborate each other;
  * **tamper-evident retrieval** — :meth:`PodVault.verify_capture` re-hashes
    fetched bytes against the expected digest, so a vault (or the wire to it)
    that altered an original is caught at read time.
"""

from __future__ import annotations

from ..core import canonical, crypto
from ..fabric.observation import FieldObservation

__all__ = [
    "PodError",
    "PodUnavailable",
    "PodBridge",
    "MemoryPodBridge",
    "PodVault",
    "CAPTURES_CONTAINER",
    "OBSERVATIONS_CONTAINER",
]

CAPTURES_CONTAINER = "field/captures/"
OBSERVATIONS_CONTAINER = "field/observations/"

_CBOR_CONTENT_TYPE = "application/cbor"
_BINARY_CONTENT_TYPE = "application/octet-stream"


class PodError(RuntimeError):
    """A pod/vault storage failure."""


class PodUnavailable(PodError):
    """Raised when the vault is used but no pod bridge is installed."""


class PodBridge:
    """Injectable seam to an actual Solid pod.

    A real implementation wraps a Solid-OIDC-authenticated protocol client and
    is supplied by an optional backend. The base class is abstract: every
    method raises so an accidentally-unwired vault fails loudly instead of
    silently dropping the wearer's data.

    ``put`` stores ``data`` at ``path`` (relative to the wearer's pod
    container) and returns the absolute ``pod_ref`` URL. ``get`` fetches the
    bytes back by the same relative path.
    """

    def put(self, path: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError

    def get(self, path: str) -> bytes:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError


class MemoryPodBridge(PodBridge):
    """In-process bridge for tests — NOT a real pod.

    Stores bytes in a dict and mints ``pod_ref`` URLs under a clearly
    non-routable base, so nothing can mistake it for actual Solid storage.
    """

    def __init__(self, base_url: str = "https://pod.invalid/") -> None:
        if not base_url.endswith("/"):
            base_url += "/"
        self.base_url = base_url
        self._store: dict[str, bytes] = {}

    def put(self, path: str, data: bytes, content_type: str) -> str:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        self._store[path] = data
        return self.base_url + path

    def get(self, path: str) -> bytes:
        try:
            return self._store[path]
        except KeyError:
            raise PodError(f"no resource at {path!r}") from None

    def exists(self, path: str) -> bool:
        return path in self._store

    # test helper: simulate a vault that was tampered with
    def corrupt(self, path: str) -> None:
        data = bytearray(self.get(path))
        data[0] ^= 0xFF
        self._store[path] = bytes(data)


class PodVault:
    """The wearer's vault layout over an injectable :class:`PodBridge`."""

    def __init__(self, bridge: PodBridge | None = None) -> None:
        self.bridge = bridge

    def _require_bridge(self) -> PodBridge:
        if self.bridge is None:
            raise PodUnavailable(
                "no pod bridge installed; supply a PodBridge backend "
                "(or MemoryPodBridge for tests)"
            )
        return self.bridge

    # -- captures (originals) ----------------------------------------------

    def store_capture(self, capture: bytes) -> tuple[str, str]:
        """Store a raw capture; return ``(pod_ref, capture_digest)``.

        The path is the SHA-256 digest of the bytes, so the returned pair is
        exactly what :meth:`GlassObserver.observe`/``FieldObservation`` expect
        for ``pod_ref`` + ``capture_digest`` — and the two corroborate each
        other by construction.
        """
        if not isinstance(capture, bytes) or not capture:
            raise TypeError("capture must be non-empty bytes")
        digest = crypto.sha256_hex(capture)
        pod_ref = self._require_bridge().put(
            CAPTURES_CONTAINER + digest, capture, _BINARY_CONTENT_TYPE
        )
        return pod_ref, digest

    def fetch_capture(self, capture_digest: str) -> bytes:
        """Fetch a stored capture by its digest (tamper-checked)."""
        data = self._require_bridge().get(CAPTURES_CONTAINER + capture_digest)
        if crypto.sha256_hex(data) != capture_digest:
            raise PodError(
                "capture bytes do not match their digest — vault or wire tampered"
            )
        return data

    def verify_capture(self, capture_digest: str) -> bool:
        """True iff the stored capture still hashes to ``capture_digest``."""
        try:
            self.fetch_capture(capture_digest)
        except PodError:
            return False
        return True

    # -- observation records (audit trail) ----------------------------------

    def store_observation(self, observation: FieldObservation) -> str:
        """Keep the wearer's own copy of a woven record; return its pod_ref.

        Stored as the record's exact canonical bytes, so pod copy and fabric
        CID stay byte-identical (`what did I share, when, with which digest`).
        """
        data = canonical.encode(observation.to_record())
        return self._require_bridge().put(
            OBSERVATIONS_CONTAINER + observation.cid + ".cbor",
            data,
            _CBOR_CONTENT_TYPE,
        )

    def fetch_observation(self, observation_cid: str) -> dict:
        """Fetch + decode an archived observation record (CID re-checked)."""
        data = self._require_bridge().get(
            OBSERVATIONS_CONTAINER + observation_cid + ".cbor"
        )
        record = canonical.decode(data)
        if canonical.cid(record) != observation_cid:
            raise PodError(
                "archived record does not match its CID — vault or wire tampered"
            )
        return record
