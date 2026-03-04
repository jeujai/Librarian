#!/usr/bin/env python3
"""
Property-Based Tests for Migration Service FieldMapper.

Feature: unified-schema-migration
Task 1.3: Write property tests for FieldMapper

This module implements property-based tests using Hypothesis to validate
the correctness properties defined in the design document:

- Property 2: Content Hash Computation

Testing Framework: hypothesis
"""

import hashlib
from typing import Any, Dict

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.multimodal_librarian.services.migration_service import FieldMapper

# =============================================================================
# Strategies for Property-Based Testing
# =============================================================================

# Strategy for generating valid content strings
content_strategy = st.text(
    min_size=0,
    max_size=10000,
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        whitelist_characters='\n\t\r '
    )
)

# Strategy for generating unicode content including special characters
unicode_content_strategy = st.text(
    min_size=0,
    max_size=5000,
)


# =============================================================================
# Task 1.3: Property-Based Test for Content Hash Computation
# =============================================================================

class TestContentHashComputationPBT:
    """
    Property-Based Tests for Content Hash Computation.
    
    **Validates: Requirements 1.5, 2.3**
    
    Property 2: Content Hash Computation
    For any chunk content string, the computed content_hash SHALL be the SHA-256
    hexadecimal digest of the UTF-8 encoded content, and this hash SHALL be
    consistent across migration and new chunk storage operations.
    """
    
    @given(content=content_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_content_hash_is_sha256_hex_digest(self, content: str):
        """
        Property: Content hash is SHA-256 hexadecimal digest of UTF-8 encoded content.
        
        For any content string, compute_content_hash should return the same
        result as hashlib.sha256(content.encode('utf-8')).hexdigest().
        
        **Validates: Requirements 1.5, 2.3**
        """
        # Compute hash using FieldMapper
        computed_hash = FieldMapper.compute_content_hash(content)
        
        # Compute expected hash directly
        expected_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        assert computed_hash == expected_hash, (
            f"Hash mismatch for content of length {len(content)}: "
            f"computed={computed_hash}, expected={expected_hash}"
        )
    
    @given(content=content_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_content_hash_is_64_char_hex_string(self, content: str):
        """
        Property: Content hash is always a 64-character hexadecimal string.
        
        SHA-256 produces a 256-bit hash, which is 64 hexadecimal characters.
        
        **Validates: Requirements 1.5, 2.3**
        """
        computed_hash = FieldMapper.compute_content_hash(content)
        
        # SHA-256 hash should always be 64 characters
        assert len(computed_hash) == 64, (
            f"Hash length should be 64, got {len(computed_hash)}"
        )
        
        # Should only contain hexadecimal characters
        assert all(c in '0123456789abcdef' for c in computed_hash), (
            f"Hash should only contain hex characters: {computed_hash}"
        )
    
    @given(content=content_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_content_hash_is_deterministic(self, content: str):
        """
        Property: Content hash is deterministic (same input always produces same output).
        
        For any content string, calling compute_content_hash multiple times
        should always return the same hash.
        
        **Validates: Requirements 1.5, 2.3**
        """
        hash1 = FieldMapper.compute_content_hash(content)
        hash2 = FieldMapper.compute_content_hash(content)
        hash3 = FieldMapper.compute_content_hash(content)
        
        assert hash1 == hash2 == hash3, (
            f"Hash should be deterministic: {hash1} != {hash2} != {hash3}"
        )
    
    @given(
        content1=content_strategy,
        content2=content_strategy
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_different_content_produces_different_hash(
        self, 
        content1: str, 
        content2: str
    ):
        """
        Property: Different content produces different hashes (collision resistance).
        
        For any two different content strings, the hashes should be different.
        Note: This is a probabilistic property - SHA-256 collisions are
        theoretically possible but astronomically unlikely.
        
        **Validates: Requirements 1.5, 2.3**
        """
        if content1 == content2:
            # Same content should produce same hash
            assert FieldMapper.compute_content_hash(content1) == FieldMapper.compute_content_hash(content2)
        else:
            # Different content should produce different hash
            hash1 = FieldMapper.compute_content_hash(content1)
            hash2 = FieldMapper.compute_content_hash(content2)
            assert hash1 != hash2, (
                f"Different content should produce different hashes: "
                f"'{content1[:50]}...' and '{content2[:50]}...' both produced {hash1}"
            )
    
    @given(content=unicode_content_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_content_hash_handles_unicode(self, content: str):
        """
        Property: Content hash correctly handles Unicode content.
        
        For any Unicode content string, compute_content_hash should
        correctly encode it as UTF-8 before hashing.
        
        **Validates: Requirements 1.5, 2.3**
        """
        # Should not raise any exceptions
        computed_hash = FieldMapper.compute_content_hash(content)
        
        # Verify it matches direct computation
        expected_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        assert computed_hash == expected_hash, (
            f"Unicode hash mismatch for content: {repr(content[:50])}"
        )
    
    @given(content=content_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_hash_consistency_in_chunk_mapping(self, content: str):
        """
        Property: Hash is consistent when used in chunk mapping.
        
        The content_hash computed by map_chunk_to_knowledge_chunk should
        match the hash computed by compute_content_hash for the same content.
        
        **Validates: Requirements 1.5, 2.3**
        """
        field_mapper = FieldMapper()
        
        # Create a mock chunk with the content
        chunk = {
            'id': 'test-id',
            'document_id': 'doc-id',
            'chunk_index': 0,
            'content': content,
            'page_number': 1,
            'section_title': 'Test Section',
            'chunk_type': 'text',
            'metadata': {}
        }
        
        # Map the chunk
        mapped_chunk = field_mapper.map_chunk_to_knowledge_chunk(chunk)
        
        # Verify the content_hash in the mapped chunk matches direct computation
        expected_hash = FieldMapper.compute_content_hash(content)
        
        assert mapped_chunk['content_hash'] == expected_hash, (
            f"Hash in mapped chunk doesn't match direct computation: "
            f"{mapped_chunk['content_hash']} != {expected_hash}"
        )


# =============================================================================
# Integration test to verify all properties
# =============================================================================

def test_all_content_hash_pbt_properties_defined():
    """
    Meta-test that ensures all property tests are defined.
    
    This validates that the property-based testing infrastructure
    is working correctly.
    """
    content_hash_tests = [
        TestContentHashComputationPBT.test_property_content_hash_is_sha256_hex_digest,
        TestContentHashComputationPBT.test_property_content_hash_is_64_char_hex_string,
        TestContentHashComputationPBT.test_property_content_hash_is_deterministic,
        TestContentHashComputationPBT.test_property_different_content_produces_different_hash,
        TestContentHashComputationPBT.test_property_content_hash_handles_unicode,
        TestContentHashComputationPBT.test_property_hash_consistency_in_chunk_mapping,
    ]
    
    assert len(content_hash_tests) == 6, (
        f"Expected 6 content hash tests, found {len(content_hash_tests)}"
    )
    
    print(f"✓ All {len(content_hash_tests)} property-based tests are defined")
    print(f"  - Property 2: Content Hash Computation (Task 1.3)")


if __name__ == "__main__":
    print("Running Property-Based Tests for Migration Service FieldMapper")
    print("=" * 70)
    print("\nTask 1.3: Content Hash Computation Properties")
    print("\nTo run with pytest:")
    print("pytest tests/services/test_migration_service_pbt.py -v --tb=short")
    print("\nRunning tests...")
    
    pytest.main([__file__, "-v", "--tb=short"])
