#!/usr/bin/env python3
"""
Seed DomainAbbreviation nodes in Neo4j for query-time term expansion.

DomainAbbreviation nodes provide bidirectional abbreviation↔expansion
lookups for domain-specific ACRONYMS that UMLS doesn't cover (e.g. "HCP"
is not a UMLS synonym for "Health Personnel").

Once seeded, the QueryDecomposer._expand_domain_abbreviations() method
does a text lookup against these nodes at query time — no embedding needed.

DESIGN PRINCIPLE: Only true abbreviations/acronyms belong here.
Vocabulary bridges between semantically similar terms (e.g. "work
restrictions" ↔ "practice restrictions") are handled by embedding
similarity + UMLS bridge in _find_semantic_matches. Adding them to
DomainAbbreviation creates transitive fan-out that overwhelms the
phrase cap and pushes original query terms out of the search list.

Usage:
    python scripts/seed_domain_abbreviations.py
"""

import asyncio
import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from multimodal_librarian.clients.neo4j_client import Neo4jClient


# Each entry maps a surface form to its canonical expansion.
# The lookup is bidirectional: abbr→exp AND exp→abbr.
# ONLY true abbreviations/acronyms — no vocabulary bridges.
DOMAIN_ABBREVIATIONS: Dict[str, str] = {
    # ── Healthcare personnel acronym (UMLS lacks "HCP" synonym) ──
    "HCP": "healthcare personnel",
    "HCPs": "healthcare personnel",
    "healthcare personnel": "HCP",
    "healthcare worker": "HCP",
    "healthcare workers": "HCP",
    "healthcare provider": "HCP",
    "health care worker": "HCP",

    # ── Hepatitis / HBV ──────────────────────────────────────────
    "hepatitis b": "HBV",
    "hepatitis b virus": "HBV",
    "HBV": "hepatitis B",
    "hepatitis B surface antigen": "HBsAg",
    "HBsAg": "hepatitis B surface antigen",
    "hepatitis B e antigen": "HBeAg",
    "HBeAg": "hepatitis B e antigen",
    "hepatitis B core antigen": "anti-HBc",
    "anti-HBc": "hepatitis B core antigen",
    "hepatitis c": "HCV",
    "hepatitis C virus": "HCV",
    "HCV": "hepatitis C",
    "human immunodeficiency virus": "HIV",

    # ── General medical abbreviations ────────────────────────────
    "alanine aminotransferase": "ALT",
    "ALT": "alanine aminotransferase",
    "hepatocellular carcinoma": "HCC",
    "HCC": "hepatocellular carcinoma",
}


async def seed_abbreviations(neo4j: Neo4jClient) -> int:
    """Create constraint and insert DomainAbbreviation nodes. Returns count."""

    # 1. Create constraint if not exists
    try:
        await neo4j.execute_write_query(
            """CREATE CONSTRAINT domain_abbrev_abbr IF NOT EXISTS
               FOR (d:DomainAbbreviation) REQUIRE d.abbreviation_lower IS UNIQUE"""
        )
        print("Constraint domain_abbrev_abbr ready.")
    except Exception as e:
        print(f"Constraint creation failed (may already exist): {e}")

    # 1b. Create TEXT INDEX on UMLSConcept.lower_name for fast n-gram lookup
    try:
        await neo4j.execute_write_query(
            """CREATE TEXT INDEX umls_lower_name_text IF NOT EXISTS
               FOR (c:UMLSConcept) ON (c.lower_name)"""
        )
        print("TEXT INDEX umls_lower_name_text ready.")
    except Exception as e:
        print(f"TEXT INDEX creation failed (may already exist): {e}")

    # 2. Clear existing nodes and re-insert (avoids stale entries)
    try:
        await neo4j.execute_write_query(
            "MATCH (d:DomainAbbreviation) DELETE d"
        )
        print("Cleared existing DomainAbbreviation nodes.")
    except Exception as e:
        print(f"Clear failed (may be empty): {e}")

    # 3. Insert nodes
    inserted = 0
    for abbr, exp in DOMAIN_ABBREVIATIONS.items():
        try:
            result = await neo4j.execute_write_query(
                """MERGE (d:DomainAbbreviation {abbreviation_lower: $abbr_lower})
                   ON CREATE SET d.abbreviation = $abbr,
                                 d.expanded_form = $exp,
                                 d.expanded_form_lower = $exp_lower
                   ON MATCH SET d.abbreviation = $abbr,
                               d.expanded_form = $exp,
                               d.expanded_form_lower = $exp_lower
                   RETURN d.abbreviation AS abbr""",
                {
                    "abbr": abbr,
                    "abbr_lower": abbr.lower().strip(),
                    "exp": exp,
                    "exp_lower": exp.lower().strip(),
                },
            )
            if result:
                inserted += 1
        except Exception as e:
            print(f"  Failed to insert '{abbr}': {e}")

    print(f"Inserted {inserted} DomainAbbreviation nodes.")
    return inserted


async def verify(neo4j: Neo4jClient) -> None:
    """Print all DomainAbbreviation nodes for verification."""
    rows = await neo4j.execute_query(
        """MATCH (d:DomainAbbreviation)
           RETURN d.abbreviation AS abbr, d.expanded_form AS exp
           ORDER BY d.abbreviation_lower"""
    )
    if rows:
        print(f"\n{len(rows)} DomainAbbreviation nodes:")
        for row in rows:
            print(f"  {row['abbr']:40s} → {row['exp']}")
    else:
        print("\nNo DomainAbbreviation nodes found.")


async def main():
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    print(f"Connecting to Neo4j at {neo4j_uri}...")
    neo4j = Neo4jClient(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
    await neo4j.connect()

    try:
        count = await seed_abbreviations(neo4j)
        await verify(neo4j)
        if count > 0:
            print(f"\nDone. {count} abbreviations seeded.")
        else:
            print("\nNo new abbreviations seeded (all already exist).")
    finally:
        await neo4j.close()


if __name__ == "__main__":
    asyncio.run(main())
