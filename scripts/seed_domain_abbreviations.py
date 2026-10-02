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


# Each entry maps an acronym to its canonical expansion (stored ONCE per pair).
# The query-side lookup is bidirectional (abbr→exp AND exp→abbr), so a single
# node covers both directions — no reverse-direction entries needed.
# ONLY true abbreviations/acronyms — no vocabulary bridges, and no acronyms
# that collide with common English words (e.g. MS, PT, ALL, OR, ED, CC).
DOMAIN_ABBREVIATIONS: Dict[str, str] = {
    # ── Healthcare personnel (acronym "HCP" is not a UMLS synonym) ──
    "HCP": "healthcare personnel",
    "HCPs": "healthcare personnel",
    "healthcare worker": "HCP",
    "healthcare workers": "HCP",
    "healthcare provider": "HCP",
    "health care worker": "HCP",

    # ── Hepatology ────────────────────────────────────────────────
    "HBV": "hepatitis B",
    "hepatitis b virus": "HBV",
    "HBsAg": "hepatitis B surface antigen",
    "HBeAg": "hepatitis B e antigen",
    "anti-HBc": "hepatitis B core antigen",
    "HCV": "hepatitis C",
    "hepatitis C virus": "HCV",
    "HCC": "hepatocellular carcinoma",
    "ALT": "alanine aminotransferase",
    "AST": "aspartate aminotransferase",
    "NASH": "nonalcoholic steatohepatitis",
    "NAFLD": "nonalcoholic fatty liver disease",

    # ── Infectious disease ───────────────────────────────────────
    "HIV": "human immunodeficiency virus",
    "MRSA": "methicillin-resistant Staphylococcus aureus",
    "VRE": "vancomycin-resistant enterococcus",
    "TB": "tuberculosis",
    "STI": "sexually transmitted infection",
    "STD": "sexually transmitted disease",

    # ── Cardiology ───────────────────────────────────────────────
    "ACS": "acute coronary syndrome",
    "AF": "atrial fibrillation",
    "AFib": "atrial fibrillation",
    "AMI": "acute myocardial infarction",
    "BP": "blood pressure",
    "CABG": "coronary artery bypass graft",
    "CAD": "coronary artery disease",
    "CHF": "congestive heart failure",
    "ECG": "electrocardiogram",
    "EKG": "electrocardiogram",
    "HTN": "hypertension",
    "MI": "myocardial infarction",
    "PCI": "percutaneous coronary intervention",
    "VF": "ventricular fibrillation",
    "VT": "ventricular tachycardia",

    # ── Pulmonology ──────────────────────────────────────────────
    "ARDS": "acute respiratory distress syndrome",
    "COPD": "chronic obstructive pulmonary disease",
    "CXR": "chest x-ray",
    "OSA": "obstructive sleep apnea",
    "PE": "pulmonary embolism",
    "PFT": "pulmonary function test",
    "SOB": "shortness of breath",
    "URI": "upper respiratory infection",

    # ── Gastroenterology ─────────────────────────────────────────
    "GERD": "gastroesophageal reflux disease",
    "GI": "gastrointestinal",
    "IBD": "inflammatory bowel disease",
    "IBS": "irritable bowel syndrome",
    "LFT": "liver function test",
    "PUD": "peptic ulcer disease",
    "TPN": "total parenteral nutrition",

    # ── Endocrinology ────────────────────────────────────────────
    "DM": "diabetes mellitus",
    "DKA": "diabetic ketoacidosis",
    "HbA1c": "hemoglobin A1c",
    "PCOS": "polycystic ovary syndrome",
    "SIADH": "syndrome of inappropriate antidiuretic hormone secretion",
    "T1DM": "type 1 diabetes mellitus",
    "T2DM": "type 2 diabetes mellitus",
    "TSH": "thyroid stimulating hormone",

    # ── Hematology / Oncology ────────────────────────────────────
    "ANC": "absolute neutrophil count",
    "CLL": "chronic lymphocytic leukemia",
    "CML": "chronic myeloid leukemia",
    "DVT": "deep vein thrombosis",
    "Hb": "hemoglobin",
    "Hct": "hematocrit",
    "INR": "international normalized ratio",
    "NHL": "non-Hodgkin lymphoma",
    "PTT": "partial thromboplastin time",
    "RBC": "red blood cell",
    "WBC": "white blood cell",

    # ── Nephrology / Urology ─────────────────────────────────────
    "AKI": "acute kidney injury",
    "BUN": "blood urea nitrogen",
    "CKD": "chronic kidney disease",
    "CRF": "chronic renal failure",
    "ESRD": "end-stage renal disease",
    "GFR": "glomerular filtration rate",
    "UTI": "urinary tract infection",

    # ── Neurology ────────────────────────────────────────────────
    "ALS": "amyotrophic lateral sclerosis",
    "CVA": "cerebrovascular accident",
    "EEG": "electroencephalogram",
    "TBI": "traumatic brain injury",
    "TIA": "transient ischemic attack",

    # ── Rheumatology / Immunology ────────────────────────────────
    "CRP": "C-reactive protein",
    "ESR": "erythrocyte sedimentation rate",
    "OA": "osteoarthritis",
    "RA": "rheumatoid arthritis",
    "SLE": "systemic lupus erythematosus",

    # ── OB / GYN ─────────────────────────────────────────────────
    "EDD": "estimated date of delivery",
    "GYN": "gynecology",
    "IVF": "in vitro fertilization",
    "LMP": "last menstrual period",
    "OB": "obstetrics",
    "PID": "pelvic inflammatory disease",

    # ── Labs / Diagnostics ───────────────────────────────────────
    "ABG": "arterial blood gas",
    "BMP": "basic metabolic panel",
    "BNP": "brain natriuretic peptide",
    "CBC": "complete blood count",
    "CMP": "comprehensive metabolic panel",
    "CSF": "cerebrospinal fluid",
    "FBS": "fasting blood sugar",
    "LDH": "lactate dehydrogenase",
    "MCV": "mean corpuscular volume",
    "RBS": "random blood sugar",

    # ── Imaging ──────────────────────────────────────────────────
    "CT": "computed tomography",
    "MRI": "magnetic resonance imaging",
    "PET": "positron emission tomography",

    # ── Medications / Routes ─────────────────────────────────────
    "ACEI": "angiotensin-converting enzyme inhibitor",
    "ARB": "angiotensin receptor blocker",
    "ASA": "aspirin",
    "BID": "twice daily",
    "IM": "intramuscular",
    "IV": "intravenous",
    "NSAID": "nonsteroidal anti-inflammatory drug",
    "PRN": "as needed",
    "QID": "four times daily",
    "SC": "subcutaneous",
    "SQ": "subcutaneous",
    "SSRI": "selective serotonin reuptake inhibitor",
    "TID": "three times daily",

    # ── General / Vitals ─────────────────────────────────────────
    "BMI": "body mass index",
    "DOB": "date of birth",
    "HR": "heart rate",
    "HPI": "history of present illness",
    "ICU": "intensive care unit",
    "NPO": "nothing by mouth",
    "RR": "respiratory rate",
    "ROS": "review of systems",
    "VS": "vital signs",
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
