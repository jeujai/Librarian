#!/usr/bin/env python3
"""
Development Data Seeding Script for Multimodal Librarian Learning Deployment

This script seeds the development environment with sample data for testing and
learning purposes. It creates sample documents, conversations, and ML training
data to facilitate development and testing.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import random
import uuid

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from multimodal_librarian.logging_config import get_logger
    from multimodal_librarian.database.connection import get_database_connection
    from multimodal_librarian.database.models import (
        Document, Conversation, Message, User, MLTrainingJob
    )
    from config.dev_config_basic import dev_config
except ImportError as e:
    print(f"Warning: Could not import application modules: {e}")
    print("Running in standalone mode with basic functionality")
    
    # Basic logging setup for standalone mode
    logging.basicConfig(level=logging.INFO)
    
    def get_logger(name):
        return logging.getLogger(name)

class DevelopmentDataSeeder:
    """Development data seeder for learning environment."""
    
    def __init__(self):
        self.logger = get_logger("dev_data_seeder")
        self.sample_data_dir = Path("test_data/dev_samples")
        self.sample_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample data configurations
        self.config = {
            "users": 5,
            "documents": 20,
            "conversations": 10,
            "messages_per_conversation": 5,
            "ml_training_jobs": 3
        }
    
    async def seed_all_data(self) -> None:
        """Seed all development data."""
        self.logger.info("🌱 Starting development data seeding")
        
        try:
            # Create sample files first
            await self.create_sample_files()
            
            # Seed database data
            await self.seed_users()
            await self.seed_documents()
            await self.seed_conversations()
            await self.seed_ml_training_jobs()
            
            # Create sample uploads
            await self.create_sample_uploads()
            
            self.logger.info("✅ Development data seeding completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Data seeding failed: {e}")
            raise
    
    async def create_sample_files(self) -> None:
        """Create sample files for development testing."""
        self.logger.info("Creating sample files...")
        
        # Sample PDF content (text representation)
        sample_documents = [
            {
                "filename": "machine_learning_basics.pdf",
                "title": "Introduction to Machine Learning",
                "content": """
                Machine Learning Fundamentals
                
                Machine learning is a subset of artificial intelligence that enables computers
                to learn and make decisions from data without being explicitly programmed.
                
                Key Concepts:
                1. Supervised Learning - Learning with labeled examples
                2. Unsupervised Learning - Finding patterns in unlabeled data
                3. Reinforcement Learning - Learning through interaction and feedback
                
                Applications:
                - Image recognition and computer vision
                - Natural language processing
                - Recommendation systems
                - Autonomous vehicles
                - Medical diagnosis
                
                This document provides a comprehensive introduction to machine learning
                concepts and their practical applications in modern technology.
                """,
                "metadata": {
                    "author": "Dr. Jane Smith",
                    "subject": "Machine Learning",
                    "keywords": ["AI", "ML", "algorithms", "data science"],
                    "pages": 25
                }
            },
            {
                "filename": "python_programming_guide.pdf",
                "title": "Python Programming Best Practices",
                "content": """
                Python Programming Guide
                
                Python is a versatile, high-level programming language known for its
                simplicity and readability. This guide covers best practices for
                Python development.
                
                Core Principles:
                1. Readability counts - Write clear, understandable code
                2. Simple is better than complex
                3. Explicit is better than implicit
                
                Best Practices:
                - Use meaningful variable names
                - Follow PEP 8 style guidelines
                - Write comprehensive documentation
                - Implement proper error handling
                - Use virtual environments
                
                Advanced Topics:
                - Object-oriented programming
                - Functional programming concepts
                - Asynchronous programming with asyncio
                - Testing with pytest
                - Package management with pip
                """,
                "metadata": {
                    "author": "Python Community",
                    "subject": "Programming",
                    "keywords": ["Python", "programming", "best practices", "development"],
                    "pages": 42
                }
            },
            {
                "filename": "aws_cloud_architecture.pdf",
                "title": "AWS Cloud Architecture Patterns",
                "content": """
                AWS Cloud Architecture Guide
                
                Amazon Web Services (AWS) provides a comprehensive set of cloud
                computing services for building scalable and reliable applications.
                
                Core Services:
                1. EC2 - Elastic Compute Cloud for virtual servers
                2. S3 - Simple Storage Service for object storage
                3. RDS - Relational Database Service
                4. Lambda - Serverless computing
                5. ECS - Elastic Container Service
                
                Architecture Patterns:
                - Microservices architecture
                - Serverless applications
                - Event-driven systems
                - Multi-tier applications
                - Disaster recovery strategies
                
                Security Best Practices:
                - Identity and Access Management (IAM)
                - Virtual Private Cloud (VPC) configuration
                - Encryption at rest and in transit
                - Security groups and NACLs
                - CloudTrail for audit logging
                """,
                "metadata": {
                    "author": "AWS Solutions Architecture Team",
                    "subject": "Cloud Computing",
                    "keywords": ["AWS", "cloud", "architecture", "scalability"],
                    "pages": 67
                }
            }
        ]
        
        # Create sample document files
        for doc in sample_documents:
            file_path = self.sample_data_dir / doc["filename"]
            
            # Create a simple text file (in real scenario, these would be PDFs)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Title: {doc['title']}\n")
                f.write(f"Author: {doc['metadata']['author']}\n")
                f.write(f"Subject: {doc['metadata']['subject']}\n")
                f.write(f"Keywords: {', '.join(doc['metadata']['keywords'])}\n")
                f.write(f"Pages: {doc['metadata']['pages']}\n")
                f.write("\n" + "="*50 + "\n\n")
                f.write(doc['content'])
        
        # Create sample media files (placeholder)
        sample_media = [
            "presentation_slides.pptx",
            "data_visualization.png",
            "tutorial_video.mp4",
            "audio_lecture.mp3"
        ]
        
        for media_file in sample_media:
            file_path = self.sample_data_dir / media_file
            with open(file_path, 'w') as f:
                f.write(f"Sample {media_file} content for development testing")
        
        self.logger.info(f"Created {len(sample_documents)} sample documents and {len(sample_media)} media files")
    
    async def seed_users(self) -> None:
        """Seed sample users for development."""
        self.logger.info("Seeding sample users...")
        
        sample_users = [
            {
                "username": "dev_user",
                "email": "dev@example.com",
                "full_name": "Development User",
                "role": "developer"
            },
            {
                "username": "test_admin",
                "email": "admin@example.com",
                "full_name": "Test Administrator",
                "role": "admin"
            },
            {
                "username": "researcher",
                "email": "researcher@example.com",
                "full_name": "Research Scientist",
                "role": "researcher"
            },
            {
                "username": "student",
                "email": "student@example.com",
                "full_name": "Graduate Student",
                "role": "student"
            },
            {
                "username": "analyst",
                "email": "analyst@example.com",
                "full_name": "Data Analyst",
                "role": "analyst"
            }
        ]
        
        # In a real implementation, this would interact with the database
        # For now, we'll create a JSON file with user data
        users_file = self.sample_data_dir / "users.json"
        with open(users_file, 'w') as f:
            json.dump(sample_users, f, indent=2)
        
        self.logger.info(f"Created {len(sample_users)} sample users")
    
    async def seed_documents(self) -> None:
        """Seed sample documents for development."""
        self.logger.info("Seeding sample documents...")
        
        # Generate document metadata
        sample_documents = []
        
        for i in range(self.config["documents"]):
            doc_id = str(uuid.uuid4())
            
            # Randomly select from our sample documents
            titles = [
                "Machine Learning Fundamentals",
                "Python Programming Guide",
                "AWS Cloud Architecture",
                "Data Science Methodology",
                "Software Engineering Principles",
                "Database Design Patterns",
                "Web Development Best Practices",
                "Cybersecurity Essentials",
                "DevOps and CI/CD",
                "Artificial Intelligence Ethics"
            ]
            
            subjects = [
                "Computer Science", "Data Science", "Software Engineering",
                "Cloud Computing", "Machine Learning", "Web Development",
                "Cybersecurity", "Database Systems", "DevOps", "AI Ethics"
            ]
            
            doc = {
                "id": doc_id,
                "title": random.choice(titles) + f" - Part {i+1}",
                "filename": f"document_{i+1:03d}.pdf",
                "subject": random.choice(subjects),
                "author": f"Author {random.randint(1, 10)}",
                "upload_date": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
                "file_size": random.randint(100000, 5000000),  # 100KB to 5MB
                "pages": random.randint(5, 100),
                "status": "processed",
                "tags": random.sample([
                    "tutorial", "reference", "research", "documentation",
                    "guide", "manual", "specification", "analysis"
                ], k=random.randint(1, 3))
            }
            
            sample_documents.append(doc)
        
        # Save documents metadata
        documents_file = self.sample_data_dir / "documents.json"
        with open(documents_file, 'w') as f:
            json.dump(sample_documents, f, indent=2)
        
        self.logger.info(f"Created {len(sample_documents)} sample documents")
    
    async def seed_conversations(self) -> None:
        """Seed sample conversations for development."""
        self.logger.info("Seeding sample conversations...")
        
        sample_conversations = []
        
        # Sample conversation topics and messages
        conversation_topics = [
            {
                "title": "Machine Learning Model Selection",
                "messages": [
                    {"role": "user", "content": "What's the best algorithm for text classification?"},
                    {"role": "assistant", "content": "For text classification, several algorithms work well depending on your data size and requirements. Popular choices include Naive Bayes for small datasets, SVM for medium datasets, and transformer models like BERT for large datasets with high accuracy requirements."},
                    {"role": "user", "content": "Can you explain the differences between these approaches?"},
                    {"role": "assistant", "content": "Certainly! Naive Bayes is fast and works well with limited data but assumes feature independence. SVM finds optimal decision boundaries and handles high-dimensional data well. BERT and other transformers capture complex contextual relationships but require more computational resources."},
                    {"role": "user", "content": "Which would you recommend for a sentiment analysis project?"}
                ]
            },
            {
                "title": "AWS Architecture Design",
                "messages": [
                    {"role": "user", "content": "How do I design a scalable web application on AWS?"},
                    {"role": "assistant", "content": "A scalable AWS architecture typically includes: Application Load Balancer for traffic distribution, Auto Scaling Groups for EC2 instances, RDS for managed databases, ElastiCache for caching, and S3 for static assets. Consider using ECS or EKS for containerized applications."},
                    {"role": "user", "content": "What about cost optimization?"},
                    {"role": "assistant", "content": "For cost optimization: use Reserved Instances for predictable workloads, Spot Instances for fault-tolerant tasks, implement auto-scaling to match demand, use S3 lifecycle policies, and monitor with Cost Explorer and budgets."}
                ]
            },
            {
                "title": "Python Development Best Practices",
                "messages": [
                    {"role": "user", "content": "What are the most important Python coding standards?"},
                    {"role": "assistant", "content": "Key Python standards include: Follow PEP 8 for style guidelines, use meaningful variable names, write docstrings for functions and classes, implement proper error handling with try/except blocks, and use virtual environments for dependency management."},
                    {"role": "user", "content": "How do I structure a Python project?"},
                    {"role": "assistant", "content": "A well-structured Python project includes: src/ directory for source code, tests/ for unit tests, docs/ for documentation, requirements.txt for dependencies, setup.py for packaging, and README.md for project description."}
                ]
            }
        ]
        
        # Generate conversations
        for i in range(self.config["conversations"]):
            topic = random.choice(conversation_topics)
            conversation_id = str(uuid.uuid4())
            
            conversation = {
                "id": conversation_id,
                "title": topic["title"] + f" - Session {i+1}",
                "user_id": f"user_{random.randint(1, 5)}",
                "created_at": (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
                "updated_at": datetime.now().isoformat(),
                "message_count": len(topic["messages"]),
                "status": "active",
                "messages": []
            }
            
            # Add messages to conversation
            for j, msg in enumerate(topic["messages"]):
                message = {
                    "id": str(uuid.uuid4()),
                    "conversation_id": conversation_id,
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": (datetime.now() - timedelta(minutes=random.randint(1, 60))).isoformat(),
                    "tokens": len(msg["content"].split()),
                    "metadata": {
                        "model": "gpt-3.5-turbo" if msg["role"] == "assistant" else None,
                        "processing_time": random.uniform(0.5, 3.0) if msg["role"] == "assistant" else None
                    }
                }
                conversation["messages"].append(message)
            
            sample_conversations.append(conversation)
        
        # Save conversations
        conversations_file = self.sample_data_dir / "conversations.json"
        with open(conversations_file, 'w') as f:
            json.dump(sample_conversations, f, indent=2)
        
        self.logger.info(f"Created {len(sample_conversations)} sample conversations")
    
    async def seed_ml_training_jobs(self) -> None:
        """Seed sample ML training jobs for development."""
        self.logger.info("Seeding sample ML training jobs...")
        
        sample_jobs = []
        
        job_types = [
            "document_classification",
            "sentiment_analysis",
            "entity_extraction",
            "text_summarization",
            "question_answering"
        ]
        
        statuses = ["completed", "running", "failed", "pending"]
        
        for i in range(self.config["ml_training_jobs"]):
            job_id = str(uuid.uuid4())
            job_type = random.choice(job_types)
            status = random.choice(statuses)
            
            job = {
                "id": job_id,
                "job_type": job_type,
                "status": status,
                "created_at": (datetime.now() - timedelta(days=random.randint(1, 7))).isoformat(),
                "started_at": (datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat() if status != "pending" else None,
                "completed_at": datetime.now().isoformat() if status == "completed" else None,
                "parameters": {
                    "model_type": random.choice(["bert", "roberta", "distilbert"]),
                    "learning_rate": random.uniform(0.0001, 0.01),
                    "batch_size": random.choice([8, 16, 32]),
                    "epochs": random.randint(3, 10),
                    "dataset_size": random.randint(1000, 10000)
                },
                "metrics": {
                    "accuracy": random.uniform(0.75, 0.95) if status == "completed" else None,
                    "precision": random.uniform(0.70, 0.90) if status == "completed" else None,
                    "recall": random.uniform(0.70, 0.90) if status == "completed" else None,
                    "f1_score": random.uniform(0.72, 0.88) if status == "completed" else None
                } if status == "completed" else {},
                "logs": [
                    f"Training started for {job_type}",
                    f"Epoch 1/5 - Loss: {random.uniform(0.5, 2.0):.4f}",
                    f"Epoch 2/5 - Loss: {random.uniform(0.3, 1.5):.4f}",
                    f"Validation accuracy: {random.uniform(0.7, 0.9):.4f}"
                ] if status in ["completed", "running"] else []
            }
            
            sample_jobs.append(job)
        
        # Save ML training jobs
        jobs_file = self.sample_data_dir / "ml_training_jobs.json"
        with open(jobs_file, 'w') as f:
            json.dump(sample_jobs, f, indent=2)
        
        self.logger.info(f"Created {len(sample_jobs)} sample ML training jobs")
    
    async def create_sample_uploads(self) -> None:
        """Create sample upload directory structure."""
        self.logger.info("Creating sample upload structure...")
        
        # Create upload directories
        upload_dirs = [
            "uploads/documents",
            "uploads/media",
            "uploads/temp",
            "exports/conversations",
            "exports/reports"
        ]
        
        for upload_dir in upload_dirs:
            Path(upload_dir).mkdir(parents=True, exist_ok=True)
        
        # Create sample uploaded files
        sample_uploads = [
            "uploads/documents/sample_research_paper.pdf",
            "uploads/documents/technical_specification.docx",
            "uploads/media/presentation_slides.pptx",
            "uploads/media/demo_video.mp4",
            "uploads/temp/processing_queue.json"
        ]
        
        for upload_file in sample_uploads:
            file_path = Path(upload_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w') as f:
                f.write(f"Sample content for {file_path.name}")
        
        self.logger.info(f"Created sample upload structure with {len(sample_uploads)} files")
    
    async def create_development_summary(self) -> None:
        """Create a summary of seeded development data."""
        self.logger.info("Creating development data summary...")
        
        summary = {
            "seeding_date": datetime.now().isoformat(),
            "environment": "development",
            "configuration": self.config,
            "data_location": str(self.sample_data_dir),
            "files_created": [
                "users.json",
                "documents.json",
                "conversations.json",
                "ml_training_jobs.json"
            ],
            "sample_files": list(self.sample_data_dir.glob("*")),
            "next_steps": [
                "Review seeded data in test_data/dev_samples/",
                "Start the development server",
                "Test API endpoints with sample data",
                "Verify database connections",
                "Run integration tests"
            ],
            "cleanup_instructions": [
                "Remove test_data/dev_samples/ directory when done",
                "Clear development database if needed",
                "Reset S3 development bucket",
                "Clean up CloudWatch logs"
            ]
        }
        
        summary_file = self.sample_data_dir / "seeding_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        self.logger.info(f"Development data summary saved to: {summary_file}")
        
        # Print summary to console
        print("\n" + "="*60)
        print("🌱 DEVELOPMENT DATA SEEDING SUMMARY")
        print("="*60)
        print(f"📅 Seeding Date: {summary['seeding_date']}")
        print(f"🏗️  Environment: {summary['environment']}")
        print(f"📁 Data Location: {summary['data_location']}")
        print(f"📊 Configuration: {summary['configuration']}")
        print("\n📋 Files Created:")
        for file in summary['files_created']:
            print(f"   ✅ {file}")
        print("\n🚀 Next Steps:")
        for step in summary['next_steps']:
            print(f"   • {step}")
        print("\n🧹 Cleanup Instructions:")
        for instruction in summary['cleanup_instructions']:
            print(f"   • {instruction}")
        print("="*60)

async def main():
    """Main function to run development data seeding."""
    seeder = DevelopmentDataSeeder()
    
    try:
        await seeder.seed_all_data()
        await seeder.create_development_summary()
        
        print("\n✅ Development data seeding completed successfully!")
        print("🚀 You can now start developing and testing with the seeded data.")
        
    except Exception as e:
        print(f"\n❌ Development data seeding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Run the seeding process
    asyncio.run(main())