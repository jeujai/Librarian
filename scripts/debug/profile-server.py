#!/usr/bin/env python3
"""
Performance Profiler for Development

This script starts the application with performance profiling enabled.
"""

import os
import sys
import cProfile
import pstats
from pathlib import Path

# Set up profiling
profile_dir = Path("/app/profiles")
profile_dir.mkdir(exist_ok=True)

# Set environment
os.environ.update({
    'PYTHONPATH': '/app/src:/app',
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'ENABLE_PROFILING': 'true',
    'PROFILE_OUTPUT_DIR': str(profile_dir)
})

def run_with_profiling():
    """Run the application with profiling."""
    import uvicorn
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    try:
        uvicorn.run(
            "multimodal_librarian.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Disable reload for accurate profiling
            log_level="info"
        )
    finally:
        profiler.disable()
        
        # Save profile results
        profile_file = profile_dir / f"profile_{int(time.time())}.prof"
        profiler.dump_stats(str(profile_file))
        
        # Generate text report
        with open(profile_dir / "profile_report.txt", "w") as f:
            stats = pstats.Stats(profiler, stream=f)
            stats.sort_stats('cumulative')
            stats.print_stats(50)  # Top 50 functions
        
        print(f"📊 Profile saved to: {profile_file}")
        print(f"📄 Report saved to: {profile_dir}/profile_report.txt")

if __name__ == "__main__":
    import time
    run_with_profiling()
