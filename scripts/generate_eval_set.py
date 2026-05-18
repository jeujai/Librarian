#!/usr/bin/env python3
"""
Generate an evaluation set for a completed training run.

Connects to Neo4j and the RAG service to produce eval questions
with gold-standard answers, excluding questions used in training.

Usage (inside Docker):
    docker exec librarian-app-1 python /app/scripts/generate_eval_set.py \
        --training-data /app/training_runs/2026-05-01_114048/training_data.jsonl \
        --output /app/training_runs/2026-05-01_114048/eval_set.jsonl

Usage (host, if services are accessible):
    python scripts/generate_eval_set.py \
        --training-data training_runs/2026-05-01_114048/training_data.jsonl \
        --output training_runs/2026-05-01_114048/eval_set.jsonl
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main(training_data_path: str, output_path: str, count: int) -> int:
    from multimodal_librarian.ml.evaluation_runner import EvaluationRunner
    from multimodal_librarian.ml.models import EvaluationConfig

    # Build eval runner (no judge needed for eval set generation)
    config = EvaluationConfig(output_dir=".")
    runner = EvaluationRunner(config)

    # Collect training questions for exclusion
    training_questions: set[str] = set()
    try:
        with open(training_data_path) as f:
            for line in f:
                row = json.loads(line)
                q = row.get("instruction") or row.get("question", "")
                if q:
                    training_questions.add(q)
        logger.info("Loaded %d training questions for exclusion", len(training_questions))
    except Exception as e:
        logger.warning("Could not load training data for exclusion: %s", e)

    # Build Neo4j client
    try:
        from multimodal_librarian.clients.neo4j_client import Neo4jClient
        neo4j_client = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
        await neo4j_client.connect()
        logger.info("Connected to Neo4j")
    except Exception as e:
        logger.error("Failed to connect to Neo4j: %s", e)
        return 1

    # Build RAG service
    try:
        import os

        from multimodal_librarian.clients.milvus_client import MilvusClient

        milvus = MilvusClient(host="milvus", port=19530)
        await milvus.connect()
        logger.info("Connected to Milvus")

        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            from multimodal_librarian.services.deepseek_ai_service import (
                DeepSeekAIService,
            )
            ai_service = DeepSeekAIService()
            await ai_service.verify_available()
            logger.info("Using DeepSeek for gold answers")
        else:
            from multimodal_librarian.services.ollama_ai_service import OllamaAIService
            ai_service = OllamaAIService()
            await ai_service.verify_available()
            logger.info("Using Ollama for gold answers")

        from multimodal_librarian.services.rag_service import RAGService
        rag_service = RAGService(vector_client=milvus, ai_service=ai_service)
        logger.info("RAG service ready")
    except Exception as e:
        logger.error("Failed to build RAG service: %s", e)
        return 1

    # Generate eval set
    logger.info("Generating %d evaluation questions...", count)

    def progress(cur, tot):
        if cur % 5 == 0 or cur == tot:
            logger.info("Progress: %d/%d", cur, tot)

    eval_set = await runner.generate_eval_set(
        rag_service=rag_service,
        neo4j_client=neo4j_client,
        training_questions=training_questions,
        count=count,
        min_semantic_types=5,
        progress_callback=progress,
    )

    if not eval_set.questions:
        logger.error("No evaluation questions generated")
        return 1

    # Export
    runner.export_eval_set(eval_set, Path(output_path))
    logger.info("Saved %d questions to %s", len(eval_set.questions), output_path)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate evaluation set")
    parser.add_argument("--training-data", required=True, help="Path to training_data.jsonl")
    parser.add_argument("--output", required=True, help="Output path for eval_set.jsonl")
    parser.add_argument("--count", type=int, default=50, help="Number of eval questions (default: 50)")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.training_data, args.output, args.count)))
