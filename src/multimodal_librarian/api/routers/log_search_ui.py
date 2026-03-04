"""
Log Search UI Router

This module provides web interface routes for the log search functionality.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter(tags=["Log Search UI"])

# Initialize templates
templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
templates = Jinja2Templates(directory=templates_dir)


@router.get("/logs", response_class=HTMLResponse)
async def log_search_interface(request: Request):
    """
    Serve the log search and analysis web interface.
    
    Provides a comprehensive web UI for searching, filtering, and analyzing
    logs from all services in the local development environment.
    """
    return templates.TemplateResponse("log_search.html", {"request": request})


@router.get("/logs/search", response_class=HTMLResponse)
async def log_search_page(request: Request):
    """
    Alternative route for the log search interface.
    """
    return templates.TemplateResponse("log_search.html", {"request": request})