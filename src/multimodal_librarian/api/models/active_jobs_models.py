"""
Active Jobs WebSocket Message Models.

This module defines the Pydantic models for real-time Active Jobs report
updates delivered over WebSocket connections.

Requirements: 5.1, 5.2, 5.3, 5.4
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SubstageInfo(BaseModel):
    """
    Progress info for a single substage (Bridges or KG).

    Requirements: 3.1, 5.2
    """
    label: str = Field(..., description="Substage label, e.g. 'Bridges' or 'KG'")
    percentage: int = Field(..., ge=0, le=100, description="Substage progress 0–100")


class ActiveJobPayload(BaseModel):
    """
    Row-level payload representing a single active job.

    Requirements: 2.2, 5.2
    """
    document_id: str = Field(..., description="Unique document identifier")
    document_title: str = Field(..., description="Human-readable document title")
    status: str = Field(..., description="Job status: pending | running | completed | failed")
    current_step: Optional[str] = Field(None, description="Current processing step")
    progress_percentage: int = Field(..., ge=0, le=100, description="Overall progress 0–100")
    elapsed_seconds: Optional[float] = Field(None, description="Seconds since job started")
    retry_count: int = Field(0, ge=0, description="Number of retries")
    substages: Optional[List[SubstageInfo]] = Field(None, description="Bridges/KG substage breakdown")
    error_message: Optional[str] = Field(None, description="Error details when status is 'failed'")


class ActiveJobsUpdateMessage(BaseModel):
    """
    Incremental update for a single active job, sent to subscribed connections.

    Requirements: 5.1, 5.2, 5.4
    """
    type: Literal["active_jobs_update"] = "active_jobs_update"
    job: ActiveJobPayload
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class ActiveJobsSnapshotMessage(BaseModel):
    """
    Full snapshot of all active jobs, sent on initial subscription.

    Requirements: 5.3, 5.4
    """
    type: Literal["active_jobs_snapshot"] = "active_jobs_snapshot"
    jobs: List[ActiveJobPayload] = Field(default_factory=list, description="All currently active jobs")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    error: Optional[str] = Field(None, description="Error description on degraded snapshot")
