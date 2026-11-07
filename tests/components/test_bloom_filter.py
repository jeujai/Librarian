"""Tests for the dependency-free Bloom filter used for UMLS pre-filtering."""

import pytest

from multimodal_librarian.components.knowledge_graph.bloom_filter import (
    BloomFilter,
)


def test_no_false_negatives():
    bf = BloomFilter.for_capacity(10_000, 0.001)
    items = [f"term-{i}" for i in range(5_000)]
    for item in items:
        bf.add(item)
    assert all(item in bf for item in items)


def test_false_positive_rate_within_tolerance():
    bf = BloomFilter.for_capacity(100_000, 0.01)
    items = [f"term-{i}" for i in range(100_000)]
    for item in items:
        bf.add(item)

    unseen = [f"other-{i}" for i in range(50_000)]
    fps = sum(1 for item in unseen if item in bf)
    measured = fps / len(unseen)
    # Measured FP rate should be within an order of magnitude of the target.
    assert measured < 0.05


def test_save_load_round_trip(tmp_path):
    bf = BloomFilter.for_capacity(10_000, 0.01)
    items = [f"term-{i}" for i in range(2_000)]
    for item in items:
        bf.add(item)

    path = tmp_path / "filter.bin"
    bf.save(str(path))
    loaded = BloomFilter.load(str(path))

    assert loaded.m == bf.m
    assert loaded.k == bf.k
    assert loaded.n == bf.n
    assert all(item in loaded for item in items)


def test_load_rejects_bad_magic(tmp_path):
    path = tmp_path / "junk.bin"
    path.write_bytes(b"not-a-bloom-filter")
    with pytest.raises(ValueError):
        BloomFilter.load(str(path))


def test_for_capacity_sizes_reasonably():
    bf = BloomFilter.for_capacity(4_000_000, 0.001)
    # ~7MB for 4M names at 0.1% FP, and ~10 hashes (optimal k).
    assert bf.size_bytes < 16 * 1024 * 1024
    assert 5 <= bf.k <= 15
