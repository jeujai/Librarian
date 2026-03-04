#!/usr/bin/env python3
"""
Development server runner for the Multimodal Librarian.
"""

import uvicorn
from multimodal_librarian.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    
    print(f"Starting {settings.app_name} development server...")
    print(f"Debug mode: {settings.debug}")
    print(f"Server will be available at: http://{settings.api_host}:{settings.api_port}")
    
    uvicorn.run(
        "multimodal_librarian.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,  # Enable auto-reload for development
        log_level=settings.log_level.lower(),
    )