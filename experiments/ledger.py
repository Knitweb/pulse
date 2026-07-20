"""Experiment ledger — a thread-safe SQLite record of every proof run.

Adapted from numerai-signals' stealth_annual_reports/ledger.py (resumable,
WAL-journaled audit ledger). Here it records, for each phase proof:

    phase, layer, git_sha, fixture_hash, status, detail, duration_ms, timestamp

This is the backbone of the proofs-first culture: every phase closes with a
runnable proof whose outcome is written here (and, when available, mirrored to
MLflow). The ledger has no heavy dependencies so it works in the minimal core
environment; MLflow logging is best-effort and optional.

Usage:
    # Simple record
    from experiments.ledger import record
    record("L1-transfer", "PASS", duration_ms=180)

    # Context manager — auto-times and records status on exit
    from experiments.ledger import run_proof
    with run_proof("L2-p2p-sync", layer="L2") as ctx:
        ctx.tag("peer_count", 3)
        ctx.metric("latency_ms", 42.5)
        # raises -> status=FAIL; clean exit -> status=PASS

    # Summary
    from experiments.ledger import summary
    summary()
"""

from __future__ import annotations

import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path(__file__).resolve().parent / "knitweb_experiments.sqlite"
_DEFAULT_MLFLOW_URI = str(Path(__file__).resolve().parent / "../mlflow.db")
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init(db_path: Path | str = _DEFAULT_DB) -> None:
    """Create the ledger table if it does not exist (idempotent)."""
    db_path = Path(db_path)
    with _LOCK, _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL    NOT NULL,
                phase        TEXT    NOT NULL,
                layer        TEXT,
                git_sha      TEXT    NOT NULL,
                fixture_hash TEXT,
                status       TEXT    NOT NULL,
                detail       TEXT,
                duration_ms  INTEGER,
                extra_tags   TEXT,
                extra_metrics TEXT
            )
            """
        )
        # Migrate: add columns added after initial schema
        existing = {row[1] for row in conn.execute("PRAGMA table_info(experiment_runs)")}
        for col, typedef in [("layer", "TEXT"), ("extra_tags", "TEXT"), ("extra_metrics", "TEXT")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE experiment_runs ADD COLUMN {col} {typedef}")


# ---------------------------------------------------------------------------
# Core record
# ---------------------------------------------------------------------------

def record(
    phase: str,
    status: str,
    detail: str = "",
    fixture_hash: str = "",
    duration_ms: int = 0,
    layer: str | None = None,
    tags: dict[str, Any] | None = None,
    metrics: dict[str, float] | None = None,
    db_path: Path | str = _DEFAULT_DB,
    mlflow_experiment: str | None = "knitweb",
    mlflow_tracking_uri: str | None = _DEFAULT_MLFLOW_URI,
) -> int:
    """Append one proof-run row; returns its row id. Mirrors to MLflow when available.

    Args:
        phase:   Proof phase name, e.g. "L1-transfer" or "crowdfunding-settle".
        status:  "PASS" | "FAIL" | "SKIP" | any custom string.
        detail:  Human-readable detail or error message.
        fixture_hash: Hash of the test fixture for reproducibility tracking.
        duration_ms:  Wall-clock duration in milliseconds.
        layer:   Knitweb architecture layer, e.g. "L0", "L1", ..., "L6".
        tags:    Arbitrary string key/value pairs logged to MLflow as tags.
        metrics: Numeric metrics logged to MLflow (in addition to duration_ms).
        db_path: Path to the SQLite ledger file.
        mlflow_experiment: MLflow experiment name (None = skip MLflow).
        mlflow_tracking_uri: MLflow tracking URI (sqlite file or http server).
    """
    import json

    db_path = Path(db_path)
    init(db_path)
    ts = time.time()
    sha = _git_sha()
    extra_tags_json = json.dumps(tags) if tags else None
    extra_metrics_json = json.dumps(metrics) if metrics else None

    with _LOCK, _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO experiment_runs
                (ts, phase, layer, git_sha, fixture_hash, status, detail,
                 duration_ms, extra_tags, extra_metrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, phase, layer, sha, fixture_hash, status, detail,
             int(duration_ms), extra_tags_json, extra_metrics_json),
        )
        row_id = cur.lastrowid

    # Best-effort MLflow mirror — never fail the caller if MLflow is unavailable.
    if mlflow_experiment:
        try:
            import mlflow  # type: ignore

            if mlflow_tracking_uri:
                mlflow.set_tracking_uri(
                    f"sqlite:///{mlflow_tracking_uri}"
                    if not mlflow_tracking_uri.startswith(("sqlite:///", "http"))
                    else mlflow_tracking_uri
                )
            mlflow.set_experiment(mlflow_experiment)
            with mlflow.start_run(run_name=f"{phase}:{sha}"):
                params: dict[str, str] = {"phase": phase, "git_sha": sha}
                if layer:
                    params["layer"] = layer
                mlflow.log_params(params)

                all_metrics: dict[str, float] = {"duration_ms": float(duration_ms)}
                if metrics:
                    all_metrics.update(metrics)
                mlflow.log_metrics(all_metrics)

                all_tags: dict[str, str] = {
                    "status": status,
                    "fixture_hash": fixture_hash or "",
                }
                if tags:
                    all_tags.update({k: str(v) for k, v in tags.items()})
                mlflow.set_tags(all_tags)
        except Exception:
            pass

    return int(row_id)


# ---------------------------------------------------------------------------
# run_proof context manager
# ---------------------------------------------------------------------------

class _ProofContext:
    """Accumulates tags and metrics during a proof run."""

    def __init__(self) -> None:
        self._tags: dict[str, Any] = {}
        self._metrics: dict[str, float] = {}

    def tag(self, key: str, value: Any) -> None:
        self._tags[key] = value

    def metric(self, key: str, value: float) -> None:
        self._metrics[key] = value


@contextmanager
def run_proof(
    phase: str,
    layer: str | None = None,
    fixture_hash: str = "",
    detail: str = "",
    db_path: Path | str = _DEFAULT_DB,
    mlflow_experiment: str | None = "knitweb",
    mlflow_tracking_uri: str | None = _DEFAULT_MLFLOW_URI,
):
    """Context manager that times a proof block and records it automatically.

    Usage::

        with run_proof("L2-peer-sync", layer="L2") as ctx:
            ctx.tag("peer_count", 3)
            ctx.metric("messages_exchanged", 12)
            run_sync_proof()  # raises on failure

    Raises in the block -> status="FAIL", exception re-raised.
    Clean exit         -> status="PASS".
    """
    ctx = _ProofContext()
    t0 = time.monotonic()
    err: str | None = None
    try:
        yield ctx
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
        status = "FAIL" if err else "PASS"
        full_detail = detail
        if err:
            full_detail = f"{detail} | {err}".strip(" |")
        record(
            phase=phase,
            status=status,
            detail=full_detail,
            fixture_hash=fixture_hash,
            duration_ms=duration_ms,
            layer=layer,
            tags=ctx._tags if ctx._tags else None,
            metrics=ctx._metrics if ctx._metrics else None,
            db_path=db_path,
            mlflow_experiment=mlflow_experiment,
            mlflow_tracking_uri=mlflow_tracking_uri,
        )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def history(
    db_path: Path | str = _DEFAULT_DB,
    phase: str | None = None,
    layer: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return recorded runs (most recent first) as a list of dicts.

    Filter by phase prefix, layer, or status if provided.
    """
    import json

    db_path = Path(db_path)
    init(db_path)
    where, params = [], []
    if phase:
        where.append("phase LIKE ?")
        params.append(f"{phase}%")
    if layer:
        where.append("layer = ?")
        params.append(layer)
    if status:
        where.append("status = ?")
        params.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with _LOCK, _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT id, ts, phase, layer, git_sha, status, detail, duration_ms, "
            f"extra_tags, extra_metrics FROM experiment_runs {where_sql} "
            f"ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()

    result = []
    for r in rows:
        extra_tags = json.loads(r[8]) if r[8] else {}
        extra_metrics = json.loads(r[9]) if r[9] else {}
        result.append({
            "id": r[0], "ts": r[1], "phase": r[2], "layer": r[3],
            "git_sha": r[4], "status": r[5], "detail": r[6],
            "duration_ms": r[7], **extra_tags, **extra_metrics,
        })
    return result


def summary(db_path: Path | str = _DEFAULT_DB) -> None:
    """Print a compact experiment ledger summary to stdout."""
    import datetime

    db_path = Path(db_path)
    init(db_path)
    with _LOCK, _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM experiment_runs").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) FROM experiment_runs GROUP BY status"
        ).fetchall()
        by_layer = conn.execute(
            "SELECT layer, COUNT(*), SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) "
            "FROM experiment_runs GROUP BY layer ORDER BY layer"
        ).fetchall()
        recent = conn.execute(
            "SELECT ts, phase, layer, status, duration_ms FROM experiment_runs "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()

    print(f"\n=== Knitweb Experiment Ledger ({db_path.name}) ===")
    print(f"Total runs: {total}")
    status_str = "  ".join(f"{s}={n}" for s, n in by_status)
    print(f"By status : {status_str}")
    if by_layer:
        print("By layer  :")
        for layer, count, passed in by_layer:
            lbl = layer or "—"
            pct = f"{passed/count*100:.0f}%" if count else "—"
            print(f"  {lbl:6s}  {count:3d} runs  {pct} pass")
    print("Recent runs:")
    for ts, phase, layer, status, dur in recent:
        dt = datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
        lbl = f"[{layer}]" if layer else ""
        print(f"  {dt}  {status:4s}  {lbl:5s}  {phase}  ({dur}ms)")
    print()
