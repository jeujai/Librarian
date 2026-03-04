#!/usr/bin/env python3
"""
Request Tracer for Development

This script traces HTTP requests for debugging purposes.
"""

import time
import json
from pathlib import Path

class RequestTracer:
    """Simple request tracer for development."""
    
    def __init__(self):
        self.trace_file = Path("/app/profiles/request_traces.jsonl")
        self.trace_file.parent.mkdir(exist_ok=True)
    
    def trace_request(self, method, path, headers, body=None):
        """Trace an HTTP request."""
        trace_data = {
            "timestamp": time.time(),
            "method": method,
            "path": path,
            "headers": dict(headers) if headers else {},
            "body": body,
            "trace_id": f"trace_{int(time.time() * 1000)}"
        }
        
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(trace_data) + "\n")
    
    def trace_response(self, status_code, headers, body=None, duration=None):
        """Trace an HTTP response."""
        trace_data = {
            "timestamp": time.time(),
            "type": "response",
            "status_code": status_code,
            "headers": dict(headers) if headers else {},
            "body": body,
            "duration_ms": duration * 1000 if duration else None
        }
        
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(trace_data) + "\n")

# Global tracer instance
tracer = RequestTracer()

def enable_request_tracing():
    """Enable request tracing middleware."""
    print("🔍 Request tracing enabled")
    print(f"   Traces will be saved to: {tracer.trace_file}")
    
    # This would be integrated with FastAPI middleware
    # For now, it's a placeholder for the tracing infrastructure

if __name__ == "__main__":
    enable_request_tracing()
