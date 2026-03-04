#!/usr/bin/env python3
"""
Debug Server for Development

This script starts the application with debugging enabled,
including remote debugging capabilities and profiling.
"""

import os
import sys
import debugpy

# Enable remote debugging
debugpy.listen(("0.0.0.0", 5678))
print("🐛 Debug server listening on port 5678")
print("   Attach your debugger to localhost:5678")

# Set development environment
os.environ.update({
    'PYTHONPATH': '/app/src:/app',
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'DEBUG': 'true',
    'DEVELOPMENT_MODE': 'true',
    'ENABLE_DEBUGGER': 'true'
})

# Start the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["/app/src"],
        log_level="debug"
    )
