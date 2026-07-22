"""HttpPodBridge — a stdlib HTTP backend for the pod-vault seam.

The smallest *real* :class:`~knitweb.solid.pod.PodBridge`: plain HTTP
``PUT`` / ``GET`` / ``HEAD`` against a pod base URL, with an optional bearer
token on every request. This is enough to talk to a Solid server that accepts
token-authenticated writes (e.g. a Community Solid Server with client
credentials exchanged out-of-band), to any WebDAV-ish personal store, or to a
local dev pod — using only the standard library, so the dependency-free core
stays dependency-free.

Deliberately out of scope here: the full Solid-OIDC browser dance. That flow
needs a real OIDC client and belongs in an app shell; when it completes it
hands this bridge a token, nothing more. (Same division of labour as the BLE
radio and the WebRTC JS shell.)

Security notes:

  * HTTPS is strongly recommended for any non-localhost base URL — the token
    rides in a header.
  * Environment HTTP proxies are intentionally bypassed: a personal vault
    should never be reachable *through* an ambient corporate proxy without
    the wearer knowing.
"""

from __future__ import annotations

import urllib.error
import urllib.request

from .pod import PodBridge, PodError

__all__ = ["HttpPodBridge"]

_DEFAULT_TIMEOUT_S = 30


class HttpPodBridge(PodBridge):
    """PUT/GET/HEAD a pod over HTTP with an optional bearer token."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an http(s) URL")
        if not base_url.endswith("/"):
            base_url += "/"
        if timeout_s < 1:
            raise ValueError("timeout_s must be a positive integer")
        self.base_url = base_url
        self._token = token
        self.timeout_s = timeout_s
        # No ambient proxies between a wearer and their vault.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # -- plumbing ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
    ):
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            return self._opener.open(request, timeout=self.timeout_s)
        except urllib.error.HTTPError as exc:
            raise PodError(f"pod {method} {path!r} failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise PodError(f"pod {method} {path!r} failed: {exc.reason}") from exc

    # -- PodBridge surface -----------------------------------------------------

    def put(self, path: str, data: bytes, content_type: str) -> str:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        with self._request("PUT", path, data=data, content_type=content_type) as reply:
            if reply.status not in (200, 201, 204, 205):
                raise PodError(f"pod PUT {path!r} returned HTTP {reply.status}")
        return self.base_url + path

    def get(self, path: str) -> bytes:
        with self._request("GET", path) as reply:
            if reply.status != 200:
                raise PodError(f"pod GET {path!r} returned HTTP {reply.status}")
            return reply.read()

    def exists(self, path: str) -> bool:
        try:
            with self._request("HEAD", path) as reply:
                return reply.status == 200
        except PodError:
            return False
