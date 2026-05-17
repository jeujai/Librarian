# Contributing to Multimodal Librarian

Thanks for your interest in contributing.

## Getting started

1. Fork the repository
2. Clone your fork and set up the development environment:
   ```bash
   cp .env.local.example .env.local
   make dev-local
   ```
3. Create a feature branch from `main`

## Development workflow

- Code is in `src/multimodal_librarian/`
- Tests are in `tests/`
- Run tests with `pytest` (requires Docker services running)
- This project uses spec-driven development — major features should have a spec in `openspec/specs/`

## Pull requests

- Keep changes focused. One feature or fix per PR
- Add tests for new functionality
- Ensure existing tests pass
- Follow the existing code style (Black, isort, flake8 configured in `pyproject.toml`)

## Commit conventions

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for restructuring
- `test:` for test additions or fixes

## Reporting bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Environment details (OS, Python version, Docker version)
