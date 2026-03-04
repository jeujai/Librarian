# Product Overview

## Multimodal Librarian

A production-grade conversational knowledge management system that processes PDF documents with multimodal content (text, images, charts), stores them in a unified vector database, and enables intelligent conversational queries with multimedia output generation.

## Core Capabilities

- **Multimodal PDF Processing**: Extract and process text, images, charts, and metadata from PDF files
- **Adaptive Chunking Framework**: Automated content profiling with intelligent chunking strategies and bridge generation
- **Unified Knowledge Management**: Treat books and conversations as equivalent knowledge sources
- **Conversational AI Interface**: Real-time multimedia chat with WebSocket support
- **Knowledge Graph Integration**: Concept extraction and multi-hop reasoning using AWS Neptune
- **Vector Search**: Semantic search capabilities using AWS OpenSearch
- **Document Management**: Upload, process, and manage document collections
- **Analytics Dashboard**: Usage patterns, document statistics, and performance metrics
- **Authentication & Security**: JWT-based authentication with role-based access control

## Architecture

The system follows a microservices approach with:
- **FastAPI** backend with async/await patterns
- **AWS-native databases**: Neptune (graph), OpenSearch (vector), PostgreSQL (metadata)
- **Progressive startup**: Phased initialization for fast health checks and graceful degradation
- **Comprehensive monitoring**: Structured logging, metrics, alerts, and health checks
- **Production deployment**: AWS ECS Fargate with Terraform infrastructure-as-code

## Key Features

- Real-time chat with AI-powered responses
- Document upload and processing pipeline
- Knowledge graph for concept relationships
- Vector search for semantic similarity
- Multi-format export (PDF, DOCX, PPTX, etc.)
- User experience analytics and monitoring
- Disaster recovery and backup systems
