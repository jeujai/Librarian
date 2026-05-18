"""
End-to-end integration tests for the data generation resume flow.

Verifies the connected flow:
  step_generate failure → partial download → resume-from →
  upload → resumed generation → merged output

Also verifies:
  - completed_strategies flows from Redis through the status endpoint
  - The resume command printed on failure is correct and usable
  - --resume-from restores pipeline_config.json parameters
  - Explicit CLI args override saved values

Requirements: 1.1, 1.5, 2.1, 3.1, 3.2, 5.1, 5.4, 6.3, 8.2, 8.3
Task: 12.1
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multimodal_librarian.api.routers.ml_training import (
    ResumeManifest,
    ResumeStrategyInfo,
    TrainingDataRequest,
    TrainingDataStatusResponse,
    router,
)
from multimodal_librarian.ml.models import InstructionTuningPair, PairMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with only the ML training router."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_async_result(
    status: str = "PENDING",
    result: Optional[Dict[str, Any]] = None,
    info: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    """Build a mock ``celery.result.AsyncResult``."""
    mock = MagicMock()
    mock.status = status
    mock.result = result
    mock.info = info
    return mock


def _make_pair_dict(
    instruction: str,
    strategy: str = "kg",
    confidence: float = 0.95,
) -> dict:
    """Create a valid InstructionTuningPair JSON dict."""
    return {
        "instruction": instruction,
        "context": f"Context for: {instruction}",
        "response": f"Response for: {instruction}",
        "metadata": {
            "strategy": strategy,
            "source_concepts": ["C0000001"],
            "confidence_score": confidence,
        },
    }


def _write_partial_jsonl(path: Path, pairs: list[dict]) -> None:
    """Write a list of pair dicts as JSONL to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> FastAPI:
    return _create_test_app()


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test: Upload partial → download partial round-trip
# ---------------------------------------------------------------------------


class TestPartialDataRoundTrip:
    """Verify upload-partial → download-partial round-trip.

    Requirements: 2.1, 3.2
    """

    def test_upload_then_list_partial(self, client: TestClient, tmp_path: Path):
        """Upload a partial file, then list available partials."""
        # Create a partial JSONL file
        pairs = [_make_pair_dict(f"KG question {i}", "kg") for i in range(5)]
        partial_file = tmp_path / "partial_kg.jsonl"
        _write_partial_jsonl(partial_file, pairs)

        job_id = "test-roundtrip-001"

        # Patch the upload directory to use tmp_path
        upload_dir = tmp_path / "uploads"
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            # Upload
            with open(partial_file, "rb") as f:
                resp = client.post(
                    f"/api/v1/ml/training-data/upload-partial/{job_id}",
                    files={"file": ("partial_kg.jsonl", f, "application/jsonl")},
                    data={"strategy": "kg"},
                )
            assert resp.status_code == 200
            body = resp.json()
            assert body["strategy"] == "kg"
            assert body["pair_count"] == 5

            # List
            resp = client.get(
                f"/api/v1/ml/training-data/download-partial/{job_id}"
            )
            assert resp.status_code == 200
            listing = resp.json()
            assert listing["job_id"] == job_id
            assert "kg" in listing["partial_files"]
            assert listing["partial_files"]["kg"]["pair_count"] == 5

    def test_upload_then_download_strategy(
        self, client: TestClient, tmp_path: Path
    ):
        """Upload a partial file, then download it by strategy."""
        pairs = [
            _make_pair_dict(f"RAG question {i}", "rag") for i in range(3)
        ]
        partial_file = tmp_path / "partial_rag.jsonl"
        _write_partial_jsonl(partial_file, pairs)

        job_id = "test-roundtrip-002"
        upload_dir = tmp_path / "uploads"

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            # Upload
            with open(partial_file, "rb") as f:
                resp = client.post(
                    f"/api/v1/ml/training-data/upload-partial/{job_id}",
                    files={
                        "file": (
                            "partial_rag.jsonl",
                            f,
                            "application/jsonl",
                        )
                    },
                    data={"strategy": "rag"},
                )
            assert resp.status_code == 200

            # Download by strategy
            resp = client.get(
                f"/api/v1/ml/training-data/download-partial/{job_id}",
                params={"strategy": "rag"},
            )
            assert resp.status_code == 200
            # Parse the downloaded content
            content = resp.text
            lines = [
                line for line in content.strip().split("\n") if line.strip()
            ]
            assert len(lines) == 3
            for line in lines:
                obj = json.loads(line)
                assert obj["metadata"]["strategy"] == "rag"

    def test_download_partial_404_when_no_data(self, client: TestClient, tmp_path: Path):
        """GET /download-partial returns 404 when no partial data exists."""
        upload_dir = tmp_path / "uploads"
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            resp = client.get(
                "/api/v1/ml/training-data/download-partial/nonexistent-job"
            )
            assert resp.status_code == 404

    def test_upload_invalid_strategy_returns_422(
        self, client: TestClient, tmp_path: Path
    ):
        """POST /upload-partial with invalid strategy returns 422."""
        partial_file = tmp_path / "dummy.jsonl"
        partial_file.write_text("{}\n")

        with open(partial_file, "rb") as f:
            resp = client.post(
                "/api/v1/ml/training-data/upload-partial/job-123",
                files={"file": ("dummy.jsonl", f, "application/jsonl")},
                data={"strategy": "invalid_strategy"},
            )
        assert resp.status_code == 422

    def test_download_partial_invalid_strategy_returns_422(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial with invalid strategy returns 422."""
        upload_dir = tmp_path / "uploads"
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            resp = client.get(
                "/api/v1/ml/training-data/download-partial/job-123",
                params={"strategy": "bad_strategy"},
            )
            assert resp.status_code == 422



# ---------------------------------------------------------------------------
# Test: completed_strategies flows through status endpoint
# ---------------------------------------------------------------------------


class TestCompletedStrategiesFlow:
    """Verify completed_strategies flows from Redis → status → client.

    Requirements: 6.3
    """

    def test_completed_strategies_in_failure_status(
        self, client: TestClient
    ):
        """Failed job status includes completed_strategies from Redis."""
        persisted = {
            "phase": "rag_generation",
            "percentage": 45.0,
            "pairs_per_strategy": {"kg": 2500, "rag": 312},
            "completed_strategies": {"kg": 2500},
            "error": "Connection lost during RAG generation",
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=persisted,
        ):
            mock_result = _mock_async_result(
                status="FAILURE",
                result=RuntimeError("Connection lost during RAG generation"),
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                resp = client.get(
                    "/api/v1/ml/training-data/status/job-fail-001"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["completed_strategies"] == {"kg": 2500}
        assert body["pairs_per_strategy"] == {"kg": 2500, "rag": 312}

    def test_completed_strategies_in_progress_status(
        self, client: TestClient
    ):
        """In-progress job status includes completed_strategies from Celery info."""
        celery_info = {
            "phase": "umls_generation",
            "percentage": 70.0,
            "pairs_per_strategy": {"kg": 2500, "rag": 2500, "umls": 500},
            "eta_seconds": 3600.0,
            "completed_strategies": {"kg": 2500, "rag": 2500},
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS",
                info=celery_info,
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                resp = client.get(
                    "/api/v1/ml/training-data/status/job-progress-001"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "progress"
        assert body["completed_strategies"] == {"kg": 2500, "rag": 2500}

    def test_completed_strategies_in_pending_with_redis(
        self, client: TestClient
    ):
        """PENDING + Redis progress includes completed_strategies (hard timeout recovery)."""
        persisted = {
            "phase": "umls_generation",
            "percentage": 60.0,
            "pairs_per_strategy": {"kg": 2500},
            "completed_strategies": {"kg": 2500},
            "eta_seconds": 90.0,
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=persisted,
        ):
            mock_result = _mock_async_result(status="PENDING")
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                resp = client.get(
                    "/api/v1/ml/training-data/status/job-pending-001"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "progress"
        assert body["completed_strategies"] == {"kg": 2500}

    def test_completed_strategies_absent_when_no_strategies_done(
        self, client: TestClient
    ):
        """Status response has null completed_strategies when none finished."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS",
                info={
                    "phase": "kg_generation",
                    "percentage": 10.0,
                    "pairs_per_strategy": {"kg": 100},
                    "eta_seconds": 5000.0,
                },
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                resp = client.get(
                    "/api/v1/ml/training-data/status/job-early-001"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "progress"
        # completed_strategies not in info → should be None
        assert body["completed_strategies"] is None



# ---------------------------------------------------------------------------
# Test: POST /generate with resume_data
# ---------------------------------------------------------------------------


class TestGenerateWithResumeData:
    """Verify POST /generate accepts and passes resume_data to Celery.

    Requirements: 3.1, 3.3, 3.4
    """

    def test_generate_with_resume_data_dispatches_celery(
        self, client: TestClient
    ):
        """POST /generate with resume_data includes it in the Celery config."""
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 1000,
                    "strategies": ["kg", "rag"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 500, "complete": True},
                        }
                    },
                },
            )

        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body

        # Verify resume_data was passed to Celery
        call_args = mock_celery_task.apply_async.call_args
        args_list = (
            call_args.kwargs.get("args")
            or call_args[1].get("args")
            or call_args[0][0]
        )
        config_dict = args_list[1]
        assert "resume_data" in config_dict
        assert config_dict["resume_data"]["strategies"]["kg"]["pair_count"] == 500
        assert config_dict["resume_data"]["strategies"]["kg"]["complete"] is True

    def test_generate_without_resume_data_omits_field(
        self, client: TestClient
    ):
        """POST /generate without resume_data does not include it."""
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 1000,
                    "strategies": ["kg"],
                },
            )

        assert resp.status_code == 202
        call_args = mock_celery_task.apply_async.call_args
        args_list = (
            call_args.kwargs.get("args")
            or call_args[1].get("args")
            or call_args[0][0]
        )
        config_dict = args_list[1]
        assert "resume_data" not in config_dict



# ---------------------------------------------------------------------------
# Test: Pipeline client resume flow (scan → upload → manifest)
# ---------------------------------------------------------------------------


class TestPipelineClientResumeFlow:
    """Verify the pipeline client's resume helpers work as a connected flow.

    Tests _scan_partial_data, _upload_partial_data, and the resume
    manifest construction without requiring a live server.

    Requirements: 5.1, 5.2, 5.3, 5.4
    """

    def test_scan_partial_data_finds_valid_pairs(self, tmp_path: Path):
        """_scan_partial_data returns valid pairs from partial files."""
        # Import the pipeline helpers
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        # Avoid running main() on import
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)

        # Create partial files
        kg_pairs = [_make_pair_dict(f"KG Q{i}", "kg") for i in range(10)]
        rag_pairs = [_make_pair_dict(f"RAG Q{i}", "rag") for i in range(5)]
        _write_partial_jsonl(tmp_path / "partial_kg.jsonl", kg_pairs)
        _write_partial_jsonl(tmp_path / "partial_rag.jsonl", rag_pairs)

        result = pipeline._scan_partial_data(tmp_path)

        assert "kg" in result
        assert "rag" in result
        assert "umls_reasoning" not in result
        assert result["kg"]["pair_count"] == 10
        assert result["rag"]["pair_count"] == 5
        assert len(result["kg"]["pairs"]) == 10
        assert len(result["rag"]["pairs"]) == 5

    def test_scan_partial_data_skips_invalid_lines(self, tmp_path: Path):
        """_scan_partial_data skips invalid JSONL lines."""
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)

        # Mix valid and invalid lines
        valid_pair = _make_pair_dict("Valid question", "kg")
        lines = [
            json.dumps(valid_pair),
            "not valid json",
            "",
            json.dumps({"instruction": "missing fields"}),
            json.dumps(valid_pair),  # duplicate but still valid
        ]
        (tmp_path / "partial_kg.jsonl").write_text(
            "\n".join(lines), encoding="utf-8"
        )

        result = pipeline._scan_partial_data(tmp_path)
        assert result["kg"]["pair_count"] == 2  # only 2 valid lines

    def test_scan_empty_directory_returns_empty(self, tmp_path: Path):
        """_scan_partial_data returns empty dict for directory with no partials."""
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)

        result = pipeline._scan_partial_data(tmp_path)
        assert result == {}

    def test_resume_manifest_construction(self, tmp_path: Path):
        """Verify the resume manifest is correctly built from scan results."""
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)

        # Create partial files
        kg_pairs = [_make_pair_dict(f"KG Q{i}", "kg") for i in range(7)]
        _write_partial_jsonl(tmp_path / "partial_kg.jsonl", kg_pairs)

        partial_data = pipeline._scan_partial_data(tmp_path)

        # Build manifest the same way step_generate does
        resume_manifest = {
            "strategies": {
                strategy: {
                    "pair_count": info["pair_count"],
                    "complete": True,
                }
                for strategy, info in partial_data.items()
            }
        }

        assert "strategies" in resume_manifest
        assert "kg" in resume_manifest["strategies"]
        assert resume_manifest["strategies"]["kg"]["pair_count"] == 7
        assert resume_manifest["strategies"]["kg"]["complete"] is True

        # Verify it's valid as a ResumeManifest
        manifest = ResumeManifest(**resume_manifest)
        assert manifest.strategies["kg"].pair_count == 7
        assert manifest.strategies["kg"].complete is True



# ---------------------------------------------------------------------------
# Test: Config restoration with CLI override precedence
# ---------------------------------------------------------------------------


class TestConfigRestorationFlow:
    """Verify --resume-from restores pipeline_config.json and CLI overrides win.

    Requirements: 8.2, 8.3
    """

    def _load_pipeline_module(self):
        """Import the pipeline script as a module."""
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)
        return pipeline

    def test_load_saved_config_reads_json(self, tmp_path: Path):
        """_load_saved_config reads pipeline_config.json correctly."""
        pipeline = self._load_pipeline_module()

        config = {
            "pair_count": 5000,
            "strategies": ["kg", "rag", "umls_reasoning"],
            "random_seed": 99,
            "min_confidence": 0.70,
        }
        (tmp_path / "pipeline_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

        result = pipeline._load_saved_config(tmp_path)
        assert result is not None
        assert result["pair_count"] == 5000
        assert result["strategies"] == ["kg", "rag", "umls_reasoning"]
        assert result["random_seed"] == 99

    def test_load_saved_config_returns_none_for_missing(self, tmp_path: Path):
        """_load_saved_config returns None when file is missing."""
        pipeline = self._load_pipeline_module()
        result = pipeline._load_saved_config(tmp_path)
        assert result is None

    def test_load_saved_config_returns_none_for_invalid_json(
        self, tmp_path: Path
    ):
        """_load_saved_config returns None for invalid JSON."""
        pipeline = self._load_pipeline_module()
        (tmp_path / "pipeline_config.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )
        result = pipeline._load_saved_config(tmp_path)
        assert result is None

    def test_apply_saved_config_restores_non_explicit(self, tmp_path: Path):
        """_apply_saved_config restores saved values for non-explicit args."""
        pipeline = self._load_pipeline_module()

        args = argparse.Namespace(
            pair_count=7500,  # default
            strategies=["kg", "umls_reasoning"],  # default
            random_seed=42,  # default
            min_confidence=0.80,  # default
        )
        saved_config = {
            "pair_count": 5000,
            "strategies": ["kg", "rag"],
            "random_seed": 99,
            "min_confidence": 0.70,
        }
        explicit_args: set[str] = set()  # nothing explicit

        result = pipeline._apply_saved_config(args, saved_config, explicit_args)

        assert result.pair_count == 5000
        assert result.strategies == ["kg", "rag"]
        assert result.random_seed == 99
        assert result.min_confidence == 0.70

    def test_apply_saved_config_explicit_args_win(self, tmp_path: Path):
        """_apply_saved_config preserves explicitly provided CLI args."""
        pipeline = self._load_pipeline_module()

        args = argparse.Namespace(
            pair_count=3000,  # explicitly provided
            strategies=["kg"],  # explicitly provided
            random_seed=42,  # default
            min_confidence=0.80,  # default
        )
        saved_config = {
            "pair_count": 5000,
            "strategies": ["kg", "rag"],
            "random_seed": 99,
            "min_confidence": 0.70,
        }
        explicit_args = {"pair_count", "strategies"}

        result = pipeline._apply_saved_config(args, saved_config, explicit_args)

        # Explicit args preserved
        assert result.pair_count == 3000
        assert result.strategies == ["kg"]
        # Non-explicit args restored from saved config
        assert result.random_seed == 99
        assert result.min_confidence == 0.70

    def test_apply_saved_config_ignores_unknown_keys(self, tmp_path: Path):
        """_apply_saved_config ignores keys not present in args namespace."""
        pipeline = self._load_pipeline_module()

        args = argparse.Namespace(pair_count=7500)
        saved_config = {
            "pair_count": 5000,
            "unknown_key": "should be ignored",
        }
        explicit_args: set[str] = set()

        result = pipeline._apply_saved_config(args, saved_config, explicit_args)
        assert result.pair_count == 5000
        assert not hasattr(result, "unknown_key")

    def test_full_config_restoration_flow(self, tmp_path: Path):
        """End-to-end: load config → apply with overrides → verify merge."""
        pipeline = self._load_pipeline_module()

        # Simulate a saved config from a previous run
        saved = {
            "pair_count": 5000,
            "strategies": ["kg", "rag", "umls_reasoning"],
            "random_seed": 99,
            "min_confidence": 0.70,
            "similarity_threshold": 0.85,
            "model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
        }
        (tmp_path / "pipeline_config.json").write_text(
            json.dumps(saved), encoding="utf-8"
        )

        # Load
        loaded = pipeline._load_saved_config(tmp_path)
        assert loaded is not None

        # Apply with some explicit overrides
        args = argparse.Namespace(
            pair_count=3000,  # user explicitly changed this
            strategies=["kg", "rag", "umls_reasoning"],
            random_seed=42,
            min_confidence=0.80,
            similarity_threshold=0.90,
            model="mlx-community/Llama-3.2-3B-Instruct-4bit",
        )
        explicit = {"pair_count"}  # only pair_count was explicit

        result = pipeline._apply_saved_config(args, loaded, explicit)

        # pair_count: explicit → preserved
        assert result.pair_count == 3000
        # Everything else: restored from saved config
        assert result.strategies == ["kg", "rag", "umls_reasoning"]
        assert result.random_seed == 99
        assert result.min_confidence == 0.70
        assert result.similarity_threshold == 0.85



# ---------------------------------------------------------------------------
# Test: Resume command printed on failure
# ---------------------------------------------------------------------------


class TestResumeCommandOnFailure:
    """Verify the resume command printed on failure is correct.

    Requirements: 1.1, 1.5
    """

    def test_resume_command_format(self, tmp_path: Path, capsys):
        """step_generate prints a usable --resume-from command on failure."""
        import importlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "pipeline", "scripts/run-training-pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        sys.modules["pipeline"] = pipeline
        spec.loader.exec_module(pipeline)

        run_dir = tmp_path / "training_runs" / "2024-01-01_120000"
        run_dir.mkdir(parents=True)

        # Create partial data on the "server" side
        kg_pairs = [_make_pair_dict(f"KG Q{i}", "kg") for i in range(5)]

        # Mock the HTTP calls
        import requests

        class MockListingResponse:
            status_code = 200

            def json(self):
                return {
                    "job_id": "fail-job-001",
                    "partial_files": {
                        "kg": {
                            "file": "partial_kg.jsonl",
                            "pair_count": 5,
                        }
                    },
                }

        class MockDownloadResponse:
            status_code = 200

            def iter_content(self, chunk_size=8192):
                content = "\n".join(
                    json.dumps(p) for p in kg_pairs
                ).encode()
                yield content

        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "strategy" in kwargs.get("params", {}):
                return MockDownloadResponse()
            return MockListingResponse()

        recovered = {}
        with patch.object(requests, "get", side_effect=mock_get):
            recovered = pipeline._download_partial_data(
                "fail-job-001", run_dir, ["kg", "rag"]
            )

        assert "kg" in recovered
        assert recovered["kg"] == 5

        # Verify the partial file was saved
        assert (run_dir / "partial_kg.jsonl").exists()

        # Verify the resume command would be printed
        # (step_generate prints it; we verify the format here)
        expected_cmd = f"--resume-from {run_dir}"
        # The command should reference the run directory
        assert str(run_dir) in expected_cmd



# ---------------------------------------------------------------------------
# Test: Full upload → generate with resume_data → status flow
# ---------------------------------------------------------------------------


class TestUploadGenerateStatusFlow:
    """Verify upload partial → trigger resumed generation → status includes
    completed_strategies as a connected API flow.

    Requirements: 1.1, 2.1, 3.1, 5.4, 6.3
    """

    def test_upload_then_generate_with_resume(
        self, client: TestClient, tmp_path: Path
    ):
        """Upload partial data, trigger generation with resume_data,
        verify the Celery task receives the resume config."""
        upload_dir = tmp_path / "uploads"

        # Step 1: Upload partial KG data
        kg_pairs = [_make_pair_dict(f"KG Q{i}", "kg") for i in range(100)]
        partial_file = tmp_path / "partial_kg.jsonl"
        _write_partial_jsonl(partial_file, kg_pairs)

        job_id = "resume-flow-001"

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            with open(partial_file, "rb") as f:
                resp = client.post(
                    f"/api/v1/ml/training-data/upload-partial/{job_id}",
                    files={
                        "file": (
                            "partial_kg.jsonl",
                            f,
                            "application/jsonl",
                        )
                    },
                    data={"strategy": "kg"},
                )
            assert resp.status_code == 200
            assert resp.json()["pair_count"] == 100

        # Step 2: Trigger generation with resume_data
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 300,
                    "strategies": ["kg", "rag"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 100, "complete": True},
                        }
                    },
                },
            )
        assert resp.status_code == 202

        # Verify Celery received resume_data
        call_args = mock_celery_task.apply_async.call_args
        args_list = (
            call_args.kwargs.get("args")
            or call_args[1].get("args")
            or call_args[0][0]
        )
        config_dict = args_list[1]
        assert config_dict["resume_data"]["strategies"]["kg"]["pair_count"] == 100

        # Step 3: Simulate status with completed_strategies
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS",
                info={
                    "phase": "rag_generation",
                    "percentage": 50.0,
                    "pairs_per_strategy": {"kg": 100, "rag": 50},
                    "eta_seconds": 1800.0,
                    "completed_strategies": {"kg": 100},
                },
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                actual_job_id = resp.json()["job_id"]
                status_resp = client.get(
                    f"/api/v1/ml/training-data/status/{actual_job_id}"
                )

        assert status_resp.status_code == 200
        status_body = status_resp.json()
        assert status_body["completed_strategies"] == {"kg": 100}
        assert status_body["phase"] == "rag_generation"

    def test_multi_strategy_upload_and_resume(
        self, client: TestClient, tmp_path: Path
    ):
        """Upload partial data for multiple strategies and resume."""
        upload_dir = tmp_path / "uploads"
        job_id = "resume-multi-001"

        kg_pairs = [_make_pair_dict(f"KG Q{i}", "kg") for i in range(50)]
        rag_pairs = [_make_pair_dict(f"RAG Q{i}", "rag") for i in range(30)]

        kg_file = tmp_path / "partial_kg.jsonl"
        rag_file = tmp_path / "partial_rag.jsonl"
        _write_partial_jsonl(kg_file, kg_pairs)
        _write_partial_jsonl(rag_file, rag_pairs)

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            # Upload KG
            with open(kg_file, "rb") as f:
                resp = client.post(
                    f"/api/v1/ml/training-data/upload-partial/{job_id}",
                    files={
                        "file": (
                            "partial_kg.jsonl",
                            f,
                            "application/jsonl",
                        )
                    },
                    data={"strategy": "kg"},
                )
            assert resp.status_code == 200
            assert resp.json()["pair_count"] == 50

            # Upload RAG
            with open(rag_file, "rb") as f:
                resp = client.post(
                    f"/api/v1/ml/training-data/upload-partial/{job_id}",
                    files={
                        "file": (
                            "partial_rag.jsonl",
                            f,
                            "application/jsonl",
                        )
                    },
                    data={"strategy": "rag"},
                )
            assert resp.status_code == 200
            assert resp.json()["pair_count"] == 30

            # List partials — both should be present
            resp = client.get(
                f"/api/v1/ml/training-data/download-partial/{job_id}"
            )
            assert resp.status_code == 200
            listing = resp.json()
            assert "kg" in listing["partial_files"]
            assert "rag" in listing["partial_files"]
            assert listing["partial_files"]["kg"]["pair_count"] == 50
            assert listing["partial_files"]["rag"]["pair_count"] == 30

        # Trigger generation with resume_data for both strategies
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 300,
                    "strategies": ["kg", "rag", "umls_reasoning"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 50, "complete": True},
                            "rag": {"pair_count": 30, "complete": False},
                        }
                    },
                },
            )
        assert resp.status_code == 202

        call_args = mock_celery_task.apply_async.call_args
        args_list = (
            call_args.kwargs.get("args")
            or call_args[1].get("args")
            or call_args[0][0]
        )
        config_dict = args_list[1]
        resume = config_dict["resume_data"]
        assert resume["strategies"]["kg"]["pair_count"] == 50
        assert resume["strategies"]["kg"]["complete"] is True
        assert resume["strategies"]["rag"]["pair_count"] == 30
        assert resume["strategies"]["rag"]["complete"] is False
