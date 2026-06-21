# `/interpret` — the Lens delegation endpoint

`/interpret` is the gateway's **read-only interpretation hook**. It lets a host plug an
external *Lens* — an interpreter that answers natural questions over the woven Web — into
Pulse **without** Pulse taking on a single dependency for it. An LLM, a vector index, or a
graph database can live in a separate service or package; Pulse only forwards a query and a
read-only snapshot to whatever the host registered, and returns the result. The endpoint is
a pure delegation seam (knitweb/pulse#157).

## Guarantees

- **Strictly read-only.** `/interpret` never weaves, links, mints, transfers, anchors, or
  otherwise writes. There is **no write path** in the hook. The Lens is handed a deterministic,
  deep-copied [`web_snapshot`](../src/knitweb/fabric/snapshot.py) — never the live `Web` — so it
  cannot reach back into fabric state no matter what it does. An `/interpret` call leaves the
  Web's `state_root`, node/edge counts, records, signatures, and feeds unchanged.
- **No extra dependencies.** Pulse imports no LLM / vector-DB / graph-DB library, and adds no
  new pip dependency, to support this hook. The Lens is host-supplied code; its dependencies are
  the host's concern and stay outside Pulse.
- **Runs without a Lens.** With no Lens registered, Pulse keeps serving and every other endpoint
  works normally. `/interpret` then answers with a deterministic *not-installed* contract response
  (HTTP `501`) rather than failing.

## Delegation mechanism — registering a Lens

A *Lens* is any callable with the signature:

```python
def lens(query: str, snapshot: Mapping) -> object: ...
```

- `query` — the request's query string.
- `snapshot` — the value returned by `web_snapshot(app.web)`: a deterministic, read-only deep
  copy with keys `state_root`, `node_count`, `edge_count`, `records` (CID-keyed node records), and
  `jsonld` (the deterministic JSON-LD/DKG export). Mutating it cannot affect the live Web.
- return value — any JSON-serializable object; it is returned verbatim under `result`.

The host registers (or clears) the Lens on the `App`:

```python
from knitweb.gateway import App, serve

app = App("molgang")

def my_lens(query, snapshot):
    # External interpreter: an LLM client, a vector search, a graph query — all OUTSIDE Pulse.
    hits = [cid for cid, rec in snapshot["records"].items() if query in str(rec)]
    return {"matched_cids": sorted(hits)}

app.set_lens(my_lens)     # inject the external interpreter
serve(app)                # /interpret now delegates to my_lens
```

`app.set_lens(None)` clears it; `app.has_lens` reports whether one is registered. The Lens is held
on the `App` instance only — it is never persisted, woven, or synced to peers.

## HTTP contract

### Request

```
POST /interpret
Content-Type: application/json

{ "query": "<text>", "params": { ... } }     # "params" is optional
```

(When a `token` is configured on `serve(...)`, `/interpret` requires it like every other
non-health route.)

### Response — Lens registered (`200 OK`)

```json
{ "ok": true, "lens": true, "query": "<text>", "result": <lens output> }
```

`result` is exactly what the registered Lens returned.

### Response — no Lens registered (`501 Not Implemented`)

```json
{ "ok": false, "lens": false, "reason": "no-interpreter-installed",
  "query": "<text>", "nodes": <int>, "edges": <int> }
```

This response is deterministic and safe: no interpreter is invoked, nothing is written, and the
rest of the gateway keeps serving.

## Programmatic use

The same contract is available in-process via `App.interpret(query, params=None)`, which returns
the response dict directly (without the HTTP layer). `serve()` maps the `lens` flag to the status
code: `200` when a Lens produced a result, `501` when none is installed.
