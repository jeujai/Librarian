"""
Fallback Response Service

This service provides context-aware fallback responses when full AI capabilities
are not yet available. It analyzes user intent and provides appropriate responses
with clear expectations about current limitations.

Key Features:
- User intent analysis
- Context-aware fallback responses
- Capability-specific messaging
- Clear limitation statements
- Upgrade path messaging
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ..services.capability_service import get_capability_service, CapabilityLevel
from ..startup.minimal_server import get_minimal_server
from ..logging_config import get_logger

logger = get_logger("fallback_service")


class UserIntent(Enum):
    """Categories of user intent for fallback response generation."""
    SIMPLE_QUESTION = "simple_question"
    COMPLEX_ANALYSIS = "complex_analysis"
    DOCUMENT_PROCESSING = "document_processing"
    SEARCH_QUERY = "search_query"
    CREATIVE_TASK = "creative_task"
    TECHNICAL_HELP = "technical_help"
    CONVERSATION = "conversation"
    SYSTEM_STATUS = "system_status"
    UNKNOWN = "unknown"


@dataclass
class IntentAnalysis:
    """Result of user intent analysis."""
    primary_intent: UserIntent
    confidence: float
    keywords: List[str]
    complexity_level: str  # "low", "medium", "high"
    required_capabilities: List[str]
    fallback_appropriate: bool
    reasoning: str


@dataclass
class FallbackResponse:
    """A fallback response with context and expectations."""
    response_text: str
    response_quality: CapabilityLevel
    limitations: List[str]
    available_alternatives: List[str]
    upgrade_message: str
    estimated_full_ready_time: Optional[int]  # seconds
    helpful_now: bool
    context_preserved: bool


class FallbackResponseService:
    """Service for generating context-aware fallback responses."""
    
    def __init__(self):
        self.capability_service = get_capability_service()
        self.intent_patterns = self._define_intent_patterns()
        self.response_templates = self._define_response_templates()
        
    def _define_intent_patterns(self) -> Dict[UserIntent, Dict[str, Any]]:
        """Define patterns for recognizing user intent."""
        return {
            UserIntent.SIMPLE_QUESTION: {
                "keywords": ["what", "who", "when", "where", "how", "why", "is", "are", "can", "do"],
                "patterns": [
                    r"\b(what|who|when|where|how|why)\s+is\b",
                    r"\b(can|could|would)\s+you\b",
                    r"\b(do|does|did)\s+you\b",
                    r"\?$"
                ],
                "complexity_indicators": ["simple", "basic", "quick"],
                "required_capabilities": ["simple_text"]
            },
            UserIntent.COMPLEX_ANALYSIS: {
                "keywords": ["analyze", "analysis", "compare", "evaluate", "assess", "examine", "study", "research"],
                "patterns": [
                    r"\b(analyze|analysis|compare|evaluate|assess|examine)\b",
                    r"\b(complex|detailed|comprehensive|thorough)\b",
                    r"\b(pros and cons|advantages and disadvantages)\b"
                ],
                "complexity_indicators": ["complex", "detailed", "comprehensive", "thorough", "deep"],
                "required_capabilities": ["complex_reasoning", "advanced_chat"]
            },
            UserIntent.DOCUMENT_PROCESSING: {
                "keywords": ["document", "file", "pdf", "text", "upload", "read", "parse", "extract", "analyze"],
                "patterns": [
                    r"\b(document|file|pdf|upload)\b",
                    r"\b(read|parse|extract|process)\s+(this|the|my|document|file)\b",
                    r"\b(summarize|summary)\s+(document|file|text)\b",
                    r"\b(analyze)\s+(this|the|my)?\s*(document|file|pdf)\b"
                ],
                "complexity_indicators": ["document", "file", "upload"],
                "required_capabilities": ["document_analysis", "document_upload"]
            },
            UserIntent.SEARCH_QUERY: {
                "keywords": ["search", "find", "look", "locate", "discover", "show me"],
                "patterns": [
                    r"\b(search|find|look|locate)\s+(for|up)\b",
                    r"\b(show me|give me|list)\b",
                    r"\b(where can I find|how do I find)\b"
                ],
                "complexity_indicators": ["semantic", "advanced", "intelligent"],
                "required_capabilities": ["simple_search", "semantic_search"]
            },
            UserIntent.CREATIVE_TASK: {
                "keywords": ["create", "generate", "write", "compose", "design", "make", "build"],
                "patterns": [
                    r"\b(create|generate|write|compose|design|make|build)\b",
                    r"\b(help me (create|write|make))\b",
                    r"\b(can you (create|write|generate))\b"
                ],
                "complexity_indicators": ["creative", "original", "unique"],
                "required_capabilities": ["advanced_chat", "complex_reasoning"]
            },
            UserIntent.TECHNICAL_HELP: {
                "keywords": ["help", "how to", "tutorial", "guide", "explain", "teach", "learn"],
                "patterns": [
                    r"\b(how to|how do I|how can I)\b",
                    r"\b(help me|assist me|guide me)\b",
                    r"\b(explain|teach|show)\s+(me|how)\b"
                ],
                "complexity_indicators": ["step-by-step", "detailed", "comprehensive"],
                "required_capabilities": ["basic_chat", "advanced_chat"]
            },
            UserIntent.CONVERSATION: {
                "keywords": ["hello", "hi", "hey", "thanks", "thank you", "goodbye", "bye"],
                "patterns": [
                    r"\b(hello|hi|hey|greetings)\b",
                    r"\b(thanks|thank you|appreciate)\b",
                    r"\b(goodbye|bye|see you)\b"
                ],
                "complexity_indicators": [],
                "required_capabilities": ["simple_text"]
            },
            UserIntent.SYSTEM_STATUS: {
                "keywords": ["status", "ready", "available", "working", "loaded", "capabilities"],
                "patterns": [
                    r"\b(status|ready|available|working)\b",
                    r"\b(are you (ready|available|working))\b",
                    r"\b(what can you do|capabilities)\b"
                ],
                "complexity_indicators": [],
                "required_capabilities": ["status_updates"]
            }
        }
    
    def _define_response_templates(self) -> Dict[UserIntent, Dict[str, str]]:
        """Define response templates for different intents and capability levels."""
        return {
            UserIntent.SIMPLE_QUESTION: {
                "basic": "I can provide a basic response to your question. My full AI capabilities are still loading, so this will be a simple answer.",
                "enhanced": "I can answer your question with some AI assistance. My advanced reasoning is still loading, but I can provide a helpful response.",
                "full": "I can provide a comprehensive answer with full AI capabilities."
            },
            UserIntent.COMPLEX_ANALYSIS: {
                "basic": "I understand you're asking for complex analysis. My advanced AI models are currently loading, which are needed for detailed analysis and reasoning.",
                "enhanced": "I can provide some analysis, but my advanced reasoning capabilities are still loading. I can give you a basic assessment now.",
                "full": "I can provide comprehensive analysis with full reasoning capabilities."
            },
            UserIntent.DOCUMENT_PROCESSING: {
                "basic": "I see you want to work with documents. My document processing capabilities are currently loading, including PDF parsing and text extraction.",
                "enhanced": "I can do basic document processing now, but advanced document analysis features are still loading.",
                "full": "I can fully process and analyze documents with all capabilities available."
            },
            UserIntent.SEARCH_QUERY: {
                "basic": "I understand you want to search for information. My search capabilities are loading, including semantic search and intelligent retrieval.",
                "enhanced": "I can do basic text search now, but advanced semantic search will be available shortly.",
                "full": "I can perform comprehensive search with full semantic understanding."
            },
            UserIntent.CREATIVE_TASK: {
                "basic": "I see you want help with a creative task. My advanced language models needed for creative work are currently loading.",
                "enhanced": "I can help with basic creative tasks, but my advanced creative capabilities are still loading.",
                "full": "I can assist with complex creative tasks using full AI capabilities."
            },
            UserIntent.TECHNICAL_HELP: {
                "basic": "I can provide basic technical help. My advanced knowledge models are loading, which will enable more detailed technical assistance.",
                "enhanced": "I can provide some technical guidance now, with more comprehensive help available once my advanced models load.",
                "full": "I can provide detailed technical assistance with full knowledge capabilities."
            },
            UserIntent.CONVERSATION: {
                "basic": "Hello! I'm here and ready to chat. My conversational AI is starting up, so responses will be basic initially.",
                "enhanced": "Hi there! I can have a good conversation with you. My advanced conversational abilities are still loading.",
                "full": "Hello! I'm fully ready for natural conversation with all AI capabilities."
            },
            UserIntent.SYSTEM_STATUS: {
                "basic": "I'm currently starting up. Basic functionality is available, with advanced AI capabilities loading in the background.",
                "enhanced": "I'm partially ready with some AI capabilities available. Full functionality is loading.",
                "full": "I'm fully operational with all AI capabilities ready."
            }
        }
    
    def analyze_user_intent(self, user_message: str) -> IntentAnalysis:
        """Analyze user message to determine intent and requirements."""
        message_lower = user_message.lower().strip()
        
        # Score each intent category
        intent_scores = {}
        
        for intent, config in self.intent_patterns.items():
            score = 0.0
            matched_keywords = []
            
            # Check keywords
            for keyword in config["keywords"]:
                if keyword in message_lower:
                    score += 1.0
                    matched_keywords.append(keyword)
            
            # Check patterns
            for pattern in config["patterns"]:
                if re.search(pattern, message_lower):
                    score += 2.0  # Patterns are weighted higher
            
            # Check complexity indicators
            complexity_score = 0
            for indicator in config["complexity_indicators"]:
                if indicator in message_lower:
                    complexity_score += 1
            
            # Normalize score
            total_possible = len(config["keywords"]) + (len(config["patterns"]) * 2)
            if total_possible > 0:
                score = score / total_possible
            
            intent_scores[intent] = {
                "score": score,
                "keywords": matched_keywords,
                "complexity": complexity_score,
                "required_capabilities": config["required_capabilities"]
            }
        
        # Find best match
        if not intent_scores or all(s["score"] == 0 for s in intent_scores.values()):
            primary_intent = UserIntent.UNKNOWN
            confidence = 0.0
            keywords = []
            complexity_level = "low"
            required_capabilities = ["simple_text"]
        else:
            best_intent = max(intent_scores.keys(), key=lambda k: intent_scores[k]["score"])
            best_score = intent_scores[best_intent]
            
            primary_intent = best_intent
            confidence = best_score["score"]
            keywords = best_score["keywords"]
            required_capabilities = best_score["required_capabilities"]
            
            # Determine complexity level
            complexity_score = best_score["complexity"]
            if complexity_score >= 2:
                complexity_level = "high"
            elif complexity_score >= 1:
                complexity_level = "medium"
            else:
                complexity_level = "low"
        
        # Determine if fallback is appropriate
        fallback_appropriate = confidence > 0.3 and primary_intent != UserIntent.UNKNOWN
        
        reasoning = f"Detected {primary_intent.value} with {confidence:.2f} confidence based on keywords: {keywords}"
        
        return IntentAnalysis(
            primary_intent=primary_intent,
            confidence=confidence,
            keywords=keywords,
            complexity_level=complexity_level,
            required_capabilities=required_capabilities,
            fallback_appropriate=fallback_appropriate,
            reasoning=reasoning
        )
    
    def generate_fallback_response(
        self, 
        user_message: str, 
        intent_analysis: Optional[IntentAnalysis] = None
    ) -> FallbackResponse:
        """Generate a context-aware fallback response."""
        if intent_analysis is None:
            intent_analysis = self.analyze_user_intent(user_message)
        
        # Get current system capabilities
        capabilities = self.capability_service.get_capability_summary()
        progress = self.capability_service.get_loading_progress()
        
        # Determine current capability level
        current_level = self._determine_response_level(intent_analysis, capabilities)
        
        # Get base response template
        response_text = self._get_base_response(intent_analysis, current_level)
        
        # Add context-specific information
        response_text = self._add_context_specific_info(
            response_text, user_message, intent_analysis, current_level
        )
        
        # Generate limitations and alternatives
        limitations = self._generate_limitations(intent_analysis, current_level, capabilities)
        alternatives = self._generate_alternatives(intent_analysis, current_level, capabilities)
        
        # Generate upgrade message
        upgrade_message = self._generate_upgrade_message(intent_analysis, progress)
        
        # Estimate ready time
        estimated_ready_time = self._estimate_ready_time(intent_analysis, progress)
        
        return FallbackResponse(
            response_text=response_text,
            response_quality=current_level,
            limitations=limitations,
            available_alternatives=alternatives,
            upgrade_message=upgrade_message,
            estimated_full_ready_time=estimated_ready_time,
            helpful_now=current_level != CapabilityLevel.BASIC or intent_analysis.primary_intent in [
                UserIntent.SIMPLE_QUESTION, UserIntent.CONVERSATION, UserIntent.SYSTEM_STATUS
            ],
            context_preserved=True
        )
    
    def _determine_response_level(
        self, 
        intent_analysis: IntentAnalysis, 
        capabilities: Dict[str, Any]
    ) -> CapabilityLevel:
        """Determine what level of response we can provide."""
        # Check if we can handle the required capabilities
        capability_check = self.capability_service.can_handle_request(
            request_type="fallback_response",
            required_capabilities=intent_analysis.required_capabilities
        )
        
        if capability_check["can_handle"]:
            level_str = capability_check["quality_level"]
            if level_str == "full":
                return CapabilityLevel.FULL
            elif level_str == "enhanced":
                return CapabilityLevel.ENHANCED
            else:
                return CapabilityLevel.BASIC
        else:
            return CapabilityLevel.BASIC
    
    def _get_base_response(
        self, 
        intent_analysis: IntentAnalysis, 
        current_level: CapabilityLevel
    ) -> str:
        """Get base response template for the intent and capability level."""
        templates = self.response_templates.get(intent_analysis.primary_intent, {})
        
        level_key = current_level.value
        if level_key in templates:
            return templates[level_key]
        else:
            # Fallback to basic template
            return templates.get("basic", "I'm currently starting up and can provide basic assistance.")
    
    def _add_context_specific_info(
        self, 
        base_response: str, 
        user_message: str, 
        intent_analysis: IntentAnalysis,
        current_level: CapabilityLevel
    ) -> str:
        """Add context-specific information to the base response."""
        # Add user's specific context
        if intent_analysis.primary_intent == UserIntent.DOCUMENT_PROCESSING:
            if "pdf" in user_message.lower():
                base_response += " I notice you mentioned PDF files specifically."
            elif "upload" in user_message.lower():
                base_response += " I see you want to upload documents."
        
        elif intent_analysis.primary_intent == UserIntent.SEARCH_QUERY:
            # Extract what they're searching for
            search_terms = self._extract_search_terms(user_message)
            if search_terms:
                base_response += f" I understand you're looking for information about: {', '.join(search_terms)}."
        
        elif intent_analysis.primary_intent == UserIntent.COMPLEX_ANALYSIS:
            if "compare" in user_message.lower():
                base_response += " I see you want to compare different options or concepts."
            elif "analyze" in user_message.lower():
                base_response += " I understand you need detailed analysis."
        
        # Add capability-specific context
        if current_level == CapabilityLevel.BASIC:
            base_response += " Right now I can provide basic text responses and general information."
        elif current_level == CapabilityLevel.ENHANCED:
            base_response += " I currently have some AI capabilities available for more helpful responses."
        
        return base_response
    
    def _extract_search_terms(self, message: str) -> List[str]:
        """Extract search terms from a search query."""
        # Simple extraction - look for quoted terms or key phrases
        terms = []
        
        # Find quoted terms
        quoted_terms = re.findall(r'"([^"]*)"', message)
        terms.extend(quoted_terms)
        
        # Find terms after "about", "for", "on"
        about_terms = re.findall(r'\b(?:about|for|on|regarding)\s+([^.?!,]+)', message, re.IGNORECASE)
        terms.extend([term.strip() for term in about_terms])
        
        return terms[:3]  # Limit to 3 terms
    
    def _generate_limitations(
        self, 
        intent_analysis: IntentAnalysis, 
        current_level: CapabilityLevel,
        capabilities: Dict[str, Any]
    ) -> List[str]:
        """Generate list of current limitations."""
        limitations = []
        
        if current_level == CapabilityLevel.BASIC:
            limitations.extend([
                "Advanced AI reasoning not yet available",
                "Document processing capabilities loading",
                "Semantic search not ready",
                "Complex analysis features unavailable"
            ])
        elif current_level == CapabilityLevel.ENHANCED:
            limitations.extend([
                "Advanced reasoning still loading",
                "Full document analysis not ready",
                "Some specialized features unavailable"
            ])
        
        # Add intent-specific limitations
        if intent_analysis.primary_intent == UserIntent.DOCUMENT_PROCESSING:
            if current_level != CapabilityLevel.FULL:
                limitations.append("Cannot process uploaded documents yet")
                limitations.append("PDF parsing not available")
        
        elif intent_analysis.primary_intent == UserIntent.COMPLEX_ANALYSIS:
            if current_level == CapabilityLevel.BASIC:
                limitations.append("Cannot perform detailed analysis")
                limitations.append("Multi-step reasoning not available")
        
        return limitations[:4]  # Limit to 4 most relevant limitations
    
    def _generate_alternatives(
        self, 
        intent_analysis: IntentAnalysis, 
        current_level: CapabilityLevel,
        capabilities: Dict[str, Any]
    ) -> List[str]:
        """Generate list of available alternatives."""
        alternatives = []
        
        # Always available alternatives
        alternatives.extend([
            "Ask simple questions for basic responses",
            "Check system status and loading progress",
            "Get information about available capabilities"
        ])
        
        # Level-specific alternatives
        if current_level == CapabilityLevel.ENHANCED:
            alternatives.extend([
                "Basic chat and conversation",
                "Simple text search",
                "General information queries"
            ])
        
        # Intent-specific alternatives
        if intent_analysis.primary_intent == UserIntent.DOCUMENT_PROCESSING:
            alternatives.append("Describe your document and I can provide general guidance")
        
        elif intent_analysis.primary_intent == UserIntent.COMPLEX_ANALYSIS:
            alternatives.append("Ask for a simple overview first, then detailed analysis when ready")
        
        elif intent_analysis.primary_intent == UserIntent.SEARCH_QUERY:
            if current_level == CapabilityLevel.ENHANCED:
                alternatives.append("Try basic text search for now")
        
        return alternatives[:4]  # Limit to 4 most relevant alternatives
    
    def _generate_upgrade_message(
        self, 
        intent_analysis: IntentAnalysis, 
        progress: Dict[str, Any]
    ) -> str:
        """Generate upgrade path message."""
        estimated_time = self._estimate_ready_time(intent_analysis, progress)
        
        if estimated_time is None or estimated_time <= 0:
            return "Full capabilities should be available shortly."
        
        if estimated_time <= 30:
            return f"Full AI capabilities will be ready in about {estimated_time} seconds."
        elif estimated_time <= 120:
            minutes = estimated_time // 60
            return f"Advanced features will be available in about {minutes} minute{'s' if minutes != 1 else ''}."
        else:
            minutes = estimated_time // 60
            return f"Full capabilities will be ready in approximately {minutes} minutes. You can continue using basic features in the meantime."
    
    def _estimate_ready_time(
        self, 
        intent_analysis: IntentAnalysis, 
        progress: Dict[str, Any]
    ) -> Optional[int]:
        """Estimate time until required capabilities are ready."""
        try:
            # Get estimated completion times from progress
            estimated_completion = progress.get("estimated_completion")
            
            # Handle different data structures
            if isinstance(estimated_completion, str):
                # If it's a string (ISO datetime), parse it
                try:
                    from datetime import datetime
                    completion_dt = datetime.fromisoformat(estimated_completion.replace('Z', '+00:00'))
                    now = datetime.now(completion_dt.tzinfo) if completion_dt.tzinfo else datetime.now()
                    seconds_remaining = max(0, (completion_dt - now).total_seconds())
                    return int(seconds_remaining)
                except Exception:
                    # If parsing fails, use default
                    return 60
            elif isinstance(estimated_completion, dict):
                # If it's a dict, look for specific keys
                completion_times = estimated_completion
            else:
                # Use overall progress to estimate
                overall_progress = progress.get("overall_progress", 0)
                if overall_progress >= 90:
                    return 30
                elif overall_progress >= 50:
                    return 120
                else:
                    return 300
            
            # Map intent to completion time keys (if we have a dict)
            if isinstance(estimated_completion, dict):
                if intent_analysis.primary_intent in [UserIntent.COMPLEX_ANALYSIS, UserIntent.CREATIVE_TASK]:
                    return completion_times.get("full_capabilities", 300)
                elif intent_analysis.primary_intent == UserIntent.DOCUMENT_PROCESSING:
                    return completion_times.get("document_analysis", completion_times.get("full_capabilities", 180))
                elif intent_analysis.primary_intent == UserIntent.SEARCH_QUERY:
                    return completion_times.get("advanced_search", completion_times.get("full_capabilities", 120))
                else:
                    # For basic intents, check if enhanced capabilities are coming soon
                    return completion_times.get("enhanced_capabilities", 30)
            
            # Default fallback
            return 60
        
        except Exception as e:
            logger.error(f"Error estimating ready time: {e}")
            return 60  # Default to 1 minute


# Global fallback service instance
_fallback_service = None

def get_fallback_service() -> FallbackResponseService:
    """Get the global fallback service instance."""
    global _fallback_service
    if _fallback_service is None:
        _fallback_service = FallbackResponseService()
    return _fallback_service