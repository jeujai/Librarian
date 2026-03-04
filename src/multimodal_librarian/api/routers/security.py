"""
Security management API endpoints.

This module provides security management endpoints for audit logs,
data deletion, privacy operations, and system security monitoring.
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ...security.auth import (
    get_auth_service, get_authz_service, AuthenticationService, 
    AuthorizationService, Permission, AuthenticationError, AuthorizationError
)
from ...security.audit import get_audit_logger, AuditEventType, AuditLevel
from ...security.privacy import get_privacy_service, PrivacyService
from ...security.rate_limiter import get_rate_limiter, RateLimitType
from ..models import SuccessResponse, ErrorResponse

router = APIRouter(prefix="/security", tags=["security"])
security = HTTPBearer()


class DataDeletionRequest(BaseModel):
    """Data deletion request model."""
    resource_type: str  # "book" or "conversation"
    resource_id: str
    confirm_deletion: bool = False


class DataDeletionResponse(BaseModel):
    """Data deletion response model."""
    resource_id: str
    resource_type: str
    deletion_status: str
    deleted_components: List[str]
    errors: List[str]
    timestamp: str


class AuditLogQuery(BaseModel):
    """Audit log query parameters."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    user_id: Optional[str] = None
    event_type: Optional[str] = None
    resource_type: Optional[str] = None
    limit: int = 100


class RateLimitStatus(BaseModel):
    """Rate limit status model."""
    endpoint: str
    limit: int
    window: int
    current: int
    remaining: int
    reset_time: Optional[float] = None


def require_admin_permission(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service),
    authz_service: AuthorizationService = Depends(get_authz_service)
):
    """Dependency to require admin permission."""
    try:
        token_data = auth_service.verify_token(credentials.credentials)
        
        if not authz_service.check_permission(token_data.permissions, Permission.ADMIN_ACCESS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        return token_data
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


def require_audit_permission(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service),
    authz_service: AuthorizationService = Depends(get_authz_service)
):
    """Dependency to require audit log access permission."""
    try:
        token_data = auth_service.verify_token(credentials.credentials)
        
        if not authz_service.check_permission(token_data.permissions, Permission.AUDIT_LOGS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Audit log access required"
            )
        
        return token_data
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.delete("/data", response_model=DataDeletionResponse)
async def delete_data_completely(
    request: Request,
    deletion_request: DataDeletionRequest,
    token_data = Depends(require_admin_permission),
    privacy_service: PrivacyService = Depends(get_privacy_service)
):
    """Completely delete data and all associated information."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        if not deletion_request.confirm_deletion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deletion must be confirmed by setting confirm_deletion=true"
            )
        
        # Log deletion request
        audit_logger.log_privacy_operation(
            operation="purge",
            user_id=token_data.user_id,
            resource_type=deletion_request.resource_type,
            resource_id=deletion_request.resource_id,
            details={
                "requested_by": token_data.username,
                "ip_address": client_ip,
                "confirmed": deletion_request.confirm_deletion
            }
        )
        
        # Perform deletion based on resource type
        if deletion_request.resource_type == "book":
            deletion_report = await privacy_service.delete_book_completely(
                book_id=deletion_request.resource_id,
                user_id=token_data.user_id,
                ip_address=client_ip
            )
        elif deletion_request.resource_type == "conversation":
            deletion_report = await privacy_service.delete_conversation_completely(
                conversation_id=deletion_request.resource_id,
                user_id=token_data.user_id,
                ip_address=client_ip
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported resource type: {deletion_request.resource_type}"
            )
        
        return DataDeletionResponse(
            resource_id=deletion_report["book_id"] if "book_id" in deletion_report else deletion_report["conversation_id"],
            resource_type=deletion_request.resource_type,
            deletion_status="success" if not deletion_report["errors"] else "partial_failure",
            deleted_components=deletion_report["deleted_components"],
            errors=deletion_report["errors"],
            timestamp=deletion_report["timestamp"].isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_privacy_operation(
            operation="purge",
            user_id=token_data.user_id,
            resource_type=deletion_request.resource_type,
            resource_id=deletion_request.resource_id,
            result="error",
            details={"error": str(e)}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data deletion failed: {str(e)}"
        )


@router.get("/audit-logs", response_model=List[dict])
async def get_audit_logs(
    request: Request,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    token_data = Depends(require_audit_permission)
):
    """Retrieve audit logs with filtering."""
    try:
        audit_logger = get_audit_logger()
        
        # Convert event_type string to enum if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {event_type}"
                )
        
        # Search audit logs
        logs = audit_logger.search_audit_logs(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            event_type=event_type_enum,
            resource_type=resource_type,
            limit=limit
        )
        
        # Log audit log access
        audit_logger.log_event(
            event_type=AuditEventType.AUDIT_LOGS,
            action="audit_log_access",
            result="success",
            user_id=token_data.user_id,
            ip_address=request.client.host if request.client else "unknown",
            details={
                "query_params": {
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "user_id": user_id,
                    "event_type": event_type,
                    "resource_type": resource_type,
                    "limit": limit
                },
                "results_count": len(logs)
            }
        )
        
        return logs
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit log retrieval failed: {str(e)}"
        )


@router.get("/audit-summary", response_model=dict)
async def get_audit_summary(
    request: Request,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    token_data = Depends(require_audit_permission)
):
    """Get audit log summary statistics."""
    try:
        audit_logger = get_audit_logger()
        
        summary = audit_logger.get_audit_summary(
            start_time=start_time,
            end_time=end_time
        )
        
        # Log summary access
        audit_logger.log_event(
            event_type=AuditEventType.AUDIT_LOGS,
            action="audit_summary_access",
            result="success",
            user_id=token_data.user_id,
            ip_address=request.client.host if request.client else "unknown",
            details={
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None
            }
        )
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit summary retrieval failed: {str(e)}"
        )


@router.get("/rate-limits/{identifier}", response_model=List[RateLimitStatus])
async def get_rate_limit_status(
    request: Request,
    identifier: str,
    limit_type: RateLimitType = Query(RateLimitType.PER_USER),
    token_data = Depends(require_admin_permission)
):
    """Get rate limit status for a specific identifier."""
    try:
        rate_limiter = get_rate_limiter()
        audit_logger = get_audit_logger()
        
        # Get status for all configured endpoints
        endpoints = [
            "api_general", "api_upload", "api_query", "api_export",
            "ml_streaming", "ml_batch", "ml_training",
            "auth_login", "auth_token", "websocket_connect"
        ]
        
        statuses = []
        for endpoint in endpoints:
            status_info = rate_limiter.get_rate_limit_status(
                identifier=identifier,
                endpoint=endpoint,
                limit_type=limit_type
            )
            
            if status_info.get("status") == "active":
                statuses.append(RateLimitStatus(
                    endpoint=endpoint,
                    limit=status_info["limit"],
                    window=status_info["window"],
                    current=status_info["current"],
                    remaining=status_info["remaining"],
                    reset_time=status_info.get("reset_time")
                ))
        
        # Log rate limit status access
        audit_logger.log_event(
            event_type=AuditEventType.SYSTEM_CONFIG_CHANGE,
            action="rate_limit_status_check",
            result="success",
            user_id=token_data.user_id,
            ip_address=request.client.host if request.client else "unknown",
            details={
                "identifier": identifier,
                "limit_type": limit_type.value,
                "endpoints_checked": len(endpoints)
            }
        )
        
        return statuses
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rate limit status retrieval failed: {str(e)}"
        )


@router.post("/rate-limits/{identifier}/reset", response_model=SuccessResponse)
async def reset_rate_limit(
    request: Request,
    identifier: str,
    endpoint: str,
    limit_type: RateLimitType = Query(RateLimitType.PER_USER),
    token_data = Depends(require_admin_permission)
):
    """Reset rate limit for a specific identifier and endpoint."""
    try:
        rate_limiter = get_rate_limiter()
        audit_logger = get_audit_logger()
        
        # Reset rate limit
        rate_limiter.reset_rate_limit(
            identifier=identifier,
            endpoint=endpoint,
            limit_type=limit_type
        )
        
        # Log rate limit reset
        audit_logger.log_event(
            event_type=AuditEventType.SYSTEM_CONFIG_CHANGE,
            action="rate_limit_reset",
            result="success",
            user_id=token_data.user_id,
            ip_address=request.client.host if request.client else "unknown",
            details={
                "identifier": identifier,
                "endpoint": endpoint,
                "limit_type": limit_type.value
            }
        )
        
        return SuccessResponse(
            message="Rate limit reset successfully",
            details={
                "identifier": identifier,
                "endpoint": endpoint,
                "limit_type": limit_type.value
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rate limit reset failed: {str(e)}"
        )


@router.get("/privacy/compliance-check", response_model=dict)
async def check_privacy_compliance(
    request: Request,
    token_data = Depends(require_admin_permission),
    privacy_service: PrivacyService = Depends(get_privacy_service)
):
    """Check data retention and privacy compliance."""
    try:
        audit_logger = get_audit_logger()
        
        compliance_report = privacy_service.check_data_retention_compliance()
        
        # Log compliance check
        audit_logger.log_event(
            event_type=AuditEventType.PRIVACY_REQUEST,
            action="compliance_check",
            result="success",
            user_id=token_data.user_id,
            ip_address=request.client.host if request.client else "unknown",
            details={"compliance_status": compliance_report.get("compliance_status")}
        )
        
        return compliance_report
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Privacy compliance check failed: {str(e)}"
        )


@router.post("/privacy/export-user-data", response_model=dict)
async def export_user_data(
    request: Request,
    user_id: str,
    export_format: str = "json",
    token_data = Depends(require_admin_permission),
    privacy_service: PrivacyService = Depends(get_privacy_service)
):
    """Export all data for a specific user (GDPR compliance)."""
    try:
        export_report = privacy_service.export_user_data(
            user_id=user_id,
            requesting_user_id=token_data.user_id,
            export_format=export_format
        )
        
        return export_report
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User data export failed: {str(e)}"
        )