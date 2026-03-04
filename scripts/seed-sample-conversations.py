#!/usr/bin/env python3
"""
Sample Conversations and Chat History Generator

This script generates sample conversations and chat history for local development.
It creates realistic conversation threads with messages, knowledge references, and metadata.

Usage:
    python scripts/seed-sample-conversations.py [--count N] [--reset] [--messages-per-conversation M]
    
    --count N: Number of conversations to create (default: 15)
    --reset: Drop existing conversations before creating new ones
    --messages-per-conversation M: Average messages per conversation (default: 8)
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
from multimodal_librarian.models.core import MessageType, SourceType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SampleConversationGenerator:
    """Generator for sample conversations and chat history."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Sample conversation templates
        self.conversation_templates = [
            {
                "topic": "Machine Learning Basics",
                "summary": "Discussion about fundamental machine learning concepts and algorithms",
                "messages": [
                    {"type": "user", "content": "Can you explain what machine learning is?"},
                    {"type": "system", "content": "Machine learning is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed for every task."},
                    {"type": "user", "content": "What are the main types of machine learning?"},
                    {"type": "system", "content": "There are three main types: supervised learning (learning from labeled data), unsupervised learning (finding patterns in unlabeled data), and reinforcement learning (learning through interaction and feedback)."},
                    {"type": "user", "content": "Can you give me an example of supervised learning?"},
                    {"type": "system", "content": "A classic example is email spam detection. You train a model on thousands of emails labeled as 'spam' or 'not spam', and it learns to classify new emails based on patterns it discovered in the training data."}
                ]
            },
            {
                "topic": "Neural Networks Deep Dive",
                "summary": "Technical discussion about neural network architectures and training",
                "messages": [
                    {"type": "user", "content": "How do neural networks actually work?"},
                    {"type": "system", "content": "Neural networks are inspired by biological neurons. They consist of interconnected nodes (artificial neurons) organized in layers that process information through weighted connections."},
                    {"type": "user", "content": "What happens during training?"},
                    {"type": "system", "content": "During training, the network adjusts its weights through backpropagation. It compares its predictions to the correct answers and updates weights to minimize the error."},
                    {"type": "user", "content": "What are activation functions?"},
                    {"type": "system", "content": "Activation functions determine whether a neuron should be activated. Common ones include ReLU (Rectified Linear Unit), sigmoid, and tanh. They introduce non-linearity, allowing networks to learn complex patterns."}
                ]
            },
            {
                "topic": "Data Preprocessing Techniques",
                "summary": "Conversation about data cleaning and preparation methods",
                "messages": [
                    {"type": "user", "content": "Why is data preprocessing so important?"},
                    {"type": "system", "content": "Data preprocessing is crucial because real-world data is often messy, incomplete, or inconsistent. Clean, well-prepared data leads to better model performance and more reliable results."},
                    {"type": "user", "content": "What are common preprocessing steps?"},
                    {"type": "system", "content": "Common steps include handling missing values, removing duplicates, normalizing or scaling features, encoding categorical variables, and detecting outliers."},
                    {"type": "user", "content": "How do you handle missing data?"},
                    {"type": "system", "content": "Several approaches exist: deletion (removing rows/columns), imputation (filling with mean, median, or predicted values), or using algorithms that handle missing data naturally."}
                ]
            },
            {
                "topic": "Computer Vision Applications",
                "summary": "Exploring computer vision techniques and real-world applications",
                "messages": [
                    {"type": "user", "content": "What can computer vision do in practice?"},
                    {"type": "system", "content": "Computer vision has many applications: medical image analysis, autonomous vehicles, facial recognition, quality control in manufacturing, and augmented reality."},
                    {"type": "user", "content": "How does image classification work?"},
                    {"type": "system", "content": "Image classification uses convolutional neural networks (CNNs) to identify patterns in images. The network learns features like edges, shapes, and textures to categorize images into predefined classes."},
                    {"type": "user", "content": "What's the difference between classification and object detection?"},
                    {"type": "system", "content": "Classification identifies what's in an image, while object detection finds where objects are located. Object detection combines classification with localization, drawing bounding boxes around detected objects."}
                ]
            },
            {
                "topic": "Natural Language Processing",
                "summary": "Discussion about NLP techniques and language models",
                "messages": [
                    {"type": "user", "content": "How do computers understand human language?"},
                    {"type": "system", "content": "NLP uses various techniques to process text: tokenization (breaking text into words), part-of-speech tagging, named entity recognition, and semantic analysis to understand meaning and context."},
                    {"type": "user", "content": "What are transformers in NLP?"},
                    {"type": "system", "content": "Transformers are a neural network architecture that uses attention mechanisms to process sequences. They can focus on relevant parts of input text, making them excellent for translation, summarization, and language generation."},
                    {"type": "user", "content": "How do large language models work?"},
                    {"type": "system", "content": "Large language models like GPT are trained on vast amounts of text to predict the next word in a sequence. This simple task teaches them grammar, facts, reasoning, and even some world knowledge."}
                ]
            }
        ]
        
        # Sample user questions for generating additional conversations
        self.sample_questions = [
            "What is the difference between AI and machine learning?",
            "How do I choose the right algorithm for my problem?",
            "What is overfitting and how can I prevent it?",
            "Can you explain cross-validation?",
            "What are the best practices for feature engineering?",
            "How do I evaluate model performance?",
            "What is the bias-variance tradeoff?",
            "When should I use deep learning vs traditional ML?",
            "How do I handle imbalanced datasets?",
            "What is transfer learning?",
            "How do I optimize hyperparameters?",
            "What are ensemble methods?",
            "How do I deploy a machine learning model?",
            "What is the difference between batch and online learning?",
            "How do I handle categorical variables?",
            "What is dimensionality reduction?",
            "How do I interpret model results?",
            "What are the ethical considerations in AI?",
            "How do I ensure data privacy in ML projects?",
            "What is explainable AI?"
        ]
        
        # Sample system responses
        self.sample_responses = [
            "That's a great question! Let me break this down for you...",
            "This is a fundamental concept in machine learning. Here's how it works...",
            "There are several approaches to this problem. Let me explain the most common ones...",
            "This depends on your specific use case, but generally...",
            "Based on current best practices, I'd recommend...",
            "This is a common challenge in data science. Here's how to approach it...",
            "Let me provide you with a practical example to illustrate this concept...",
            "This technique is particularly useful when...",
            "The key insight here is understanding the relationship between...",
            "From a theoretical perspective, this involves..."
        ]
    
    async def generate_conversations(self, count: int = 15, reset: bool = False, messages_per_conversation: int = 8) -> List[Dict[str, Any]]:
        """
        Generate sample conversations with chat history.
        
        Args:
            count: Total number of conversations to create
            reset: Whether to reset existing conversations first
            messages_per_conversation: Average number of messages per conversation
            
        Returns:
            List of created conversation data dictionaries
        """
        logger.info(f"Generating {count} sample conversations (reset={reset}, avg_messages={messages_per_conversation})")
        
        try:
            # Get database client
            db_client = await self.factory.get_relational_client()
            
            # Get sample users for conversation ownership
            users = await self._get_sample_users(db_client)
            if not users:
                logger.warning("No users found. Creating conversations without user assignment.")
            
            # Reset conversations if requested
            if reset:
                await self._reset_conversations(db_client)
            
            # Create conversations
            created_conversations = []
            
            for i in range(count):
                # Use template or generate random conversation
                if i < len(self.conversation_templates):
                    conv_data = self.conversation_templates[i].copy()
                else:
                    conv_data = self._generate_random_conversation(i, messages_per_conversation)
                
                # Assign random user if available
                if users:
                    conv_data["user_id"] = random.choice(users)["user_id"]
                else:
                    conv_data["user_id"] = f"user_{i:03d}"  # Fallback user ID
                
                # Create conversation
                conversation = await self._create_conversation(db_client, conv_data)
                created_conversations.append(conversation)
                
                logger.info(f"Created conversation: {conversation['topic']} ({len(conversation['messages'])} messages)")
            
            # Create chat messages for quick access
            await self._create_chat_messages(db_client, created_conversations)
            
            logger.info(f"Successfully created {len(created_conversations)} conversations")
            return created_conversations
            
        except Exception as e:
            logger.error(f"Failed to generate conversations: {e}")
            raise
    
    async def _get_sample_users(self, db_client) -> List[Dict[str, Any]]:
        """Get existing sample users for conversation assignment."""
        try:
            async with db_client.get_async_session() as session:
                result = await session.execute(
                    "SELECT id, user_id, username, email FROM users WHERE is_active = true LIMIT 10"
                )
                users = [
                    {"id": row[0], "user_id": row[1], "username": row[2], "email": row[3]} 
                    for row in result.fetchall()
                ]
                return users
        except Exception as e:
            logger.warning(f"Could not fetch users: {e}")
            return []
    
    async def _reset_conversations(self, db_client) -> None:
        """Reset existing conversations and related data."""
        logger.info("Resetting existing conversations and chat history")
        
        try:
            async with db_client.get_async_session() as session:
                # Delete in order of foreign key dependencies
                await session.execute("DELETE FROM chat_messages")
                await session.execute("DELETE FROM messages")
                await session.execute("DELETE FROM conversations")
                
                # Delete conversation-related knowledge sources
                await session.execute("DELETE FROM knowledge_sources WHERE source_type = 'conversation'")
                
                # Reset sequences if they exist
                try:
                    await session.execute("ALTER SEQUENCE conversations_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE messages_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE chat_messages_id_seq RESTART WITH 1")
                except Exception:
                    # Sequences might not exist, ignore
                    pass
                
                await session.commit()
                
            logger.info("Successfully reset conversation data")
            
        except Exception as e:
            logger.error(f"Failed to reset conversations: {e}")
            raise
    
    async def _create_conversation(self, db_client, conv_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single conversation with messages."""
        
        # Generate conversation IDs
        conversation_id = str(uuid.uuid4())
        thread_id = f"thread_{uuid.uuid4().hex[:12]}"
        
        # Generate timestamps
        created_time = datetime.utcnow() - timedelta(
            days=random.randint(1, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        
        # Create knowledge source for conversation
        source_id = str(uuid.uuid4())
        
        # Create knowledge source record
        source_record = {
            "id": source_id,
            "source_type": SourceType.CONVERSATION.value,
            "title": conv_data["topic"],
            "author": None,
            "file_path": None,
            "file_size": 0,
            "page_count": 0,
            "language": "en",
            "subject": "AI/ML Discussion",
            "keywords": "{" + ",".join([
                '"conversation"', '"chat"', '"ai"', '"machine learning"'
            ]) + "}",
            "created_at": created_time,
            "updated_at": created_time,
            "is_active": True
        }
        
        # Insert knowledge source
        async with db_client.get_async_session() as session:
            source_sql = """
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
            await session.execute(source_sql, source_record)
            await session.commit()
        
        # Create conversation record
        conversation_record = {
            "id": conversation_id,
            "thread_id": thread_id,
            "user_id": conv_data["user_id"],
            "source_id": source_id,
            "knowledge_summary": conv_data["summary"],
            "created_at": created_time,
            "last_updated": created_time,
            "is_active": True
        }
        
        # Insert conversation
        async with db_client.get_async_session() as session:
            conv_sql = """
                INSERT INTO conversations (
                    id, thread_id, user_id, source_id, knowledge_summary,
                    created_at, last_updated, is_active
                ) VALUES (
                    :id, :thread_id, :user_id, :source_id, :knowledge_summary,
                    :created_at, :last_updated, :is_active
                )
            """
            await session.execute(conv_sql, conversation_record)
            await session.commit()
        
        # Create messages
        messages = []
        current_time = created_time
        
        for i, msg_data in enumerate(conv_data["messages"]):
            message_id = str(uuid.uuid4())
            msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            
            # Add some time between messages
            current_time += timedelta(
                minutes=random.randint(1, 15),
                seconds=random.randint(0, 59)
            )
            
            # Generate knowledge references for system messages
            knowledge_refs = []
            if msg_data["type"] == "system" and random.random() < 0.7:
                # 70% chance of having knowledge references
                ref_count = random.randint(1, 3)
                knowledge_refs = [f"chunk_{uuid.uuid4().hex[:8]}" for _ in range(ref_count)]
            
            message_record = {
                "id": message_id,
                "message_id": msg_id,
                "conversation_id": conversation_id,
                "content": msg_data["content"],
                "message_type": msg_data["type"],
                "multimedia_content": json.dumps([]),  # Empty for text-only messages
                "knowledge_references": "{" + ",".join(f'"{ref}"' for ref in knowledge_refs) + "}" if knowledge_refs else None,
                "timestamp": current_time
            }
            
            # Insert message
            async with db_client.get_async_session() as session:
                msg_sql = """
                    INSERT INTO messages (
                        id, message_id, conversation_id, content, message_type,
                        multimedia_content, knowledge_references, timestamp
                    ) VALUES (
                        :id, :message_id, :conversation_id, :content, :message_type,
                        :multimedia_content, :knowledge_references, :timestamp
                    )
                """
                await session.execute(msg_sql, message_record)
                await session.commit()
            
            messages.append({
                "id": message_id,
                "message_id": msg_id,
                "content": msg_data["content"],
                "message_type": msg_data["type"],
                "knowledge_references": knowledge_refs,
                "timestamp": current_time
            })
        
        # Update conversation last_updated time
        async with db_client.get_async_session() as session:
            update_sql = "UPDATE conversations SET last_updated = :last_updated WHERE id = :id"
            await session.execute(update_sql, {"last_updated": current_time, "id": conversation_id})
            await session.commit()
        
        return {
            "id": conversation_id,
            "thread_id": thread_id,
            "user_id": conv_data["user_id"],
            "topic": conv_data["topic"],
            "summary": conv_data["summary"],
            "created_at": created_time,
            "last_updated": current_time,
            "messages": messages
        }
    
    async def _create_chat_messages(self, db_client, conversations: List[Dict[str, Any]]) -> None:
        """Create chat message records for quick access."""
        logger.info("Creating chat message records")
        
        for conversation in conversations:
            for message in conversation["messages"]:
                chat_message_id = str(uuid.uuid4())
                
                # Determine sources based on knowledge references
                sources = []
                if message.get("knowledge_references"):
                    sources = [f"doc_{ref}" for ref in message["knowledge_references"][:2]]  # Limit to 2 sources
                
                # Create message metadata
                metadata = {
                    "conversation_id": conversation["id"],
                    "thread_id": conversation["thread_id"],
                    "response_time": random.uniform(0.5, 3.0),  # Simulated response time
                    "confidence_score": random.uniform(0.8, 1.0) if message["message_type"] == "system" else None
                }
                
                chat_record = {
                    "id": chat_message_id,
                    "user_id": conversation["user_id"],
                    "content": message["content"],
                    "message_type": message["message_type"],
                    "timestamp": message["timestamp"],
                    "sources": "{" + ",".join(f'"{s}"' for s in sources) + "}" if sources else "{}",
                    "message_metadata": json.dumps(metadata)
                }
                
                # Insert chat message
                async with db_client.get_async_session() as session:
                    chat_sql = """
                        INSERT INTO chat_messages (
                            id, user_id, content, message_type, timestamp,
                            sources, message_metadata
                        ) VALUES (
                            :id, :user_id, :content, :message_type, :timestamp,
                            :sources, :message_metadata
                        )
                    """
                    await session.execute(chat_sql, chat_record)
                    await session.commit()
    
    def _generate_random_conversation(self, index: int, avg_messages: int) -> Dict[str, Any]:
        """Generate a random conversation."""
        
        topics = [
            "Deep Learning Fundamentals",
            "Data Science Best Practices", 
            "Computer Vision Techniques",
            "Natural Language Processing",
            "Reinforcement Learning",
            "MLOps and Model Deployment",
            "Feature Engineering Strategies",
            "Model Evaluation Methods",
            "Ethical AI Considerations",
            "Time Series Analysis",
            "Recommendation Systems",
            "Anomaly Detection",
            "Ensemble Learning Methods",
            "Transfer Learning Applications",
            "Hyperparameter Optimization"
        ]
        
        topic = random.choice(topics)
        
        # Generate messages
        message_count = max(3, int(random.gauss(avg_messages, 2)))  # At least 3 messages
        messages = []
        
        # Start with a user question
        messages.append({
            "type": "user",
            "content": random.choice(self.sample_questions)
        })
        
        # Alternate between system and user messages
        for i in range(1, message_count):
            if i % 2 == 1:  # System response
                response_start = random.choice(self.sample_responses)
                technical_content = f"In the context of {topic.lower()}, this involves understanding the underlying principles and applying them effectively to solve real-world problems."
                messages.append({
                    "type": "system",
                    "content": f"{response_start} {technical_content}"
                })
            else:  # User follow-up
                follow_ups = [
                    "Can you give me a practical example?",
                    "How does this apply to real-world scenarios?",
                    "What are the common pitfalls to avoid?",
                    "Are there any tools or libraries you'd recommend?",
                    "How do I get started with implementing this?",
                    "What are the performance considerations?",
                    "How does this compare to other approaches?"
                ]
                messages.append({
                    "type": "user",
                    "content": random.choice(follow_ups)
                })
        
        return {
            "topic": f"{topic} Discussion {index:03d}",
            "summary": f"Interactive discussion about {topic.lower()} concepts and practical applications",
            "messages": messages
        }
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the sample conversation generator."""
    parser = argparse.ArgumentParser(description="Generate sample conversations for local development")
    parser.add_argument("--count", type=int, default=15, help="Number of conversations to create")
    parser.add_argument("--reset", action="store_true", help="Reset existing conversations first")
    parser.add_argument("--messages-per-conversation", type=int, default=8, help="Average messages per conversation")
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
    
    # Generate sample conversations
    generator = SampleConversationGenerator(config)
    
    try:
        conversations = await generator.generate_conversations(
            count=args.count,
            reset=args.reset,
            messages_per_conversation=args.messages_per_conversation
        )
        
        print(f"\n✅ Successfully created {len(conversations)} sample conversations!")
        
        # Calculate statistics
        total_messages = sum(len(conv["messages"]) for conv in conversations)
        avg_messages = total_messages / len(conversations) if conversations else 0
        
        user_messages = sum(
            len([msg for msg in conv["messages"] if msg["message_type"] == "user"])
            for conv in conversations
        )
        system_messages = total_messages - user_messages
        
        print(f"\n📊 Conversation Statistics:")
        print("=" * 40)
        print(f"Total Messages:     {total_messages:4d}")
        print(f"Average per Conv:   {avg_messages:6.1f}")
        print(f"User Messages:      {user_messages:4d}")
        print(f"System Messages:    {system_messages:4d}")
        
        print(f"\nSample Conversations:")
        print("=" * 80)
        for conv in conversations[:5]:  # Show first 5 conversations
            msg_count = len(conv["messages"])
            duration = (conv["last_updated"] - conv["created_at"]).total_seconds() / 60
            print(f"💬 {conv['topic'][:50]:50} | {msg_count:2d} msgs | {duration:4.0f}min")
        
        if len(conversations) > 5:
            print(f"... and {len(conversations) - 5} more conversations")
        
        print(f"\n💡 Conversations include realistic timestamps, knowledge references, and user interactions")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate sample conversations: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)