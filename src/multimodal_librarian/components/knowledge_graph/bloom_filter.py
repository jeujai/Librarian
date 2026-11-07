"""Dependency-free Bloom filter for UMLS name pre-filtering.

A Bloom filter is a probabilistic set-membership structure: it answers
"definitely not present" with certainty (no false negatives) and "maybe
present" with a tunable false-positive rate.  The UMLS client uses it to
reject the ~97% of generated n-grams that are not UMLS terms before paying
a Neo4j round-trip.

Pure Python (hashlib + bytearray) to avoid adding a dependency — the
project deliberately avoids cachetools and similar packages.  Uses
Kirsch-Mitzenmacher double hashing so only two SHA-256 digests per element
are needed for any k.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

_MAGIC = b"UBF1"
_HEADER = struct.Struct(">4sQQI")  # magic, m(bits), n(inserted), k(hashes)


class BloomFilter:
    """A fixed-size Bloom filter over string members."""

    def __init__(self, m: int, k: int) -> None:
        if m <= 0 or k <= 0:
            raise ValueError("m (bits) and k (hashes) must be positive")
        self.m = m
        self.k = k
        self.n = 0
        self._bits = bytearray((m + 7) // 8)

    @classmethod
    def for_capacity(cls, n: int, fp_rate: float) -> "BloomFilter":
        """Size a filter for ~n elements at a target false-positive rate."""
        n = max(1, n)
        m = int(math.ceil(-n * math.log(fp_rate) / (math.log(2) ** 2)))
        k = int(round((m / n) * math.log(2)))
        return cls(max(1, m), max(1, k))

    def _positions(self, item: str) -> Iterable[int]:
        digest = hashlib.sha256(item.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[:8], "big")
        # Force odd so double hashing never degenerates modulo any m.
        h2 = int.from_bytes(digest[8:16], "big") | 1
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, item: str) -> None:
        for pos in self._positions(item):
            self._bits[pos >> 3] |= 1 << (pos & 7)
        self.n += 1

    def __contains__(self, item: str) -> bool:
        for pos in self._positions(item):
            if not (self._bits[pos >> 3] & (1 << (pos & 7))):
                return False
        return True

    def estimate_fp_rate(self) -> float:
        """Estimated false-positive rate given the elements inserted so far."""
        return (1.0 - math.exp(-self.k * self.n / self.m)) ** self.k

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(_HEADER.pack(_MAGIC, self.m, self.n, self.k))
            f.write(bytes(self._bits))

    @classmethod
    def load(cls, path: str) -> "BloomFilter":
        with open(path, "rb") as f:
            header = f.read(_HEADER.size)
            if len(header) < _HEADER.size:
                raise ValueError("truncated bloom filter file")
            magic, m, n, k = _HEADER.unpack(header)
            if magic != _MAGIC:
                raise ValueError("not a bloom filter file (bad magic)")
            bits = f.read()
        expected = (m + 7) // 8
        if len(bits) != expected:
            raise ValueError(
                f"bit length mismatch: expected {expected}, got {len(bits)}"
            )
        bf = cls(m, k)
        bf.n = n
        bf._bits = bytearray(bits)
        return bf

    def __len__(self) -> int:
        return self.n

    @property
    def size_bytes(self) -> int:
        return len(self._bits)
