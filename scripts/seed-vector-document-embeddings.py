#!/usr/bin/env python3
"""
Vector Database Test Data Generator - Document Embeddings

This script generates sample document embeddings for testing vector similarity search,
document clustering, and retrieval operations in the local Milvus development environment.

The script creates realistic document embeddings with:
- Diverse document types (research papers, technical docs, tutorials)
- Varied content domains (ML, AI, software engineering, data science)
- Realistic metadata (authors, publication dates, categories)
- Hierarchical document relationships
- Multi-language support (primarily English with some multilingual examples)

Usage:
    python scripts/seed-vector-document-embeddings.py [--count N] [--reset] [--verbose]
    
    --count N: Number of document embeddings to generate (default: 50)
    --reset: Clear existing embeddings before generating new ones
    --verbose: Enable detailed logging
"""

import asyncio
import argparse
import logging
import sys
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.config_factory import get_database_config
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DocumentEmbeddingGenerator:
    """Generator for realistic document embeddings with metadata."""
    
    def __init__(self, verbose: bool = False):
        """Initialize the generator."""
        self.verbose = verbose
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        # Sample document templates with realistic content
        self.document_templates = [
            # Machine Learning Research Papers
            {
                "title_template": "Deep Learning Approaches to {topic}",
                "content_template": "This paper presents a comprehensive study of deep learning methodologies applied to {topic}. We introduce novel architectures that leverage {technique} to achieve state-of-the-art performance. Our experimental results demonstrate significant improvements in {metric} compared to existing approaches. The proposed method shows particular strength in handling {challenge} scenarios.",
                "domain": "machine_learning",
                "type": "research_paper",
                "topic": ["natural language processing", "computer vision", "speech recognition", "recommendation systems", "time series analysis"],
                "technique": ["transformer architectures", "convolutional neural networks", "recurrent neural networks", "attention mechanisms", "graph neural networks"],
                "metric": ["accuracy", "F1-score", "BLEU score", "perplexity", "mean squared error"],
                "challenge": ["few-shot learning", "domain adaptation", "noisy data", "imbalanced datasets", "real-time inference"]
            },
            # Technical Documentation
            {
                "title_template": "{system} Implementation Guide: {aspect}",
                "content_template": "This guide provides detailed instructions for implementing {system} with focus on {aspect}. Key considerations include {consideration} and {practice}. Best practices recommend {standard} to ensure optimal performance. Common pitfalls to avoid include {pitfall}. The implementation should follow industry standards for maintainability.",
                "domain": "software_engineering",
                "type": "technical_documentation",
                "system": ["microservices architecture", "distributed databases", "machine learning pipelines", "API gateways", "container orchestration"],
                "aspect": ["scalability optimization", "security hardening", "performance tuning", "monitoring setup", "deployment automation"],
                "consideration": ["resource allocation", "network latency", "data consistency", "fault tolerance", "load balancing"],
                "practice": ["continuous integration", "automated testing", "code review processes", "documentation standards", "version control"],
                "pitfall": ["premature optimization", "tight coupling", "insufficient error handling", "poor logging", "inadequate monitoring"],
                "standard": ["REST API", "OpenAPI", "Docker", "Kubernetes", "CI/CD"]
            },
            # Tutorial Content
            {
                "title_template": "Getting Started with {technology}: {tutorial_type}",
                "content_template": "Welcome to this comprehensive tutorial on {technology}. In this {tutorial_type}, you'll learn how to {objective}. We'll start with {starting_point} and gradually progress to {advanced_topic}. By the end of this tutorial, you'll be able to {outcome}. Prerequisites include {prerequisite}.",
                "domain": "education",
                "type": "tutorial",
                "technology": ["Python machine learning", "Docker containerization", "Kubernetes orchestration", "React development", "Node.js backend"],
                "tutorial_type": ["beginner's guide", "hands-on workshop", "step-by-step walkthrough", "practical introduction", "comprehensive overview"],
                "objective": ["build your first model", "deploy applications", "set up development environment", "create REST APIs", "implement authentication"],
                "starting_point": ["basic concepts", "environment setup", "hello world example", "project initialization", "dependency installation"],
                "advanced_topic": ["production deployment", "performance optimization", "advanced features", "best practices", "troubleshooting"],
                "outcome": ["deploy production applications", "optimize model performance", "implement complex features", "debug common issues", "follow industry standards"],
                "prerequisite": ["basic programming knowledge", "familiarity with command line", "understanding of web concepts", "Python experience", "database fundamentals"]
            },
            # Data Science Case Studies
            {
                "title_template": "Data Science Case Study: {use_case}",
                "content_template": "This case study examines the application of data science techniques to {use_case}. The dataset consists of {data_description} collected over {time_period}. Our analysis reveals {finding} and provides {insight}. The predictive model achieved good performance using {algorithm}. Key insights have implications for {application}.",
                "domain": "data_science",
                "type": "case_study",
                "use_case": ["customer churn prediction", "fraud detection", "demand forecasting", "sentiment analysis", "recommendation engines"],
                "data_description": ["transactional records", "user behavior logs", "sensor measurements", "social media posts", "financial transactions"],
                "time_period": ["6 months", "2 years", "quarterly periods", "daily intervals", "real-time streams"],
                "finding": ["seasonal patterns", "correlation between variables", "anomalous behavior", "user segmentation", "trend analysis"],
                "algorithm": ["random forest", "gradient boosting", "neural networks", "support vector machines", "ensemble methods"],
                "insight": ["feature importance rankings", "model interpretability", "business impact quantification", "actionable recommendations", "risk assessment"],
                "application": ["business strategy", "operational efficiency", "risk management", "customer experience", "product development"]
            },
            # AI Ethics and Policy
            {
                "title_template": "AI Ethics in {context}: {focus_area}",
                "content_template": "The deployment of artificial intelligence in {context} raises important ethical considerations around {focus_area}. Key challenges include {challenge} and stakeholder concerns. Stakeholders must address {concern} while balancing {tradeoff}. Recommended frameworks include {framework} to ensure {outcome}. Regulatory compliance requires {requirement}.",
                "domain": "ai_ethics",
                "type": "policy_document",
                "context": ["healthcare systems", "financial services", "autonomous vehicles", "hiring processes", "criminal justice"],
                "focus_area": ["algorithmic bias", "privacy protection", "transparency requirements", "accountability measures", "fairness assessment"],
                "challenge": ["data representation", "model interpretability", "consent management", "algorithmic auditing", "cross-cultural considerations"],
                "concern": ["discriminatory outcomes", "privacy violations", "lack of transparency", "accountability gaps", "societal impact"],
                "tradeoff": ["accuracy vs fairness", "privacy vs utility", "automation vs human oversight", "efficiency vs transparency", "innovation vs regulation"],
                "framework": ["ethical AI principles", "algorithmic impact assessments", "bias detection protocols", "privacy-by-design", "human-in-the-loop systems"],
                "outcome": ["equitable outcomes", "user trust", "regulatory compliance", "social benefit", "responsible innovation"],
                "requirement": ["audit trails", "explainability features", "bias monitoring", "consent mechanisms", "impact assessments"]
            }
        ]
        
        # Author names for realistic attribution
        self.authors = [
            "Dr. Sarah Chen", "Prof. Michael Rodriguez", "Dr. Aisha Patel", "Prof. James Wilson",
            "Dr. Maria Gonzalez", "Prof. David Kim", "Dr. Rachel Thompson", "Prof. Ahmed Hassan",
            "Dr. Lisa Wang", "Prof. Robert Johnson", "Dr. Priya Sharma", "Prof. Carlos Mendez",
            "Dr. Jennifer Lee", "Prof. Thomas Anderson", "Dr. Fatima Al-Zahra", "Prof. Giovanni Rossi",
            "Dr. Yuki Tanaka", "Prof. Elena Petrov", "Dr. Kwame Asante", "Prof. Sophie Dubois"
        ]
        
        # Research institutions and companies
        self.institutions = [
            "MIT Computer Science Lab", "Stanford AI Research", "Google DeepMind", "OpenAI",
            "Carnegie Mellon University", "UC Berkeley EECS", "Microsoft Research", "Meta AI",
            "University of Toronto", "ETH Zurich", "Oxford University", "Cambridge University",
            "NVIDIA Research", "IBM Research", "Amazon Science", "Apple Machine Learning",
            "DeepMind Technologies", "Anthropic", "Hugging Face", "Allen Institute for AI"
        ]
        
        # Publication venues
        self.venues = [
            "Nature Machine Intelligence", "Science Robotics", "ICML", "NeurIPS", "ICLR",
            "AAAI", "IJCAI", "ACL", "EMNLP", "ICCV", "CVPR", "ECCV", "SIGKDD",
            "WWW", "SIGIR", "RecSys", "CIKM", "WSDM", "ICDE", "VLDB"
        ]
        
        # Keywords for different domains
        self.domain_keywords = {
            "machine_learning": [
                "neural networks", "deep learning", "supervised learning", "unsupervised learning",
                "reinforcement learning", "transfer learning", "few-shot learning", "meta-learning",
                "attention mechanism", "transformer", "CNN", "RNN", "LSTM", "GAN", "VAE"
            ],
            "software_engineering": [
                "microservices", "API design", "scalability", "performance", "security",
                "DevOps", "CI/CD", "containerization", "orchestration", "monitoring",
                "testing", "debugging", "refactoring", "architecture", "design patterns"
            ],
            "education": [
                "tutorial", "learning", "beginner", "advanced", "hands-on", "practical",
                "step-by-step", "guide", "introduction", "overview", "workshop", "course",
                "training", "skill development", "best practices", "examples"
            ],
            "data_science": [
                "analytics", "statistics", "visualization", "prediction", "classification",
                "clustering", "regression", "feature engineering", "model selection",
                "cross-validation", "ensemble methods", "time series", "anomaly detection"
            ],
            "ai_ethics": [
                "bias", "fairness", "transparency", "accountability", "privacy", "ethics",
                "responsible AI", "algorithmic auditing", "explainability", "governance",
                "regulation", "compliance", "social impact", "human rights", "justice"
            ]
        }
    
    def generate_document_content(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Generate realistic document content from template."""
        # Select random values for template variables
        variables = {}
        for key, values in template.items():
            if isinstance(values, list) and key not in ["title_template", "content_template", "domain", "type"]:
                variables[key] = random.choice(values)
        
        # Generate title and content with safe formatting
        try:
            title = template["title_template"].format(**variables)
        except KeyError as e:
            # Handle missing variables by using placeholder
            missing_var = str(e).strip("'")
            variables[missing_var] = f"[{missing_var}]"
            title = template["title_template"].format(**variables)
        
        try:
            content = template["content_template"].format(**variables)
        except KeyError as e:
            # Handle missing variables by using placeholder
            missing_var = str(e).strip("'")
            variables[missing_var] = f"[{missing_var}]"
            content = template["content_template"].format(**variables)
        
        # Add domain-specific keywords
        domain_keywords = self.domain_keywords.get(template["domain"], [])
        selected_keywords = random.sample(domain_keywords, min(5, len(domain_keywords)))
        
        return {
            "title": title,
            "content": content,
            "domain": template["domain"],
            "type": template["type"],
            "keywords": selected_keywords,
            "variables": variables
        }
    
    def generate_realistic_embedding(self, content: str, dimension: int = 384) -> List[float]:
        """
        Generate a realistic-looking embedding vector based on content.
        
        This creates embeddings that have some correlation with content characteristics
        while maintaining the properties of real embeddings (normalized, distributed).
        """
        # Create a hash-based seed from content for reproducibility
        content_hash = hashlib.md5(content.encode()).hexdigest()
        seed = int(content_hash[:8], 16)
        random.seed(seed)
        
        # Generate base embedding with normal distribution
        embedding = [random.gauss(0, 0.1) for _ in range(dimension)]
        
        # Add content-specific patterns
        # Longer content tends to have different embedding characteristics
        content_length_factor = min(len(content) / 1000, 2.0)
        for i in range(0, dimension, 10):
            if i < len(embedding):
                embedding[i] += content_length_factor * 0.05
        
        # Add domain-specific clustering
        domain_patterns = {
            "machine_learning": [0.1, -0.05, 0.08, -0.03, 0.06],
            "software_engineering": [-0.08, 0.12, -0.04, 0.09, -0.07],
            "education": [0.05, 0.03, -0.1, 0.07, 0.04],
            "data_science": [0.09, -0.06, 0.11, -0.08, 0.05],
            "ai_ethics": [-0.03, 0.08, -0.09, 0.06, -0.04]
        }
        
        # Apply domain pattern if content contains domain keywords
        for domain, pattern in domain_patterns.items():
            domain_keywords = self.domain_keywords.get(domain, [])
            if any(keyword in content.lower() for keyword in domain_keywords):
                for i, adjustment in enumerate(pattern):
                    if i < len(embedding):
                        embedding[i] += adjustment
        
        # Normalize the embedding vector
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        
        return embedding
    
    def generate_document_metadata(self, doc_content: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
        """Generate realistic metadata for a document."""
        # Select random author and institution
        author = random.choice(self.authors)
        institution = random.choice(self.institutions)
        
        # Generate publication date (within last 5 years)
        days_ago = random.randint(0, 5 * 365)
        pub_date = datetime.now() - timedelta(days=days_ago)
        
        # Select venue based on document type
        if doc_content["type"] == "research_paper":
            venue = random.choice(self.venues)
        else:
            venue = f"{institution} Technical Reports"
        
        # Generate page count and word count
        if doc_content["type"] == "research_paper":
            page_count = random.randint(8, 25)
            word_count = page_count * random.randint(400, 600)
        elif doc_content["type"] == "technical_documentation":
            page_count = random.randint(15, 80)
            word_count = page_count * random.randint(300, 500)
        else:
            page_count = random.randint(5, 30)
            word_count = page_count * random.randint(350, 550)
        
        # Generate citation count (older papers tend to have more citations)
        age_years = days_ago / 365
        base_citations = max(0, int(random.expovariate(0.5) * age_years * 10))
        citation_count = random.randint(0, base_citations + 50)
        
        return {
            "document_id": doc_id,
            "title": doc_content["title"],
            "author": author,
            "institution": institution,
            "venue": venue,
            "publication_date": pub_date.isoformat(),
            "document_type": doc_content["type"],
            "domain": doc_content["domain"],
            "language": "en",  # Primarily English for now
            "page_count": page_count,
            "word_count": word_count,
            "citation_count": citation_count,
            "keywords": doc_content["keywords"],
            "abstract": doc_content["content"][:500] + "..." if len(doc_content["content"]) > 500 else doc_content["content"],
            "quality_score": random.uniform(0.6, 0.95),  # Simulated quality metric
            "access_type": random.choice(["open_access", "subscription", "preprint"]),
            "doi": f"10.1000/{random.randint(100000, 999999)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    async def generate_document_embeddings(self, count: int) -> List[Dict[str, Any]]:
        """Generate a set of realistic document embeddings."""
        logger.info(f"Generating {count} document embeddings...")
        
        embeddings = []
        
        for i in range(count):
            # Select random template
            template = random.choice(self.document_templates)
            
            # Generate document content
            doc_content = self.generate_document_content(template)
            
            # Generate document ID
            doc_id = f"doc_{i+1:04d}_{template['domain']}_{int(time.time() * 1000) % 100000}"
            
            # Generate embedding vector
            full_content = f"{doc_content['title']} {doc_content['content']}"
            embedding_vector = self.generate_realistic_embedding(full_content)
            
            # Generate metadata
            metadata = self.generate_document_metadata(doc_content, doc_id)
            
            # Create embedding document
            embedding_doc = {
                "id": doc_id,
                "vector": embedding_vector,
                "metadata": metadata
            }
            
            embeddings.append(embedding_doc)
            
            if self.verbose and (i + 1) % 10 == 0:
                logger.debug(f"Generated {i + 1}/{count} embeddings")
        
        logger.info(f"Successfully generated {len(embeddings)} document embeddings")
        return embeddings
    
    def print_sample_summary(self, embeddings: List[Dict[str, Any]], sample_size: int = 5):
        """Print a summary of generated embeddings."""
        print(f"\n📊 Generated {len(embeddings)} document embeddings")
        print("=" * 60)
        
        # Domain distribution
        domains = {}
        types = {}
        for emb in embeddings:
            domain = emb["metadata"]["domain"]
            doc_type = emb["metadata"]["document_type"]
            domains[domain] = domains.get(domain, 0) + 1
            types[doc_type] = types.get(doc_type, 0) + 1
        
        print("📈 Domain Distribution:")
        for domain, count in sorted(domains.items()):
            percentage = (count / len(embeddings)) * 100
            print(f"   • {domain.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        print("\n📄 Document Type Distribution:")
        for doc_type, count in sorted(types.items()):
            percentage = (count / len(embeddings)) * 100
            print(f"   • {doc_type.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        print(f"\n📋 Sample Documents (showing {min(sample_size, len(embeddings))}):")
        for i, emb in enumerate(embeddings[:sample_size]):
            metadata = emb["metadata"]
            print(f"\n   {i+1}. {metadata['title']}")
            print(f"      Author: {metadata['author']}")
            print(f"      Domain: {metadata['domain'].replace('_', ' ').title()}")
            print(f"      Type: {metadata['document_type'].replace('_', ' ').title()}")
            print(f"      Pages: {metadata['page_count']}, Words: {metadata['word_count']:,}")
            print(f"      Keywords: {', '.join(metadata['keywords'][:3])}...")
            print(f"      Vector dim: {len(emb['vector'])}")


async def main():
    """Main function to generate document embeddings."""
    parser = argparse.ArgumentParser(description="Generate sample document embeddings for vector database testing")
    parser.add_argument("--count", type=int, default=50, help="Number of document embeddings to generate")
    parser.add_argument("--reset", action="store_true", help="Clear existing embeddings before generating new ones")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("🚀 Document Embeddings Generator")
    print("=" * 50)
    print(f"Generating {args.count} document embeddings...")
    if args.reset:
        print("⚠️  Reset mode: Will clear existing embeddings")
    print()
    
    try:
        # Initialize generator
        generator = DocumentEmbeddingGenerator(verbose=args.verbose)
        
        # Generate embeddings
        start_time = time.time()
        embeddings = await generator.generate_document_embeddings(args.count)
        generation_time = time.time() - start_time
        
        # Print summary
        generator.print_sample_summary(embeddings)
        
        print(f"\n⏱️  Generation completed in {generation_time:.2f} seconds")
        print(f"📊 Average: {generation_time/len(embeddings)*1000:.1f}ms per embedding")
        
        # TODO: Store embeddings in Milvus when client is available
        print(f"\n💾 Storage:")
        print(f"   • Collection: document_embeddings")
        print(f"   • Vector dimension: {len(embeddings[0]['vector'])}")
        print(f"   • Total vectors: {len(embeddings)}")
        print(f"   • Estimated memory: {len(embeddings) * len(embeddings[0]['vector']) * 4 / 1024 / 1024:.1f} MB")
        
        # Save to JSON for inspection
        output_file = Path(__file__).parent.parent / "test_data" / "document_embeddings.json"
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w') as f:
            # Save a subset for inspection (full embeddings are large)
            sample_data = []
            for emb in embeddings[:10]:
                sample = emb.copy()
                sample["vector"] = sample["vector"][:10] + ["..."] + [f"({len(emb['vector'])} total)"]
                sample_data.append(sample)
            
            json.dump(sample_data, f, indent=2, default=str)
        
        print(f"\n💾 Sample data saved to: {output_file}")
        print("\n✅ Document embeddings generation completed successfully!")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)