"""
Data sanitization and privacy protection service.

This module provides comprehensive data sanitization to prevent
sensitive information from being logged or stored inappropriately.
"""

import re
import hashlib
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SanitizationRule:
    """Rule for sanitizing sensitive data."""
    name: str
    pattern: str
    replacement: str
    description: str
    enabled: bool = True


class DataSanitizer:
    """Service for sanitizing sensitive data in logs and storage."""
    
    def __init__(self):
        """Initialize data sanitizer with default rules."""
        self.rules = self._get_default_rules()
        self.custom_rules = []
    
    def _get_default_rules(self) -> List[SanitizationRule]:
        """Get default sanitization rules for common sensitive data."""
        return [
            # Personal identifiers
            SanitizationRule(
                name="ssn",
                pattern=r'\b\d{3}-\d{2}-\d{4}\b',
                replacement="[SSN-REDACTED]",
                description="Social Security Numbers"
            ),
            SanitizationRule(
                name="ssn_no_dash",
                pattern=r'\b\d{9}\b',
                replacement="[SSN-REDACTED]",
                description="Social Security Numbers without dashes"
            ),
            
            # Financial information
            SanitizationRule(
                name="credit_card",
                pattern=r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
                replacement="[CARD-REDACTED]",
                description="Credit card numbers"
            ),
            SanitizationRule(
                name="bank_account",
                pattern=r'\b\d{8,17}\b',
                replacement="[ACCOUNT-REDACTED]",
                description="Bank account numbers"
            ),
            
            # Contact information
            SanitizationRule(
                name="email",
                pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                replacement="[EMAIL-REDACTED]",
                description="Email addresses"
            ),
            SanitizationRule(
                name="phone",
                pattern=r'\b\d{3}[- ]?\d{3}[- ]?\d{4}\b',
                replacement="[PHONE-REDACTED]",
                description="Phone numbers"
            ),
            SanitizationRule(
                name="phone_international",
                pattern=r'\+\d{1,3}[- ]?\d{3,14}',
                replacement="[PHONE-REDACTED]",
                description="International phone numbers"
            ),
            
            # Addresses
            SanitizationRule(
                name="zip_code",
                pattern=r'\b\d{5}(-\d{4})?\b',
                replacement="[ZIP-REDACTED]",
                description="ZIP codes"
            ),
            
            # Authentication tokens
            SanitizationRule(
                name="jwt_token",
                pattern=r'eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*',
                replacement="[JWT-REDACTED]",
                description="JWT tokens"
            ),
            SanitizationRule(
                name="api_key",
                pattern=r'(?i)(api[_-]?key|token|secret)["\s]*[:=]["\s]*[A-Za-z0-9+/=]{20,}',
                replacement=r'\1: [API-KEY-REDACTED]',
                description="API keys and tokens"
            ),
            
            # Passwords
            SanitizationRule(
                name="password",
                pattern=r'(?i)(password|passwd|pwd)["\s]*[:=]["\s]*[^\s"]{6,}',
                replacement=r'\1: [PASSWORD-REDACTED]',
                description="Passwords"
            ),
            
            # IP addresses (optional - might be needed for debugging)
            SanitizationRule(
                name="ipv4",
                pattern=r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
                replacement="[IP-REDACTED]",
                description="IPv4 addresses",
                enabled=False  # Disabled by default
            ),
            
            # Medical information
            SanitizationRule(
                name="medical_record",
                pattern=r'\b(MRN|MR#|Medical Record)[:\s]*\d+',
                replacement="[MEDICAL-RECORD-REDACTED]",
                description="Medical record numbers"
            ),
            
            # Government IDs
            SanitizationRule(
                name="passport",
                pattern=r'\b[A-Z]{1,2}\d{6,9}\b',
                replacement="[PASSPORT-REDACTED]",
                description="Passport numbers"
            ),
            SanitizationRule(
                name="drivers_license",
                pattern=r'\b[A-Z]{1,2}\d{6,8}\b',
                replacement="[LICENSE-REDACTED]",
                description="Driver's license numbers"
            ),
        ]
    
    def add_custom_rule(self, rule: SanitizationRule):
        """Add custom sanitization rule."""
        try:
            # Test the regex pattern
            re.compile(rule.pattern)
            self.custom_rules.append(rule)
            logger.info(f"Added custom sanitization rule: {rule.name}")
        except re.error as e:
            logger.error(f"Invalid regex pattern in rule {rule.name}: {e}")
            raise ValueError(f"Invalid regex pattern: {e}")
    
    def sanitize_text(self, text: str, preserve_structure: bool = True) -> str:
        """Sanitize sensitive data in text."""
        if not text:
            return text
        
        try:
            sanitized = text
            
            # Apply default rules
            for rule in self.rules:
                if rule.enabled:
                    sanitized = re.sub(rule.pattern, rule.replacement, sanitized)
            
            # Apply custom rules
            for rule in self.custom_rules:
                if rule.enabled:
                    sanitized = re.sub(rule.pattern, rule.replacement, sanitized)
            
            # Log if sanitization occurred
            if sanitized != text:
                logger.debug("Text sanitization applied")
            
            return sanitized
            
        except Exception as e:
            logger.error(f"Text sanitization failed: {e}")
            return "[SANITIZATION-ERROR]"
    
    def sanitize_dict(
        self, 
        data: Dict[str, Any], 
        sensitive_keys: Optional[List[str]] = None,
        deep_sanitize: bool = True
    ) -> Dict[str, Any]:
        """Sanitize sensitive data in dictionary."""
        if not isinstance(data, dict):
            return data
        
        try:
            # Default sensitive keys
            if sensitive_keys is None:
                sensitive_keys = [
                    'password', 'passwd', 'pwd', 'secret', 'token', 'key',
                    'api_key', 'access_token', 'refresh_token', 'jwt',
                    'ssn', 'social_security', 'credit_card', 'card_number',
                    'email', 'phone', 'address', 'zip', 'postal_code'
                ]
            
            sanitized = {}
            
            for key, value in data.items():
                key_lower = key.lower()
                
                # Check if key is sensitive
                is_sensitive_key = any(sensitive_key in key_lower for sensitive_key in sensitive_keys)
                
                if is_sensitive_key:
                    # Replace sensitive values
                    if isinstance(value, str) and value:
                        sanitized[key] = "[REDACTED]"
                    elif isinstance(value, (int, float)) and value != 0:
                        sanitized[key] = "[REDACTED]"
                    else:
                        sanitized[key] = value
                elif isinstance(value, str):
                    # Sanitize string values for patterns
                    sanitized[key] = self.sanitize_text(value) if deep_sanitize else value
                elif isinstance(value, dict):
                    # Recursively sanitize nested dictionaries
                    sanitized[key] = self.sanitize_dict(value, sensitive_keys, deep_sanitize)
                elif isinstance(value, list):
                    # Sanitize list items
                    sanitized[key] = self._sanitize_list(value, sensitive_keys, deep_sanitize)
                else:
                    sanitized[key] = value
            
            return sanitized
            
        except Exception as e:
            logger.error(f"Dictionary sanitization failed: {e}")
            return {"sanitization_error": str(e)}
    
    def _sanitize_list(
        self, 
        data: List[Any], 
        sensitive_keys: List[str],
        deep_sanitize: bool
    ) -> List[Any]:
        """Sanitize sensitive data in list."""
        try:
            sanitized = []
            
            for item in data:
                if isinstance(item, str):
                    sanitized.append(self.sanitize_text(item) if deep_sanitize else item)
                elif isinstance(item, dict):
                    sanitized.append(self.sanitize_dict(item, sensitive_keys, deep_sanitize))
                elif isinstance(item, list):
                    sanitized.append(self._sanitize_list(item, sensitive_keys, deep_sanitize))
                else:
                    sanitized.append(item)
            
            return sanitized
            
        except Exception as e:
            logger.error(f"List sanitization failed: {e}")
            return ["[SANITIZATION-ERROR]"]
    
    def sanitize_log_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Sanitize log message and context."""
        try:
            # Sanitize the main message
            sanitized_message = self.sanitize_text(message)
            
            # If context is provided, sanitize it and append
            if context:
                sanitized_context = self.sanitize_dict(context)
                # Convert context to string representation
                context_str = str(sanitized_context)
                sanitized_message += f" | Context: {context_str}"
            
            return sanitized_message
            
        except Exception as e:
            logger.error(f"Log message sanitization failed: {e}")
            return "[LOG-SANITIZATION-ERROR]"
    
    def create_data_hash(self, data: Union[str, Dict[str, Any]]) -> str:
        """Create hash of sensitive data for audit purposes."""
        try:
            if isinstance(data, dict):
                # Sort keys for consistent hashing
                data_str = str(sorted(data.items()))
            else:
                data_str = str(data)
            
            # Create SHA-256 hash
            hash_obj = hashlib.sha256(data_str.encode('utf-8'))
            return hash_obj.hexdigest()
            
        except Exception as e:
            logger.error(f"Data hashing failed: {e}")
            return "hash-error"
    
    def is_sensitive_content(self, text: str) -> bool:
        """Check if text contains sensitive information."""
        if not text:
            return False
        
        try:
            # Check against all enabled rules
            for rule in self.rules + self.custom_rules:
                if rule.enabled and re.search(rule.pattern, text):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Sensitive content detection failed: {e}")
            return True  # Err on the side of caution
    
    def get_sanitization_summary(self, original: str, sanitized: str) -> Dict[str, Any]:
        """Get summary of sanitization changes."""
        try:
            changes = []
            
            # Check which rules were applied
            for rule in self.rules + self.custom_rules:
                if rule.enabled:
                    if re.search(rule.pattern, original) and rule.replacement in sanitized:
                        changes.append({
                            "rule": rule.name,
                            "description": rule.description,
                            "pattern_matched": True
                        })
            
            return {
                "original_length": len(original),
                "sanitized_length": len(sanitized),
                "changes_applied": len(changes),
                "rules_triggered": changes,
                "contains_sensitive_data": len(changes) > 0
            }
            
        except Exception as e:
            logger.error(f"Sanitization summary failed: {e}")
            return {"error": str(e)}
    
    def enable_rule(self, rule_name: str):
        """Enable a sanitization rule."""
        for rule in self.rules + self.custom_rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"Enabled sanitization rule: {rule_name}")
                return
        
        logger.warning(f"Sanitization rule not found: {rule_name}")
    
    def disable_rule(self, rule_name: str):
        """Disable a sanitization rule."""
        for rule in self.rules + self.custom_rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"Disabled sanitization rule: {rule_name}")
                return
        
        logger.warning(f"Sanitization rule not found: {rule_name}")
    
    def get_active_rules(self) -> List[Dict[str, Any]]:
        """Get list of active sanitization rules."""
        active_rules = []
        
        for rule in self.rules + self.custom_rules:
            if rule.enabled:
                active_rules.append({
                    "name": rule.name,
                    "description": rule.description,
                    "pattern": rule.pattern,
                    "replacement": rule.replacement
                })
        
        return active_rules


# Global sanitizer instance
_data_sanitizer = None


def get_data_sanitizer() -> DataSanitizer:
    """Get global data sanitizer instance."""
    global _data_sanitizer
    if _data_sanitizer is None:
        _data_sanitizer = DataSanitizer()
    return _data_sanitizer