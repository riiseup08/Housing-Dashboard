"""Tests for pipeline-level output validation."""

import pandas as pd

import run_pipeline


def test_validate_output_accepts_healthy_frame(monkeypatch):
    monkeypatch.setattr(run_pipeline, "VALIDATION_MAX_NULL_PCT", 0.30)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
            "value": [1.0, 2.0, 3.0],
        }
    )

    assert run_pipeline.validate_output("sample", frame, min_rows=3)


def test_validate_output_rejects_too_few_rows():
    frame = pd.DataFrame({"value": [1.0]})

    assert not run_pipeline.validate_output("sample", frame, min_rows=2)


def test_validate_output_rejects_excessive_nulls(monkeypatch):
    monkeypatch.setattr(run_pipeline, "VALIDATION_MAX_NULL_PCT", 0.30)
    frame = pd.DataFrame({"value": [1.0, None, None]})

    assert not run_pipeline.validate_output("sample", frame, min_rows=3)
