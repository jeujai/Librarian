"""
Integration tests for the data generation resume flow.

Tests the end-to-end resume lifecycle:
  1. Upload partial data → trigger resumed generation with resume_data
     → verify status includes completed_strategies
  2. Download-partial endpoint returns correct files after a job
     produces partial data

Requirements: 1.1, 2.1, 3.1, 5.4, 6.3
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from multimodal_librarian.api.routers.ml_training import router
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


def _make_pair(
    instruction: str,
    strategy: str = "kg",
    confidence: float = 0.9,
) -> InstructionTuningPair:
    """Create a valid InstructionTuningPair for testing."""
    return InstructionTuningPair(
        instruction=instruction,
        context=f"Context for: {instruction}",
        response=f"Response for: {instruction}",
        metadata=PairMetadata(
            strategy=strategy,
            source_concepts=["C0000001"],
            confidence_score=confidence,
        ),
    )


def _pairs_to_jsonl(pairs: list[InstructionTuningPair]) -> str:
    """Serialize a list of pairs to JSONL text."""
    return "\n".join(p.to_jsonl_line() for p in pairs)


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
# Test 1: Upload partial data → resumed generation → status includes
#          completed_strategies
# Requirements: 3.1, 5.4, 6.3
# ---------------------------------------------------------------------------


class TestUploadResumeStatusFlow:
    """End-to-end: upload partial → generate with resume_data → poll status."""

    def test_upload_then_resume_generation_with_completed_strategies(
        self, client: TestClient, tmp_path: Path
    ):
        """Upload partial KG data, trigger a resumed generation, then
        verify that the status endpoint includes completed_strategies.

        This exercises the full resume lifecycle at the API layer:
        1. POST /upload-partial/{job_id} — upload partial KG JSONL
        2. POST /generate — include resume_data manifest
        3. GET /status/{job_id} — verify completed_strategies in response
        """
        # -- Arrange: build partial KG data --
        kg_pairs = [
            _make_pair(f"KG question {i}", strategy="kg")
            for i in range(5)
        ]
        jsonl_content = _pairs_to_jsonl(kg_pairs)

        # Use tmp_path as the upload directory so we don't touch /app
        upload_dir = tmp_path / "ml_training"
        upload_dir.mkdir(parents=True)

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            # -- Step 1: Upload partial KG data --
            upload_response = client.post(
                "/api/v1/ml/training-data/upload-partial/resume-job-1",
                data={"strategy": "kg"},
                files={"file": ("partial_kg.jsonl", jsonl_content, "application/x-ndjson")},
            )

        assert upload_response.status_code == 200
        upload_body = upload_response.json()
        assert upload_body["strategy"] == "kg"
        assert upload_body["pair_count"] == 5

        # Verify the file was actually written
        uploaded_file = upload_dir / "resume-job-1" / "partial_kg.jsonl"
        assert uploaded_file.is_file()
        assert uploaded_file.read_text(encoding="utf-8").strip() == jsonl_content.strip()

        # -- Step 2: Trigger resumed generation with resume_data --
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            gen_response = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 1000,
                    "strategies": ["kg", "umls_reasoning"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 5, "complete": True},
                        }
                    },
                },
            )

        assert gen_response.status_code == 202
        job_id = gen_response.json()["job_id"]

        # Verify resume_data was passed to the Celery task
        call_args = mock_celery_task.apply_async.call_args
        config_dict = call_args[1].get("args") or call_args[0][0]
        # args is [job_id, config_dict]
        actual_config = config_dict[1]
        assert "resume_data" in actual_config
        assert actual_config["resume_data"]["strategies"]["kg"]["pair_count"] == 5
        assert actual_config["resume_data"]["strategies"]["kg"]["complete"] is True

        # -- Step 3: Simulate PROGRESS state with completed_strategies --
        progress_info = {
            "phase": "umls_generation",
            "percentage": 60.0,
            "pairs_per_strategy": {"kg": 5, "umls_reasoning": 300},
            "eta_seconds": 45.0,
            "completed_strategies": {"kg": 5},
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
                status_response = client.get(
                    f"/api/v1/ml/training-data/status/{job_id}"
                )

        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] == "progress"
        assert status_body["completed_strategies"] == {"kg": 5}
        assert status_body["phase"] == "umls_generation"

    def test_failed_job_status_includes_completed_strategies(
        self, client: TestClient
    ):
        """When a job fails, the status endpoint should include
        completed_strategies from the Redis-persisted progress snapshot.

        Requirements: 6.3
        """
        persisted_progress = {
            "phase": "rag_generation",
            "percentage": 45.0,
            "pairs_per_strategy": {"kg": 2500, "rag": 312},
            "completed_strategies": {"kg": 2500},
        }

        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=persisted_progress,
        ):
            mock_result = _mock_async_result(
                status="FAILURE",
                result=RuntimeError("RAG strategy timeout"),
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                response = client.get(
                    "/api/v1/ml/training-data/status/failed-job-1"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["completed_strategies"] == {"kg": 2500}
        assert "RAG strategy timeout" in body["error"]

    def test_pending_with_redis_includes_completed_strategies(
        self, client: TestClient
    ):
        """PENDING + Redis progress (hard timeout) should include
        completed_strategies.

        Requirements: 6.3
        """
        persisted = {
            "phase": "umls_generation",
            "percentage": 65.0,
            "pairs_per_strategy": {"kg": 2500, "rag": 2000},
            "completed_strategies": {"kg": 2500, "rag": 2000},
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
                    "/api/v1/ml/training-data/status/lost-job-1"
                )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "progress"
        assert body["completed_strategies"] == {"kg": 2500, "rag": 2000}

    def test_upload_multiple_strategies_then_resume(
        self, client: TestClient, tmp_path: Path
    ):
        """Upload partial data for multiple strategies, then trigger
        a resumed generation with a full resume manifest.

        Requirements: 3.1, 5.4
        """
        upload_dir = tmp_path / "ml_training"
        upload_dir.mkdir(parents=True)

        kg_pairs = [_make_pair(f"KG q{i}", strategy="kg") for i in range(3)]
        rag_pairs = [_make_pair(f"RAG q{i}", strategy="rag") for i in range(2)]

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            # Upload KG partial
            resp_kg = client.post(
                "/api/v1/ml/training-data/upload-partial/multi-job-1",
                data={"strategy": "kg"},
                files={"file": ("partial_kg.jsonl", _pairs_to_jsonl(kg_pairs), "application/x-ndjson")},
            )
            assert resp_kg.status_code == 200
            assert resp_kg.json()["pair_count"] == 3

            # Upload RAG partial
            resp_rag = client.post(
                "/api/v1/ml/training-data/upload-partial/multi-job-1",
                data={"strategy": "rag"},
                files={"file": ("partial_rag.jsonl", _pairs_to_jsonl(rag_pairs), "application/x-ndjson")},
            )
            assert resp_rag.status_code == 200
            assert resp_rag.json()["pair_count"] == 2

        # Trigger resumed generation with both strategies in manifest
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            gen_response = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 500,
                    "strategies": ["kg", "rag", "umls_reasoning"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 3, "complete": True},
                            "rag": {"pair_count": 2, "complete": False},
                        }
                    },
                },
            )

        assert gen_response.status_code == 202

        # Verify resume_data was forwarded correctly
        call_args = mock_celery_task.apply_async.call_args
        config_dict = (call_args[1].get("args") or call_args[0][0])[1]
        resume = config_dict["resume_data"]
        assert resume["strategies"]["kg"]["pair_count"] == 3
        assert resume["strategies"]["kg"]["complete"] is True
        assert resume["strategies"]["rag"]["pair_count"] == 2
        assert resume["strategies"]["rag"]["complete"] is False

    def test_upload_partial_invalid_strategy_returns_422(
        self, client: TestClient, tmp_path: Path
    ):
        """POST /upload-partial with an invalid strategy returns 422.

        Requirements: 3.2
        """
        upload_dir = tmp_path / "ml_training"
        upload_dir.mkdir(parents=True)

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            response = client.post(
                "/api/v1/ml/training-data/upload-partial/job-1",
                data={"strategy": "invalid_strategy"},
                files={"file": ("partial.jsonl", "data", "application/x-ndjson")},
            )

        assert response.status_code == 422
        assert "invalid_strategy" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test 2: Download-partial endpoint returns correct files after a job
#          produces partial data
# Requirements: 1.1, 2.1
# ---------------------------------------------------------------------------


class TestDownloadPartialAfterGeneration:
    """Verify the download-partial endpoint serves correct partial files."""

    def test_download_partial_listing_shows_available_files(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id} without strategy param returns
        a JSON listing of available partial files with pair counts.

        Requirements: 2.1, 2.2
        """
        # Simulate partial files on disk (as if the generator wrote them)
        job_dir = tmp_path / "partial-job-1"
        job_dir.mkdir(parents=True)

        kg_pairs = [_make_pair(f"KG pair {i}", strategy="kg") for i in range(10)]
        rag_pairs = [_make_pair(f"RAG pair {i}", strategy="rag") for i in range(7)]

        (job_dir / "partial_kg.jsonl").write_text(
            _pairs_to_jsonl(kg_pairs), encoding="utf-8"
        )
        (job_dir / "partial_rag.jsonl").write_text(
            _pairs_to_jsonl(rag_pairs), encoding="utf-8"
        )

        # Point _PARTIAL_UPLOAD_DIR to tmp_path so job_dir is found
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/partial-job-1"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "partial-job-1"
        assert "kg" in body["partial_files"]
        assert "rag" in body["partial_files"]
        assert "umls_reasoning" not in body["partial_files"]
        assert body["partial_files"]["kg"]["pair_count"] == 10
        assert body["partial_files"]["kg"]["file"] == "partial_kg.jsonl"
        assert body["partial_files"]["rag"]["pair_count"] == 7
        assert body["partial_files"]["rag"]["file"] == "partial_rag.jsonl"

    def test_download_partial_specific_strategy_streams_file(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id}?strategy=kg streams the JSONL file.

        Requirements: 2.3
        """
        job_dir = tmp_path / "stream-job-1"
        job_dir.mkdir(parents=True)

        kg_pairs = [_make_pair(f"KG stream pair {i}", strategy="kg") for i in range(3)]
        jsonl_content = _pairs_to_jsonl(kg_pairs)
        (job_dir / "partial_kg.jsonl").write_text(
            jsonl_content, encoding="utf-8"
        )

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/stream-job-1",
                params={"strategy": "kg"},
            )

        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers["content-type"]

        # Verify the content is valid JSONL with the expected pairs
        lines = response.text.strip().split("\n")
        assert len(lines) == 3
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed["instruction"] == f"KG stream pair {i}"
            assert parsed["metadata"]["strategy"] == "kg"

    def test_download_partial_no_data_returns_404(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id} returns 404 when no partial data
        exists for the job.

        Requirements: 2.4
        """
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/nonexistent-job"
            )

        assert response.status_code == 404
        assert "nonexistent-job" in response.json()["detail"]

    def test_download_partial_invalid_strategy_returns_422(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id}?strategy=bad returns 422.

        Requirements: 2.4
        """
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/any-job",
                params={"strategy": "bad_strategy"},
            )

        assert response.status_code == 422
        assert "bad_strategy" in response.json()["detail"]

    def test_download_partial_strategy_not_found_returns_404(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id}?strategy=rag returns 404 when
        only KG partial data exists.

        Requirements: 2.3, 2.4
        """
        job_dir = tmp_path / "partial-only-kg"
        job_dir.mkdir(parents=True)

        kg_pairs = [_make_pair("KG only", strategy="kg")]
        (job_dir / "partial_kg.jsonl").write_text(
            _pairs_to_jsonl(kg_pairs), encoding="utf-8"
        )

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/partial-only-kg",
                params={"strategy": "rag"},
            )

        assert response.status_code == 404
        assert "rag" in response.json()["detail"]

    def test_download_partial_empty_dir_returns_404(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id} returns 404 when the job
        directory exists but contains no partial files.

        Requirements: 2.4
        """
        job_dir = tmp_path / "empty-job"
        job_dir.mkdir(parents=True)
        # Directory exists but has no partial_*.jsonl files

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/empty-job"
            )

        assert response.status_code == 404

    def test_download_partial_all_three_strategies(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /download-partial/{job_id} lists all three strategies
        when all partial files exist.

        Requirements: 2.1, 2.2
        """
        job_dir = tmp_path / "full-partial-job"
        job_dir.mkdir(parents=True)

        for strategy, filename, count in [
            ("kg", "partial_kg.jsonl", 100),
            ("rag", "partial_rag.jsonl", 50),
            ("umls_reasoning", "partial_umls.jsonl", 75),
        ]:
            pairs = [
                _make_pair(f"{strategy} pair {i}", strategy=strategy)
                for i in range(count)
            ]
            (job_dir / filename).write_text(
                _pairs_to_jsonl(pairs), encoding="utf-8"
            )

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            tmp_path,
        ):
            response = client.get(
                "/api/v1/ml/training-data/download-partial/full-partial-job"
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body["partial_files"]) == 3
        assert body["partial_files"]["kg"]["pair_count"] == 100
        assert body["partial_files"]["rag"]["pair_count"] == 50
        assert body["partial_files"]["umls_reasoning"]["pair_count"] == 75


# ---------------------------------------------------------------------------
# Test: Full resume round-trip
# Upload → generate → fail → download-partial → re-upload → resume
# Requirements: 1.1, 2.1, 3.1, 5.4, 6.3
# ---------------------------------------------------------------------------


class TestFullResumeRoundTrip:
    """End-to-end resume round-trip through the API layer."""

    def test_generate_fail_download_partial_resume(
        self, client: TestClient, tmp_path: Path
    ):
        """Simulate the full resume lifecycle:
        1. Start a generation job
        2. Job fails mid-RAG — status shows completed_strategies
        3. Download partial KG data
        4. Upload partial KG data for a new job
        5. Trigger resumed generation with resume_data
        6. Verify the resumed job's status includes completed_strategies
        """
        upload_dir = tmp_path / "ml_training"
        upload_dir.mkdir(parents=True)

        # -- Step 1: Start initial generation --
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            gen_resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 3000,
                    "strategies": ["kg", "rag"],
                },
            )

        assert gen_resp.status_code == 202
        original_job_id = gen_resp.json()["job_id"]

        # -- Step 2: Job fails — status shows completed_strategies --
        persisted = {
            "phase": "rag_generation",
            "percentage": 40.0,
            "pairs_per_strategy": {"kg": 1500, "rag": 200},
            "completed_strategies": {"kg": 1500},
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
                result=RuntimeError("Worker OOM during RAG"),
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                fail_resp = client.get(
                    f"/api/v1/ml/training-data/status/{original_job_id}"
                )

        assert fail_resp.status_code == 200
        fail_body = fail_resp.json()
        assert fail_body["status"] == "failed"
        assert fail_body["completed_strategies"] == {"kg": 1500}

        # -- Step 3: Download partial KG data --
        # Simulate that the server has partial_kg.jsonl on disk
        original_job_dir = upload_dir / original_job_id
        original_job_dir.mkdir(parents=True)

        kg_pairs = [
            _make_pair(f"KG pair {i}", strategy="kg")
            for i in range(1500)
        ]
        (original_job_dir / "partial_kg.jsonl").write_text(
            _pairs_to_jsonl(kg_pairs), encoding="utf-8"
        )

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            listing_resp = client.get(
                f"/api/v1/ml/training-data/download-partial/{original_job_id}"
            )

        assert listing_resp.status_code == 200
        assert listing_resp.json()["partial_files"]["kg"]["pair_count"] == 1500

        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            download_resp = client.get(
                f"/api/v1/ml/training-data/download-partial/{original_job_id}",
                params={"strategy": "kg"},
            )

        assert download_resp.status_code == 200
        downloaded_lines = download_resp.text.strip().split("\n")
        assert len(downloaded_lines) == 1500

        # -- Step 4: Upload partial KG data for a new resumed job --
        with patch(
            "multimodal_librarian.api.routers.ml_training._PARTIAL_UPLOAD_DIR",
            upload_dir,
        ):
            upload_resp = client.post(
                "/api/v1/ml/training-data/upload-partial/resumed-job-1",
                data={"strategy": "kg"},
                files={
                    "file": (
                        "partial_kg.jsonl",
                        download_resp.text,
                        "application/x-ndjson",
                    )
                },
            )

        assert upload_resp.status_code == 200
        assert upload_resp.json()["pair_count"] == 1500

        # -- Step 5: Trigger resumed generation --
        with patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".generate_training_data_task"
        ) as mock_celery_task:
            mock_celery_task.apply_async = MagicMock()

            resume_resp = client.post(
                "/api/v1/ml/training-data/generate",
                json={
                    "target_pair_count": 3000,
                    "strategies": ["kg", "rag"],
                    "resume_data": {
                        "strategies": {
                            "kg": {"pair_count": 1500, "complete": True},
                        }
                    },
                },
            )

        assert resume_resp.status_code == 202
        resumed_job_id = resume_resp.json()["job_id"]

        # Verify resume_data was forwarded
        call_args = mock_celery_task.apply_async.call_args
        config_dict = (call_args[1].get("args") or call_args[0][0])[1]
        assert config_dict["resume_data"]["strategies"]["kg"]["pair_count"] == 1500

        # -- Step 6: Resumed job in progress — completed_strategies --
        resumed_progress = {
            "phase": "rag_generation",
            "percentage": 30.0,
            "pairs_per_strategy": {"kg": 1500, "rag": 450},
            "eta_seconds": 120.0,
            "completed_strategies": {"kg": 1500},
        }
        with patch(
            "multimodal_librarian.services.celery_service.celery_app"
        ), patch(
            "multimodal_librarian.services.ml_training_tasks"
            ".get_persisted_progress",
            return_value=None,
        ):
            mock_result = _mock_async_result(
                status="PROGRESS", info=resumed_progress
            )
            with patch(
                "multimodal_librarian.api.routers.ml_training.AsyncResult",
                return_value=mock_result,
            ):
                resumed_status = client.get(
                    f"/api/v1/ml/training-data/status/{resumed_job_id}"
                )

        assert resumed_status.status_code == 200
        resumed_body = resumed_status.json()
        assert resumed_body["status"] == "progress"
        assert resumed_body["completed_strategies"] == {"kg": 1500}
        assert resumed_body["pairs_per_strategy"]["kg"] == 1500
