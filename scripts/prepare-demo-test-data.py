#!/usr/bin/env python3
"""
Demo Test Data Preparation Script

This script prepares comprehensive test data for user acceptance testing
of the Multimodal Librarian system.
"""

import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DemoDataPreparator:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_data_dir = Path("test_data")
        self.demo_scenarios = {
            "research_assistant": {
                "documents": [
                    "Machine_Learning_Fundamentals.pdf",
                    "Deep_Learning_Applications.pdf", 
                    "Neural_Network_Architectures.pdf"
                ],
                "questions": [
                    "What are the main topics covered in Machine Learning Fundamentals?",
                    "Summarize the key findings from the Deep Learning Applications paper",
                    "Compare the approaches mentioned in all three papers",
                    "What does the Neural Network paper say about backpropagation?",
                    "How do the papers define overfitting?"
                ]
            },
            "business_analyst": {
                "documents": [
                    "Q3_Financial_Report.pdf",
                    "Market_Analysis_2024.pdf",
                    "Competitive_Landscape.pdf"
                ],
                "questions": [
                    "What were the key financial metrics in Q3?",
                    "How did revenue compare to previous quarters?",
                    "What market trends are identified in the analysis?",
                    "What competitive advantages are mentioned?",
                    "Create an executive summary of the key findings"
                ]
            },
            "technical_documentation": {
                "documents": [
                    "API_Reference_Manual.pdf",
                    "Developer_Guide.pdf",
                    "Best_Practices_Guide.pdf"
                ],
                "questions": [
                    "How do I authenticate with the API?",
                    "What are the rate limits mentioned?",
                    "Show me examples of API calls from the documentation",
                    "What does error code 401 mean according to the docs?",
                    "How do I handle rate limiting?"
                ]
            }
        }
    
    async def prepare_all_demo_data(self):
        """Prepare all demo test data."""
        logger.info("Starting demo test data preparation...")
        
        # Create test data directory
        self.test_data_dir.mkdir(exist_ok=True)
        
        # Generate sample PDF documents
        await self.generate_sample_documents()
        
        # Create question banks
        await self.create_question_banks()
        
        # Generate expected responses
        await self.generate_expected_responses()
        
        # Create user personas
        await self.create_user_personas()
        
        # Generate performance test data
        await self.generate_performance_test_data()
        
        # Create feedback collection templates
        await self.create_feedback_templates()
        
        logger.info("Demo test data preparation completed!")
    
    async def generate_sample_documents(self):
        """Generate sample PDF documents for testing."""
        logger.info("Generating sample PDF documents...")
        
        documents_dir = self.test_data_dir / "documents"
        documents_dir.mkdir(exist_ok=True)
        
        # Sample document contents
        sample_documents = {
            "Machine_Learning_Fundamentals.pdf": {
                "title": "Machine Learning Fundamentals",
                "content": """
                # Machine Learning Fundamentals
                
                ## Introduction
                Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed. This document covers the fundamental concepts and algorithms that form the foundation of modern machine learning.
                
                ## Key Concepts
                
                ### Supervised Learning
                Supervised learning involves training algorithms on labeled data to make predictions on new, unseen data. Common algorithms include:
                - Linear Regression: Used for predicting continuous values
                - Logistic Regression: Used for binary classification problems
                - Decision Trees: Tree-like models for both regression and classification
                - Random Forest: Ensemble method combining multiple decision trees
                - Support Vector Machines: Effective for high-dimensional data
                
                ### Unsupervised Learning
                Unsupervised learning finds patterns in data without labeled examples:
                - K-Means Clustering: Groups data into k clusters
                - Hierarchical Clustering: Creates tree-like cluster structures
                - Principal Component Analysis (PCA): Dimensionality reduction technique
                - Association Rules: Finds relationships between variables
                
                ### Reinforcement Learning
                Reinforcement learning involves agents learning through interaction with an environment:
                - Q-Learning: Model-free reinforcement learning algorithm
                - Policy Gradient Methods: Direct optimization of policies
                - Actor-Critic Methods: Combines value and policy-based approaches
                
                ## Overfitting and Underfitting
                
                ### Overfitting
                Overfitting occurs when a model learns the training data too well, including noise and irrelevant patterns. Signs of overfitting include:
                - High training accuracy but low validation accuracy
                - Complex models with many parameters
                - Poor generalization to new data
                
                Prevention techniques:
                - Cross-validation
                - Regularization (L1, L2)
                - Early stopping
                - Dropout in neural networks
                
                ### Underfitting
                Underfitting happens when a model is too simple to capture underlying patterns:
                - Low training and validation accuracy
                - High bias, low variance
                - Model lacks complexity
                
                ## Model Evaluation
                
                ### Metrics for Classification
                - Accuracy: Proportion of correct predictions
                - Precision: True positives / (True positives + False positives)
                - Recall: True positives / (True positives + False negatives)
                - F1-Score: Harmonic mean of precision and recall
                - ROC-AUC: Area under the receiver operating characteristic curve
                
                ### Metrics for Regression
                - Mean Squared Error (MSE)
                - Root Mean Squared Error (RMSE)
                - Mean Absolute Error (MAE)
                - R-squared (Coefficient of determination)
                
                ## Conclusion
                Understanding these fundamental concepts is crucial for successful machine learning implementation. The choice of algorithm depends on the problem type, data characteristics, and performance requirements.
                """
            },
            "Deep_Learning_Applications.pdf": {
                "title": "Deep Learning Applications in Modern AI",
                "content": """
                # Deep Learning Applications in Modern AI
                
                ## Abstract
                This paper explores the revolutionary impact of deep learning across various domains, from computer vision to natural language processing. We examine key applications, architectural innovations, and future directions in deep learning research.
                
                ## Introduction
                Deep learning has transformed artificial intelligence by enabling machines to automatically learn hierarchical representations from data. Unlike traditional machine learning approaches that require manual feature engineering, deep learning models can discover complex patterns through multiple layers of abstraction.
                
                ## Computer Vision Applications
                
                ### Image Classification
                Convolutional Neural Networks (CNNs) have achieved superhuman performance in image classification tasks:
                - ResNet: Introduced residual connections to enable training of very deep networks
                - EfficientNet: Optimized architecture scaling for better accuracy-efficiency trade-offs
                - Vision Transformers: Applied transformer architecture to computer vision
                
                Key findings:
                - Deeper networks generally perform better with proper regularization
                - Data augmentation significantly improves generalization
                - Transfer learning accelerates training on new domains
                
                ### Object Detection
                Modern object detection systems combine classification and localization:
                - YOLO (You Only Look Once): Real-time object detection
                - R-CNN family: Region-based convolutional neural networks
                - SSD (Single Shot Detector): Efficient multi-scale detection
                
                Performance metrics show 95%+ accuracy on standard benchmarks like COCO dataset.
                
                ### Semantic Segmentation
                Pixel-level classification for detailed scene understanding:
                - U-Net: Encoder-decoder architecture for medical imaging
                - DeepLab: Atrous convolutions for dense prediction
                - Mask R-CNN: Instance segmentation combining detection and segmentation
                
                ## Natural Language Processing
                
                ### Language Models
                Transformer-based models have revolutionized NLP:
                - BERT: Bidirectional encoder representations from transformers
                - GPT series: Generative pre-trained transformers
                - T5: Text-to-text transfer transformer
                
                Key innovations:
                - Attention mechanisms enable long-range dependencies
                - Pre-training on large corpora improves downstream performance
                - Fine-tuning adapts models to specific tasks
                
                ### Machine Translation
                Neural machine translation has surpassed statistical methods:
                - Sequence-to-sequence models with attention
                - Transformer architecture for parallel processing
                - Multilingual models supporting 100+ languages
                
                BLEU scores have improved from 20-30 to 40-50 on standard benchmarks.
                
                ## Challenges and Limitations
                
                ### Data Requirements
                Deep learning models typically require large amounts of labeled data:
                - ImageNet contains 14 million images
                - Common Crawl text corpus exceeds 1 trillion tokens
                - Data quality significantly impacts model performance
                
                ### Computational Costs
                Training large models requires substantial computational resources:
                - GPT-3 training cost estimated at $4.6 million
                - Carbon footprint concerns for large-scale training
                - Need for specialized hardware (GPUs, TPUs)
                
                ### Interpretability
                Deep learning models are often considered "black boxes":
                - Difficulty in understanding decision-making process
                - Limited explainability for critical applications
                - Ongoing research in interpretable AI
                
                ## Future Directions
                
                ### Efficient Architectures
                Research focuses on reducing computational requirements:
                - MobileNets for mobile and edge devices
                - Pruning and quantization techniques
                - Neural architecture search (NAS)
                
                ### Few-Shot Learning
                Learning from limited examples:
                - Meta-learning approaches
                - Prototypical networks
                - Model-agnostic meta-learning (MAML)
                
                ### Multimodal Learning
                Combining different data modalities:
                - Vision-language models (CLIP, DALL-E)
                - Audio-visual learning
                - Cross-modal retrieval and generation
                
                ## Conclusion
                Deep learning continues to drive breakthroughs across AI applications. While challenges remain in data efficiency, computational costs, and interpretability, ongoing research promises even more powerful and accessible deep learning systems.
                
                The convergence of improved architectures, larger datasets, and increased computational power suggests that deep learning will remain at the forefront of AI innovation for years to come.
                """
            },
            "Neural_Network_Architectures.pdf": {
                "title": "Neural Network Architectures: A Comprehensive Survey",
                "content": """
                # Neural Network Architectures: A Comprehensive Survey
                
                ## Executive Summary
                This comprehensive survey examines the evolution of neural network architectures from simple perceptrons to modern transformer models. We analyze architectural innovations, training techniques, and performance characteristics across different domains.
                
                ## Historical Development
                
                ### Early Neural Networks
                The foundation of modern neural networks was laid in the 1940s-1960s:
                - Perceptron (1957): First trainable neural network
                - Multi-layer Perceptron (MLP): Introduction of hidden layers
                - Backpropagation (1986): Efficient training algorithm for deep networks
                
                ### Revival Period (1980s-2000s)
                Key developments that revived interest in neural networks:
                - Universal approximation theorem
                - Improved optimization techniques
                - Better initialization strategies
                
                ## Fundamental Architectures
                
                ### Feedforward Networks
                The simplest neural network architecture:
                - Input layer receives data
                - Hidden layers perform transformations
                - Output layer produces predictions
                
                Mathematical formulation:
                y = f(W₃ · σ(W₂ · σ(W₁ · x + b₁) + b₂) + b₃)
                
                Where σ is the activation function (ReLU, sigmoid, tanh).
                
                ### Convolutional Neural Networks (CNNs)
                Specialized for processing grid-like data (images):
                
                #### Key Components
                - Convolutional layers: Apply filters to detect local features
                - Pooling layers: Reduce spatial dimensions
                - Fully connected layers: Final classification/regression
                
                #### Architectural Innovations
                - LeNet-5 (1998): First successful CNN for digit recognition
                - AlexNet (2012): Breakthrough in ImageNet competition
                - VGGNet (2014): Demonstrated importance of depth
                - ResNet (2015): Residual connections enable very deep networks
                - DenseNet (2017): Dense connections improve feature reuse
                
                #### Backpropagation in CNNs
                Backpropagation in convolutional layers involves:
                1. Forward pass: Convolution operations
                2. Backward pass: Gradient computation through convolution
                3. Parameter updates: Filter weights and biases
                
                The gradient of a convolution operation is computed as:
                ∂L/∂W = ∂L/∂Y ⊛ X
                
                Where ⊛ denotes convolution and L is the loss function.
                
                ### Recurrent Neural Networks (RNNs)
                Designed for sequential data processing:
                
                #### Vanilla RNNs
                Basic recurrent architecture:
                h_t = tanh(W_hh · h_{t-1} + W_xh · x_t + b_h)
                y_t = W_hy · h_t + b_y
                
                #### Long Short-Term Memory (LSTM)
                Addresses vanishing gradient problem:
                - Forget gate: Decides what information to discard
                - Input gate: Determines what new information to store
                - Output gate: Controls what parts of cell state to output
                
                LSTM equations:
                f_t = σ(W_f · [h_{t-1}, x_t] + b_f)  # Forget gate
                i_t = σ(W_i · [h_{t-1}, x_t] + b_i)  # Input gate
                C̃_t = tanh(W_C · [h_{t-1}, x_t] + b_C)  # Candidate values
                C_t = f_t * C_{t-1} + i_t * C̃_t  # Cell state
                o_t = σ(W_o · [h_{t-1}, x_t] + b_o)  # Output gate
                h_t = o_t * tanh(C_t)  # Hidden state
                
                #### Gated Recurrent Unit (GRU)
                Simplified alternative to LSTM:
                - Reset gate: Controls how much past information to forget
                - Update gate: Decides how much to update hidden state
                
                ### Transformer Architecture
                Revolutionary architecture based on self-attention:
                
                #### Self-Attention Mechanism
                Attention(Q, K, V) = softmax(QK^T / √d_k)V
                
                Where Q, K, V are query, key, and value matrices.
                
                #### Multi-Head Attention
                Allows model to attend to different representation subspaces:
                MultiHead(Q, K, V) = Concat(head_1, ..., head_h)W^O
                
                Where head_i = Attention(QW_i^Q, KW_i^K, VW_i^V)
                
                #### Positional Encoding
                Since transformers lack inherent sequence order:
                PE(pos, 2i) = sin(pos / 10000^{2i/d_model})
                PE(pos, 2i+1) = cos(pos / 10000^{2i/d_model})
                
                ## Training Techniques
                
                ### Backpropagation Algorithm
                The cornerstone of neural network training:
                
                1. Forward Pass:
                   - Compute activations layer by layer
                   - Calculate loss function
                
                2. Backward Pass:
                   - Compute gradients using chain rule
                   - Propagate errors backward through network
                
                3. Parameter Update:
                   - Update weights using gradient descent
                   - W := W - α · ∇W L
                
                ### Optimization Algorithms
                
                #### Stochastic Gradient Descent (SGD)
                Basic optimization algorithm:
                θ := θ - α · ∇θ J(θ)
                
                #### Adam Optimizer
                Adaptive learning rate method:
                m_t = β₁ · m_{t-1} + (1 - β₁) · g_t
                v_t = β₂ · v_{t-1} + (1 - β₂) · g_t²
                θ_t = θ_{t-1} - α · m̂_t / (√v̂_t + ε)
                
                Where m̂_t and v̂_t are bias-corrected estimates.
                
                ### Regularization Techniques
                
                #### Dropout
                Randomly sets neurons to zero during training:
                - Prevents overfitting
                - Improves generalization
                - Typical dropout rates: 0.2-0.5
                
                #### Batch Normalization
                Normalizes inputs to each layer:
                BN(x) = γ · (x - μ) / σ + β
                
                Benefits:
                - Faster training
                - Higher learning rates
                - Less sensitive to initialization
                
                ## Modern Architectures
                
                ### Vision Transformers (ViTs)
                Apply transformer architecture to computer vision:
                - Divide images into patches
                - Treat patches as sequence tokens
                - Apply standard transformer encoder
                
                Performance comparable to CNNs on large datasets.
                
                ### BERT (Bidirectional Encoder Representations)
                Transformer-based language model:
                - Bidirectional context understanding
                - Pre-training on masked language modeling
                - Fine-tuning for downstream tasks
                
                ### GPT (Generative Pre-trained Transformer)
                Autoregressive language model:
                - Unidirectional (left-to-right) generation
                - Scaling laws: performance improves with size
                - Few-shot learning capabilities
                
                ## Performance Analysis
                
                ### Computational Complexity
                - CNNs: O(n²) for n×n images
                - RNNs: O(n) sequential operations
                - Transformers: O(n²) attention computation
                
                ### Memory Requirements
                - Model parameters: Millions to billions
                - Activation memory: Depends on batch size and depth
                - Gradient storage: Same as parameters
                
                ### Training Time
                Factors affecting training duration:
                - Dataset size
                - Model complexity
                - Hardware capabilities
                - Optimization efficiency
                
                ## Future Directions
                
                ### Efficient Architectures
                Research on reducing computational costs:
                - Pruning: Remove unnecessary connections
                - Quantization: Reduce precision
                - Knowledge distillation: Transfer knowledge to smaller models
                
                ### Neural Architecture Search (NAS)
                Automated architecture design:
                - Reinforcement learning-based search
                - Evolutionary algorithms
                - Differentiable architecture search
                
                ### Hybrid Architectures
                Combining different architectural components:
                - CNN-RNN hybrids for video analysis
                - Transformer-CNN combinations
                - Graph neural networks for structured data
                
                ## Conclusion
                Neural network architectures have evolved dramatically from simple perceptrons to sophisticated transformer models. Each architecture addresses specific challenges and application domains. The field continues to advance with new architectural innovations, training techniques, and optimization methods.
                
                Understanding the principles behind different architectures, particularly the backpropagation algorithm and attention mechanisms, is crucial for developing effective deep learning solutions. Future research will likely focus on efficiency, interpretability, and domain-specific optimizations.
                """
            }
        }
        
        # Generate PDF-like content files (in practice, these would be actual PDFs)
        for filename, doc_data in sample_documents.items():
            doc_path = documents_dir / filename.replace('.pdf', '.txt')
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(doc_data['content'])
        
        # Create document metadata
        metadata_path = documents_dir / "document_metadata.json"
        metadata = {
            filename: {
                "title": doc_data["title"],
                "type": "academic_paper",
                "pages": len(doc_data["content"].split('\n\n')),
                "size_kb": len(doc_data["content"].encode('utf-8')) // 1024,
                "topics": self.extract_topics(doc_data["content"])
            }
            for filename, doc_data in sample_documents.items()
        }
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Generated {len(sample_documents)} sample documents")
    
    def extract_topics(self, content: str) -> List[str]:
        """Extract key topics from document content."""
        # Simple keyword extraction (in practice, would use NLP)
        keywords = [
            "machine learning", "deep learning", "neural networks", "backpropagation",
            "overfitting", "CNN", "RNN", "transformer", "attention", "classification",
            "regression", "supervised learning", "unsupervised learning", "optimization"
        ]
        
        content_lower = content.lower()
        found_topics = [keyword for keyword in keywords if keyword in content_lower]
        return found_topics[:10]  # Limit to top 10 topics
    
    async def create_question_banks(self):
        """Create comprehensive question banks for testing."""
        logger.info("Creating question banks...")
        
        questions_dir = self.test_data_dir / "questions"
        questions_dir.mkdir(exist_ok=True)
        
        # Question categories
        question_categories = {
            "factual": [
                "What is {topic} according to the document?",
                "How is {concept} defined in the paper?",
                "What are the key components of {system}?",
                "List the main features of {algorithm}.",
                "What does the document say about {term}?"
            ],
            "analytical": [
                "Compare {concept1} and {concept2} mentioned in the documents.",
                "What are the advantages and disadvantages of {approach}?",
                "How do the different papers approach {problem}?",
                "What relationships exist between {topic1} and {topic2}?",
                "Analyze the effectiveness of {method} based on the documents."
            ],
            "summary": [
                "Summarize the main points about {topic}.",
                "Provide an overview of {concept} from all documents.",
                "What are the key takeaways regarding {subject}?",
                "Create a brief summary of {paper_title}.",
                "Outline the main arguments presented about {issue}."
            ],
            "application": [
                "How would you apply {concept} in practice?",
                "What are the real-world implications of {finding}?",
                "How can {method} be used to solve {problem}?",
                "What practical steps are needed to implement {approach}?",
                "How does {theory} translate to practical applications?"
            ],
            "evaluation": [
                "What evidence supports {claim} in the documents?",
                "How reliable are the findings about {topic}?",
                "What limitations are mentioned regarding {approach}?",
                "How do the authors validate their {conclusions}?",
                "What gaps exist in the research on {subject}?"
            ]
        }
        
        # Generate questions for each scenario
        for scenario_name, scenario_data in self.demo_scenarios.items():
            scenario_questions = {
                "scenario": scenario_name,
                "documents": scenario_data["documents"],
                "predefined_questions": scenario_data["questions"],
                "generated_questions": {}
            }
            
            for category, templates in question_categories.items():
                scenario_questions["generated_questions"][category] = []
                
                # Generate questions based on document topics
                for template in templates[:3]:  # Limit to 3 per category
                    # This would be more sophisticated in practice
                    if "{topic}" in template:
                        question = template.replace("{topic}", "machine learning")
                    elif "{concept}" in template:
                        question = template.replace("{concept}", "neural networks")
                    else:
                        question = template
                    
                    scenario_questions["generated_questions"][category].append(question)
            
            # Save scenario questions
            scenario_path = questions_dir / f"{scenario_name}_questions.json"
            with open(scenario_path, 'w') as f:
                json.dump(scenario_questions, f, indent=2)
        
        logger.info(f"Created question banks for {len(self.demo_scenarios)} scenarios")
    
    async def generate_expected_responses(self):
        """Generate expected responses for validation."""
        logger.info("Generating expected responses...")
        
        responses_dir = self.test_data_dir / "expected_responses"
        responses_dir.mkdir(exist_ok=True)
        
        # Sample expected responses
        expected_responses = {
            "research_assistant": {
                "What are the main topics covered in Machine Learning Fundamentals?": {
                    "response": "The Machine Learning Fundamentals document covers several key topics including supervised learning (linear regression, logistic regression, decision trees, random forest, support vector machines), unsupervised learning (k-means clustering, hierarchical clustering, PCA, association rules), reinforcement learning (Q-learning, policy gradient methods, actor-critic methods), overfitting and underfitting concepts, and model evaluation metrics for both classification and regression tasks.",
                    "sources": ["Machine_Learning_Fundamentals.pdf"],
                    "confidence": 0.95,
                    "citations": ["Machine Learning Fundamentals, Page 1-3"]
                },
                "How do the papers define overfitting?": {
                    "response": "According to the Machine Learning Fundamentals document, overfitting occurs when a model learns the training data too well, including noise and irrelevant patterns. Signs of overfitting include high training accuracy but low validation accuracy, complex models with many parameters, and poor generalization to new data. The document suggests prevention techniques such as cross-validation, regularization (L1, L2), early stopping, and dropout in neural networks.",
                    "sources": ["Machine_Learning_Fundamentals.pdf"],
                    "confidence": 0.92,
                    "citations": ["Machine Learning Fundamentals, Page 2"]
                }
            },
            "business_analyst": {
                "What were the key financial metrics in Q3?": {
                    "response": "I don't have access to the specific Q3 Financial Report document to provide the exact financial metrics. To answer this question accurately, I would need the actual Q3 financial report to be uploaded and processed.",
                    "sources": [],
                    "confidence": 0.0,
                    "citations": []
                }
            }
        }
        
        # Save expected responses
        for scenario, responses in expected_responses.items():
            response_path = responses_dir / f"{scenario}_expected_responses.json"
            with open(response_path, 'w') as f:
                json.dump(responses, f, indent=2)
        
        logger.info("Generated expected responses for validation")
    
    async def create_user_personas(self):
        """Create detailed user personas for testing."""
        logger.info("Creating user personas...")
        
        personas_dir = self.test_data_dir / "personas"
        personas_dir.mkdir(exist_ok=True)
        
        user_personas = {
            "graduate_student": {
                "name": "Sarah Chen",
                "role": "PhD Student in Computer Science",
                "background": "Researching machine learning applications in healthcare",
                "technical_level": "High",
                "goals": [
                    "Quickly review and analyze research papers",
                    "Find connections between different studies",
                    "Generate literature review summaries",
                    "Identify research gaps and opportunities"
                ],
                "pain_points": [
                    "Information overload from too many papers",
                    "Difficulty tracking citations and sources",
                    "Time-consuming manual analysis",
                    "Inconsistent note-taking across documents"
                ],
                "usage_patterns": [
                    "Uploads 5-10 papers per research session",
                    "Asks detailed technical questions",
                    "Needs precise citations for academic writing",
                    "Works in focused 2-3 hour sessions"
                ],
                "success_metrics": [
                    "Reduces literature review time by 50%",
                    "Finds relevant connections between papers",
                    "Generates accurate citations automatically",
                    "Improves research productivity"
                ]
            },
            "business_executive": {
                "name": "Michael Rodriguez",
                "role": "VP of Strategy",
                "background": "15 years experience in business strategy and operations",
                "technical_level": "Medium",
                "goals": [
                    "Quickly extract insights from business reports",
                    "Prepare executive summaries",
                    "Identify trends and patterns",
                    "Support data-driven decision making"
                ],
                "pain_points": [
                    "Limited time to read lengthy reports",
                    "Need for quick, actionable insights",
                    "Difficulty synthesizing information across documents",
                    "Pressure to make informed decisions quickly"
                ],
                "usage_patterns": [
                    "Uploads quarterly reports and market analyses",
                    "Asks high-level strategic questions",
                    "Needs executive-level summaries",
                    "Uses system in short, focused sessions"
                ],
                "success_metrics": [
                    "Reduces report analysis time by 60%",
                    "Improves decision-making speed",
                    "Increases confidence in strategic choices",
                    "Better stakeholder communication"
                ]
            },
            "software_developer": {
                "name": "Alex Kim",
                "role": "Senior Software Engineer",
                "background": "Full-stack developer with 8 years experience",
                "technical_level": "Very High",
                "goals": [
                    "Quickly understand API documentation",
                    "Find code examples and best practices",
                    "Troubleshoot technical issues",
                    "Learn new technologies efficiently"
                ],
                "pain_points": [
                    "Scattered documentation across multiple sources",
                    "Outdated or incomplete technical docs",
                    "Difficulty finding specific implementation details",
                    "Time pressure to deliver features quickly"
                ],
                "usage_patterns": [
                    "Uploads technical manuals and API docs",
                    "Asks specific implementation questions",
                    "Needs code examples and snippets",
                    "Uses system for just-in-time learning"
                ],
                "success_metrics": [
                    "Reduces documentation search time by 70%",
                    "Finds accurate technical information faster",
                    "Improves code quality through better practices",
                    "Accelerates feature development"
                ]
            }
        }
        
        # Save user personas
        for persona_id, persona_data in user_personas.items():
            persona_path = personas_dir / f"{persona_id}.json"
            with open(persona_path, 'w') as f:
                json.dump(persona_data, f, indent=2)
        
        logger.info(f"Created {len(user_personas)} user personas")
    
    async def generate_performance_test_data(self):
        """Generate data for performance testing."""
        logger.info("Generating performance test data...")
        
        performance_dir = self.test_data_dir / "performance"
        performance_dir.mkdir(exist_ok=True)
        
        # Performance test scenarios
        performance_scenarios = {
            "load_testing": {
                "concurrent_users": [1, 5, 10, 20, 50],
                "test_duration_minutes": 10,
                "operations": [
                    {"type": "document_upload", "weight": 0.2},
                    {"type": "chat_query", "weight": 0.6},
                    {"type": "document_search", "weight": 0.2}
                ],
                "expected_metrics": {
                    "response_time_p95": 3.0,  # seconds
                    "error_rate": 0.01,  # 1%
                    "throughput_rps": 100  # requests per second
                }
            },
            "stress_testing": {
                "max_concurrent_users": 100,
                "ramp_up_time_minutes": 5,
                "test_duration_minutes": 30,
                "breaking_point_detection": True,
                "recovery_testing": True
            },
            "volume_testing": {
                "document_sizes": [1, 5, 10, 25, 50, 100],  # MB
                "document_counts": [1, 10, 50, 100, 500],
                "concurrent_processing": [1, 5, 10],
                "storage_limits": {
                    "per_user_gb": 10,
                    "total_system_gb": 1000
                }
            }
        }
        
        # Save performance test configurations
        for scenario, config in performance_scenarios.items():
            scenario_path = performance_dir / f"{scenario}_config.json"
            with open(scenario_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        # Generate sample load test script
        load_test_script = """
#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import json
from concurrent.futures import ThreadPoolExecutor

class LoadTester:
    def __init__(self, base_url, concurrent_users=10):
        self.base_url = base_url
        self.concurrent_users = concurrent_users
        self.results = []
    
    async def simulate_user_session(self, user_id):
        async with aiohttp.ClientSession() as session:
            # Upload document
            start_time = time.time()
            # ... upload logic ...
            upload_time = time.time() - start_time
            
            # Chat queries
            for i in range(5):
                start_time = time.time()
                # ... chat logic ...
                chat_time = time.time() - start_time
                
                self.results.append({
                    'user_id': user_id,
                    'operation': 'chat',
                    'response_time': chat_time,
                    'timestamp': time.time()
                })
    
    async def run_load_test(self, duration_minutes=10):
        tasks = []
        for user_id in range(self.concurrent_users):
            task = asyncio.create_task(self.simulate_user_session(user_id))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        return self.analyze_results()
    
    def analyze_results(self):
        # Calculate metrics
        response_times = [r['response_time'] for r in self.results]
        avg_response_time = sum(response_times) / len(response_times)
        p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
        
        return {
            'total_requests': len(self.results),
            'avg_response_time': avg_response_time,
            'p95_response_time': p95_response_time,
            'throughput_rps': len(self.results) / (max(r['timestamp'] for r in self.results) - min(r['timestamp'] for r in self.results))
        }

if __name__ == "__main__":
    tester = LoadTester("http://localhost:8000", concurrent_users=10)
    results = asyncio.run(tester.run_load_test(duration_minutes=5))
    print(json.dumps(results, indent=2))
"""
        
        with open(performance_dir / "load_test.py", 'w') as f:
            f.write(load_test_script)
        
        logger.info("Generated performance test data and scripts")
    
    async def create_feedback_templates(self):
        """Create feedback collection templates."""
        logger.info("Creating feedback templates...")
        
        feedback_dir = self.test_data_dir / "feedback_templates"
        feedback_dir.mkdir(exist_ok=True)
        
        # Feedback form templates
        feedback_templates = {
            "post_demo_survey": {
                "title": "Multimodal Librarian Demo Feedback",
                "sections": [
                    {
                        "name": "Overall Experience",
                        "questions": [
                            {
                                "id": "overall_satisfaction",
                                "type": "rating",
                                "scale": "1-5",
                                "question": "How satisfied are you with the overall system?",
                                "required": True
                            },
                            {
                                "id": "ease_of_use",
                                "type": "rating",
                                "scale": "1-5",
                                "question": "How easy was the system to use?",
                                "required": True
                            },
                            {
                                "id": "first_impression",
                                "type": "text",
                                "question": "What was your first impression of the system?",
                                "required": False
                            }
                        ]
                    },
                    {
                        "name": "Feature Feedback",
                        "questions": [
                            {
                                "id": "document_upload_rating",
                                "type": "rating",
                                "scale": "1-5",
                                "question": "Rate the document upload experience",
                                "required": True
                            },
                            {
                                "id": "chat_quality_rating",
                                "type": "rating",
                                "scale": "1-5",
                                "question": "Rate the AI chat response quality",
                                "required": True
                            },
                            {
                                "id": "most_valuable_feature",
                                "type": "text",
                                "question": "Which feature did you find most valuable?",
                                "required": False
                            }
                        ]
                    }
                ]
            },
            "quick_feedback_widget": {
                "triggers": [
                    {
                        "event": "document_upload_complete",
                        "question": "How was your document upload experience?",
                        "options": ["Great 😊", "Okay 😐", "Poor 😞"]
                    },
                    {
                        "event": "chat_response_received",
                        "question": "Was this response helpful?",
                        "options": ["Yes 👍", "No 👎"]
                    }
                ]
            }
        }
        
        # Save feedback templates
        for template_name, template_data in feedback_templates.items():
            template_path = feedback_dir / f"{template_name}.json"
            with open(template_path, 'w') as f:
                json.dump(template_data, f, indent=2)
        
        logger.info("Created feedback collection templates")
    
    async def generate_demo_report_template(self):
        """Generate demo report template."""
        logger.info("Generating demo report template...")
        
        report_template = """
# User Acceptance Testing Demo Report

## Demo Information
- **Date**: {demo_date}
- **Duration**: {demo_duration}
- **Scenario**: {scenario_name}
- **Participant**: {participant_name}
- **Role**: {participant_role}

## Demo Execution

### Setup Phase (5 minutes)
- [ ] System access verified
- [ ] Documents uploaded successfully
- [ ] Processing completed without errors
- [ ] Initial system tour completed

### Demonstration Phase (20 minutes)
- [ ] Document upload workflow demonstrated
- [ ] Chat functionality showcased
- [ ] RAG responses with citations shown
- [ ] Cross-document analysis performed
- [ ] Error handling demonstrated

### Feedback Collection (10 minutes)
- [ ] Immediate feedback collected
- [ ] Survey completed
- [ ] Follow-up questions asked
- [ ] Additional comments recorded

## Results Summary

### Quantitative Results
- **Task Completion Rate**: {completion_rate}%
- **Average Response Time**: {avg_response_time}s
- **User Satisfaction Score**: {satisfaction_score}/5
- **System Performance**: {performance_rating}/5

### Qualitative Feedback
- **Most Liked Features**: {liked_features}
- **Pain Points**: {pain_points}
- **Improvement Suggestions**: {suggestions}
- **Overall Impression**: {overall_impression}

## Technical Performance
- **Document Processing Time**: {processing_time}s
- **Chat Response Time**: {chat_response_time}s
- **System Errors**: {error_count}
- **Uptime**: {uptime}%

## Action Items
1. {action_item_1}
2. {action_item_2}
3. {action_item_3}

## Recommendations
- **Immediate**: {immediate_recommendations}
- **Short-term**: {short_term_recommendations}
- **Long-term**: {long_term_recommendations}

## Next Steps
- [ ] Address critical issues
- [ ] Schedule follow-up demo
- [ ] Implement feedback
- [ ] Update documentation

---
**Report Generated**: {report_timestamp}
**Generated By**: {report_author}
"""
        
        report_path = self.test_data_dir / "demo_report_template.md"
        with open(report_path, 'w') as f:
            f.write(report_template)
        
        logger.info("Generated demo report template")

async def main():
    """Main function to prepare all demo test data."""
    preparator = DemoDataPreparator()
    
    try:
        await preparator.prepare_all_demo_data()
        await preparator.generate_demo_report_template()
        
        print("\n✅ Demo test data preparation completed successfully!")
        print(f"📁 Test data available in: {preparator.test_data_dir}")
        print("\n📋 Generated components:")
        print("  - Sample PDF documents (3 academic papers)")
        print("  - Question banks for different scenarios")
        print("  - Expected responses for validation")
        print("  - User personas (3 detailed profiles)")
        print("  - Performance test configurations")
        print("  - Feedback collection templates")
        print("  - Demo report template")
        
        print("\n🚀 Ready for user acceptance testing!")
        
    except Exception as e:
        logger.error(f"Failed to prepare demo test data: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())