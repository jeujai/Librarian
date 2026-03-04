#!/bin/bash
#
# Code Quality Checker
#
# This script runs comprehensive code quality checks.
#

set -e

echo "🔍 Running code quality checks..."

# Format check
echo "📝 Checking code formatting..."
if command -v black >/dev/null 2>&1; then
    black --check --diff src/ tests/ || {
        echo "❌ Code formatting issues found. Run 'make format' to fix."
        exit 1
    }
    echo "✅ Code formatting is good"
else
    echo "⚠️  Black not found, skipping format check"
fi

# Import sorting check
echo "📦 Checking import sorting..."
if command -v isort >/dev/null 2>&1; then
    isort --check-only --diff src/ tests/ || {
        echo "❌ Import sorting issues found. Run 'make format' to fix."
        exit 1
    }
    echo "✅ Import sorting is good"
else
    echo "⚠️  isort not found, skipping import check"
fi

# Linting
echo "🔍 Running linter..."
if command -v flake8 >/dev/null 2>&1; then
    flake8 src/ tests/ || {
        echo "❌ Linting issues found. Fix the issues above."
        exit 1
    }
    echo "✅ Linting passed"
else
    echo "⚠️  flake8 not found, skipping lint check"
fi

# Type checking
echo "🔬 Running type checker..."
if command -v mypy >/dev/null 2>&1; then
    mypy src/ || {
        echo "❌ Type checking issues found. Fix the issues above."
        exit 1
    }
    echo "✅ Type checking passed"
else
    echo "⚠️  mypy not found, skipping type check"
fi

echo "🎉 All code quality checks passed!"
