"""
Audit logging service for security and compliance.

This module provides comprehensive audit logging for all data access,
user actions, and system operations to ensure compliance and security monitoring.
"""

import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import get_settings
from ..logging_config import get_logger
from .encryption import get_encryption_service

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_CREATED = "token_created"
    TOKEN_EXPIRED = "token_expired"
    
    # User management events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"
    USER_DELETED = "user_deleted"
    
    # Access control events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_CHANGED = "permission_changed"
    
    # Data access events
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    
    # Book operations
    BOOK_UPLOAD = "book_upload"
    BOOK_DOWNLOAD = "book_download"
    BOOK_DELETE = "book_delete"
    BOOK_QUERY = "book_query"
    
    # Conversation operations
    CONVERSATION_CREATE = "conversation_create"
    CONVERSATION_READ = "conversation_read"
    CONVERSATION_UPDATE = "conversation_update"
    CONVERSATION_DELETE = "conversation_delete"
    
    # Export operations
    DATA_EXPORT = "data_export"
    EXPORT_DOWNLOAD = "export_download"
    
    # ML API operations
    ML_DATA_ACCESS = "ml_data_access"
    ML_TRAINING_REQUEST = "ml_training_request"
    ML_BATCH_REQUEST = "ml_batch_request"
    
    # System operations
    SYSTEM_CONFIG_CHANGE = "system_config_change"
    SYSTEM_BACKUP = "system_backup"
    SYSTEM_RESTORE = "system_restore"
    
    # Security events
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SECURITY_VIOLATION = "security_violation"
    
    # Privacy operations
    DATA_ANONYMIZATION = "data_anonymization"
    DATA_PURGE = "data_purge"
    PRIVACY_REQUEST = "privacy_request"


class AuditLevel(str, Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    event_id: str
    event_type: AuditEventType
    level: AuditLevel
    timestamp: datetime
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: str
    result: str  # success, failure, error
    details: Dict[str, Any]
    sensitive_data_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """Service for audit logging and compliance monitoring."""
    
    def __init__(self):
        """Initialize audit logger."""
        self.settings = get_settings()
        self.encryption_service = get_encryption_service()
        
        # Create audit log directory
        self.audit_dir = Path("audit_logs")
        self.audit_dir.mkdir(exist_ok=True)
        
        # Audit log files
        self.audit_file = self.audit_dir / "audit.log"
        self.security_file = self.audit_dir / "security.log"
        self.access_file = self.audit_dir / "access.log"
        
        # Event queue for async processing
        self.event_queue = asyncio.Queue()
        self.processing_task = None
        
        # Start background processing
        self._start_processing()
    
    def _start_processing(self):
        """Start background audit event processing."""
        if self.processing_task is None or self.processing_task.done():
            self.processing_task = asyncio.create_task(self._process_events())
    
    async def _process_events(self):
        """Process audit events from queue."""
        while True:
            try:
                event = await self.event_queue.get()
                await self._write_audit_event(event)
                self.event_queue.task_done()
            except Exception as e:
                logger.error(f"Failed to process audit event: {e}")
                await asyncio.sleep(1)
    
    async def _write_audit_event(self, event: AuditEvent):
        """Write audit event to appropriate log files."""
        try:
            # Convert event to JSON
            event_data = event.to_dict()
            event_json = json.dumps(event_data, default=str)
            
            # Write to main audit log
            with open(self.audit_file, 'a', encoding='utf-8') as f:
                f.write(f"{event_json}\n")
            
            # Write to specific log files based on event type
            if event.event_type in [
                AuditEventType.UNAUTHORIZED_ACCESS,
                AuditEventType.RATE_LIMIT_EXCEEDED,
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.LOGIN_FAILURE
            ]:
                with open(self.security_file, 'a', encoding='utf-8') as f:
                    f.write(f"{event_json}\n")
            
            if event.event_type in [
                AuditEventType.DATA_READ,
                AuditEventType.DATA_WRITE,
                AuditEventType.DATA_UPDATE,
                AuditEventType.DATA_DELETE,
                AuditEventType.ML_DATA_ACCESS
            ]:
                with open(self.access_file, 'a', encoding='utf-8') as f:
                    f.write(f"{event_json}\n")
            
            logger.debug(f"Audit event written: {event.event_type.value}")
            
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")
    
    def log_event(
        self,
        event_type: AuditEventType,
        action: str,
        result: str = "success",
        level: AuditLevel = AuditLevel.INFO,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        sensitive_data: Optional[str] = None
    ):
        """Log audit event."""
        try:
            # Generate event ID
            event_id = self.encryption_service.generate_secure_token(16)
            
            # Hash sensitive data if provided
            sensitive_data_hash = None
            if sensitive_data:
                import hashlib
                sensitive_data_hash = hashlib.sha256(sensitive_data.encode()).hexdigest()
            
            # Create audit event
            event = AuditEvent(
                event_id=event_id,
                event_type=event_type,
                level=level,
                timestamp=datetime.utcnow(),
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                result=result,
                details=details or {},
                sensitive_data_hash=sensitive_data_hash
            )
            
            # Add to processing queue
            try:
                self.event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Audit event queue full, dropping event")
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    
    def log_authentication(
        self,
        event_type: AuditEventType,
        username: str,
        result: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log authentication event."""
        level = AuditLevel.INFO if result == "success" else AuditLevel.WARNING
        
        self.log_event(
            event_type=event_type,
            action=f"user_authentication_{event_type.value}",
            result=result,
            level=level,
            user_id=username,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="authentication",
            details=details
        )
    
    def log_data_access(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log data access event."""
        event_type_map = {
            "read": AuditEventType.DATA_READ,
            "write": AuditEventType.DATA_WRITE,
            "update": AuditEventType.DATA_UPDATE,
            "delete": AuditEventType.DATA_DELETE
        }
        
        event_type = event_type_map.get(action.lower(), AuditEventType.DATA_READ)
        level = AuditLevel.INFO if result == "success" else AuditLevel.ERROR
        
        self.log_event(
            event_type=event_type,
            action=f"data_{action}",
            result=result,
            level=level,
            user_id=user_id,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details
        )
    
    def log_book_operation(
        self,
        operation: str,
        book_id: str,
        user_id: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log book operation event."""
        event_type_map = {
            "upload": AuditEventType.BOOK_UPLOAD,
            "download": AuditEventType.BOOK_DOWNLOAD,
            "delete": AuditEventType.BOOK_DELETE,
            "query": AuditEventType.BOOK_QUERY
        }
        
        event_type = event_type_map.get(operation.lower(), AuditEventType.BOOK_QUERY)
        level = AuditLevel.INFO if result == "success" else AuditLevel.ERROR
        
        self.log_event(
            event_type=event_type,
            action=f"book_{operation}",
            result=result,
            level=level,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="book",
            resource_id=book_id,
            details=details
        )
    
    def log_conversation_operation(
        self,
        operation: str,
        conversation_id: str,
        user_id: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log conversation operation event."""
        event_type_map = {
            "create": AuditEventType.CONVERSATION_CREATE,
            "read": AuditEventType.CONVERSATION_READ,
            "update": AuditEventType.CONVERSATION_UPDATE,
            "delete": AuditEventType.CONVERSATION_DELETE
        }
        
        event_type = event_type_map.get(operation.lower(), AuditEventType.CONVERSATION_READ)
        level = AuditLevel.INFO if result == "success" else AuditLevel.ERROR
        
        self.log_event(
            event_type=event_type,
            action=f"conversation_{operation}",
            result=result,
            level=level,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="conversation",
            resource_id=conversation_id,
            details=details
        )
    
    def log_ml_access(
        self,
        operation: str,
        user_id: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log ML API access event."""
        event_type_map = {
            "data_access": AuditEventType.ML_DATA_ACCESS,
            "training_request": AuditEventType.ML_TRAINING_REQUEST,
            "batch_request": AuditEventType.ML_BATCH_REQUEST
        }
        
        event_type = event_type_map.get(operation.lower(), AuditEventType.ML_DATA_ACCESS)
        level = AuditLevel.INFO if result == "success" else AuditLevel.ERROR
        
        self.log_event(
            event_type=event_type,
            action=f"ml_{operation}",
            result=result,
            level=level,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="ml_api",
            details=details
        )
    
    def log_security_event(
        self,
        event_type: AuditEventType,
        action: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log security event."""
        self.log_event(
            event_type=event_type,
            action=action,
            result="security_event",
            level=AuditLevel.WARNING,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="security",
            details=details
        )
    
    def log_privacy_operation(
        self,
        operation: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None
    ):
        """Log privacy-related operation."""
        event_type_map = {
            "anonymize": AuditEventType.DATA_ANONYMIZATION,
            "purge": AuditEventType.DATA_PURGE,
            "request": AuditEventType.PRIVACY_REQUEST
        }
        
        event_type = event_type_map.get(operation.lower(), AuditEventType.PRIVACY_REQUEST)
        level = AuditLevel.INFO if result == "success" else AuditLevel.ERROR
        
        self.log_event(
            event_type=event_type,
            action=f"privacy_{operation}",
            result=result,
            level=level,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details
        )
    
    def search_audit_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        resource_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search audit logs with filters."""
        try:
            events = []
            
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event_data = json.loads(line.strip())
                        
                        # Apply filters
                        if start_time and datetime.fromisoformat(event_data['timestamp']) < start_time:
                            continue
                        if end_time and datetime.fromisoformat(event_data['timestamp']) > end_time:
                            continue
                        if user_id and event_data.get('user_id') != user_id:
                            continue
                        if event_type and event_data.get('event_type') != event_type.value:
                            continue
                        if resource_type and event_data.get('resource_type') != resource_type:
                            continue
                        
                        events.append(event_data)
                        
                        if len(events) >= limit:
                            break
                            
                    except json.JSONDecodeError:
                        continue
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to search audit logs: {e}")
            return []
    
    def get_audit_summary(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit log summary statistics."""
        try:
            summary = {
                "total_events": 0,
                "event_types": {},
                "users": set(),
                "resources": {},
                "security_events": 0,
                "failed_operations": 0
            }
            
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event_data = json.loads(line.strip())
                        
                        # Apply time filters
                        if start_time and datetime.fromisoformat(event_data['timestamp']) < start_time:
                            continue
                        if end_time and datetime.fromisoformat(event_data['timestamp']) > end_time:
                            continue
                        
                        summary["total_events"] += 1
                        
                        # Count event types
                        event_type = event_data.get('event_type', 'unknown')
                        summary["event_types"][event_type] = summary["event_types"].get(event_type, 0) + 1
                        
                        # Track users
                        if event_data.get('user_id'):
                            summary["users"].add(event_data['user_id'])
                        
                        # Count resources
                        resource_type = event_data.get('resource_type', 'unknown')
                        summary["resources"][resource_type] = summary["resources"].get(resource_type, 0) + 1
                        
                        # Count security events
                        if event_type in ['unauthorized_access', 'rate_limit_exceeded', 'security_violation']:
                            summary["security_events"] += 1
                        
                        # Count failed operations
                        if event_data.get('result') in ['failure', 'error']:
                            summary["failed_operations"] += 1
                            
                    except json.JSONDecodeError:
                        continue
            
            summary["unique_users"] = len(summary["users"])
            summary["users"] = list(summary["users"])  # Convert set to list for JSON serialization
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get audit summary: {e}")
            return {"error": str(e)}


# Global audit logger instance
_audit_logger = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger