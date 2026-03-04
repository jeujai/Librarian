"""
Ollama Client for Local LLM Inference.

This module provides a client for interacting with Ollama, enabling local LLM
inference using models like DeepSeek-R1 running on the host machine with GPU
acceleration via Metal (Apple Silicon).

The client is designed to be called from Docker containers, connecting to
Ollama running natively on the host for optimal GPU performance.

IMPORTANT: This client provides BOTH sync and async interfaces:
- Use sync methods (generate_sync, is_available_sync) in Celery workers
- Use async methods (generate, is_available) in FastAPI async contexts
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class OllamaResponse:
    """Response from Ollama API."""
    content: str
    model: str
    total_duration_ns: int
    load_duration_ns: int
    prompt_eval_count: int
    eval_count: int
    error: Optional[str] = None
    
    @property
    def total_duration_ms(self) -> float:
        """Get total duration in milliseconds."""
        return self.total_duration_ns / 1_000_000
    
    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens per second."""
        if self.total_duration_ns > 0:
            return (self.eval_count / self.total_duration_ns) * 1_000_000_000
        return 0.0
    
    def is_successful(self) -> bool:
        """Check if the response was successful."""
        return self.error is None and bool(self.content.strip())


class OllamaClient:
    """
    Client for Ollama local LLM inference.
    
    Connects to Ollama running on the host machine (outside Docker) to leverage
    Metal GPU acceleration on Apple Silicon Macs.
    
    Usage:
        client = OllamaClient()
        response = await client.generate("What is the capital of France?")
        print(response.content)
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        """
        Initialize the Ollama client.
        
        Args:
            host: Ollama API host URL. Defaults to settings.ollama_host.
            model: Model to use. Defaults to settings.ollama_model.
            timeout: Request timeout in seconds. Defaults to settings.ollama_timeout.
        """
        self.settings = get_settings()
        self.host = host or self.settings.ollama_host
        self.model = model or self.settings.ollama_model
        self.timeout = timeout or self.settings.ollama_timeout
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_tokens_generated': 0,
            'total_duration_ms': 0.0
        }
        
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.host,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def is_available(self, force_check: bool = False) -> bool:
        """
        Check if Ollama is available and the model is loaded.
        
        Args:
            force_check: Force a fresh check even if cached.
            
        Returns:
            True if Ollama is available and model exists.
        """
        if self._available is not None and not force_check:
            return self._available
        
        try:
            client = await self._get_client()
            
            # Check if Ollama is running
            response = await client.get("/api/tags")
            if response.status_code != 200:
                self._available = False
                return False
            
            # Check if our model is available
            data = response.json()
            models = [m.get('name', '') for m in data.get('models', [])]
            
            # Check for exact match or partial match (model:tag format)
            model_available = any(
                self.model in m or m.startswith(self.model.split(':')[0])
                for m in models
            )
            
            if not model_available:
                logger.warning(
                    f"Ollama model '{self.model}' not found. "
                    f"Available models: {models}"
                )
                self._available = False
                return False
            
            self._available = True
            logger.info(f"Ollama available with model: {self.model}")
            return True
            
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self._available = False
            return False
    
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        **kwargs
    ) -> OllamaResponse:
        """
        Generate text using Ollama.
        
        Args:
            prompt: The prompt to generate from.
            system: Optional system prompt.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters for the API.
            
        Returns:
            OllamaResponse with generated content.
        """
        self.stats['total_requests'] += 1
        
        try:
            client = await self._get_client()
            
            # Build request payload
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    **kwargs.get('options', {})
                }
            }
            
            if system:
                payload["system"] = system
            
            # Make the request
            response = await client.post("/api/generate", json=payload)
            
            if response.status_code != 200:
                error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                self.stats['failed_requests'] += 1
                return OllamaResponse(
                    content="",
                    model=self.model,
                    total_duration_ns=0,
                    load_duration_ns=0,
                    prompt_eval_count=0,
                    eval_count=0,
                    error=error_msg
                )
            
            data = response.json()
            
            # Extract response
            result = OllamaResponse(
                content=data.get('response', ''),
                model=data.get('model', self.model),
                total_duration_ns=data.get('total_duration', 0),
                load_duration_ns=data.get('load_duration', 0),
                prompt_eval_count=data.get('prompt_eval_count', 0),
                eval_count=data.get('eval_count', 0)
            )
            
            # Update statistics
            self.stats['successful_requests'] += 1
            self.stats['total_tokens_generated'] += result.eval_count
            self.stats['total_duration_ms'] += result.total_duration_ms
            
            logger.debug(
                f"Ollama generated {result.eval_count} tokens in "
                f"{result.total_duration_ms:.1f}ms "
                f"({result.tokens_per_second:.1f} tok/s)"
            )
            
            return result
            
        except httpx.TimeoutException:
            error_msg = f"Ollama request timed out after {self.timeout}s"
            logger.error(error_msg)
            self.stats['failed_requests'] += 1
            return OllamaResponse(
                content="",
                model=self.model,
                total_duration_ns=0,
                load_duration_ns=0,
                prompt_eval_count=0,
                eval_count=0,
                error=error_msg
            )
            
        except Exception as e:
            error_msg = f"Ollama generation failed: {e}"
            logger.error(error_msg)
            self.stats['failed_requests'] += 1
            return OllamaResponse(
                content="",
                model=self.model,
                total_duration_ns=0,
                load_duration_ns=0,
                prompt_eval_count=0,
                eval_count=0,
                error=error_msg
            )
    
    async def chat(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1000,
        **kwargs
    ) -> OllamaResponse:
        """
        Chat completion using Ollama.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters.
            
        Returns:
            OllamaResponse with generated content.
        """
        self.stats['total_requests'] += 1
        
        try:
            client = await self._get_client()
            
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    **kwargs.get('options', {})
                }
            }
            
            response = await client.post("/api/chat", json=payload)
            
            if response.status_code != 200:
                error_msg = f"Ollama chat API error: {response.status_code}"
                logger.error(error_msg)
                self.stats['failed_requests'] += 1
                return OllamaResponse(
                    content="",
                    model=self.model,
                    total_duration_ns=0,
                    load_duration_ns=0,
                    prompt_eval_count=0,
                    eval_count=0,
                    error=error_msg
                )
            
            data = response.json()
            message = data.get('message', {})
            
            result = OllamaResponse(
                content=message.get('content', ''),
                model=data.get('model', self.model),
                total_duration_ns=data.get('total_duration', 0),
                load_duration_ns=data.get('load_duration', 0),
                prompt_eval_count=data.get('prompt_eval_count', 0),
                eval_count=data.get('eval_count', 0)
            )
            
            self.stats['successful_requests'] += 1
            self.stats['total_tokens_generated'] += result.eval_count
            self.stats['total_duration_ms'] += result.total_duration_ms
            
            return result
            
        except Exception as e:
            error_msg = f"Ollama chat failed: {e}"
            logger.error(error_msg)
            self.stats['failed_requests'] += 1
            return OllamaResponse(
                content="",
                model=self.model,
                total_duration_ns=0,
                load_duration_ns=0,
                prompt_eval_count=0,
                eval_count=0,
                error=error_msg
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics."""
        stats = self.stats.copy()
        if stats['successful_requests'] > 0:
            stats['avg_tokens_per_request'] = (
                stats['total_tokens_generated'] / stats['successful_requests']
            )
            stats['avg_duration_ms'] = (
                stats['total_duration_ms'] / stats['successful_requests']
            )
        else:
            stats['avg_tokens_per_request'] = 0
            stats['avg_duration_ms'] = 0
        return stats


# Singleton instance
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get the singleton Ollama client instance."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


async def cleanup_ollama_client():
    """Cleanup the Ollama client."""
    global _ollama_client
    if _ollama_client is not None:
        await _ollama_client.close()
        _ollama_client = None
