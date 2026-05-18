## Purpose

Consolidate and clean up the multimodal-librarian project configuration to eliminate technical debt, reduce complexity, and establish a single source of truth for deployment configurations.

## Requirements

### Requirement: US-1: Single Source of Truth

The system SHALL implement us-1: single source of truth as described in the requirements.

#### Scenario: Single main application file for production deployment

- **THEN** Single main application file for production deployment

#### Scenario: Single Dockerfile for production deployment

- **THEN** Single Dockerfile for production deployment

#### Scenario: Single deployment script for production deployment

- **THEN** Single deployment script for production deployment

#### Scenario: Single task definition for production deployment

- **THEN** Single task definition for production deployment

#### Scenario: All experimental/learning configurations clearly separated o

- **THEN** All experimental/learning configurations clearly separated or removed

### Requirement: US-2: Consistent Secret Management

The system SHALL implement us-2: consistent secret management as described in the requirements.

#### Scenario: All application code uses `multimodal-librarian/full-ml/*` s

- **THEN** All application code uses `multimodal-librarian/full-ml/*` secrets

#### Scenario: Remove backward-compatible `multimodal-librarian/learning/*`

- **THEN** Remove backward-compatible `multimodal-librarian/learning/*` secrets

#### Scenario: Update all configuration files to use consistent naming

- **THEN** Update all configuration files to use consistent naming

#### Scenario: Document secret structure and naming conventions

- **THEN** Document secret structure and naming conventions

### Requirement: US-3: Clean Development Environment

The system SHALL implement us-3: clean development environment as described in the requirements.

#### Scenario: Remove unused/experimental files

- **THEN** Remove unused/experimental files

#### Scenario: Organize remaining files with clear naming

- **THEN** Organize remaining files with clear naming

#### Scenario: Create clear documentation for each configuration

- **THEN** Create clear documentation for each configuration

#### Scenario: Establish naming conventions for future development

- **THEN** Establish naming conventions for future development

### Requirement: US-4: Maintainable Deployment Process

The system SHALL implement us-4: maintainable deployment process as described in the requirements.

#### Scenario: Single deployment script that works reliably

- **THEN** Single deployment script that works reliably

#### Scenario: Clear rollback procedures

- **THEN** Clear rollback procedures

#### Scenario: Comprehensive deployment documentation

- **THEN** Comprehensive deployment documentation

#### Scenario: Automated validation of deployment configuration

- **THEN** Automated validation of deployment configuration
