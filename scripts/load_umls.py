#!/usr/bin/env python3
"""
UMLS Knowledge Graph Loader CLI.

Standalone script for loading UMLS Metathesaurus data into Neo4j.
Instantiates Neo4jClient directly (not via FastAPI DI) since this
runs independently of the application lifecycle.

Subcommands:
    dry-run  Scan RRF files and report estimates without writing
    load     Parse RRF files and bulk-load into Neo4j
    bridge   Create SAME_AS edges between UMLS and document concepts
    stats    Display counts of loaded UMLS data
    clean    Remove all UMLS data from Neo4j
"""

import argparse
import asyncio
import os
import sys
import time

import structlog

logger = structlog.get_logger(__name__)

# Default targeted vocabulary set
# Diagnosis: SNOMEDCT_US, MSH, ICD10CM, HPO
# Treatment & Prescription: RXNORM, MED-RT, ATC, ICD10PCS
# Lab & Observation: LNC
# Note: MED-RT replaced NDF-RT in UMLS starting 2018AB
TARGETED_VOCABULARY_SET = [
    "SNOMEDCT_US",
    "MSH",
    "ICD10CM",
    "RXNORM",
    "LNC",
    "HPO",
    "MED-RT",
    "ICD10PCS",
    "ATC",
]


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="load_umls",
        description="UMLS Knowledge Graph Loader — bulk-load UMLS data into Neo4j",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- dry-run ---
    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Scan RRF files and report estimated counts and memory usage",
    )
    dry_run_parser.add_argument("rrf_dir", help="Path to directory containing RRF files")
    dry_run_parser.add_argument(
        "--vocabs",
        nargs="+",
        default=TARGETED_VOCABULARY_SET,
        help="Source vocabularies to include (default: targeted set)",
    )
    dry_run_parser.add_argument(
        "--memory-limit",
        type=int,
        default=2048,
        help="Memory budget in MB (default: 2048)",
    )
    _add_neo4j_args(dry_run_parser)

    # --- load ---
    load_parser = subparsers.add_parser(
        "load",
        help="Parse RRF files and bulk-load UMLS data into Neo4j",
    )
    load_parser.add_argument("rrf_dir", help="Path to directory containing RRF files")
    load_parser.add_argument(
        "--vocabs",
        nargs="+",
        default=TARGETED_VOCABULARY_SET,
        help="Source vocabularies to include (default: targeted set)",
    )
    load_parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for concept loading (default: 5000)",
    )
    load_parser.add_argument(
        "--rel-batch-size",
        type=int,
        default=10000,
        help="Batch size for relationship loading (default: 10000)",
    )
    load_parser.add_argument(
        "--memory-limit",
        type=int,
        default=None,
        help="Memory limit in MB; abort if estimate exceeds this",
    )
    load_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    load_parser.add_argument(
        "--bridge",
        action="store_true",
        help="Run SAME_AS bridging after load completes",
    )
    load_parser.add_argument(
        "--check-config",
        action="store_true",
        help="Check Neo4j memory configuration before loading",
    )
    _add_neo4j_args(load_parser)

    # --- bridge ---
    bridge_parser = subparsers.add_parser(
        "bridge",
        help="Create SAME_AS edges between UMLS and document-extracted concepts",
    )
    _add_neo4j_args(bridge_parser)

    # --- stats ---
    stats_parser = subparsers.add_parser(
        "stats",
        help="Display counts of loaded UMLS data",
    )
    _add_neo4j_args(stats_parser)

    # --- clean ---
    clean_parser = subparsers.add_parser(
        "clean",
        help="Remove all UMLS data from Neo4j",
    )
    clean_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip interactive confirmation prompt",
    )
    _add_neo4j_args(clean_parser)

    return parser


def _add_neo4j_args(parser: argparse.ArgumentParser) -> None:
    """Add common Neo4j connection arguments to a subparser."""
    parser.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j bolt URI (default: env NEO4J_URI or bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (default: env NEO4J_USER or neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (default: env NEO4J_PASSWORD or password)",
    )


def _resolve_neo4j_args(args: argparse.Namespace) -> dict:  # type: ignore[type-arg]
    """Resolve Neo4j connection parameters from args or env vars."""
    return {
        "uri": args.neo4j_uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        "user": args.neo4j_user or os.environ.get("NEO4J_USER", "neo4j"),
        "password": args.neo4j_password or os.environ.get("NEO4J_PASSWORD", "password"),
    }


async def _create_neo4j_client(args: argparse.Namespace):
    """Instantiate and connect a Neo4jClient from CLI args."""
    from multimodal_librarian.clients.neo4j_client import Neo4jClient

    conn = _resolve_neo4j_args(args)
    client = Neo4jClient(
        uri=conn["uri"],
        user=conn["user"],
        password=conn["password"],
    )
    await client.connect()
    return client


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


async def cmd_dry_run(args: argparse.Namespace) -> None:
    """Scan RRF files and report estimates without writing to Neo4j."""
    from multimodal_librarian.components.knowledge_graph.rrf_parser import (
        validate_rrf_directory,
    )

    print(f"Scanning RRF directory: {args.rrf_dir}")
    print(f"Vocabularies: {', '.join(args.vocabs)}")

    found_files, missing_required = validate_rrf_directory(args.rrf_dir)

    if missing_required:
        print(f"\nERROR: Missing required files: {', '.join(missing_required)}")
        sys.exit(1)

    print(f"\nFound files: {', '.join(found_files.keys())}")

    # Use UMLSLoader.dry_run for estimates
    client = await _create_neo4j_client(args)
    try:
        from multimodal_librarian.components.knowledge_graph.umls_loader import (
            UMLSLoader,
        )

        loader = UMLSLoader(client)
        result = await loader.dry_run(
            mrconso_path=found_files["MRCONSO.RRF"],
            mrrel_path=found_files["MRREL.RRF"],
            source_vocabs=args.vocabs,
            memory_budget_mb=args.memory_limit,
        )

        print("\n--- Dry-Run Results ---")
        print(f"Estimated concepts:      {result.estimated_nodes:,}")
        print(f"Estimated relationships:  {result.estimated_relationships:,}")
        print(f"Estimated memory:         {result.estimated_memory_mb:.1f} MB")
        print(f"Memory budget:            {args.memory_limit} MB")
        print(f"Fits in budget:           {'Yes' if result.fits_in_budget else 'No'}")

        if not result.fits_in_budget and result.recommended_vocabs:
            print("\nRecommended reduced vocabulary set:")
            print(f"  {', '.join(result.recommended_vocabs)}")
    finally:
        await client.close()


async def cmd_load(args: argparse.Namespace) -> None:
    """Parse RRF files and bulk-load UMLS data into Neo4j."""
    from multimodal_librarian.components.knowledge_graph.rrf_parser import (
        validate_rrf_directory,
    )
    from multimodal_librarian.components.knowledge_graph.umls_loader import UMLSLoader

    start_time = time.monotonic()

    # Validate RRF directory
    found_files, missing_required = validate_rrf_directory(args.rrf_dir)
    if missing_required:
        print(f"ERROR: Missing required files: {', '.join(missing_required)}")
        sys.exit(1)

    print(f"RRF directory: {args.rrf_dir}")
    print(f"Vocabularies:  {', '.join(args.vocabs)}")
    print(f"Batch size:    {args.batch_size} (concepts), {args.rel_batch_size} (relationships)")
    if args.resume:
        print("Resume mode:   enabled")

    client = await _create_neo4j_client(args)
    try:
        loader = UMLSLoader(client)

        # (optional) Check Neo4j config
        if args.check_config:
            print("\n--- Neo4j Configuration Check ---")
            config = await loader.check_neo4j_config()
            print(f"Heap size:       {config['current'].get('heap_size', 'unknown')}")
            print(f"Page cache:      {config['current'].get('page_cache_size', 'unknown')}")
            print(f"Sufficient:      {'Yes' if config['sufficient'] else 'No'}")
            if not config["sufficient"]:
                print("Issues:")
                for issue in config.get("issues", []):
                    print(f"  - {issue}")
                recs = config.get("docker_compose_recommendations", {})
                if recs:
                    print("Recommended docker-compose.yml environment changes:")
                    for key, val in recs.items():
                        print(f"  {key}={val}")
                print()

        # (optional) Memory limit pre-check via dry-run
        if args.memory_limit is not None:
            print(f"\nRunning dry-run estimate (memory limit: {args.memory_limit} MB)...")
            dr = await loader.dry_run(
                mrconso_path=found_files["MRCONSO.RRF"],
                mrrel_path=found_files["MRREL.RRF"],
                source_vocabs=args.vocabs,
                memory_budget_mb=args.memory_limit,
            )
            if not dr.fits_in_budget:
                print(
                    f"ABORTED: Estimated memory {dr.estimated_memory_mb:.1f} MB "
                    f"exceeds limit {args.memory_limit} MB."
                )
                if dr.recommended_vocabs:
                    print(f"Try: --vocabs {' '.join(dr.recommended_vocabs)}")
                sys.exit(1)
            print(f"Estimate OK: {dr.estimated_memory_mb:.1f} MB within budget.\n")

        # Track totals across steps
        total_concepts = 0
        total_relationships = 0
        total_same_as = 0
        total_failed = 0

        # (a) Create indexes
        print("Step 1/6: Creating indexes...")
        await loader.create_indexes()
        print("  Indexes created.")

        # (b) Load semantic network from SRDEF if present
        print("Step 2/6: Loading semantic network (SRDEF)...")
        if "SRDEF" in found_files:
            sn_result = await loader.load_semantic_network(found_files["SRDEF"])
            print(
                f"  Semantic types: {sn_result.nodes_created}, "
                f"relationships: {sn_result.relationships_created}"
            )
        else:
            print("  SRDEF not found — skipping semantic network (non-fatal).")
            logger.warning("srdef_not_found", message="SRDEF missing, skipping semantic network")

        # (c) Load concepts from MRCONSO
        print("Step 3/6: Loading concepts from MRCONSO...")
        mrsty_path = found_files.get("MRSTY.RRF", "")
        # load_concepts requires mrsty_path; if missing, pass empty and it will
        # raise — but MRSTY is optional per design, so handle gracefully
        if not mrsty_path:
            # Create a temp empty file so load_concepts doesn't fail
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".RRF", delete=False)
            tmp.close()
            mrsty_path = tmp.name

        concept_result = await loader.load_concepts(
            mrconso_path=found_files["MRCONSO.RRF"],
            mrsty_path=mrsty_path,
            source_vocabs=args.vocabs,
            batch_size=args.batch_size,
            memory_limit_mb=args.memory_limit,
        )
        total_concepts += concept_result.nodes_created
        total_relationships += concept_result.relationships_created
        total_failed += concept_result.batches_failed
        print(
            f"  Concepts: {concept_result.nodes_created:,}, "
            f"HAS_SEMANTIC_TYPE: {concept_result.relationships_created:,}, "
            f"failed batches: {concept_result.batches_failed}"
        )

        # (d) Load semantic type edges from MRSTY
        # Already handled inside load_concepts above
        print("Step 4/6: Semantic type edges (handled in step 3).")

        # (e) Load definitions from MRDEF
        print("Step 5/6: Loading definitions from MRDEF...")
        if "MRDEF.RRF" in found_files:
            def_result = await loader.load_definitions(
                mrdef_path=found_files["MRDEF.RRF"],
                source_vocabs=args.vocabs,
                batch_size=args.batch_size,
            )
            print(
                f"  Definitions applied: {def_result.nodes_created:,}, "
                f"failed batches: {def_result.batches_failed}"
            )
            total_failed += def_result.batches_failed
        else:
            print("  MRDEF.RRF not found — skipping definitions.")

        # (f) Load relationships from MRREL
        print("Step 6/6: Loading relationships from MRREL...")
        rel_result = await loader.load_relationships(
            mrrel_path=found_files["MRREL.RRF"],
            source_vocabs=args.vocabs,
            batch_size=args.rel_batch_size,
        )
        total_relationships += rel_result.relationships_created
        total_failed += rel_result.batches_failed
        print(
            f"  Relationships: {rel_result.relationships_created:,}, "
            f"failed batches: {rel_result.batches_failed}"
        )

        # (optional) Bridge
        if args.bridge:
            print("\nBridging: Creating SAME_AS edges...")
            from multimodal_librarian.components.knowledge_graph.umls_bridger import (
                UMLSBridger,
            )

            bridger = UMLSBridger(client)
            bridge_result = await bridger.create_same_as_edges()
            total_same_as = bridge_result.same_as_edges_created
            print(
                f"  Matched: {bridge_result.concepts_matched:,}, "
                f"SAME_AS edges: {bridge_result.same_as_edges_created:,}, "
                f"unmatched: {bridge_result.unmatched_concepts:,}"
            )

        elapsed = time.monotonic() - start_time
        print(f"\n{'='*50}")
        print("UMLS Load Complete")
        print(f"  Concepts loaded:       {total_concepts:,}")
        print(f"  Relationships loaded:  {total_relationships:,}")
        if args.bridge:
            print(f"  SAME_AS edges:         {total_same_as:,}")
        print(f"  Failed batches:        {total_failed}")
        print(f"  Elapsed time:          {elapsed:.1f}s")
        print(f"{'='*50}")

    finally:
        await client.close()


async def cmd_bridge(args: argparse.Namespace) -> None:
    """Create SAME_AS edges between UMLS and document-extracted concepts."""
    from multimodal_librarian.components.knowledge_graph.umls_bridger import UMLSBridger

    client = await _create_neo4j_client(args)
    try:
        bridger = UMLSBridger(client)
        print("Creating SAME_AS edges...")
        result = await bridger.create_same_as_edges()

        print("\n--- Bridge Results ---")
        print(f"Concepts matched:    {result.concepts_matched:,}")
        print(f"SAME_AS edges:       {result.same_as_edges_created:,}")
        print(f"Unmatched concepts:  {result.unmatched_concepts:,}")
        print(f"Elapsed time:        {result.elapsed_seconds:.1f}s")
    finally:
        await client.close()


async def cmd_stats(args: argparse.Namespace) -> None:
    """Display counts of loaded UMLS data."""
    from multimodal_librarian.components.knowledge_graph.umls_loader import UMLSLoader

    client = await _create_neo4j_client(args)
    try:
        loader = UMLSLoader(client)
        stats = await loader.get_umls_stats()

        print("\n--- UMLS Stats ---")
        print(f"Loaded tier:         {stats.loaded_tier}")
        print(f"UMLSConcept nodes:   {stats.concept_count:,}")
        print(f"UMLSSemanticType:    {stats.semantic_type_count:,}")
        print(f"HAS_SEMANTIC_TYPE:   {stats.has_semantic_type_count:,}")
        print(f"UMLS_REL edges:      {stats.relationship_count:,}")
        print(f"SAME_AS edges:       {stats.same_as_count:,}")
        if stats.umls_version:
            print(f"UMLS version:        {stats.umls_version}")
        if stats.load_timestamp:
            print(f"Load timestamp:      {stats.load_timestamp}")
    finally:
        await client.close()


async def cmd_clean(args: argparse.Namespace) -> None:
    """Remove all UMLS data from Neo4j."""
    from multimodal_librarian.components.knowledge_graph.umls_loader import UMLSLoader

    if not args.confirm:
        response = input(
            "This will delete ALL UMLS data from Neo4j. Continue? [y/N] "
        )
        if response.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    client = await _create_neo4j_client(args)
    try:
        loader = UMLSLoader(client)
        print("Removing all UMLS data...")
        counts = await loader.remove_all_umls_data_with_counts()

        print("\n--- Cleanup Results ---")
        for category, count in counts.items():
            print(f"  {category}: {count:,} deleted")
        total = sum(counts.values())
        print(f"  Total: {total:,} deleted")
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler_map = {
        "dry-run": cmd_dry_run,
        "load": cmd_load,
        "bridge": cmd_bridge,
        "stats": cmd_stats,
        "clean": cmd_clean,
    }

    handler = handler_map[args.command]
    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
