"""
Integration tests for ML Training Data Generation API endpoints.

Tests the POST /generate → GET /status → GET /download lifecycle
with mocked Celery, configuration parameter validation, and error
responses for invalid job IDs.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multimodal_librarian.api.routers.ml_training import (
    TrainingDataJobResponse,
    TrainingDataRequest,
    TrainingDataStatusResponse,
    router,
)
from multimodal_librarian.ml.models import (
    DatasetSummary,
    InstructionTuningPair,
    PairMetadata,
    TrainingDataConfig,
    TrainingDataResult,
    ValidationResult,
)
from multimodal_librarian.ml.training_data_generator import TrainingDataGenerator

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app() -> FastAPI:
    return _create_test_app()


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def jsonl_file(tmp_path: Path) -> Path:
    """Create a small JSONL file to serve as a downloadable dataset."""
    path = tmp_path / "training_data.jsonl"
    lines = [
        json.dumps({
            "instruction": "What is aspirin?",
            "context": "Aspirin is a nonsteroidal anti-inflammatory drug.",
            "response": "Aspirin is used to reduce pain, fever, and inflammation.",
            "metadata": {
                "strategy": "kg",
                "source_concepts": ["C0004057"],
                "confidence_score": 0.95,
            },
        }),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# POST /generate — happy path
# ---------------------------------------------------------------------------

class TestStartGeneration:
    """Tests for POST /api/v1/ml/training-data/generate."""

    @patch(
        "multimodal_librarian.api.routers.ml_training"
        ".generate_training_data_task",
        create=True,
    )
    def test_generate_returns_202_with_job_id(self, mock_task, client: TestClient):
        """POST /generate dispatches a Celery task and returns 202."""
        # The router does a lazy import; we patch at the import target.
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            response = client.post(
                "/api/v1/ml/training-data/generate",
                json={},  # all defaults
            )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert "status_url" in body
        assert body["status_url"].startswith("/api/v1/ml/training-data/status/")
        assert body["message"] == "Training data generation job started."

    @patch(
        "multimodal_librarian.services.ml_training_tasks"
        ".generate_training_data_task"
    )
    def test_generate_with_custom_config(self, mock_celery_task, client: TestClient):
        """POST /generate accepts custom configuration parameters."""
        mock_celery_task.apply_async = MagicMock()

        payload = {
            "target_pair_count": 5000,
            "strategies": ["kg", "rag"],
            "random_seed": 123,
            "min_confidence_score": 0.7,
        }
        response = client.post(
            "/api/v1/ml/training-data/generate",
            json=payload,
        )

        assert response.status_code == 202
        # Verify the Celery task was called with the right config
        call_args = mock_celery_task.apply_async.call_args
        config_dict = call_args.kwargs.get("args") or call_args[1].get("args")
        if config_dict is None:
            config_dict = call_args[0][0]  # positional
        # config_dict is [job_id, config_dict]
        actual_config = config_dict[1]
        assert actual_config["target_pair_count"] == 5000
        assert actual_config["strategies"] == ["kg", "rag"]
        assert actual_config["random_seed"] == 123
        assert actual_config["min_confidence_score"] == 0.7

    @patch(
        "multimodal_librarian.services.ml_training_tasks"
        ".generate_training_data_task"
    )
    def test_generate_default_config_values(self, mock_celery_task, client: TestClient):
        """POST /generate uses correct defaults when no body fields given."""
        mock_celery_task.apply_async = MagicMock()

        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={},
        )

        assert response.status_code == 202
        call_args = mock_celery_task.apply_async.call_args
        config_dict = (call_args.kwargs.get("args") or call_args[1].get("args") or call_args[0][0])[1]
        assert config_dict["target_pair_count"] == 7500
        assert config_dict["strategies"] == ["kg", "umls_reasoning"]
        assert config_dict["random_seed"] == 42
        assert config_dict["min_confidence_score"] == 0.5


# ---------------------------------------------------------------------------
# POST /generate — validation errors
# ---------------------------------------------------------------------------

class TestGenerateValidation:
    """Tests for configuration parameter validation on POST /generate."""

    @patch(
        "multimodal_librarian.services.ml_training_tasks"
        ".generate_training_data_task"
    )
    def test_invalid_strategy_returns_422(self, mock_celery_task, client: TestClient):
        """Invalid strategy names are rejected with 422."""
        mock_celery_task.apply_async = MagicMock()

        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"strategies": ["kg", "invalid_strategy"]},
        )

        assert response.status_code == 422
        assert "invalid_strategy" in response.json()["detail"]

    @patch(
        "multimodal_librarian.services.ml_training_tasks"
        ".generate_training_data_task"
    )
    def test_empty_strategies_returns_422(self, mock_celery_task, client: TestClient):
        """An empty strategies list is rejected with 422."""
        mock_celery_task.apply_async = MagicMock()

        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"strategies": []},
        )

        assert response.status_code == 422

    def test_target_pair_count_below_minimum_returns_422(self, client: TestClient):
        """target_pair_count below 100 is rejected by Pydantic."""
        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"target_pair_count": 50},
        )
        assert response.status_code == 422

    def test_target_pair_count_above_maximum_returns_422(self, client: TestClient):
        """target_pair_count above 50000 is rejected by Pydantic."""
        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"target_pair_count": 100000},
        )
        assert response.status_code == 422

    def test_min_confidence_below_zero_returns_422(self, client: TestClient):
        """min_confidence_score below 0.0 is rejected."""
        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"min_confidence_score": -0.1},
        )
        assert response.status_code == 422

    def test_min_confidence_above_one_returns_422(self, client: TestClient):
        """min_confidence_score above 1.0 is rejected."""
        response = client.post(
            "/api/v1/ml/training-data/generate",
            json={"min_confidence_score": 1.5},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /generate — Celery dispatch failure
# ---------------------------------------------------------------------------

class TestGenerateCeleryFailure:
    """Tests for Celery dispatch failure handling."""

    def test_celery_unavailable_returns_503(self, client: TestClient):
        """When Celery task dispatch fails, return 503."""
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async.side_effect = ConnectionError(
                "Redis connection refused"
            )

            response = client.post(
                "/api/v1/ml/training-data/generate",
                json={},
            )

        assert response.status_code == 503
        assert "Celery workers may be unavailable" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /status/{job_id} — various Celery states
# ---------------------------------------------------------------------------

class TestGetStatus:
    """Tests for GET /api/v1/ml/training-data/status/{job_id}."""

    def test_status_pending(self, client: TestClient):
        """PENDING state with no Redis progress returns pending."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ) as mock_celery_app, patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(status="PENDING")
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/unknown-job-id"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["job_id"] == "unknown-job-id"
        assert body["phase"] is None
        assert body["percentage"] is None

    def test_status_started(self, client: TestClient):
        """STARTED state returns initializing phase."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(status="STARTED")
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "started"
        assert body["phase"] == "initializing"
        assert body["percentage"] == 0.0

    def test_status_progress(self, client: TestClient):
        """PROGRESS state returns phase, percentage, and per-strategy counts."""
        progress_info = {
            "phase": "kg_generation",
            "percentage": 35.0,
            "pairs_per_strategy": {"kg": 1200},
            "eta_seconds": 120.5,
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS", info=progress_info
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "progress"
        assert body["phase"] == "kg_generation"
        assert body["percentage"] == 35.0
        assert body["pairs_per_strategy"] == {"kg": 1200}
        assert body["eta_seconds"] == 120.5

    def test_status_success(self, client: TestClient):
        """SUCCESS state returns completed with summary."""
        task_result = {
            "summary": {
                "total_pairs": 7500,
                "pairs_per_strategy": {"kg": 3750, "umls_reasoning": 3750},
                "dedup_removed": 150,
                "avg_response_length": 120.5,
                "pass_rate": 0.85,
                "generation_time_seconds": 3600.0,
            },
            "output_path": "/tmp/training_data.jsonl",
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["phase"] == "completed"
        assert body["percentage"] == 100.0
        assert body["result"]["total_pairs"] == 7500
        assert body["pairs_per_strategy"] == {
            "kg": 3750, "umls_reasoning": 3750
        }

    def test_status_failure(self, client: TestClient):
        """FAILURE state returns error message."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value={"phase": "rag_generation", "percentage": 45.0},
        ):
            mock_result = _mock_async_result(
                status="FAILURE",
                result=RuntimeError("Neo4j connection lost"),
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert "Neo4j connection lost" in body["error"]
        # Falls back to Redis-persisted progress
        assert body["phase"] == "rag_generation"
        assert body["percentage"] == 45.0

    def test_status_pending_with_redis_progress(self, client: TestClient):
        """PENDING state with Redis progress (hard timeout recovery)."""
        persisted = {
            "phase": "umls_generation",
            "percentage": 60.0,
            "pairs_per_strategy": {"kg": 2500, "rag": 2000},
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
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "progress"
        assert body["phase"] == "umls_generation"
        assert body["percentage"] == 60.0

    def test_status_pending_with_redis_failed(self, client: TestClient):
        """PENDING + Redis shows failed → report as failed."""
        persisted = {
            "phase": "failed",
            "percentage": 30.0,
            "error": "Task lost after hard timeout",
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
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["error"] == "Task lost after hard timeout"

    def test_status_pending_with_redis_completed(self, client: TestClient):
        """PENDING + Redis shows completed → report as completed."""
        persisted = {
            "phase": "completed",
            "percentage": 100.0,
            "pairs_per_strategy": {"kg": 3750, "umls_reasoning": 3750},
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
                response = client.get(
                    "/api/v1/ml/training-data/status/job-123"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["percentage"] == 100.0


# ---------------------------------------------------------------------------
# GET /download/{job_id}
# ---------------------------------------------------------------------------

class TestDownloadDataset:
    """Tests for GET /api/v1/ml/training-data/download/{job_id}."""

    def test_download_completed_job(self, client: TestClient, jsonl_file: Path):
        """Download returns JSONL file for a completed job."""
        task_result = {
            "output_path": str(jsonl_file),
            "summary": {"total_pairs": 1},
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/job-123"
                )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        assert "training_data_job-123.jsonl" in response.headers.get(
            "content-disposition", ""
        )
        # Verify the content is valid JSONL
        lines = response.text.strip().split("\n")
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert "instruction" in parsed
        assert "response" in parsed

    def test_download_not_completed_returns_404(self, client: TestClient):
        """Download for a non-completed job returns 404."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(status="STARTED")
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/job-123"
                )

        assert response.status_code == 404
        assert "not completed" in response.json()["detail"]

    def test_download_missing_file_returns_404(self, client: TestClient):
        """Download returns 404 when the JSONL file has been cleaned up."""
        task_result = {
            "output_path": "/nonexistent/path/training_data.jsonl",
            "summary": {},
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/job-123"
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_download_no_output_path_returns_404(self, client: TestClient):
        """Download returns 404 when result has no output_path."""
        task_result = {"summary": {}}
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/job-123"
                )

        assert response.status_code == 404

    def test_download_pending_job_returns_404(self, client: TestClient):
        """Download for a PENDING job returns 404."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(status="PENDING")
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/nonexistent-id"
                )

        assert response.status_code == 404

    def test_download_failed_job_returns_404(self, client: TestClient):
        """Download for a FAILURE job returns 404."""
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(
                status="FAILURE",
                result=RuntimeError("Generation failed"),
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/download/job-123"
                )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Full lifecycle: POST /generate → GET /status → GET /download
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    """End-to-end lifecycle test with mocked Celery."""

    def test_generate_status_download_lifecycle(
        self, client: TestClient, jsonl_file: Path
    ):
        """Full lifecycle: generate → poll status → download."""
        # Step 1: Start generation
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            gen_response = client.post(
                "/api/v1/ml/training-data/generate",
                json={"target_pair_count": 1000, "strategies": ["kg"]},
            )

        assert gen_response.status_code == 202
        job_id = gen_response.json()["job_id"]
        status_url = gen_response.json()["status_url"]

        # Step 2: Poll status — simulate PROGRESS
        progress_info = {
            "phase": "kg_generation",
            "percentage": 50.0,
            "pairs_per_strategy": {"kg": 500},
            "eta_seconds": 60.0,
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS", info=progress_info
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                status_response = client.get(status_url)

        assert status_response.status_code == 200
        assert status_response.json()["status"] == "progress"
        assert status_response.json()["percentage"] == 50.0

        # Step 3: Poll status — simulate SUCCESS
        task_result = {
            "output_path": str(jsonl_file),
            "summary": {
                "total_pairs": 1000,
                "pairs_per_strategy": {"kg": 1000},
                "dedup_removed": 20,
                "avg_response_length": 95.0,
                "pass_rate": 0.88,
                "generation_time_seconds": 120.0,
            },
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                status_response = client.get(status_url)

        assert status_response.status_code == 200
        assert status_response.json()["status"] == "completed"
        assert status_response.json()["percentage"] == 100.0

        # Step 4: Download the dataset
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ):
            mock_result = _mock_async_result(
                status="SUCCESS", result=task_result
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                download_response = client.get(
                    f"/api/v1/ml/training-data/download/{job_id}"
                )

        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "application/x-ndjson"
        parsed = json.loads(download_response.text.strip().split("\n")[0])
        assert parsed["instruction"] == "What is aspirin?"


# ---------------------------------------------------------------------------
# End-to-end data generation (small scale) with mocked services
# Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.1
# ---------------------------------------------------------------------------


# -- Fake NERResult for the NER extractor mock ----------------------------

@dataclass
class _FakeNERResult:
    """Minimal stand-in for ``NERResult`` returned by NER_Extractor."""

    web_entities: List[str] = dc_field(default_factory=list)
    sci_entities: List[str] = dc_field(default_factory=list)
    umls_entities: List[str] = dc_field(default_factory=list)
    key_terms: Set[str] = dc_field(default_factory=set)


# -- Known test data -------------------------------------------------------

# 30 medical concepts for the KG strategy
_KG_CONCEPTS = [
    {
        "name": f"Concept_{i}",
        "cui": f"C{1000000 + i:07d}",
        "semantic_type": [
            "Pharmacologic Substance",
            "Disease or Syndrome",
            "Therapeutic Procedure",
            "Body Part, Organ, or Organ Component",
            "Clinical Attribute",
        ][i % 5],
        "synonyms": [f"Synonym_A_{i}", f"Synonym_B_{i}"],
        "chunk_ids": [f"chunk-kg-{i}-a", f"chunk-kg-{i}-b"],
    }
    for i in range(30)
]

# Chunk content returned by the vector store (>= 50 tokens each)
_CHUNK_CONTENT_TEMPLATE = (
    "This is a detailed medical reference passage about {concept}. "
    "It covers the clinical significance, mechanism of action, "
    "pharmacokinetics, indications, contraindications, adverse effects, "
    "drug interactions, dosage forms, and monitoring parameters. "
    "The information is sourced from peer-reviewed medical literature "
    "and clinical practice guidelines published in major medical journals. "
    "Additional details include therapeutic dosing ranges, special "
    "population considerations such as pediatric and geriatric patients, "
    "renal and hepatic dose adjustments, pregnancy and lactation safety "
    "profiles, and evidence-based treatment algorithms for common "
    "clinical scenarios encountered in primary care and specialty practice."
)

# UMLS concepts for the RAG strategy seed generation
_UMLS_CONCEPTS_BY_TYPE = {
    "Pharmacologic Substance": [
        {"preferred_name": "Metformin"},
        {"preferred_name": "Lisinopril"},
        {"preferred_name": "Atorvastatin"},
        {"preferred_name": "Omeprazole"},
    ],
    "Disease or Syndrome": [
        {"preferred_name": "Type 2 Diabetes Mellitus"},
        {"preferred_name": "Hypertension"},
        {"preferred_name": "Hyperlipidemia"},
        {"preferred_name": "Gastroesophageal Reflux Disease"},
    ],
    "Therapeutic Procedure": [
        {"preferred_name": "Coronary Artery Bypass Grafting"},
        {"preferred_name": "Percutaneous Coronary Intervention"},
    ],
    "Body Part, Organ, or Organ Component": [
        {"preferred_name": "Left Ventricle"},
        {"preferred_name": "Hepatic Portal Vein"},
    ],
    "Clinical Attribute": [
        {"preferred_name": "Blood Pressure"},
        {"preferred_name": "Heart Rate"},
    ],
}

# 1-hop relationship paths for the UMLS reasoning strategy
_ONE_HOP_PATHS = [
    {
        "concept_a_name": "Aspirin",
        "concept_a_cui": "C0004057",
        "concept_b_name": "Headache",
        "concept_b_cui": "C0018681",
        "relationship_type": "TREATS",
    },
    {
        "concept_a_name": "Smoking",
        "concept_a_cui": "C0037369",
        "concept_b_name": "Lung Cancer",
        "concept_b_cui": "C0242379",
        "relationship_type": "CAUSES",
    },
    {
        "concept_a_name": "Diabetes Mellitus",
        "concept_a_cui": "C0011849",
        "concept_b_name": "Polyuria",
        "concept_b_cui": "C0032617",
        "relationship_type": "PRESENTS_WITH",
    },
    {
        "concept_a_name": "Insulin",
        "concept_a_cui": "C0021641",
        "concept_b_name": "Diabetes Mellitus",
        "concept_b_cui": "C0011849",
        "relationship_type": "TREATS",
    },
    {
        "concept_a_name": "Ibuprofen",
        "concept_a_cui": "C0020740",
        "concept_b_name": "Inflammation",
        "concept_b_cui": "C0021368",
        "relationship_type": "TREATS",
    },
]

# 2-hop relationship paths
_TWO_HOP_PATHS = [
    {
        "concept_a_name": "Aspirin",
        "concept_a_cui": "C0004057",
        "concept_b_name": "Headache",
        "concept_b_cui": "C0018681",
        "concept_c_name": "Photophobia",
        "concept_c_cui": "C0085636",
        "relationship_type_1": "TREATS",
        "relationship_type_2": "PRESENTS_WITH",
    },
    {
        "concept_a_name": "Metformin",
        "concept_a_cui": "C0025598",
        "concept_b_name": "Type 2 Diabetes",
        "concept_b_cui": "C0011860",
        "concept_c_name": "Retinopathy",
        "concept_c_cui": "C0035309",
        "relationship_type_1": "TREATS",
        "relationship_type_2": "CAUSES",
    },
]


# -- Mock service builders -------------------------------------------------

def _build_neo4j_mock() -> MagicMock:
    """Build a mock Neo4j client that returns known concept/path data."""
    mock = MagicMock()

    async def _execute_query(query: str, params: Optional[Dict] = None):
        params = params or {}

        # KG strategy: concept query
        if "EXTRACTED_FROM" in query and "chunk_ids" in query:
            limit = params.get("limit", 30)
            return _KG_CONCEPTS[:limit]

        # RAG strategy: UMLS concepts by semantic type
        if "semantic_type" in (params or {}):
            sem_type = params["semantic_type"]
            concepts = _UMLS_CONCEPTS_BY_TYPE.get(sem_type, [])
            limit = params.get("limit", 10)
            return concepts[:limit]

        # UMLS reasoning: 1-hop paths
        if "relationship_types" in (params or {}) and "concept_c_name" not in query:
            limit = params.get("limit", 20)
            return _ONE_HOP_PATHS[:limit]

        # UMLS reasoning: 2-hop paths
        if "relationship_types" in (params or {}) and "concept_c_name" in query:
            limit = params.get("limit", 20)
            return _TWO_HOP_PATHS[:limit]

        # UMLS reasoning: chunk IDs for a CUI
        if "cui" in (params or {}):
            cui = params["cui"]
            return [{"chunk_id": f"chunk-umls-{cui[-4:]}"}]

        return []

    mock.execute_query = MagicMock(side_effect=_execute_query)
    return mock


def _build_vector_mock() -> MagicMock:
    """Build a mock vector store client returning chunk content."""
    mock = MagicMock()

    async def _get_chunk_by_id(chunk_id: str):
        # Derive a concept name from the chunk ID for realistic content
        concept_label = chunk_id.replace("chunk-kg-", "").replace(
            "chunk-umls-", ""
        )
        return {
            "content": _CHUNK_CONTENT_TEMPLATE.format(
                concept=f"entity_{concept_label}"
            ),
            "metadata": {
                "content": _CHUNK_CONTENT_TEMPLATE.format(
                    concept=f"entity_{concept_label}"
                ),
                "document_title": f"Medical Reference ({concept_label})",
            },
            "document_title": f"Medical Reference ({concept_label})",
            "chunk_id": chunk_id,
        }

    mock.get_chunk_by_id = MagicMock(side_effect=_get_chunk_by_id)
    return mock


@dataclass
class _FakeCitationSource:
    document_id: str = "doc-001"
    document_title: str = "Harrison's Principles of Internal Medicine"
    page_number: Optional[int] = 42
    chunk_id: str = "chunk-rag-001"
    relevance_score: float = 0.92
    excerpt: str = (
        "This is a detailed excerpt from the medical reference text "
        "covering clinical significance, pharmacology, indications, "
        "contraindications, and monitoring parameters for the queried "
        "medical concept. The information is evidence-based."
    )


@dataclass
class _FakeRAGResponse:
    response: str = ""
    sources: List[Any] = dc_field(default_factory=list)
    confidence_score: float = 0.9
    processing_time_ms: int = 100
    tokens_used: int = 200
    search_results_count: int = 3
    fallback_used: bool = False
    metadata: Dict[str, Any] = dc_field(default_factory=dict)


def _build_rag_mock() -> MagicMock:
    """Build a mock RAG service returning cited responses."""
    mock = MagicMock()

    async def _generate_response(query: str, user_id: str = "", **kwargs):
        return _FakeRAGResponse(
            response=(
                f"Based on current medical literature, {query.lower()} "
                "The clinical evidence supports the following key points: "
                "mechanism of action involves specific molecular pathways, "
                "therapeutic indications include several clinical conditions, "
                "and monitoring parameters should be assessed regularly. "
                "Adverse effects are generally mild and dose-dependent. "
                "Drug interactions should be carefully evaluated."
            ),
            sources=[
                _FakeCitationSource(
                    document_id="doc-001",
                    document_title="Harrison's Principles",
                    chunk_id="chunk-rag-001",
                ),
                _FakeCitationSource(
                    document_id="doc-002",
                    document_title="Goodman & Gilman's Pharmacology",
                    chunk_id="chunk-rag-002",
                ),
                _FakeCitationSource(
                    document_id="doc-003",
                    document_title="UpToDate Clinical Reference",
                    chunk_id="chunk-rag-003",
                ),
            ],
        )

    mock.generate_response = MagicMock(side_effect=_generate_response)
    return mock


def _build_umls_client_mock() -> MagicMock:
    """Build a mock UMLS client."""
    mock = MagicMock()
    mock.get_concept = MagicMock(return_value=None)
    return mock


def _build_relationship_traverser_mock() -> MagicMock:
    """Build a mock RelationshipTraverser with a nested Neo4j client."""
    mock = MagicMock()
    # The UMLS strategy accesses _neo4j_client from the traverser
    mock._neo4j_client = _build_neo4j_mock()
    mock._timeout_seconds = 3.0
    return mock


def _build_ner_mock() -> MagicMock:
    """Build a mock NER extractor that always finds UMLS concepts."""
    mock = MagicMock()

    async def _extract_key_terms(text: str):
        return _FakeNERResult(
            umls_entities=["C0000001"],
            key_terms={"medical_concept"},
        )

    mock.extract_key_terms = MagicMock(side_effect=_extract_key_terms)
    return mock


# -- The integration test class --------------------------------------------


class TestEndToEndDataGeneration:
    """Small-scale end-to-end integration test for TrainingDataGenerator.

    Exercises the full pipeline — all three strategies, deduplication,
    validation, JSONL export, and summary report — against mocked
    Neo4j, Milvus, and RAG services with known data.

    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.1
    """

    @pytest.fixture()
    def generator(self) -> TrainingDataGenerator:
        """Create a TrainingDataGenerator wired to mock services."""
        return TrainingDataGenerator(
            neo4j_client=_build_neo4j_mock(),
            vector_client=_build_vector_mock(),
            rag_service=_build_rag_mock(),
            umls_client=_build_umls_client_mock(),
            relationship_traverser=_build_relationship_traverser_mock(),
            ner_extractor=_build_ner_mock(),
        )

    @pytest.fixture()
    def config(self, tmp_path: Path) -> TrainingDataConfig:
        """Small-scale generation config targeting 50 pairs."""
        return TrainingDataConfig(
            target_pair_count=50,
            strategies=["kg", "umls_reasoning"],
            random_seed=42,
            min_confidence_score=0.5,
            min_chunk_tokens=50,
            similarity_threshold=0.85,
            output_dir=str(tmp_path / "output"),
        )

    # -- Helper to run async code in sync tests ----------------------------

    @staticmethod
    def _run(coro):
        """Run an async coroutine synchronously."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # -- Tests -------------------------------------------------------------

    def test_generate_produces_result(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """generate() returns a TrainingDataResult with non-empty output."""
        result: TrainingDataResult = self._run(generator.generate(config))

        assert isinstance(result, TrainingDataResult)
        assert result.output_path != ""
        assert Path(result.output_path).exists()
        assert result.generation_time_seconds > 0

    def test_output_jsonl_structure(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Every line in the output JSONL is a valid InstructionTuningPair."""
        result = self._run(generator.generate(config))
        output_path = Path(result.output_path)

        lines = output_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) > 0, "Output JSONL should not be empty"

        for i, line in enumerate(lines, start=1):
            parsed = json.loads(line)
            # Required top-level fields (Requirement 4.4)
            assert "instruction" in parsed, f"Line {i}: missing instruction"
            assert "context" in parsed, f"Line {i}: missing context"
            assert "response" in parsed, f"Line {i}: missing response"
            assert "metadata" in parsed, f"Line {i}: missing metadata"

            meta = parsed["metadata"]
            assert meta["strategy"] in (
                "kg",
                "rag",
                "umls_reasoning",
            ), f"Line {i}: invalid strategy '{meta['strategy']}'"
            assert isinstance(
                meta["source_concepts"], list
            ), f"Line {i}: source_concepts should be a list"
            assert (
                0.0 <= meta["confidence_score"] <= 1.0
            ), f"Line {i}: confidence_score out of range"

    def test_round_trip_serialization(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """parse_jsonl(output) produces equivalent InstructionTuningPair objects."""
        result = self._run(generator.generate(config))
        output_path = Path(result.output_path)

        parsed_pairs = TrainingDataGenerator.parse_jsonl(output_path)
        assert len(parsed_pairs) > 0

        # Re-export and re-parse to verify round-trip
        round_trip_path = output_path.parent / "round_trip.jsonl"
        TrainingDataGenerator.print_jsonl(parsed_pairs, round_trip_path)
        reparsed = TrainingDataGenerator.parse_jsonl(round_trip_path)

        assert len(reparsed) == len(parsed_pairs)
        for original, reparsed_pair in zip(parsed_pairs, reparsed):
            assert original == reparsed_pair

    def test_deduplication_removes_near_duplicates(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Deduplication removes near-duplicate instruction texts (Req 4.2)."""
        result = self._run(generator.generate(config))
        output_path = Path(result.output_path)

        pairs = TrainingDataGenerator.parse_jsonl(output_path)
        instructions = [p.instruction for p in pairs]

        # No two remaining instructions should be exact duplicates
        assert len(instructions) == len(set(instructions)), (
            "Exact duplicate instructions found in output"
        )

    def test_dedup_count_in_summary(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Dataset summary includes dedup_removed count (Req 4.5)."""
        result = self._run(generator.generate(config))
        summary = result.dataset_summary

        assert isinstance(summary.dedup_removed, int)
        assert summary.dedup_removed >= 0

    def test_deterministic_shuffling(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Same seed produces identical ordering (Req 4.3)."""
        result_1 = self._run(generator.generate(config))
        result_2 = self._run(generator.generate(config))

        lines_1 = (
            Path(result_1.output_path)
            .read_text(encoding="utf-8")
            .strip()
            .split("\n")
        )
        lines_2 = (
            Path(result_2.output_path)
            .read_text(encoding="utf-8")
            .strip()
            .split("\n")
        )

        assert lines_1 == lines_2, (
            "Two runs with the same seed should produce identical output"
        )

    def test_validation_partitions_pairs(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Validation produces accepted/rejected partitions (Req 11.1–11.3)."""
        result = self._run(generator.generate(config))
        validation = result.validation_result

        assert isinstance(validation, ValidationResult)
        assert validation.total > 0
        assert len(validation.accepted) + len(validation.rejected) == validation.total
        assert 0.0 <= validation.pass_rate <= 1.0

        # All accepted pairs should have non-empty fields
        for pair in validation.accepted:
            assert pair.instruction.strip() != ""
            assert pair.context.strip() != ""
            assert pair.response.strip() != ""

    def test_summary_report_structure(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Dataset summary contains required statistics (Req 4.5)."""
        result = self._run(generator.generate(config))
        summary = result.dataset_summary

        assert isinstance(summary, DatasetSummary)
        assert summary.total_pairs > 0
        assert isinstance(summary.pairs_per_strategy, dict)
        assert len(summary.pairs_per_strategy) > 0
        assert summary.avg_response_length > 0
        assert isinstance(summary.concept_coverage, dict)
        assert isinstance(summary.confidence_distribution, dict)
        assert summary.output_path != ""

    def test_all_three_strategies_contribute(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Both default strategies produce at least one pair (Req 4.1)."""
        result = self._run(generator.generate(config))
        strategy_counts = result.dataset_summary.pairs_per_strategy

        for strategy in ("kg", "umls_reasoning"):
            assert strategy in strategy_counts, (
                f"Strategy '{strategy}' missing from summary"
            )
            assert strategy_counts[strategy] > 0, (
                f"Strategy '{strategy}' produced 0 pairs"
            )

    def test_rejected_pairs_file_created(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Rejected pairs are written to a separate file when present."""
        # Use a NER mock that rejects some pairs (no UMLS concepts)
        reject_count = 0

        async def _sometimes_reject(text: str):
            nonlocal reject_count
            reject_count += 1
            # Reject every 5th pair
            if reject_count % 5 == 0:
                return _FakeNERResult(
                    umls_entities=[],
                    key_terms=set(),
                )
            return _FakeNERResult(
                umls_entities=["C0000001"],
                key_terms={"concept"},
            )

        generator._ner.extract_key_terms = MagicMock(
            side_effect=_sometimes_reject
        )

        result = self._run(generator.generate(config))
        output_dir = Path(config.output_dir)

        if result.validation_result.rejected:
            rejected_path = output_dir / "rejected_pairs.jsonl"
            assert rejected_path.exists(), (
                "rejected_pairs.jsonl should exist when pairs are rejected"
            )
            rejected_lines = (
                rejected_path.read_text(encoding="utf-8").strip().split("\n")
            )
            assert len(rejected_lines) == len(
                result.validation_result.rejected
            )

    def test_confidence_distribution_in_summary(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Confidence distribution buckets sum to total_pairs."""
        result = self._run(generator.generate(config))
        summary = result.dataset_summary

        bucket_total = sum(summary.confidence_distribution.values())
        assert bucket_total == summary.total_pairs, (
            f"Confidence buckets sum ({bucket_total}) != "
            f"total_pairs ({summary.total_pairs})"
        )

    def test_concept_coverage_in_summary(
        self, generator: TrainingDataGenerator, config: TrainingDataConfig
    ):
        """Concept coverage includes total and per-strategy counts."""
        result = self._run(generator.generate(config))
        coverage = result.dataset_summary.concept_coverage

        assert "total_unique_concepts" in coverage
        assert coverage["total_unique_concepts"] > 0

        # At least one per-strategy concept count should exist
        strategy_keys = [
            k for k in coverage if k.endswith("_concepts")
        ]
        assert len(strategy_keys) > 0
        assert len(strategy_keys) > 0
