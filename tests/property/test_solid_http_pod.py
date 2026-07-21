"""Proofs for the stdlib HTTP pod backend, against a real local HTTP server.

An in-process ``http.server`` plays the pod: PUT stores, GET serves, HEAD
answers existence, and every request's Authorization header is recorded. The
whole PodVault flow (digest-as-path capture storage, tamper-evident retrieval,
observation archive) runs over an actual socket.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from knitweb.core import crypto
from knitweb.solid.http_pod import HttpPodBridge
from knitweb.solid.pod import CAPTURES_CONTAINER, PodError, PodVault

_FRAME = b"\x89PNG-fake-frame-bytes"


class _PodHandler(BaseHTTPRequestHandler):
    store: dict[str, bytes] = {}
    auth_seen: list[str | None] = []
    require_token: str | None = None

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization")
        type(self).auth_seen.append(header)
        if type(self).require_token is None:
            return True
        return header == f"Bearer {type(self).require_token}"

    def do_PUT(self):
        if not self._authorized():
            self.send_response(401); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        type(self).store[self.path] = self.rfile.read(length)
        self.send_response(201); self.end_headers()

    def do_GET(self):
        if not self._authorized():
            self.send_response(401); self.end_headers(); return
        data = type(self).store.get(self.path)
        if data is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        if not self._authorized():
            self.send_response(401); self.end_headers(); return
        self.send_response(200 if self.path in type(self).store else 404)
        self.end_headers()

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture()
def pod_server():
    _PodHandler.store = {}
    _PodHandler.auth_seen = []
    _PodHandler.require_token = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PodHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.property
def test_vault_flow_over_real_http(pod_server):
    vault = PodVault(HttpPodBridge(pod_server, token="s3cret"))
    pod_ref, digest = vault.store_capture(_FRAME)
    assert pod_ref == pod_server + CAPTURES_CONTAINER + digest
    assert vault.fetch_capture(digest) == _FRAME
    assert vault.verify_capture(digest)
    assert vault.bridge.exists(CAPTURES_CONTAINER + digest)
    assert not vault.bridge.exists(CAPTURES_CONTAINER + "00" * 32)
    # the bearer token rode along on every request
    assert set(_PodHandler.auth_seen) == {"Bearer s3cret"}


@pytest.mark.property
def test_server_side_tamper_is_caught_over_http(pod_server):
    vault = PodVault(HttpPodBridge(pod_server))
    _pod_ref, digest = vault.store_capture(_FRAME)
    key = "/" + CAPTURES_CONTAINER + digest
    _PodHandler.store[key] = b"tampered" + _PodHandler.store[key][8:]
    with pytest.raises(PodError):
        vault.fetch_capture(digest)


@pytest.mark.property
def test_unauthorized_and_missing_map_to_pod_errors(pod_server):
    _PodHandler.require_token = "expected"
    bridge = HttpPodBridge(pod_server, token="wrong")
    with pytest.raises(PodError):
        bridge.put("field/captures/aa", b"x", "application/octet-stream")
    _PodHandler.require_token = None
    good = HttpPodBridge(pod_server)
    with pytest.raises(PodError):
        good.get("field/captures/" + "00" * 32)


@pytest.mark.property
def test_observation_archive_over_http(pod_server):
    from knitweb.edge.observer import GlassObserver
    from knitweb.edge.recognize import MarkerBackend, recognize

    vault = PodVault(HttpPodBridge(pod_server))
    priv, _pub = crypto.generate_keypair()
    glass = GlassObserver(priv, 52.3702, 4.8952, precision=9)
    observation = glass.observe(
        recognize("qr:pot-7", MarkerBackend({"qr:pot-7": "bafyreilp001"})),
        label="qr:pot-7", beat=1,
    )
    vault.store_observation(observation)
    assert vault.fetch_observation(observation.cid) == observation.to_record()


@pytest.mark.property
def test_base_url_and_timeout_validation():
    with pytest.raises(ValueError):
        HttpPodBridge("ftp://nope")
    with pytest.raises(ValueError):
        HttpPodBridge("https://ok.example/", timeout_s=0)