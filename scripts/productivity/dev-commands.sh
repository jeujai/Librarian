#!/bin/bash
#
# Quick Development Commands
#
# This script provides shortcuts for common development tasks.
#

# Quick restart
dev-restart() {
    echo "🔄 Quick restart..."
    make restart-optimized
}

# Quick test
dev-test() {
    echo "🧪 Running tests..."
    make test-local-optimized
}

# Quick format
dev-format() {
    echo "✨ Formatting code..."
    make format
}

# Quick lint
dev-lint() {
    echo "🔍 Linting code..."
    make lint
}

# Quick status
dev-status() {
    echo "📊 Development status..."
    make status-optimized
}

# Quick logs
dev-logs() {
    echo "📋 Showing logs..."
    make logs-optimized
}

# Quick health check
dev-health() {
    echo "🏥 Health check..."
    curl -s http://localhost:8000/health/simple | jq .
}

# Quick performance check
dev-perf() {
    echo "⚡ Performance check..."
    python scripts/dev-optimization-manager.py metrics
}

# Export functions
export -f dev-restart dev-test dev-format dev-lint dev-status dev-logs dev-health dev-perf

echo "🚀 Development commands loaded:"
echo "  dev-restart  - Quick restart"
echo "  dev-test     - Run tests"
echo "  dev-format   - Format code"
echo "  dev-lint     - Lint code"
echo "  dev-status   - Show status"
echo "  dev-logs     - Show logs"
echo "  dev-health   - Health check"
echo "  dev-perf     - Performance check"
