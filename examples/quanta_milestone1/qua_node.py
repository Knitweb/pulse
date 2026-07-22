#!/usr/bin/env python3
"""
QUA Node — Milestone 1 Reference Implementation
================================================
"Een netwerk van 3 Python nodes die hetzelfde fysieke object kunnen
observeren, er een gedeelde QUA-identiteit aan geven en zonder centrale
database de geschiedenis synchroniseren."

3S = Sense -> Spatial -> Share

Design principles (from the QUA Master Plan):
  1. GEOSPATIAL-FIRST  : every observation is bound to position + time + orientation
  2. DETERMINISTIC ID  : two independent nodes observing the same object in the
                         same spatial cell derive the SAME QUA ID — identity
                         emerges from the world, not from a central registry
  3. EHMAC LEDGER      : every node keeps an append-only, HMAC-chained event log
                         (LedgerField) — tamper-evident without blockchain/mining
  4. P2P DELTA SYNC    : nodes gossip event hashes ("do you have X?") and
                         exchange only missing events — no central database
  5. CONSENSUS SCORE   : object confidence grows with independent observations

Zero external dependencies — Python 3.10+ stdlib only.
YOLO / camera / GPS are pluggable (see SensorInterface); this demo simulates them.

Run the full 3-node demo:
    python3 qua_node.py demo

Run a single node (for real multi-machine tests):
    python3 qua_node.py node --id qua-node-a --port 9001 --peers 127.0.0.1:9002
"""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import hmac
import json
import math
import os
import secrets
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

# ============================================================================
# 1. SPATIAL LAYER — geospatial cells (QUA Spatial Chunking)
# ============================================================================

# Cell size ~11m x ~7m at NL latitude: fine enough to separate objects,
# coarse enough that GPS noise (±1-5 m) keeps one object in one cell.
CELL_DECIMALS = 4  # 0.0001 deg


def spatial_cell(lat: float, lon: float, decimals: int = CELL_DECIMALS) -> str:
    """Quantize a coordinate into a deterministic spatial cell key.

    Example: (52.37401, 4.89903) -> "52.3740_4.8990"
    Any node computing this for the same physical spot gets the same key.
    """
    q = 10 ** decimals
    lat_q = math.floor(lat * q) / q
    lon_q = math.floor(lon * q) / q
    return f"{lat_q:.{decimals}f}_{lon_q:.{decimals}f}"


def chunk_of(lat: float, lon: float) -> str:
    """Coarser Minecraft-style geographic chunk (~1.1 km), for cache/sync scoping."""
    return spatial_cell(lat, lon, decimals=2)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two WGS84 coordinates."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ============================================================================
# 2. IDENTITY LAYER — deterministic QUA object identity
# ============================================================================

def qua_id(object_class: str, lat: float, lon: float) -> str:
    """Deterministic QUA identity: qua:<class>:<hash8(cell)>.

    KEY INNOVATION of Milestone 1:
    identity = f(what, where). Two nodes that independently observe a "cow"
    inside the same spatial cell compute the SAME ID — so a shared identity
    exists without any coordination, registry, or blockchain. Sync then only
    has to MERGE histories, never negotiate identity.
    """
    cell = spatial_cell(lat, lon)
    h = hashlib.sha256(f"{object_class}|{cell}".encode()).hexdigest()[:8]
    return f"qua:{object_class}:{h}"


# ============================================================================
# 3. DATA MODEL — QUA Spatial Object + Observation events
# ============================================================================

@dataclass
class Observation:
    """One 'Sense' result: what was seen, where, when, by whom, how sure."""
    object_id: str
    object_class: str
    confidence: float
    lat: float
    lon: float
    altitude: float
    heading: float           # yaw in degrees
    observer: str            # node id
    timestamp: float
    frame_hash: str          # evidence pointer (image is proof, not identity)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QUASpatialObject:
    """The living digital twin — aggregated from observations (4D: x,y,z,t)."""
    id: str
    object_class: str
    lat: float
    lon: float
    altitude: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    observations: list = field(default_factory=list)   # list[Observation dict]
    observers: set = field(default_factory=set)        # distinct node ids
    consensus: float = 0.0

    def add_observation(self, obs: Observation) -> None:
        self.observations.append(obs.to_dict())
        self.observers.add(obs.observer)
        self.last_seen = max(self.last_seen, obs.timestamp)
        if self.first_seen == 0.0 or obs.timestamp < self.first_seen:
            self.first_seen = obs.timestamp
        # Position refinement: running average (later: Kalman/SLAM fusion)
        n = len(self.observations)
        self.lat = ((self.lat * (n - 1)) + obs.lat) / n
        self.lon = ((self.lon * (n - 1)) + obs.lon) / n
        self._update_consensus()

    def _update_consensus(self) -> None:
        """Consensus grows with (a) detection confidence, (b) # independent observers."""
        if not self.observations:
            self.consensus = 0.0
            return
        avg_conf = sum(o["confidence"] for o in self.observations) / len(self.observations)
        observer_weight = min(len(self.observers) / 3.0, 1.0)  # 3 observers = full weight
        self.consensus = round(0.6 * avg_conf + 0.4 * observer_weight, 4)

    def summary(self) -> str:
        return (f"{self.id} [{self.object_class}] "
                f"obs={len(self.observations)} observers={len(self.observers)} "
                f"consensus={self.consensus:.2f} "
                f"pos=({self.lat:.5f},{self.lon:.5f})")


# ============================================================================
# 4. LEDGERFIELD — append-only, EHMAC-chained event log (no blockchain)
# ============================================================================

class LedgerField:
    """Local append-only log. Each event is HMAC-signed and hash-chained to the
    previous event (EHMAC pattern from 02_EHMAC_Encryption_Engine.py, simplified):

        event_hash = SHA256(prev_hash || canonical_json(event))
        signature  = HMAC-SHA256(node_key, event_hash)

    Tamper-evident, instantly verifiable, no mining. Events are content-addressed
    by event_hash, which is what peers gossip about.
    """

    def __init__(self, node_id: str, node_key: bytes, path: Optional[str] = None):
        self.node_id = node_id
        self.node_key = node_key
        self.path = path
        self.events: dict[str, dict] = {}      # event_hash -> envelope
        self.order: list[str] = []             # local append order
        self.prev_hash = "0" * 64              # genesis
        if path and os.path.exists(path):
            self._load()

    # -- core -----------------------------------------------------------------

    @staticmethod
    def canonical(payload: dict) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def append(self, event_type: str, payload: dict) -> dict:
        """Create, sign, chain and store a new local event. Returns the envelope."""
        body = {
            "type": event_type,
            "payload": payload,
            "author": self.node_id,
            "ts": time.time(),
        }
        event_hash = hashlib.sha256(
            self.prev_hash.encode() + self.canonical(body)
        ).hexdigest()
        signature = hmac.new(self.node_key, event_hash.encode(), hashlib.sha256).hexdigest()
        envelope = {
            "hash": event_hash,
            "prev": self.prev_hash,
            "body": body,
            "sig": signature,
        }
        self._store(envelope)
        self.prev_hash = event_hash
        return envelope

    def ingest_remote(self, envelope: dict, author_key: Optional[bytes]) -> bool:
        """Store an event received from a peer.

        Remote events keep their own author chain; we verify the HMAC when we
        know the author's key (in this demo keys are exchanged at handshake —
        production: Pulse HD-wallet public identities, see file 07/08).
        """
        h = envelope.get("hash", "")
        if h in self.events:
            return False  # already have it (gossip dedup)
        body = envelope.get("body", {})
        # Recompute hash over prev+body — structural integrity check
        expect = hashlib.sha256(
            envelope.get("prev", "").encode() + self.canonical(body)
        ).hexdigest()
        if expect != h:
            return False
        if author_key is not None:
            expect_sig = hmac.new(author_key, h.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expect_sig, envelope.get("sig", "")):
                return False
        self._store(envelope)
        return True

    def _store(self, envelope: dict) -> None:
        self.events[envelope["hash"]] = envelope
        self.order.append(envelope["hash"])
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(envelope) + "\n")

    def _load(self) -> None:
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    env = json.loads(line)
                    self.events[env["hash"]] = env
                    self.order.append(env["hash"])
                    if env["body"]["author"] == self.node_id:
                        self.prev_hash = env["hash"]

    # -- verification & sync helpers -------------------------------------------

    def verify_own_chain(self) -> bool:
        """Verify our full local author-chain (hashes + HMAC signatures)."""
        prev = "0" * 64
        for h in self.order:
            env = self.events[h]
            if env["body"]["author"] != self.node_id:
                continue
            if env["prev"] != prev:
                return False
            expect = hashlib.sha256(prev.encode() + self.canonical(env["body"])).hexdigest()
            if expect != h:
                return False
            sig = hmac.new(self.node_key, h.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, env["sig"]):
                return False
            prev = h
        return True

    def all_hashes(self) -> list[str]:
        return list(self.events.keys())

    def get(self, event_hash: str) -> Optional[dict]:
        return self.events.get(event_hash)


# ============================================================================
# 5. LENS LAYER — pluggable detector (YOLO in production, simulated in demo)
# ============================================================================

class SensorInterface:
    """Sense: yields detections as (class, confidence, lat, lon, alt, heading).

    Production implementations plug in here:
      - CameraYOLOSensor  : ultralytics YOLOv9 + phone GPS  (Phase 1)
      - SnapLensSensor    : Snap AR Lens bridge             (QUA_Meta_3S guide)
      - QuestEdgeSensor   : Quest 3S -> Android WebRTC feed (QUA_MVP guide)
    """

    def detect(self) -> list[tuple[str, float, float, float, float, float]]:
        raise NotImplementedError


class SimulatedSensor(SensorInterface):
    """Deterministic scripted observations so the demo is reproducible."""

    def __init__(self, script: list[tuple[str, float, float, float, float, float]]):
        self._script = list(script)

    def detect(self):
        if self._script:
            return [self._script.pop(0)]
        return []


def try_real_yolo_sensor(source: int = 0):
    """Return a real YOLO sensor if ultralytics+opencv are installed, else None."""
    try:
        from ultralytics import YOLO  # type: ignore
        import cv2  # type: ignore
    except ImportError:
        return None

    class CameraYOLOSensor(SensorInterface):
        def __init__(self):
            self.model = YOLO("yolov9c.pt")
            self.cap = cv2.VideoCapture(source)
            self.lat, self.lon = 52.3740, 4.8990  # TODO: real GPS provider

        def detect(self):
            ok, frame = self.cap.read()
            if not ok:
                return []
            out = []
            for r in self.model(frame, verbose=False):
                for box in r.boxes:
                    out.append((r.names[int(box.cls[0])], float(box.conf[0]),
                                self.lat, self.lon, 0.0, 0.0))
            return out

    return CameraYOLOSensor()


# ============================================================================
# 6. P2P LAYER — asyncio JSON-lines gossip (HELLO / HAVE / WANT / EVENT)
# ============================================================================

class QUANode:
    """A full QUA node: Sense -> Spatial -> Share.

    Protocol (newline-delimited JSON over TCP):
      HELLO {node, key}          - handshake, exchange node id + HMAC pubkey*
      HAVE  {hashes: [...]}      - "these event hashes exist in my ledger"
      WANT  {hashes: [...]}      - "send me these events"
      EVENT {envelope}           - one signed ledger event

    (*Demo shares the HMAC key directly for verification; production replaces
     this with Pulse HD-wallet public-key signatures — see files 07 & 08.)
    """

    def __init__(self, node_id: str, port: int,
                 peers: list[tuple[str, int]],
                 sensor: Optional[SensorInterface] = None,
                 ledger_path: Optional[str] = None,
                 log: Callable[[str], None] = print):
        self.node_id = node_id
        self.port = port
        self.peers = peers
        self.sensor = sensor
        self.log = log
        self.key = secrets.token_bytes(32)
        self.ledger = LedgerField(node_id, self.key, ledger_path)
        self.objects: dict[str, QUASpatialObject] = {}
        self.peer_keys: dict[str, bytes] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: list[asyncio.Task] = []
        self.stats = {"sent": 0, "received": 0, "synced_events": 0}

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_conn, "127.0.0.1", self.port)
        self._tasks.append(asyncio.create_task(self._sense_loop()))
        self._tasks.append(asyncio.create_task(self._gossip_loop()))
        self.log(f"[{self.node_id}] up on :{self.port}, peers={self.peers}")

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # -- SENSE ------------------------------------------------------------------

    async def _sense_loop(self) -> None:
        while True:
            await asyncio.sleep(0.4)
            if not self.sensor:
                continue
            for (cls, conf, lat, lon, alt, heading) in self.sensor.detect():
                self.observe(cls, conf, lat, lon, alt, heading)

    def observe(self, cls: str, conf: float, lat: float, lon: float,
                alt: float = 0.0, heading: float = 0.0) -> Observation:
        """SENSE -> SPATIAL: turn a detection into an identity-bound observation
        and record it in the LedgerField."""
        oid = qua_id(cls, lat, lon)
        frame_hash = hashlib.sha256(
            f"{self.node_id}{time.time()}{secrets.token_hex(4)}".encode()
        ).hexdigest()[:12]
        obs = Observation(
            object_id=oid, object_class=cls, confidence=conf,
            lat=lat, lon=lon, altitude=alt, heading=heading,
            observer=self.node_id, timestamp=time.time(), frame_hash=frame_hash,
        )
        self._apply_observation(obs)
        env = self.ledger.append("OBJECT_OBSERVED", obs.to_dict())
        self.log(f"[{self.node_id}] SENSE {cls} conf={conf:.2f} -> {oid} "
                 f"(event {env['hash'][:8]})")
        return obs

    def _apply_observation(self, obs: Observation) -> None:
        obj = self.objects.get(obs.object_id)
        if obj is None:
            obj = QUASpatialObject(
                id=obs.object_id, object_class=obs.object_class,
                lat=obs.lat, lon=obs.lon, altitude=obs.altitude,
            )
            self.objects[obs.object_id] = obj
        obj.add_observation(obs)

    # -- SHARE (gossip) -------------------------------------------------------

    async def _gossip_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            for host, port in self.peers:
                try:
                    await self._sync_with(host, port)
                except (ConnectionRefusedError, OSError):
                    pass  # peer offline — resilient by design

    async def _sync_with(self, host: str, port: int) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await self._send(writer, {"t": "HELLO", "node": self.node_id,
                                      "key": self.key.hex()})
            hello = await self._recv(reader)
            if hello and hello.get("t") == "HELLO":
                self.peer_keys[hello["node"]] = bytes.fromhex(hello["key"])

            await self._send(writer, {"t": "HAVE", "hashes": self.ledger.all_hashes()})
            msg = await self._recv(reader)
            if msg and msg.get("t") == "WANT":
                for h in msg["hashes"]:
                    env = self.ledger.get(h)
                    if env:
                        await self._send(writer, {"t": "EVENT", "envelope": env})
                        self.stats["sent"] += 1
            await self._send(writer, {"t": "BYE"})
        finally:
            writer.close()
            await writer.wait_closed()

    async def _on_conn(self, reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                msg = await self._recv(reader)
                if msg is None or msg.get("t") == "BYE":
                    break
                t = msg.get("t")
                if t == "HELLO":
                    self.peer_keys[msg["node"]] = bytes.fromhex(msg["key"])
                    await self._send(writer, {"t": "HELLO", "node": self.node_id,
                                              "key": self.key.hex()})
                elif t == "HAVE":
                    missing = [h for h in msg["hashes"] if h not in self.ledger.events]
                    await self._send(writer, {"t": "WANT", "hashes": missing})
                elif t == "EVENT":
                    self._ingest(msg["envelope"])
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    def _ingest(self, envelope: dict) -> None:
        author = envelope.get("body", {}).get("author", "")
        key = self.peer_keys.get(author)
        if self.ledger.ingest_remote(envelope, key):
            self.stats["received"] += 1
            self.stats["synced_events"] += 1
            body = envelope["body"]
            if body["type"] == "OBJECT_OBSERVED":
                self._apply_observation(Observation(**body["payload"]))
                oid = body["payload"]["object_id"]
                self.log(f"[{self.node_id}] SYNC <- {author}: "
                         f"{oid} (event {envelope['hash'][:8]})")

    # -- wire helpers ----------------------------------------------------------

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, obj: dict) -> None:
        writer.write(json.dumps(obj).encode() + b"\n")
        await writer.drain()

    @staticmethod
    async def _recv(reader: asyncio.StreamReader) -> Optional[dict]:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        except asyncio.TimeoutError:
            return None
        if not line:
            return None
        return json.loads(line)

    # -- reporting -------------------------------------------------------------

    def report(self) -> str:
        lines = [f"── {self.node_id} ─ ledger={len(self.ledger.events)} events, "
                 f"chain_valid={self.ledger.verify_own_chain()}, "
                 f"synced_in={self.stats['synced_events']}"]
        for obj in self.objects.values():
            lines.append(f"   {obj.summary()}")
        return "\n".join(lines)


# ============================================================================
# 7. MILESTONE 1 DEMO — 3 nodes, 1 cow, shared identity, full sync
# ============================================================================

async def run_demo() -> int:
    print("=" * 74)
    print("QUA Milestone 1 — 3 nodes / shared identity / P2P sync / no central DB")
    print("=" * 74)

    # The same physical cow at ~ (52.3740, 4.8990). Nodes A and B observe it
    # independently with slightly different GPS fixes (realistic noise, same cell).
    # Node C never sees the cow — it must learn about it purely via P2P sync.
    cow = "cow"
    node_a = QUANode(
        "qua-node-a", 9101,
        peers=[("127.0.0.1", 9102), ("127.0.0.1", 9103)],
        sensor=SimulatedSensor([
            (cow, 0.97, 52.37401, 4.89903, 0.0, 118.0),
            ("tree", 0.88, 52.37455, 4.89960, 0.0, 30.0),
        ]),
    )
    node_b = QUANode(
        "qua-node-b", 9102,
        peers=[("127.0.0.1", 9101), ("127.0.0.1", 9103)],
        sensor=SimulatedSensor([
            (cow, 0.94, 52.37404, 4.89907, 0.0, 210.0),  # same cell as A's cow
        ]),
    )
    node_c = QUANode(
        "qua-node-c", 9103,
        peers=[("127.0.0.1", 9101), ("127.0.0.1", 9102)],
        sensor=None,  # pure listener — proves sync works
    )

    nodes = [node_a, node_b, node_c]
    for n in nodes:
        await n.start()

    print("\n--- sensing + gossip running (6 s) ---\n")
    await asyncio.sleep(6.0)

    print("\n--- FINAL STATE ---")
    for n in nodes:
        print(n.report())

    # ---------------- acceptance criteria ----------------
    cow_id = qua_id(cow, 52.37401, 4.89903)
    checks = {
        "A and B derived the SAME QUA ID for the cow":
            qua_id(cow, 52.37401, 4.89903) == qua_id(cow, 52.37404, 4.89907),
        "Node C learned about the cow via P2P only":
            cow_id in node_c.objects,
        "Cow has 2 independent observers everywhere":
            all(len(n.objects.get(cow_id, QUASpatialObject("", "", 0, 0)).observers) == 2
                for n in nodes),
        "All ledgers converged to the same event set":
            (set(node_a.ledger.events) == set(node_b.ledger.events)
             == set(node_c.ledger.events)),
        "All EHMAC hash-chains verify":
            all(n.ledger.verify_own_chain() for n in nodes),
        "Consensus rose above single-observation level":
            node_c.objects[cow_id].consensus > 0.6 if cow_id in node_c.objects else False,
    }

    print("\n--- ACCEPTANCE CRITERIA ---")
    ok = True
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed

    for n in nodes:
        await n.stop()

    print("\n" + ("✔ MILESTONE 1 ACHIEVED" if ok else "✘ MILESTONE 1 FAILED"))
    print("=" * 74)
    return 0 if ok else 1


# ============================================================================
# 8. CLI
# ============================================================================

async def run_single_node(args) -> int:
    peers = []
    for p in (args.peers.split(",") if args.peers else []):
        host, port = p.strip().split(":")
        peers.append((host, int(port)))
    sensor = try_real_yolo_sensor() if args.camera else None
    node = QUANode(args.id, args.port, peers, sensor=sensor,
                   ledger_path=args.ledger)
    await node.start()
    print(f"Node {args.id} running. Ctrl+C to stop. "
          f"{'(YOLO camera active)' if sensor else '(no sensor — sync-only node)'}")
    try:
        while True:
            await asyncio.sleep(10)
            print(node.report())
    except (KeyboardInterrupt, asyncio.CancelledError):
        await node.stop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="QUA Node — Milestone 1")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("demo", help="run the 3-node acceptance demo")
    np = sub.add_parser("node", help="run one node")
    np.add_argument("--id", default=f"qua-node-{secrets.token_hex(3)}")
    np.add_argument("--port", type=int, default=9101)
    np.add_argument("--peers", default="", help="host:port,host:port")
    np.add_argument("--ledger", default=None, help="path for persistent JSONL ledger")
    np.add_argument("--camera", action="store_true", help="use real YOLO if installed")
    args = ap.parse_args()

    if args.cmd == "node":
        return asyncio.run(run_single_node(args))
    return asyncio.run(run_demo())


if __name__ == "__main__":
    sys.exit(main())
