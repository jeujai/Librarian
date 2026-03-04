"""
Integration examples for the comprehensive error logging service.

This module demonstrates how to integrate the error logging service
with existing components and services in the multimodal librarian system.
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from .error_logging_service import get_error_logging_service, ErrorSeverity, ErrorCategory
from .error_handler import (
    handle_errors, 
    handle_database_errors, 
    handle_search_errors, 
    handle_ai_errors,
    get_recovery_manager,
    with_recovery
)
from ..logging_config import get_logger

logger = get_logger("error_logging_integration")


class EnhancedVectorStoreService:
    """
    Example integration of error logging with vector store operations.
    
    This demonstrates how to add comprehensive error logging to an existing
    service without major refactoring.
    """
    
    def __init__(self):
        self.error_service = get_error_logging_service()
        self.recovery_manager = get_recovery_manager()
        self.logger = get_logger("vector_store_service")
    
    @handle_search_errors("vector_search")
    @with_recovery("retry_with_backoff")
    async def search_vectors(self, query_vector: List[float], 
                           top_k: int = 10, 
                           filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors with comprehensive error logging.
        
        Args:
            query_vector: Query vector for similarity search
            top_k: Number of results to return
            filters: Optional filters to apply
            
        Returns:
            List of search results with metadata
        """
        # Validate inputs
        if not query_vector:
            raise ValueError("Query vector cannot be empty")
        
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        
        # Simulate vector search operation
        try:
            # This would be actual vector store operations
            await asyncio.sleep(0.1)  # Simulate processing time
            
            # Simulate potential failures
            import random
            if random.random() < 0.1:  # 10% chance of failure
                raise ConnectionError("Vector store connection lost")
            
            # Return mock results
            results = [
                {
                    "id": f"doc_{i}",
                    "score": 0.9 - (i * 0.1),
                    "metadata": {"title": f"Document {i}"}
                }
                for i in range(min(top_k, 5))
            ]
            
            # Log successful operation
            self.error_service.logging_service.log_performance(
                service="vector_store",
                operation="vector_search",
                duration_ms=100,  # Mock duration
                success=True,
                metadata={
                    "query_vector_dim": len(query_vector),
                    "top_k": top_k,
                    "results_count": len(results),
                    "filters_applied": filters is not None
                }
            )
            
            return results
            
        except Exception as e:
            # Error is automatically logged by the decorator
            # Add additional context if needed
            self.logger.error(f"Vector search failed: {e}")
            raise
    
    @handle_search_errors("index_document")
    async def index_document(self, document_id: str, 
                           content_vector: List[float],
                           metadata: Dict[str, Any]) -> bool:
        """
        Index a document with error logging.
        
        Args:
            document_id: Unique document identifier
            content_vector: Document content vector
            metadata: Document metadata
            
        Returns:
            True if indexing successful
        """
        try:
            # Validate inputs
            if not document_id:
                raise ValueError("Document ID cannot be empty")
            
            if not content_vector:
                raise ValueError("Content vector cannot be empty")
            
            # Simulate indexing operation
            await asyncio.sleep(0.05)
            
            # Simulate potential failures
            import random
            if random.random() < 0.05:  # 5% chance of failure
                raise Exception("Indexing service temporarily unavailable")
            
            # Log successful indexing
            self.error_service.logging_service.log_business_metric(
                metric_name="documents_indexed",
                metric_value=1,
                metric_type="counter",
                tags={"service": "vector_store"}
            )
            
            return True
            
        except Exception as e:
            # Log additional context for indexing failures
            error_id = self.error_service.log_error(
                error=e,
                service="vector_store",
                operation="index_document",
                additional_context={
                    "document_id": document_id,
                    "vector_dimension": len(content_vector) if content_vector else 0,
                    "metadata_keys": list(metadata.keys()) if metadata else []
                }
            )
            
            self.logger.error(f"Document indexing failed [{error_id}]: {e}")
            raise


class EnhancedDatabaseService:
    """
    Example integration of error logging with database operations.
    """
    
    def __init__(self):
        self.error_service = get_error_logging_service()
        self.logger = get_logger("database_service")
    
    @handle_database_errors("execute_query")
    @with_recovery("retry_with_backoff")
    async def execute_query(self, query: str, 
                          parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute database query with comprehensive error logging.
        
        Args:
            query: SQL query to execute
            parameters: Query parameters
            
        Returns:
            Query results
        """
        start_time = datetime.now()
        
        try:
            # Validate query
            if not query or not query.strip():
                raise ValueError("Query cannot be empty")
            
            # Simulate database operation
            await asyncio.sleep(0.02)
            
            # Simulate potential database issues
            import random
            failure_type = random.random()
            
            if failure_type < 0.02:  # 2% chance of connection error
                raise ConnectionError("Database connection lost")
            elif failure_type < 0.04:  # 2% chance of timeout
                raise TimeoutError("Query timeout exceeded")
            elif failure_type < 0.05:  # 1% chance of integrity error
                raise Exception("IntegrityError: Constraint violation")
            
            # Mock results
            results = [{"id": 1, "data": "sample"}]
            
            # Log performance metrics
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self.error_service.logging_service.log_performance(
                service="database",
                operation="execute_query",
                duration_ms=duration,
                success=True,
                metadata={
                    "query_length": len(query),
                    "parameter_count": len(parameters) if parameters else 0,
                    "result_count": len(results)
                }
            )
            
            return results
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log performance metrics for failed queries too
            self.error_service.logging_service.log_performance(
                service="database",
                operation="execute_query",
                duration_ms=duration,
                success=False,
                metadata={
                    "query_length": len(query) if query else 0,
                    "parameter_count": len(parameters) if parameters else 0,
                    "error_type": type(e).__name__
                }
            )
            
            raise
    
    @handle_database_errors("transaction")
    async def execute_transaction(self, operations: List[Dict[str, Any]]) -> bool:
        """
        Execute database transaction with error logging.
        
        Args:
            operations: List of database operations to execute in transaction
            
        Returns:
            True if transaction successful
        """
        transaction_id = f"txn_{datetime.now().timestamp()}"
        
        try:
            if not operations:
                raise ValueError("Transaction cannot be empty")
            
            # Log transaction start
            self.error_service.logging_service.log_structured(
                level="INFO",
                service="database",
                operation="transaction_start",
                message=f"Starting transaction {transaction_id}",
                metadata={
                    "transaction_id": transaction_id,
                    "operation_count": len(operations)
                }
            )
            
            # Simulate transaction execution
            for i, operation in enumerate(operations):
                await asyncio.sleep(0.01)
                
                # Simulate potential failure in transaction
                import random
                if random.random() < 0.03:  # 3% chance of failure
                    raise Exception(f"Transaction failed at operation {i+1}")
            
            # Log successful transaction
            self.error_service.logging_service.log_business_metric(
                metric_name="transactions_completed",
                metric_value=1,
                metric_type="counter",
                tags={"service": "database", "operation_count": str(len(operations))}
            )
            
            return True
            
        except Exception as e:
            # Log transaction failure with context
            error_id = self.error_service.log_error(
                error=e,
                service="database",
                operation="transaction",
                additional_context={
                    "transaction_id": transaction_id,
                    "operation_count": len(operations),
                    "operations": [op.get("type", "unknown") for op in operations]
                }
            )
            
            self.logger.error(f"Transaction {transaction_id} failed [{error_id}]: {e}")
            raise


class EnhancedAIService:
    """
    Example integration of error logging with AI service operations.
    """
    
    def __init__(self):
        self.error_service = get_error_logging_service()
        self.logger = get_logger("ai_service")
    
    @handle_ai_errors("generate_response")
    @with_recovery("retry_with_fallback")
    async def generate_response(self, prompt: str, 
                              context: Optional[str] = None,
                              max_tokens: int = 1000) -> str:
        """
        Generate AI response with comprehensive error logging.
        
        Args:
            prompt: Input prompt for AI
            context: Optional context information
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated response text
        """
        start_time = datetime.now()
        
        try:
            # Validate inputs
            if not prompt or not prompt.strip():
                raise ValueError("Prompt cannot be empty")
            
            if max_tokens <= 0:
                raise ValueError("max_tokens must be positive")
            
            # Simulate AI service call
            await asyncio.sleep(0.5)  # Simulate AI processing time
            
            # Simulate potential AI service issues
            import random
            failure_type = random.random()
            
            if failure_type < 0.05:  # 5% chance of service unavailable
                raise ConnectionError("AI service temporarily unavailable")
            elif failure_type < 0.08:  # 3% chance of rate limit
                raise Exception("RateLimitError: API rate limit exceeded")
            elif failure_type < 0.10:  # 2% chance of content filter
                raise Exception("ContentFilterError: Content violates policy")
            
            # Generate mock response
            response = f"AI response to: {prompt[:50]}..."
            
            # Log successful generation
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self.error_service.logging_service.log_performance(
                service="ai_service",
                operation="generate_response",
                duration_ms=duration,
                success=True,
                metadata={
                    "prompt_length": len(prompt),
                    "context_provided": context is not None,
                    "max_tokens": max_tokens,
                    "response_length": len(response)
                }
            )
            
            # Log business metrics
            self.error_service.logging_service.log_business_metric(
                metric_name="ai_responses_generated",
                metric_value=1,
                metric_type="counter",
                tags={"service": "ai_service"}
            )
            
            return response
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log performance metrics for failed requests
            self.error_service.logging_service.log_performance(
                service="ai_service",
                operation="generate_response",
                duration_ms=duration,
                success=False,
                metadata={
                    "prompt_length": len(prompt) if prompt else 0,
                    "context_provided": context is not None,
                    "max_tokens": max_tokens,
                    "error_type": type(e).__name__
                }
            )
            
            raise


class ErrorLoggingMiddleware:
    """
    Middleware for automatic error logging in web applications.
    
    This can be integrated with FastAPI or other web frameworks
    to automatically log all unhandled errors.
    """
    
    def __init__(self):
        self.error_service = get_error_logging_service()
        self.logger = get_logger("error_middleware")
    
    async def __call__(self, request, call_next):
        """
        Process request with automatic error logging.
        
        Args:
            request: HTTP request object
            call_next: Next middleware/handler in chain
            
        Returns:
            HTTP response
        """
        start_time = datetime.now()
        
        try:
            # Extract request context
            request_context = {
                "method": getattr(request, "method", "unknown"),
                "url": str(getattr(request, "url", "unknown")),
                "user_agent": getattr(request.headers, "user-agent", "unknown") if hasattr(request, "headers") else "unknown",
                "request_id": getattr(request.state, "request_id", None) if hasattr(request, "state") else None
            }
            
            # Process request
            response = await call_next(request)
            
            # Log successful request
            duration = (datetime.now() - start_time).total_seconds() * 1000
            self.error_service.logging_service.log_performance(
                service="api",
                operation=f"{request_context['method']}_{request_context['url']}",
                duration_ms=duration,
                success=True,
                metadata=request_context
            )
            
            return response
            
        except Exception as e:
            # Log request error
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            error_id = self.error_service.log_error(
                error=e,
                service="api",
                operation="request_processing",
                additional_context={
                    **request_context,
                    "duration_ms": duration
                },
                custom_severity=ErrorSeverity.HIGH,
                custom_category=ErrorCategory.SERVICE_FAILURE
            )
            
            self.logger.error(f"Request processing failed [{error_id}]: {e}")
            
            # Log performance metrics for failed requests
            self.error_service.logging_service.log_performance(
                service="api",
                operation=f"{request_context['method']}_{request_context['url']}",
                duration_ms=duration,
                success=False,
                metadata={
                    **request_context,
                    "error_id": error_id,
                    "error_type": type(e).__name__
                }
            )
            
            raise


# Example usage and integration patterns
async def demonstrate_error_logging_integration():
    """
    Demonstrate how to use the error logging service with various components.
    """
    logger.info("Starting error logging integration demonstration")
    
    # Initialize services
    vector_service = EnhancedVectorStoreService()
    db_service = EnhancedDatabaseService()
    ai_service = EnhancedAIService()
    
    # Demonstrate vector store operations
    try:
        query_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        results = await vector_service.search_vectors(query_vector, top_k=5)
        logger.info(f"Vector search returned {len(results)} results")
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
    
    # Demonstrate database operations
    try:
        query_results = await db_service.execute_query(
            "SELECT * FROM documents WHERE active = ?",
            {"active": True}
        )
        logger.info(f"Database query returned {len(query_results)} results")
    except Exception as e:
        logger.error(f"Database query failed: {e}")
    
    # Demonstrate AI service operations
    try:
        response = await ai_service.generate_response(
            "What is the meaning of life?",
            context="Philosophy discussion",
            max_tokens=500
        )
        logger.info(f"AI generated response: {response[:100]}...")
    except Exception as e:
        logger.error(f"AI response generation failed: {e}")
    
    # Get error summary
    error_service = get_error_logging_service()
    summary = error_service.get_error_summary(hours=1)
    
    logger.info(f"Error summary: {summary['total_errors']} errors in the last hour")
    logger.info(f"Error categories: {summary['error_categories']}")
    
    return summary


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(demonstrate_error_logging_integration())