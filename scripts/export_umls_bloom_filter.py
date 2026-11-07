#!/usr/bin/env python3
"""Export a Bloom filter over the UMLS vocabulary for n-gram pre-filtering.

Builds a serialized Bloom filter containing every ``UMLSConcept.lower_name``
and ``UMLSSynonym.name`` (the exact strings ``batch_search_by_names`` queries
against).  The UMLS client loads this file and rejects the ~97% of generated
n-grams that are not UMLS terms without a Neo4j round-trip.

The filter must be re-exported whenever the UMLS data in Neo4j is reloaded or
upgraded; version it alongside ``UMLSMetadata.loaded_tier``.

Run on the host, where Neo4j's bolt port (7687) is published:

    venv/bin/python scripts/export_umls_bloom_filter.py \
        --output data/umls_bloom_filter.bin
"""

import argparse
import sys

from neo4j import GraphDatabase

from multimodal_librarian.components.knowledge_graph.bloom_filter import (
    BloomFilter,
)

DEFAULT_URI = "bolt://localhost:7687"
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "password"

_CONCEPT_COUNT = "MATCH (c:UMLSConcept) RETURN count(c) AS n"
_SYNONYM_COUNT = "MATCH (s:UMLSSynonym) RETURN count(s) AS n"
_CONCEPT_NAMES = "MATCH (c:UMLSConcept) RETURN c.lower_name AS name"
_SYNONYM_NAMES = "MATCH (s:UMLSSynonym) RETURN s.name AS name"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASSWORD)
    ap.add_argument("--fp-rate", type=float, default=0.001,
                    help="target false-positive rate")
    ap.add_argument("--output", default="data/umls_bloom_filter.bin")
    args = ap.parse_args()

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    def count(query: str) -> int:
        with driver.session() as session:
            return session.run(query).single()["n"]

    concept_count = count(_CONCEPT_COUNT)
    synonym_count = count(_SYNONYM_COUNT)
    # Upper bound on distinct names (some synonyms repeat the preferred name);
    # sizing for the sum yields a false-positive rate below the target.
    capacity = concept_count + synonym_count
    print(f"concepts={concept_count} synonyms={synonym_count} "
          f"capacity={capacity}", file=sys.stderr)

    bf = BloomFilter.for_capacity(capacity, args.fp_rate)
    print(f"filter: m={bf.m} bits ({bf.size_bytes} bytes) k={bf.k}",
          file=sys.stderr)

    inserted = 0
    with driver.session() as session:
        for query in (_CONCEPT_NAMES, _SYNONYM_NAMES):
            for record in session.run(query):
                name = record["name"]
                if name:
                    bf.add(name)
                    inserted += 1
                    if inserted % 500_000 == 0:
                        print(f"  inserted {inserted:,} names", file=sys.stderr)

    bf.save(args.output)
    print(f"wrote {args.output}: n={bf.n:,} m={bf.m} k={bf.k} "
          f"size={bf.size_bytes:,} bytes "
          f"est_fp_rate={bf.estimate_fp_rate():.4f}",
          file=sys.stderr)
    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
