"""NLP model wrapper for spacy."""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Global model instance
_nlp_model: Optional["NLPModel"] = None


class NLPModel:
    """Wrapper for spacy NLP model."""
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        self.model_name = model_name
        self._nlp = None
        self._loaded = False
        self._load_time_seconds: Optional[float] = None
        self._error: Optional[str] = None
    
    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded
    
    @property
    def load_time_seconds(self) -> Optional[float]:
        """Get model load time in seconds."""
        return self._load_time_seconds
    
    @property
    def error(self) -> Optional[str]:
        """Get error message if loading failed."""
        return self._error
    
    def load(self) -> bool:
        """Load the NLP model."""
        if self._loaded:
            return True
        
        logger.info(f"Loading NLP model: {self.model_name}")
        start_time = time.time()
        
        try:
            import spacy
            
            try:
                self._nlp = spacy.load(self.model_name)
            except OSError:
                # Model not found, try to download it
                logger.info(f"Downloading spacy model: {self.model_name}")
                spacy.cli.download(self.model_name)
                self._nlp = spacy.load(self.model_name)
            
            self._load_time_seconds = time.time() - start_time
            self._loaded = True
            self._error = None
            
            logger.info(
                f"NLP model loaded successfully: {self.model_name} "
                f"(time={self._load_time_seconds:.2f}s)"
            )
            return True
            
        except Exception as e:
            self._error = str(e)
            self._load_time_seconds = time.time() - start_time
            logger.error(f"Failed to load NLP model: {e}")
            return False
    
    def process(
        self,
        texts: List[str],
        tasks: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process texts with specified NLP tasks.
        
        Args:
            texts: List of texts to process
            tasks: List of tasks to perform (tokenize, ner, pos, lemma, sentences)
                   If None, performs all tasks
            
        Returns:
            List of results for each text
        """
        if not self._loaded:
            raise RuntimeError("NLP model not loaded")
        
        if not texts:
            return []
        
        if tasks is None:
            tasks = ["tokenize", "ner", "pos"]
        
        results = []
        
        try:
            # Process texts in batch using pipe for efficiency
            docs = list(self._nlp.pipe(texts))
            
            for doc in docs:
                result = {"text": doc.text}
                
                if "tokenize" in tasks:
                    result["tokens"] = [token.text for token in doc]
                
                if "ner" in tasks:
                    result["entities"] = [
                        {
                            "text": ent.text,
                            "label": ent.label_,
                            "start": ent.start_char,
                            "end": ent.end_char
                        }
                        for ent in doc.ents
                    ]
                
                if "pos" in tasks:
                    result["pos_tags"] = [
                        {
                            "token": token.text,
                            "pos": token.pos_,
                            "tag": token.tag_
                        }
                        for token in doc
                    ]
                
                if "lemma" in tasks:
                    result["lemmas"] = [token.lemma_ for token in doc]
                
                if "sentences" in tasks:
                    result["sentences"] = [sent.text for sent in doc.sents]
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing texts: {e}")
            raise
    
    def tokenize(self, texts: List[str]) -> List[List[str]]:
        """Tokenize texts."""
        results = self.process(texts, tasks=["tokenize"])
        return [r.get("tokens", []) for r in results]
    
    def get_entities(self, texts: List[str]) -> List[List[Dict]]:
        """Extract named entities from texts."""
        results = self.process(texts, tasks=["ner"])
        return [r.get("entities", []) for r in results]
    
    def get_status(self) -> dict:
        """Get model status information."""
        return {
            "name": self.model_name,
            "status": "loaded" if self._loaded else "not_loaded",
            "load_time_seconds": self._load_time_seconds,
            "error": self._error
        }


def get_nlp_model() -> Optional[NLPModel]:
    """Get the global NLP model instance."""
    return _nlp_model


def initialize_nlp_model(model_name: str = "en_core_web_sm") -> NLPModel:
    """Initialize the global NLP model."""
    global _nlp_model
    
    _nlp_model = NLPModel(model_name=model_name)
    _nlp_model.load()
    
    return _nlp_model
