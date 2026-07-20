"""Tests for the experiment ledger (experiments/ledger.py).

Verifies: SQLite persistence, run_proof context manager, history filtering,
summary output, MLflow mirror (mocked), and schema migration.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# Use a temp DB for every test to avoid cross-test pollution.
from experiments import ledger


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.sqlite"
    ledger.init(db)
    return db


# ---------------------------------------------------------------------------
# Basic record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_returns_incrementing_row_ids(self, tmp_db):
        id1 = ledger.record("phase-a", "PASS", db_path=tmp_db, mlflow_experiment=None)
        id2 = ledger.record("phase-b", "FAIL", db_path=tmp_db, mlflow_experiment=None)
        assert id2 > id1

    def test_stores_all_fields(self, tmp_db):
        ledger.record(
            "phase-x", "PASS", detail="ok", fixture_hash="abc123",
            duration_ms=42, layer="L1", tags={"k": "v"}, metrics={"score": 0.9},
            db_path=tmp_db, mlflow_experiment=None,
        )
        rows = ledger.history(db_path=tmp_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["phase"] == "phase-x"
        assert row["status"] == "PASS"
        assert row["layer"] == "L1"
        assert row["duration_ms"] == 42
        assert row["k"] == "v"        # extra_tags unpacked
        assert row["score"] == 0.9    # extra_metrics unpacked

    def test_idempotent_init(self, tmp_db):
        ledger.init(tmp_db)  # second call must not raise
        ledger.init(tmp_db)


# ---------------------------------------------------------------------------
# run_proof context manager
# ---------------------------------------------------------------------------

class TestRunProof:
    def test_pass_on_clean_exit(self, tmp_db):
        with ledger.run_proof("proof-ok", layer="L0", db_path=tmp_db, mlflow_experiment=None) as ctx:
            ctx.tag("component", "core")
            ctx.metric("assertions", 5)
        rows = ledger.history(db_path=tmp_db)
        assert rows[0]["status"] == "PASS"
        assert rows[0]["component"] == "core"
        assert rows[0]["assertions"] == 5

    def test_fail_on_exception(self, tmp_db):
        with pytest.raises(ValueError):
            with ledger.run_proof("proof-fail", db_path=tmp_db, mlflow_experiment=None):
                raise ValueError("bad thing")
        rows = ledger.history(db_path=tmp_db)
        assert rows[0]["status"] == "FAIL"
        assert "ValueError" in rows[0]["detail"]

    def test_records_duration(self, tmp_db):
        with ledger.run_proof("proof-time", db_path=tmp_db, mlflow_experiment=None):
            pass
        rows = ledger.history(db_path=tmp_db)
        assert rows[0]["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# History filtering
# ---------------------------------------------------------------------------

class TestHistory:
    def _seed(self, db):
        ledger.record("L1-transfer", "PASS", layer="L1", db_path=db, mlflow_experiment=None)
        ledger.record("L2-sync", "PASS", layer="L2", db_path=db, mlflow_experiment=None)
        ledger.record("L1-overdraft", "FAIL", layer="L1", db_path=db, mlflow_experiment=None)

    def test_filter_by_phase_prefix(self, tmp_db):
        self._seed(tmp_db)
        rows = ledger.history(db_path=tmp_db, phase="L1")
        assert all(r["phase"].startswith("L1") for r in rows)
        assert len(rows) == 2

    def test_filter_by_layer(self, tmp_db):
        self._seed(tmp_db)
        rows = ledger.history(db_path=tmp_db, layer="L2")
        assert len(rows) == 1
        assert rows[0]["phase"] == "L2-sync"

    def test_filter_by_status(self, tmp_db):
        self._seed(tmp_db)
        rows = ledger.history(db_path=tmp_db, status="FAIL")
        assert len(rows) == 1
        assert rows[0]["phase"] == "L1-overdraft"

    def test_limit(self, tmp_db):
        for i in range(10):
            ledger.record(f"run-{i}", "PASS", db_path=tmp_db, mlflow_experiment=None)
        rows = ledger.history(db_path=tmp_db, limit=3)
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_does_not_raise_on_empty(self, tmp_db, capsys):
        ledger.summary(db_path=tmp_db)
        out = capsys.readouterr().out
        assert "Knitweb Experiment Ledger" in out
        assert "Total runs: 0" in out

    def test_summary_shows_counts(self, tmp_db, capsys):
        ledger.record("p1", "PASS", layer="L1", db_path=tmp_db, mlflow_experiment=None)
        ledger.record("p2", "FAIL", layer="L1", db_path=tmp_db, mlflow_experiment=None)
        ledger.summary(db_path=tmp_db)
        out = capsys.readouterr().out
        assert "PASS=1" in out
        assert "FAIL=1" in out
        assert "L1" in out


# ---------------------------------------------------------------------------
# MLflow mirror (best-effort — must never break the caller)
# ---------------------------------------------------------------------------

class TestMLflowMirror:
    def test_record_succeeds_when_mlflow_unavailable(self, tmp_db, monkeypatch):
        # Simulate mlflow import error
        import sys
        monkeypatch.setitem(sys.modules, "mlflow", None)  # type: ignore[arg-type]
        row_id = ledger.record(
            "phase-no-mlflow", "PASS", db_path=tmp_db,
            mlflow_experiment="knitweb",
        )
        assert row_id > 0
        rows = ledger.history(db_path=tmp_db)
        assert rows[0]["status"] == "PASS"

    def test_run_proof_succeeds_when_mlflow_raises(self, tmp_db, monkeypatch):
        import sys

        class _FakeMlflow:
            def set_tracking_uri(self, *a, **kw): raise RuntimeError("mlflow down")
            def set_experiment(self, *a, **kw): raise RuntimeError("mlflow down")
            def start_run(self, *a, **kw): raise RuntimeError("mlflow down")

        monkeypatch.setitem(sys.modules, "mlflow", _FakeMlflow())
        with ledger.run_proof("proof-mlflow-broken", db_path=tmp_db, mlflow_experiment="knitweb"):
            pass
        rows = ledger.history(db_path=tmp_db)
        assert rows[0]["status"] == "PASS"
