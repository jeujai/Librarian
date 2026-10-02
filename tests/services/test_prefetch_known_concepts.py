"""Unit tests for _prefetch_known_concept_names.

Verifies the vetted-concept vocabulary handed to the sync chunker includes
both canonical names and their ``surface_forms`` (the literal-paraphrase
bridge), and degrades to an empty set on failure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.multimodal_librarian.services.celery_service import (
    _prefetch_known_concept_names,
)


def _settings_mock():
    settings = MagicMock()
    settings.neo4j_uri = None
    settings.neo4j_user = None
    settings.neo4j_password = None
    return settings


@pytest.mark.asyncio
async def test_prefetch_includes_surface_forms():
    """Canonical names and surface forms both land in the returned set."""
    rows = [
        {"term": "Knowledge Graph"},
        {"term": "management of HCP"},
        {"term": "category III"},
        {"term": "singleword"},
    ]
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.execute_query = AsyncMock(return_value=rows)

    with patch(
        "src.multimodal_librarian.clients.neo4j_client.Neo4jClient",
        return_value=mock_client,
    ), patch(
        "src.multimodal_librarian.config.get_settings",
        return_value=_settings_mock(),
    ):
        result = await _prefetch_known_concept_names()

    assert "knowledge graph" in result
    assert "management of hcp" in result  # surface form, lowercased
    assert "category iii" in result       # surface form
    assert "singleword" not in result     # single-word terms are filtered


@pytest.mark.asyncio
async def test_prefetch_degrades_to_empty_on_failure():
    """A connection failure yields an empty set, not an exception."""
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(side_effect=RuntimeError("boom"))
    mock_client.close = AsyncMock()

    with patch(
        "src.multimodal_librarian.clients.neo4j_client.Neo4jClient",
        return_value=mock_client,
    ), patch(
        "src.multimodal_librarian.config.get_settings",
        return_value=_settings_mock(),
    ):
        result = await _prefetch_known_concept_names()

    assert result == set()
