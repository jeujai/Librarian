#!/usr/bin/env python3
"""
Sample Documents and Metadata Generator

This script generates sample documents and metadata for local development.
It creates realistic document records with processing status, chunks, and metadata.

Usage:
    python scripts/seed-sample-documents.py [--count N] [--reset] [--with-chunks]
    
    --count N: Number of documents to create (default: 20)
    --reset: Drop existing documents before creating new ones
    --with-chunks: Generate sample chunks for documents
"""

import asyncio
import argparse
import logging
import uuid
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from multimodal_librarian.models.documents import DocumentStatus, ChunkType
from multimodal_librarian.models.core import ContentType, SourceType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SampleDocumentGenerator:
    """Generator for sample documents and metadata."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Sample document templates
        self.document_templates = [
            {
                "title": "Machine Learning Fundamentals",
                "description": "A comprehensive guide to machine learning concepts and algorithms",
                "filename": "ml_fundamentals.pdf",
                "content_type": "technical",
                "subject": "Machine Learning",
                "keywords": ["machine learning", "algorithms", "neural networks", "data science"],
                "page_count": 245,
                "file_size": 5242880,  # 5MB
                "language": "en"
            },
            {
                "title": "Deep Learning with PyTorch",
                "description": "Practical guide to implementing deep learning models using PyTorch",
                "filename": "pytorch_deep_learning.pdf", 
                "content_type": "technical",
                "subject": "Deep Learning",
                "keywords": ["pytorch", "deep learning", "neural networks", "python"],
                "page_count": 189,
                "file_size": 4194304,  # 4MB
                "language": "en"
            },
            {
                "title": "Natural Language Processing Handbook",
                "description": "Complete reference for NLP techniques and applications",
                "filename": "nlp_handbook.pdf",
                "content_type": "academic",
                "subject": "Natural Language Processing",
                "keywords": ["nlp", "text processing", "linguistics", "transformers"],
                "page_count": 312,
                "file_size": 7340032,  # 7MB
                "language": "en"
            },
            {
                "title": "Computer Vision Applications",
                "description": "Modern approaches to computer vision and image processing",
                "filename": "computer_vision_apps.pdf",
                "content_type": "technical",
                "subject": "Computer Vision",
                "keywords": ["computer vision", "image processing", "opencv", "cnn"],
                "page_count": 156,
                "file_size": 3145728,  # 3MB
                "language": "en"
            },
            {
                "title": "Data Science Ethics",
                "description": "Ethical considerations in data science and AI development",
                "filename": "data_science_ethics.pdf",
                "content_type": "academic",
                "subject": "Ethics",
                "keywords": ["ethics", "data science", "ai", "bias", "fairness"],
                "page_count": 98,
                "file_size": 2097152,  # 2MB
                "language": "en"
            },
            {
                "title": "Quantum Computing Primer",
                "description": "Introduction to quantum computing concepts and algorithms",
                "filename": "quantum_computing_primer.pdf",
                "content_type": "academic",
                "subject": "Quantum Computing",
                "keywords": ["quantum computing", "qubits", "algorithms", "physics"],
                "page_count": 134,
                "file_size": 2621440,  # 2.5MB
                "language": "en"
            },
            {
                "title": "Blockchain Technology Overview",
                "description": "Technical overview of blockchain technology and cryptocurrencies",
                "filename": "blockchain_overview.pdf",
                "content_type": "technical",
                "subject": "Blockchain",
                "keywords": ["blockchain", "cryptocurrency", "distributed systems", "consensus"],
                "page_count": 87,
                "file_size": 1572864,  # 1.5MB
                "language": "en"
            },
            {
                "title": "Software Architecture Patterns",
                "description": "Common patterns and practices in software architecture",
                "filename": "software_architecture.pdf",
                "content_type": "technical",
                "subject": "Software Engineering",
                "keywords": ["architecture", "patterns", "microservices", "design"],
                "page_count": 203,
                "file_size": 4718592,  # 4.5MB
                "language": "en"
            }
        ]
        
        # Sample content for chunks
        self.sample_content_templates = {
            "technical": [
                "Machine learning algorithms can be broadly categorized into supervised, unsupervised, and reinforcement learning approaches. Each category serves different purposes and requires different types of data preparation.",
                "Neural networks consist of interconnected nodes (neurons) organized in layers. The input layer receives data, hidden layers process it through weighted connections, and the output layer produces results.",
                "Feature engineering is the process of selecting, modifying, or creating features from raw data to improve model performance. This step often determines the success of machine learning projects.",
                "Cross-validation is a statistical method used to estimate the performance of machine learning models on unseen data by partitioning the dataset into training and validation sets.",
                "Gradient descent is an optimization algorithm used to minimize the cost function in machine learning models by iteratively adjusting parameters in the direction of steepest descent."
            ],
            "academic": [
                "The philosophical implications of artificial intelligence extend beyond technical considerations to fundamental questions about consciousness, intelligence, and human nature.",
                "Ethical frameworks for AI development must consider fairness, accountability, transparency, and the potential for unintended consequences in automated decision-making systems.",
                "The history of computing reveals a pattern of exponential growth in processing power, storage capacity, and algorithmic sophistication over the past several decades.",
                "Interdisciplinary collaboration between computer scientists, domain experts, and ethicists is essential for developing responsible AI systems that benefit society.",
                "Research methodology in artificial intelligence requires careful consideration of experimental design, data collection, and evaluation metrics to ensure reproducible results."
            ]
        }
    
    async def generate_documents(self, count: int = 20, reset: bool = False, with_chunks: bool = False) -> List[Dict[str, Any]]:
        """
        Generate sample documents with metadata.
        
        Args:
            count: Total number of documents to create
            reset: Whether to reset existing documents first
            with_chunks: Whether to generate sample chunks
            
        Returns:
            List of created document data dictionaries
        """
        logger.info(f"Generating {count} sample documents (reset={reset}, with_chunks={with_chunks})")
        
        try:
            # Get database client
            db_client = await self.factory.get_relational_client()
            
            # Get sample users for document ownership
            users = await self._get_sample_users(db_client)
            if not users:
                logger.warning("No users found. Creating documents without user assignment.")
            
            # Reset documents if requested
            if reset:
                await self._reset_documents(db_client)
            
            # Create documents
            created_documents = []
            
            for i in range(count):
                # Use template or generate random document
                if i < len(self.document_templates):
                    doc_data = self.document_templates[i].copy()
                else:
                    doc_data = self._generate_random_document(i)
                
                # Assign random user if available
                if users:
                    doc_data["user_id"] = random.choice(users)["id"]
                else:
                    doc_data["user_id"] = str(uuid.uuid4())  # Fallback user ID
                
                # Create document
                document = await self._create_document(db_client, doc_data)
                created_documents.append(document)
                
                # Create chunks if requested
                if with_chunks:
                    await self._create_document_chunks(db_client, document, doc_data)
                
                logger.info(f"Created document: {document['title']} ({document['status']})")
            
            # Create knowledge sources for some documents
            await self._create_knowledge_sources(db_client, created_documents)
            
            logger.info(f"Successfully created {len(created_documents)} documents")
            return created_documents
            
        except Exception as e:
            logger.error(f"Failed to generate documents: {e}")
            raise
    
    async def _get_sample_users(self, db_client) -> List[Dict[str, Any]]:
        """Get existing sample users for document assignment."""
        try:
            async with db_client.get_async_session() as session:
                result = await session.execute(
                    "SELECT id, username, email FROM users WHERE is_active = true LIMIT 10"
                )
                users = [{"id": row[0], "username": row[1], "email": row[2]} for row in result.fetchall()]
                return users
        except Exception as e:
            logger.warning(f"Could not fetch users: {e}")
            return []
    
    async def _reset_documents(self, db_client) -> None:
        """Reset existing documents and related data."""
        logger.info("Resetting existing documents and metadata")
        
        try:
            async with db_client.get_async_session() as session:
                # Delete in order of foreign key dependencies
                await session.execute("DELETE FROM document_chunks")
                await session.execute("DELETE FROM knowledge_chunks")
                await session.execute("DELETE FROM documents")
                await session.execute("DELETE FROM knowledge_sources")
                
                # Reset sequences if they exist
                try:
                    await session.execute("ALTER SEQUENCE documents_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE document_chunks_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE knowledge_sources_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE knowledge_chunks_id_seq RESTART WITH 1")
                except Exception:
                    # Sequences might not exist, ignore
                    pass
                
                await session.commit()
                
            logger.info("Successfully reset document data")
            
        except Exception as e:
            logger.error(f"Failed to reset documents: {e}")
            raise
    
    async def _create_document(self, db_client, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single document record."""
        
        # Generate document IDs and metadata
        doc_id = str(uuid.uuid4())
        s3_key = f"documents/{doc_id}/{doc_data['filename']}"
        
        # Determine processing status (simulate realistic distribution)
        status_weights = [
            (DocumentStatus.COMPLETED, 0.7),
            (DocumentStatus.PROCESSING, 0.1),
            (DocumentStatus.UPLOADED, 0.15),
            (DocumentStatus.FAILED, 0.05)
        ]
        status = random.choices(
            [s[0] for s in status_weights],
            weights=[s[1] for s in status_weights]
        )[0]
        
        # Generate timestamps
        upload_time = datetime.utcnow() - timedelta(
            days=random.randint(1, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        
        processing_started = None
        processing_completed = None
        
        if status in [DocumentStatus.PROCESSING, DocumentStatus.COMPLETED, DocumentStatus.FAILED]:
            processing_started = upload_time + timedelta(minutes=random.randint(1, 30))
            
            if status in [DocumentStatus.COMPLETED, DocumentStatus.FAILED]:
                processing_completed = processing_started + timedelta(
                    minutes=random.randint(1, 60)
                )
        
        # Generate chunk count for completed documents
        chunk_count = None
        if status == DocumentStatus.COMPLETED:
            # Estimate chunks based on page count (roughly 2-5 chunks per page)
            chunks_per_page = random.uniform(2, 5)
            chunk_count = int(doc_data.get("page_count", 10) * chunks_per_page)
        
        # Create document metadata
        metadata = {
            "content_type": doc_data.get("content_type", "general"),
            "subject": doc_data.get("subject"),
            "keywords": doc_data.get("keywords", []),
            "language": doc_data.get("language", "en"),
            "processing_version": "1.0",
            "extraction_method": "multimodal_pdf_processor"
        }
        
        if status == DocumentStatus.FAILED:
            metadata["error_details"] = random.choice([
                "PDF parsing failed: Corrupted file structure",
                "OCR processing timeout: Document too large",
                "Unsupported PDF version: Requires manual processing",
                "Memory limit exceeded during text extraction"
            ])
        
        document_record = {
            "id": doc_id,
            "user_id": doc_data["user_id"],
            "title": doc_data["title"],
            "description": doc_data.get("description"),
            "filename": doc_data["filename"],
            "file_size": doc_data.get("file_size", random.randint(1048576, 10485760)),  # 1-10MB
            "mime_type": "application/pdf",
            "s3_key": s3_key,
            "status": status.value,
            "processing_error": metadata.get("error_details") if status == DocumentStatus.FAILED else None,
            "upload_timestamp": upload_time,
            "processing_started_at": processing_started,
            "processing_completed_at": processing_completed,
            "page_count": doc_data.get("page_count", random.randint(10, 300)),
            "chunk_count": chunk_count,
            "doc_metadata": json.dumps(metadata)
        }
        
        # Insert document
        async with db_client.get_async_session() as session:
            insert_sql = """
                INSERT INTO documents (
                    id, user_id, title, description, filename, file_size, mime_type,
                    s3_key, status, processing_error, upload_timestamp,
                    processing_started_at, processing_completed_at, page_count,
                    chunk_count, doc_metadata
                ) VALUES (
                    :id, :user_id, :title, :description, :filename, :file_size, :mime_type,
                    :s3_key, :status, :processing_error, :upload_timestamp,
                    :processing_started_at, :processing_completed_at, :page_count,
                    :chunk_count, :doc_metadata
                )
            """
            
            await session.execute(insert_sql, document_record)
            await session.commit()
        
        # Return document data
        return {
            "id": document_record["id"],
            "user_id": document_record["user_id"],
            "title": document_record["title"],
            "description": document_record["description"],
            "filename": document_record["filename"],
            "file_size": document_record["file_size"],
            "status": document_record["status"],
            "upload_timestamp": document_record["upload_timestamp"],
            "page_count": document_record["page_count"],
            "chunk_count": document_record["chunk_count"],
            "metadata": metadata
        }
    
    async def _create_document_chunks(self, db_client, document: Dict[str, Any], doc_data: Dict[str, Any]) -> None:
        """Create sample chunks for a document."""
        if document["status"] != "completed":
            return  # Only create chunks for completed documents
        
        chunk_count = document.get("chunk_count", 0)
        if chunk_count == 0:
            return
        
        logger.info(f"Creating {chunk_count} chunks for document: {document['title']}")
        
        content_type = doc_data.get("content_type", "technical")
        content_templates = self.sample_content_templates.get(content_type, 
                                                            self.sample_content_templates["technical"])
        
        for i in range(min(chunk_count, 50)):  # Limit to 50 chunks for performance
            chunk_id = str(uuid.uuid4())
            
            # Generate chunk content
            base_content = random.choice(content_templates)
            chunk_content = f"{base_content} This content is from page {(i // 3) + 1} of {document['title']}."
            
            # Determine chunk type (mostly text, some special types)
            chunk_type_weights = [
                (ChunkType.TEXT, 0.85),
                (ChunkType.IMAGE, 0.08),
                (ChunkType.TABLE, 0.05),
                (ChunkType.CHART, 0.02)
            ]
            chunk_type = random.choices(
                [t[0] for t in chunk_type_weights],
                weights=[t[1] for t in chunk_type_weights]
            )[0]
            
            # Generate chunk metadata
            chunk_metadata = {
                "extraction_confidence": random.uniform(0.8, 1.0),
                "processing_method": "pdf_text_extraction",
                "word_count": len(chunk_content.split()),
                "character_count": len(chunk_content)
            }
            
            if chunk_type != ChunkType.TEXT:
                chunk_metadata["media_type"] = chunk_type.value
                chunk_metadata["extraction_method"] = f"{chunk_type.value}_detection"
            
            chunk_record = {
                "id": chunk_id,
                "document_id": document["id"],
                "chunk_index": i,
                "content": chunk_content,
                "page_number": (i // 3) + 1,  # Roughly 3 chunks per page
                "section_title": f"Section {((i // 10) + 1)}",
                "chunk_type": chunk_type.value,
                "chunk_metadata": json.dumps(chunk_metadata),
                "created_at": datetime.utcnow()
            }
            
            # Insert chunk
            async with db_client.get_async_session() as session:
                insert_sql = """
                    INSERT INTO document_chunks (
                        id, document_id, chunk_index, content, page_number,
                        section_title, chunk_type, chunk_metadata, created_at
                    ) VALUES (
                        :id, :document_id, :chunk_index, :content, :page_number,
                        :section_title, :chunk_type, :chunk_metadata, :created_at
                    )
                """
                
                await session.execute(insert_sql, chunk_record)
                await session.commit()
    
    async def _create_knowledge_sources(self, db_client, documents: List[Dict[str, Any]]) -> None:
        """Create knowledge source entries for documents."""
        logger.info("Creating knowledge source entries")
        
        for document in documents:
            if document["status"] != "completed":
                continue  # Only create knowledge sources for completed documents
            
            source_id = str(uuid.uuid4())
            
            # Extract keywords from metadata
            keywords = document.get("metadata", {}).get("keywords", [])
            
            source_record = {
                "id": source_id,
                "source_type": SourceType.BOOK.value,
                "title": document["title"],
                "author": "Sample Author",  # Could be extracted from metadata
                "file_path": f"/uploads/{document['filename']}",
                "file_size": document["file_size"],
                "page_count": document["page_count"],
                "language": document.get("metadata", {}).get("language", "en"),
                "subject": document.get("metadata", {}).get("subject"),
                "keywords": "{" + ",".join(f'"{k}"' for k in keywords) + "}" if keywords else None,
                "created_at": document["upload_timestamp"],
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
            
            # Insert knowledge source
            async with db_client.get_async_session() as session:
                insert_sql = """
                    INSERT INTO knowledge_sources (
                        id, source_type, title, author, file_path, file_size,
                        page_count, language, subject, keywords, created_at,
                        updated_at, is_active
                    ) VALUES (
                        :id, :source_type, :title, :author, :file_path, :file_size,
                        :page_count, :language, :subject, :keywords, :created_at,
                        :updated_at, :is_active
                    )
                """
                
                await session.execute(insert_sql, source_record)
                await session.commit()
    
    def _generate_random_document(self, index: int) -> Dict[str, Any]:
        """Generate a random document based on templates."""
        
        subjects = [
            "Artificial Intelligence", "Data Science", "Software Engineering",
            "Cybersecurity", "Cloud Computing", "Mobile Development",
            "Web Development", "Database Systems", "Network Engineering",
            "DevOps", "Machine Learning", "Computer Graphics"
        ]
        
        content_types = ["technical", "academic", "general"]
        
        subject = random.choice(subjects)
        content_type = random.choice(content_types)
        
        return {
            "title": f"{subject} Guide {index:03d}",
            "description": f"Comprehensive guide covering {subject.lower()} concepts and practices",
            "filename": f"{subject.lower().replace(' ', '_')}_guide_{index:03d}.pdf",
            "content_type": content_type,
            "subject": subject,
            "keywords": [subject.lower(), "guide", "tutorial", "reference"],
            "page_count": random.randint(50, 400),
            "file_size": random.randint(2097152, 8388608),  # 2-8MB
            "language": "en"
        }
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the sample document generator."""
    parser = argparse.ArgumentParser(description="Generate sample documents for local development")
    parser.add_argument("--count", type=int, default=20, help="Number of documents to create")
    parser.add_argument("--reset", action="store_true", help="Reset existing documents first")
    parser.add_argument("--with-chunks", action="store_true", help="Generate sample chunks for documents")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    try:
        config = LocalDatabaseConfig()
        logger.info(f"Loaded configuration for {config.database_type} environment")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
    
    # Generate sample documents
    generator = SampleDocumentGenerator(config)
    
    try:
        documents = await generator.generate_documents(
            count=args.count, 
            reset=args.reset,
            with_chunks=args.with_chunks
        )
        
        print(f"\n✅ Successfully created {len(documents)} sample documents!")
        
        # Show status distribution
        status_counts = {}
        for doc in documents:
            status = doc["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nDocument Status Distribution:")
        print("=" * 40)
        for status, count in status_counts.items():
            emoji = {
                "completed": "✅",
                "processing": "⏳",
                "uploaded": "📤",
                "failed": "❌"
            }.get(status, "📄")
            print(f"{emoji} {status.title():12} | {count:3d} documents")
        
        print("\nSample Documents:")
        print("=" * 80)
        for doc in documents[:5]:  # Show first 5 documents
            status_emoji = {
                "completed": "✅",
                "processing": "⏳", 
                "uploaded": "📤",
                "failed": "❌"
            }.get(doc["status"], "📄")
            
            size_mb = doc["file_size"] / (1024 * 1024)
            print(f"{status_emoji} {doc['title'][:40]:40} | {size_mb:.1f}MB | {doc['page_count']:3d} pages")
        
        if len(documents) > 5:
            print(f"... and {len(documents) - 5} more documents")
        
        if args.with_chunks:
            total_chunks = sum(doc.get("chunk_count", 0) or 0 for doc in documents)
            print(f"\n📝 Generated {total_chunks} document chunks")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate sample documents: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)