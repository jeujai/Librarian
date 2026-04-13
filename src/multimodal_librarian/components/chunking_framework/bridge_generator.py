"""
Smart Bridge Generator with Multi-Provider LLM Support.

This module implements LLM-powered bridge generation supporting multiple providers:
- Ollama (local, fast, GPU-accelerated via Metal on Apple Silicon)
- Gemini 2.5 Flash (cloud, higher quality)

The provider can be configured via BRIDGE_GENERATION_PROVIDER environment variable.
Default is "ollama" for faster local processing.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import google.generativeai as genai
    from google.generativeai.types import HarmBlockThreshold, HarmCategory
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

from ...clients.ollama_client import OllamaClient, get_ollama_client
from ...config import get_settings
from ...models.chunking import BridgeChunk, DomainConfig, GapAnalysis
from ...models.core import BridgeStrategy, ContentType
from ...services.ollama_pool_manager import PoolExhaustedError, submit_ollama_work

logger = logging.getLogger(__name__)


@dataclass
class BridgeGenerationRequest:
    """Request for bridge generation between two chunks."""
    chunk1_content: str
    chunk2_content: str
    chunk1_id: str
    chunk2_id: str
    gap_analysis: GapAnalysis
    content_type: ContentType
    domain_config: Optional[DomainConfig] = None
    context: Optional[str] = None
    bisected_concepts: Optional[List[str]] = None
    
    def get_request_id(self) -> str:
        """Generate unique request ID."""
        return f"{self.chunk1_id}_{self.chunk2_id}_{int(time.time())}"


@dataclass
class BridgeGenerationResult:
    """Result of bridge generation."""
    request_id: str
    bridge_content: str
    generation_method: str
    confidence_score: float
    generation_time: float
    token_usage: Dict[str, int]
    error: Optional[str] = None
    
    def is_successful(self) -> bool:
        """Check if generation was successful."""
        return self.error is None and bool(self.bridge_content.strip())


@dataclass
class BatchGenerationStats:
    """Statistics for batch generation."""
    total_requests: int
    successful_generations: int
    failed_generations: int
    total_tokens_used: int
    total_cost_estimate: float
    average_generation_time: float
    batch_processing_time: float


class SmartBridgeGenerator:
    """
    Smart bridge generator supporting multiple LLM providers.
    
    Supports:
    - Ollama (local, fast, GPU-accelerated) - default
    - Gemini 2.5 Flash (cloud, higher quality)
    
    The provider is selected via settings.bridge_generation_provider.
    
    IMPORTANT: LLM initialization is LAZY to avoid blocking the event loop.
    The model is only initialized on first use, not during __init__.
    """
    
    def __init__(self):
        """Initialize the smart bridge generator.
        
        NOTE: Does NOT initialize LLM here to avoid blocking the event loop.
        LLM is initialized lazily on first use.
        """
        self.settings = get_settings()
        
        # Provider selection
        self.provider = getattr(self.settings, 'bridge_generation_provider', 'ollama')
        
        # Lazy initialization - models are None until first use
        self._gemini_model = None
        self._gemini_initialized = False
        self._ollama_client: Optional[OllamaClient] = None
        self._ollama_available: Optional[bool] = None
        
        # Generation statistics
        self.generation_stats = {
            'total_requests': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'provider_used': {}
        }
        
        # Rate limiting (mainly for Gemini)
        self.rate_limit_delay = 0.1  # Reduced from 1.0s for faster processing
        self.last_request_time = 0.0
        
        # Batch processing configuration
        self.batch_size = 60  # Process 60 at a time (3 rounds of 20 workers)
        self.batch_timeout = 30.0  # Timeout for batch processing
        
        # Thread-local state preserved for httpx.AsyncClient compatibility
        import threading
        self._thread_local = threading.local()
        
        # Domain-specific prompting strategies (no blocking calls)
        self.domain_strategies = self._initialize_domain_strategies()
        
        # Cost optimization settings
        self.cost_optimization = {
            'max_tokens_per_request': 1000,
            'use_batch_processing': True,
            'adaptive_token_limits': True,
            'cost_threshold_per_batch': 0.10  # USD
        }
        
        logger.info(f"Bridge generator initialized with provider: {self.provider}")
    
    @property
    def model(self):
        """Lazy property to get the Gemini model. Initializes on first access."""
        if not self._gemini_initialized:
            self._initialize_gemini()
        return self._gemini_model
    
    def _get_model(self):
        """Get the Gemini model, initializing lazily if needed."""
        return self.model
    
    async def _get_ollama_client(self) -> Optional[OllamaClient]:
        """Get Ollama client, checking availability.
        
        Uses a per-thread cached client to avoid creating a new
        OllamaClient + httpx.AsyncClient + availability HTTP check
        on every single bridge call. Thread-local storage is used
        because each thread pool worker has its own event loop.
        """
        import threading
        local = self._thread_local
        client = getattr(local, 'ollama_client', None)
        if client is not None:
            return client
        
        # First call on this thread — create and check once
        client = OllamaClient()
        is_available = await client.is_available()
        if is_available:
            local.ollama_client = client
            return client
        else:
            logger.warning(
                "Ollama not available, will fall back to "
                "Gemini or mechanical"
            )
            return None
    
    def _initialize_gemini(self):
        """Initialize Gemini API client (called lazily on first use).
        
        WARNING: This method performs blocking I/O. It should only be called
        when actually needed for bridge generation, not during startup.
        """
        if self._gemini_initialized:
            return
            
        self._gemini_initialized = True  # Mark as initialized even if it fails
        
        if not GEMINI_AVAILABLE:
            logger.warning("google-generativeai not installed - Gemini unavailable")
            self._gemini_model = None
            return
        
        try:
            api_key = getattr(self.settings, 'GEMINI_API_KEY', None) or getattr(self.settings, 'gemini_api_key', None)
            if not api_key:
                logger.warning("GEMINI_API_KEY not found in settings - Gemini unavailable")
                self._gemini_model = None
                return
            
            genai.configure(api_key=api_key)
            
            # Configure the model
            self._gemini_model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",  # Using Gemini 2.5 Flash
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,  # Lower temperature for more consistent bridges
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=1000,
                    candidate_count=1
                ),
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            )
            
            logger.info("Initialized Gemini 2.5 Flash for bridge generation (lazy init)")
        
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API: {e}")
            self._gemini_model = None
    
    def _initialize_domain_strategies(self) -> Dict[ContentType, Dict[str, Any]]:
        """Initialize domain-specific prompting strategies."""
        return {
            ContentType.TECHNICAL: {
                'prompt_template': """You are creating a bridge between two technical content sections. 
Create a smooth transition that maintains technical accuracy and context flow.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains technical terminology consistency
2. Preserves code context and API relationships
3. Ensures logical flow of technical concepts
4. Keeps the bridge concise (2-3 sentences maximum)

Bridge:""",
                'max_tokens': 800,
                'temperature': 0.2,
                'focus_areas': ['technical_accuracy', 'api_continuity', 'code_context']
            },
            
            ContentType.MEDICAL: {
                'prompt_template': """You are creating a bridge between two medical content sections.
Create a transition that maintains clinical accuracy and patient safety context.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains medical terminology precision
2. Preserves clinical context and safety information
3. Ensures logical flow of medical concepts
4. Prioritizes patient safety considerations
5. Keeps the bridge concise (2-3 sentences maximum)

Bridge:""",
                'max_tokens': 900,
                'temperature': 0.1,  # Very low temperature for medical accuracy
                'focus_areas': ['clinical_accuracy', 'safety_continuity', 'medical_terminology']
            },
            
            ContentType.LEGAL: {
                'prompt_template': """You are creating a bridge between two legal content sections.
Create a transition that maintains legal precision and statutory context.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains legal terminology precision
2. Preserves statutory and regulatory context
3. Ensures logical flow of legal concepts
4. Maintains formal legal tone
5. Keeps the bridge concise (2-3 sentences maximum)

Bridge:""",
                'max_tokens': 1000,
                'temperature': 0.15,
                'focus_areas': ['legal_precision', 'statutory_flow', 'precedent_continuity']
            },
            
            ContentType.ACADEMIC: {
                'prompt_template': """You are creating a bridge between two academic content sections.
Create a transition that maintains scholarly rigor and research context.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains academic terminology and rigor
2. Preserves research methodology context
3. Ensures logical flow of academic concepts
4. Maintains scholarly tone
5. Keeps the bridge concise (2-3 sentences maximum)

Bridge:""",
                'max_tokens': 900,
                'temperature': 0.25,
                'focus_areas': ['research_continuity', 'methodological_flow', 'academic_rigor']
            },
            
            ContentType.NARRATIVE: {
                'prompt_template': """You are creating a bridge between two narrative content sections.
Create a transition that maintains story flow and character continuity.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains narrative voice and tone
2. Preserves character and scene continuity
3. Ensures smooth story progression
4. Maintains reader engagement
5. Keeps the bridge concise (1-2 sentences maximum)

Bridge:""",
                'max_tokens': 600,
                'temperature': 0.4,  # Higher temperature for creative flow
                'focus_areas': ['narrative_flow', 'character_continuity', 'scene_transition']
            },
            
            ContentType.GENERAL: {
                'prompt_template': """You are creating a bridge between two content sections.
Create a smooth transition that maintains context and readability.

CHUNK 1 (ending):
{chunk1_end}

CHUNK 2 (beginning):
{chunk2_start}

Gap Analysis: {gap_summary}

Create a bridge that:
1. Maintains consistent tone and style
2. Preserves conceptual flow
3. Ensures smooth transition between ideas
4. Keeps the bridge concise (2-3 sentences maximum)

Bridge:""",
                'max_tokens': 700,
                'temperature': 0.3,
                'focus_areas': ['conceptual_flow', 'tone_consistency', 'readability']
            }
        }
    
    def generate_bridge(self, chunk1: str, chunk2: str, gap_analysis: GapAnalysis,
                       content_type: ContentType = ContentType.GENERAL,
                       domain_config: Optional[DomainConfig] = None,
                       context: Optional[str] = None,
                       bisected_concepts: Optional[List[str]] = None) -> BridgeChunk:
        """
        Generate contextual bridge using Gemini 2.5 Flash.
        
        Args:
            chunk1: Content of first chunk
            chunk2: Content of second chunk
            gap_analysis: Analysis of the gap between chunks
            content_type: Type of content for domain-specific generation
            domain_config: Domain configuration for thresholds
            context: Additional context for generation
            bisected_concepts: Optional list of concept names bisected at this boundary
            
        Returns:
            BridgeChunk with generated bridge content
        """
        request = BridgeGenerationRequest(
            chunk1_content=chunk1,
            chunk2_content=chunk2,
            chunk1_id="chunk1",
            chunk2_id="chunk2",
            gap_analysis=gap_analysis,
            content_type=content_type,
            domain_config=domain_config,
            context=context,
            bisected_concepts=bisected_concepts
        )
        
        result = self._generate_single_bridge(request)
        
        return BridgeChunk(
            content=result.bridge_content,
            source_chunks=[request.chunk1_id, request.chunk2_id],
            generation_method=result.generation_method,
            gap_analysis=gap_analysis,
            confidence_score=result.confidence_score,
            created_at=datetime.now()
        )
    
    def batch_generate_bridges(self, boundary_pairs: List[Tuple[str, str, GapAnalysis]],
                             content_type: ContentType = ContentType.GENERAL,
                             domain_config: Optional[DomainConfig] = None,
                             bisected_concepts_per_boundary: Optional[Dict[int, List[str]]] = None,
                             progress_callback: Optional[callable] = None,
                             storage_callback: Optional[callable] = None) -> Tuple[List[BridgeChunk], BatchGenerationStats]:
        """
        Batch process multiple bridges for cost optimization.
        
        Args:
            boundary_pairs: List of (chunk1, chunk2, gap_analysis) tuples
            content_type: Type of content for domain-specific generation
            domain_config: Domain configuration
            bisected_concepts_per_boundary: Optional mapping from boundary index
                to list of bisected concept names for prompt augmentation
            progress_callback: Optional callback for progress reporting
            storage_callback: Optional async callback for incremental storage.
                Called after each batch of bridges is generated and validated.
                Signature: async def callback(bridges: List[BridgeChunk]) -> None
                This enables incremental storage to preserve progress on failure.
            
        Returns:
            Tuple of (List of BridgeChunk objects, BatchGenerationStats)
        """
        logger.info(f"Starting batch generation for {len(boundary_pairs)} bridge requests")
        
        # Create requests
        requests = []
        for i, (chunk1, chunk2, gap_analysis) in enumerate(boundary_pairs):
            concepts = None
            if bisected_concepts_per_boundary and i in bisected_concepts_per_boundary:
                concepts = bisected_concepts_per_boundary[i]
            request = BridgeGenerationRequest(
                chunk1_content=chunk1,
                chunk2_content=chunk2,
                chunk1_id=f"chunk_{i}",
                chunk2_id=f"chunk_{i+1}",
                gap_analysis=gap_analysis,
                content_type=content_type,
                domain_config=domain_config,
                bisected_concepts=concepts
            )
            requests.append(request)
        
        # Process in batches
        bridge_chunks = []
        batch_stats = BatchGenerationStats(
            total_requests=len(requests),
            successful_generations=0,
            failed_generations=0,
            total_tokens_used=0,
            total_cost_estimate=0.0,
            average_generation_time=0.0,
            batch_processing_time=0.0
        )
        
        start_time = time.time()
        
        for i in range(0, len(requests), self.batch_size):
            batch = requests[i:i + self.batch_size]
            batch_results = self._process_batch(batch)
            
            # Collect bridges generated in this batch for incremental storage
            batch_bridges = []
            
            for request, result in zip(batch, batch_results):
                if result.is_successful():
                    bridge_chunk = BridgeChunk(
                        content=result.bridge_content,
                        source_chunks=[request.chunk1_id, request.chunk2_id],
                        generation_method=result.generation_method,
                        gap_analysis=request.gap_analysis,
                        confidence_score=result.confidence_score,
                        created_at=datetime.now()
                    )
                    bridge_chunks.append(bridge_chunk)
                    batch_bridges.append(bridge_chunk)
                    batch_stats.successful_generations += 1
                else:
                    logger.warning(f"Failed to generate bridge for {result.request_id}: {result.error}")
                    batch_stats.failed_generations += 1
                
                # Update statistics
                batch_stats.total_tokens_used += result.token_usage.get('total_tokens', 0)
                batch_stats.total_cost_estimate += self._estimate_cost(result.token_usage)
            
            # Invoke storage callback for incremental storage after each batch
            # This ensures bridges are stored immediately, preserving progress on failure
            if storage_callback and batch_bridges:
                try:
                    storage_callback(batch_bridges)
                except Exception as e:
                    logger.error(f"Storage callback failed for batch: {e}")
                    # Re-raise to propagate storage failures
                    raise
            
            # Report incremental progress after each batch
            if progress_callback:
                try:
                    progress_callback(
                        bridges_so_far=len(bridge_chunks),
                        total_bridges=len(requests),
                        failed=batch_stats.failed_generations,
                    )
                except Exception:
                    pass  # Don't let callback errors break generation
        
        batch_stats.batch_processing_time = time.time() - start_time
        batch_stats.average_generation_time = (
            batch_stats.batch_processing_time / batch_stats.total_requests
            if batch_stats.total_requests > 0 else 0.0
        )
        
        logger.info(f"Batch generation completed: {batch_stats.successful_generations}/{batch_stats.total_requests} successful")
        logger.info(f"Total tokens used: {batch_stats.total_tokens_used}, Estimated cost: ${batch_stats.total_cost_estimate:.4f}")
        
        return (bridge_chunks, batch_stats)
    
    def _generate_single_bridge(self, request: BridgeGenerationRequest) -> BridgeGenerationResult:
        """Generate a single bridge with error handling and rate limiting."""
        start_time = time.time()
        
        # Rate limiting (mainly for Gemini)
        if self.provider == 'gemini':
            self._apply_rate_limiting()
        
        try:
            # Create adaptive prompt
            prompt = self.create_adaptive_prompt(
                request.chunk1_content,
                request.chunk2_content,
                request.gap_analysis,
                request.content_type,
                request.domain_config,
                bisected_concepts=request.bisected_concepts
            )
            
            # Try Ollama first if configured
            if self.provider == 'ollama':
                result = self._generate_with_ollama_sync(request, prompt, start_time)
                if result.is_successful():
                    return result
                # Fall through to Gemini if Ollama fails
                logger.info("Ollama generation failed, falling back to Gemini")
            
            # Try Gemini
            if self.model is not None:
                result = self._generate_with_gemini(request, prompt, start_time)
                if result.is_successful():
                    return result
            
            # Fallback to mechanical bridge
            bridge_content = self._generate_mechanical_fallback(
                request.chunk1_content, request.chunk2_content
            )
            generation_time = time.time() - start_time
            
            self.generation_stats['total_requests'] += 1
            self.generation_stats['successful_generations'] += 1
            self._track_provider('mechanical_fallback')
            
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content=bridge_content,
                generation_method="mechanical_fallback",
                confidence_score=0.5,
                generation_time=generation_time,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
            )
        
        except Exception as e:
            logger.error(f"Failed to generate bridge: {e}")
            
            # Fallback to mechanical bridge
            bridge_content = self._generate_mechanical_fallback(
                request.chunk1_content, request.chunk2_content
            )
            
            generation_time = time.time() - start_time
            
            self.generation_stats['total_requests'] += 1
            self.generation_stats['failed_generations'] += 1
            
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content=bridge_content,
                generation_method="mechanical_fallback",
                confidence_score=0.4,
                generation_time=generation_time,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                error=str(e)
            )
    
    def _generate_with_ollama_sync(
        self,
        request: BridgeGenerationRequest,
        prompt: str,
        start_time: float
    ) -> BridgeGenerationResult:
        """Generate bridge using Ollama (sync wrapper).

        Always runs inside a ThreadPoolExecutor worker, so there
        is never a running event loop. We reuse a per-thread event
        loop so the cached httpx.AsyncClient stays valid across
        calls on the same thread.
        """
        try:
            local = self._thread_local
            loop = getattr(local, 'event_loop', None)
            if loop is None or loop.is_closed():
                loop = asyncio.new_event_loop()
                local.event_loop = loop
            return loop.run_until_complete(
                self._generate_with_ollama_async(
                    request, prompt, start_time
                )
            )
        except Exception as e:
            logger.warning(f"Ollama sync wrapper failed: {e}")
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content="",
                generation_method="ollama_failed",
                confidence_score=0.0,
                generation_time=time.time() - start_time,
                token_usage={
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'total_tokens': 0
                },
                error=str(e)
            )
    
    async def _generate_with_ollama_async(
        self, 
        request: BridgeGenerationRequest, 
        prompt: str, 
        start_time: float
    ) -> BridgeGenerationResult:
        """Generate bridge using Ollama (async)."""
        ollama = await self._get_ollama_client()
        if ollama is None:
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content="",
                generation_method="ollama_unavailable",
                confidence_score=0.0,
                generation_time=time.time() - start_time,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                error="Ollama not available"
            )
        
        # System prompt for bridge generation
        system_prompt = (
            "You are a technical writer creating smooth transitions between document sections. "
            "Generate concise bridge text (2-3 sentences max) that connects the ideas naturally. "
            "Output ONLY the bridge text, no explanations or metadata."
        )
        
        response = await ollama.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.3,
            max_tokens=800  # Higher limit to accommodate reasoning model thinking tokens
        )
        
        if not response.is_successful():
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content="",
                generation_method="ollama_error",
                confidence_score=0.0,
                generation_time=time.time() - start_time,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                error=response.error
            )
        
        generation_time = time.time() - start_time
        
        # Clean up the response (remove any thinking tags from DeepSeek-R1)
        bridge_content = self._clean_ollama_response(response.content)
        
        # Update statistics
        self.generation_stats['total_requests'] += 1
        self.generation_stats['successful_generations'] += 1
        self.generation_stats['total_tokens'] += response.eval_count
        self._track_provider('ollama')
        
        return BridgeGenerationResult(
            request_id=request.get_request_id(),
            bridge_content=bridge_content,
            generation_method=f"ollama_{ollama.model}",
            confidence_score=0.75,  # Good confidence for local model
            generation_time=generation_time,
            token_usage={
                'input_tokens': response.prompt_eval_count,
                'output_tokens': response.eval_count,
                'total_tokens': response.prompt_eval_count + response.eval_count
            }
        )
    
    def _clean_ollama_response(self, content: str) -> str:
        """Clean Ollama response, removing thinking tags from DeepSeek-R1."""
        import re

        # If there's a </think> tag, extract only what comes after it
        if '</think>' in content:
            content = content.split('</think>')[-1]
        
        # Remove any remaining XML-like tags
        content = re.sub(r'<[^>]+>', '', content)
        
        # Clean up whitespace
        content = ' '.join(content.split())
        
        return content.strip()
    
    def _generate_with_gemini(
        self, 
        request: BridgeGenerationRequest, 
        prompt: str, 
        start_time: float
    ) -> BridgeGenerationResult:
        """Generate bridge using Gemini."""
        try:
            response = self.model.generate_content(prompt)
            
            if response.candidates and response.candidates[0].content.parts:
                bridge_content = response.candidates[0].content.parts[0].text.strip()
                generation_method = "gemini_2_5_flash"
                confidence_score = self._calculate_confidence_score(response, request.gap_analysis)
                token_usage = self._extract_token_usage(response)
            else:
                return BridgeGenerationResult(
                    request_id=request.get_request_id(),
                    bridge_content="",
                    generation_method="gemini_no_response",
                    confidence_score=0.0,
                    generation_time=time.time() - start_time,
                    token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                    error="No valid response from Gemini"
                )
            
            generation_time = time.time() - start_time
            
            # Update statistics
            self.generation_stats['total_requests'] += 1
            self.generation_stats['successful_generations'] += 1
            self.generation_stats['total_tokens'] += token_usage.get('total_tokens', 0)
            self.generation_stats['total_cost'] += self._estimate_cost(token_usage)
            self._track_provider('gemini')
            
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content=bridge_content,
                generation_method=generation_method,
                confidence_score=confidence_score,
                generation_time=generation_time,
                token_usage=token_usage
            )
            
        except Exception as e:
            logger.warning(f"Gemini generation failed: {e}")
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content="",
                generation_method="gemini_error",
                confidence_score=0.0,
                generation_time=time.time() - start_time,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                error=str(e)
            )
    
    def _track_provider(self, provider: str):
        """Track which provider was used."""
        if provider not in self.generation_stats['provider_used']:
            self.generation_stats['provider_used'][provider] = 0
        self.generation_stats['provider_used'][provider] += 1
    
    def _process_batch(self, requests: List[BridgeGenerationRequest]) -> List[BridgeGenerationResult]:
        """Process a batch of requests with true parallel execution via thread pool."""
        # Always use async batch processing with thread pool parallelism
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self._async_batch_process(requests))
            return results
        except Exception as e:
            logger.warning(f"Batch processing failed, falling back to sequential: {e}")
            # Fallback: run sequentially in current thread
            results = []
            for req in requests:
                results.append(self._generate_single_bridge(req))
            return results
        finally:
            if loop is not None:
                loop.close()
            # Do NOT touch the thread-local event loop here.
            # generate_bridges_task owns the persistent _task_loop and
            # will re-set it via asyncio.set_event_loop(_task_loop) after
            # batch_generate_bridges returns.
    
    async def _async_batch_process(self, requests: List[BridgeGenerationRequest]) -> List[BridgeGenerationResult]:
        """Asynchronously process batch requests."""
        tasks = []
        
        for request in requests:
            task = asyncio.create_task(self._async_generate_bridge(request))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Async generation failed for request {i}: {result}")
                # Create fallback result
                fallback_result = BridgeGenerationResult(
                    request_id=requests[i].get_request_id(),
                    bridge_content=self._generate_mechanical_fallback(
                        requests[i].chunk1_content, requests[i].chunk2_content
                    ),
                    generation_method="mechanical_fallback",
                    confidence_score=0.4,
                    generation_time=0.0,
                    token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                    error=str(result)
                )
                processed_results.append(fallback_result)
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _async_generate_bridge(self, request: BridgeGenerationRequest) -> BridgeGenerationResult:
        """Asynchronously generate a single bridge.
        
        Submits the blocking _generate_single_bridge to the shared Ollama
        pool with task_type="bridge" for fair share scheduling.
        Falls back to mechanical bridge generation if the pool is exhausted.
        """
        try:
            future = submit_ollama_work(
                self._generate_single_bridge, request,
                task_type="bridge"
            )
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, future.result)
        except PoolExhaustedError:
            logger.warning(
                "Shared Ollama pool exhausted, falling back to mechanical bridge "
                f"for request {request.get_request_id()}"
            )
            bridge_content = self._generate_mechanical_fallback(
                request.chunk1_content, request.chunk2_content
            )
            self.generation_stats['total_requests'] += 1
            self.generation_stats['successful_generations'] += 1
            self._track_provider('mechanical_fallback_pool_exhausted')
            return BridgeGenerationResult(
                request_id=request.get_request_id(),
                bridge_content=bridge_content,
                generation_method="mechanical_fallback",
                confidence_score=0.4,
                generation_time=0.0,
                token_usage={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                error="Pool exhausted"
            )
    
    def create_adaptive_prompt(self, chunk1: str, chunk2: str, gap_analysis: GapAnalysis,
                             content_type: ContentType, domain_config: Optional[DomainConfig],
                             bisected_concepts: Optional[List[str]] = None) -> str:
        """
        Create domain-specific bridge generation prompt.
        
        Args:
            chunk1: First chunk content
            chunk2: Second chunk content
            gap_analysis: Gap analysis results
            content_type: Content type for domain-specific prompting
            domain_config: Domain configuration
            bisected_concepts: Optional list of concept names bisected at this boundary
            
        Returns:
            Formatted prompt for bridge generation
        """
        # Get domain strategy
        strategy = self.domain_strategies.get(content_type, self.domain_strategies[ContentType.GENERAL])
        
        # Extract relevant portions of chunks for context
        chunk1_end = self._extract_chunk_end(chunk1, max_length=200)
        chunk2_start = self._extract_chunk_start(chunk2, max_length=200)
        
        # Create gap summary
        gap_summary = self._create_gap_summary(gap_analysis)
        
        # Format the prompt
        prompt = strategy['prompt_template'].format(
            chunk1_end=chunk1_end,
            chunk2_start=chunk2_start,
            gap_summary=gap_summary
        )
        
        # Add domain-specific context if available
        if domain_config and domain_config.bridge_thresholds:
            domain_context = self._create_domain_context(domain_config, content_type)
            prompt += f"\n\nDomain Context: {domain_context}"
        
        # Append concept-preservation instructions when bisected concepts exist
        if bisected_concepts:
            concept_list = "\n".join(f"  - {c}" for c in bisected_concepts)
            prompt += (
                f"\n\nCRITICAL: The following concepts were split across the chunk boundary. "
                f"You MUST include each of these concepts VERBATIM in your bridge text:\n"
                f"{concept_list}\n"
                f"Weave them naturally into the bridge while preserving the exact terminology."
            )
        
        return prompt

    def create_recovery_prompt(self, chunk1: str, chunk2: str,
                               bisected_concepts: List[str],
                               content_type: ContentType,
                               domain_config: Optional[DomainConfig] = None) -> str:
        """
        Create a prompt specifically for concept-recovery bridges.

        Uses a wider context window (recovery_bridge_context_chars from settings,
        default 400) and explicitly instructs the LLM to preserve each bisected
        concept verbatim in the bridge text.

        Args:
            chunk1: First chunk content (before the boundary)
            chunk2: Second chunk content (after the boundary)
            bisected_concepts: List of concept names that were bisected at this boundary
            content_type: Content type for domain-specific context
            domain_config: Optional domain configuration

        Returns:
            Formatted prompt for concept-recovery bridge generation
        """
        settings = get_settings()
        context_chars = settings.recovery_bridge_context_chars

        chunk1_end = self._extract_chunk_end(chunk1, max_length=context_chars)
        chunk2_start = self._extract_chunk_start(chunk2, max_length=context_chars)

        concept_list = "\n".join(f"  - {c}" for c in bisected_concepts)

        return (
            f"You are creating a concept-recovery bridge between two content sections. "
            f"The following concepts were split across the chunk boundary and MUST be "
            f"preserved verbatim in your bridge text:\n\n"
            f"BISECTED CONCEPTS (include each EXACTLY as written):\n{concept_list}\n\n"
            f"CHUNK 1 (ending):\n{chunk1_end}\n\n"
            f"CHUNK 2 (beginning):\n{chunk2_start}\n\n"
            f"Create a bridge of 2-3 sentences that:\n"
            f"1. Includes each bisected concept verbatim\n"
            f"2. Provides enough context for each concept to be meaningful\n"
            f"3. Maintains natural readability\n\n"
            f"Bridge:"
        )

    
    def _extract_chunk_end(self, chunk: str, max_length: int = 200) -> str:
        """Extract the end portion of a chunk for context."""
        if len(chunk) <= max_length:
            return chunk
        
        # Try to break at sentence boundary
        sentences = chunk.split('.')
        if len(sentences) > 1:
            # Take the last few sentences that fit within max_length
            result = ""
            for sentence in reversed(sentences[:-1]):  # Exclude empty last element
                candidate = sentence.strip() + ". " + result
                if len(candidate) <= max_length:
                    result = candidate
                else:
                    break
            
            if result:
                return result.strip()
        
        # Fallback to simple truncation
        return "..." + chunk[-max_length:]
    
    def _extract_chunk_start(self, chunk: str, max_length: int = 200) -> str:
        """Extract the start portion of a chunk for context."""
        if len(chunk) <= max_length:
            return chunk
        
        # Try to break at sentence boundary
        sentences = chunk.split('.')
        if len(sentences) > 1:
            # Take the first few sentences that fit within max_length
            result = ""
            for sentence in sentences[:-1]:  # Exclude empty last element
                candidate = result + sentence.strip() + ". "
                if len(candidate) <= max_length:
                    result = candidate
                else:
                    break
            
            if result:
                return result.strip()
        
        # Fallback to simple truncation
        return chunk[:max_length] + "..."
    
    def _create_gap_summary(self, gap_analysis: GapAnalysis) -> str:
        """Create a summary of gap analysis for the prompt."""
        summary_parts = []
        
        summary_parts.append(f"Gap Type: {gap_analysis.gap_type.value}")
        summary_parts.append(f"Necessity Score: {gap_analysis.necessity_score:.2f}")
        summary_parts.append(f"Semantic Distance: {gap_analysis.semantic_distance:.2f}")
        summary_parts.append(f"Concept Overlap: {gap_analysis.concept_overlap:.2f}")
        
        if gap_analysis.cross_reference_density > 0.1:
            summary_parts.append(f"Cross-reference Density: {gap_analysis.cross_reference_density:.2f}")
        
        if gap_analysis.domain_specific_gaps:
            top_gaps = sorted(gap_analysis.domain_specific_gaps.items(), 
                            key=lambda x: x[1], reverse=True)[:2]
            for gap_name, gap_value in top_gaps:
                summary_parts.append(f"{gap_name.replace('_', ' ').title()}: {gap_value:.2f}")
        
        return "; ".join(summary_parts)
    
    def _create_domain_context(self, domain_config: DomainConfig, content_type: ContentType) -> str:
        """Create domain-specific context for the prompt."""
        context_parts = []
        
        # Add relevant thresholds
        if domain_config.bridge_thresholds:
            relevant_thresholds = []
            for threshold_name, threshold_value in domain_config.bridge_thresholds.items():
                if threshold_value > 0.5:  # Only include significant thresholds
                    relevant_thresholds.append(f"{threshold_name}: {threshold_value:.2f}")
            
            if relevant_thresholds:
                context_parts.append(f"Key thresholds: {', '.join(relevant_thresholds)}")
        
        # Add preservation patterns
        if domain_config.preservation_patterns:
            context_parts.append(f"Preserve: {', '.join(domain_config.preservation_patterns[:2])}")
        
        return "; ".join(context_parts)
    
    def _generate_mechanical_fallback(self, chunk1: str, chunk2: str) -> str:
        """Generate a mechanical fallback bridge when LLM generation fails."""
        # Simple overlap-based bridge
        chunk1_words = chunk1.split()
        chunk2_words = chunk2.split()
        
        # Find overlapping words
        chunk1_end_words = set(chunk1_words[-10:]) if len(chunk1_words) >= 10 else set(chunk1_words)
        chunk2_start_words = set(chunk2_words[:10]) if len(chunk2_words) >= 10 else set(chunk2_words)
        
        overlap = chunk1_end_words.intersection(chunk2_start_words)
        
        if overlap:
            # Create bridge using overlapping concepts
            overlap_list = list(overlap)[:3]  # Limit to 3 words
            bridge = f"Building on the concepts of {', '.join(overlap_list)}, "
        else:
            # Generic transition
            bridge = "Continuing with the next section, "
        
        return bridge
    
    def _apply_rate_limiting(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _calculate_confidence_score(self, response: Any, gap_analysis: GapAnalysis) -> float:
        """Calculate confidence score for generated bridge."""
        base_confidence = 0.7  # Base confidence for successful generation
        
        # Adjust based on gap analysis
        if gap_analysis.necessity_score > 0.8:
            base_confidence += 0.1  # High necessity suggests good bridge needed
        elif gap_analysis.necessity_score < 0.3:
            base_confidence -= 0.1  # Low necessity might not need complex bridge
        
        # Adjust based on semantic distance
        if gap_analysis.semantic_distance > 0.7:
            base_confidence += 0.1  # Large gap successfully bridged
        
        # Adjust based on response quality indicators
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # Check for safety ratings (lower is better)
            if hasattr(candidate, 'safety_ratings'):
                for rating in candidate.safety_ratings:
                    if rating.probability.name in ['HIGH', 'MEDIUM']:
                        base_confidence -= 0.2
                        break
            
            # Check finish reason
            if hasattr(candidate, 'finish_reason'):
                if candidate.finish_reason.name == 'STOP':
                    base_confidence += 0.05  # Natural completion
                elif candidate.finish_reason.name in ['MAX_TOKENS', 'SAFETY']:
                    base_confidence -= 0.1  # Truncated or safety-stopped
        
        return max(0.0, min(1.0, base_confidence))
    
    def _extract_token_usage(self, response: Any) -> Dict[str, int]:
        """Extract token usage information from response."""
        token_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
        
        try:
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                token_usage['input_tokens'] = getattr(usage, 'prompt_token_count', 0)
                token_usage['output_tokens'] = getattr(usage, 'candidates_token_count', 0)
                token_usage['total_tokens'] = getattr(usage, 'total_token_count', 0)
        except Exception as e:
            logger.debug(f"Could not extract token usage: {e}")
        
        return token_usage
    
    def _estimate_cost(self, token_usage: Dict[str, int]) -> float:
        """Estimate cost based on token usage."""
        # Gemini 2.0 Flash pricing (approximate)
        input_cost_per_1k = 0.000075  # $0.000075 per 1K input tokens
        output_cost_per_1k = 0.0003   # $0.0003 per 1K output tokens
        
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        
        input_cost = (input_tokens / 1000) * input_cost_per_1k
        output_cost = (output_tokens / 1000) * output_cost_per_1k
        
        return input_cost + output_cost
    
    def get_generation_statistics(self) -> Dict[str, Any]:
        """Get generation statistics."""
        stats = self.generation_stats.copy()
        
        if stats['total_requests'] > 0:
            stats['success_rate'] = stats['successful_generations'] / stats['total_requests']
            stats['average_tokens_per_request'] = stats['total_tokens'] / stats['total_requests']
            stats['average_cost_per_request'] = stats['total_cost'] / stats['total_requests']
        else:
            stats['success_rate'] = 0.0
            stats['average_tokens_per_request'] = 0.0
            stats['average_cost_per_request'] = 0.0
        
        stats['configured_provider'] = self.provider
        
        return stats
    
    def reset_statistics(self):
        """Reset generation statistics."""
        self.generation_stats = {
            'total_requests': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'total_tokens': 0,
            'total_cost': 0.0
        }