# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please do NOT open a public issue. Send details to the project maintainers privately. We will respond within 48 hours with an assessment and timeline for a fix.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security best practices for deployments

- Never commit `.env` or `.env.local` files containing real API keys
- Use environment variable interpolation in `docker-compose.yml` rather than hardcoded values
- Rotate API keys regularly
- Run the application behind a reverse proxy (nginx) in production, with TLS enabled
