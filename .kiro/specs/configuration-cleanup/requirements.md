# Configuration Cleanup Requirements

## Overview
Consolidate and clean up the multimodal-librarian project configuration to eliminate technical debt, reduce complexity, and establish a single source of truth for deployment configurations.

## Current State Analysis

### Problems Identified
1. **Multiple Competing Configurations**: 15+ Dockerfiles, 8+ main application files, dozens of deployment scripts
2. **Secret Naming Inconsistency**: Mix of `learning/*` and `full-ml/*` secret references
3. **Configuration Drift**: Experimental configurations left in codebase
4. **Deployment Confusion**: Unclear which deployment approach is canonical
5. **Technical Debt**: Backward-compatible hacks and workarounds

### Current Working State
- **Active Deployment**: `multimodal-librarian-full-ml` cluster
- **Working Application**: `src/multimodal_librarian/main_minimal.py`
- **Working Secrets**: `multimodal-librarian/full-ml/*` (canonical) + `multimodal-librarian/learning/*` (hack)
- **Working Dockerfile**: `Dockerfile.full-ml`
- **Working Task Definition**: `full-ml-task-def.json`

## User Stories

### US-1: Single Source of Truth
**As a** developer  
**I want** one canonical configuration for each environment  
**So that** I know exactly which files to use and modify  

**Acceptance Criteria:**
- Single main application file for production deployment
- Single Dockerfile for production deployment
- Single deployment script for production deployment
- Single task definition for production deployment
- All experimental/learning configurations clearly separated or removed

### US-2: Consistent Secret Management
**As a** system administrator  
**I want** consistent secret naming across all components  
**So that** configuration is predictable and maintainable  

**Acceptance Criteria:**
- All application code uses `multimodal-librarian/full-ml/*` secrets
- Remove backward-compatible `multimodal-librarian/learning/*` secrets
- Update all configuration files to use consistent naming
- Document secret structure and naming conventions

### US-3: Clean Development Environment
**As a** developer  
**I want** a clean, organized codebase  
**So that** I can focus on features instead of configuration management  

**Acceptance Criteria:**
- Remove unused/experimental files
- Organize remaining files with clear naming
- Create clear documentation for each configuration
- Establish naming conventions for future development

### US-4: Maintainable Deployment Process
**As a** DevOps engineer  
**I want** a simple, reliable deployment process  
**So that** deployments are predictable and debuggable  

**Acceptance Criteria:**
- Single deployment script that works reliably
- Clear rollback procedures
- Comprehensive deployment documentation
- Automated validation of deployment configuration

## Technical Requirements

### File Organization
```
Production (Keep):
- src/multimodal_librarian/main.py (rename from main_minimal.py)
- Dockerfile (rename from Dockerfile.full-ml)
- scripts/deploy.sh (rename from deploy-full-ml.sh)
- task-definition.json (rename from full-ml-task-def.json)
- requirements.txt (consolidate from requirements-full-ml.txt)

Development/Learning (Archive):
- Move all learning/experimental files to archive/ directory
- Keep for reference but remove from active development

Remove (Delete):
- Unused Dockerfiles
- Unused main application files
- Unused deployment scripts
- Unused task definitions
- Backward-compatible secrets
```

### Secret Consolidation
- **Canonical Secrets**: `multimodal-librarian/full-ml/*`
- **Remove**: `multimodal-librarian/learning/*` (backward-compatible hack)
- **Update**: All application code to use canonical secrets
- **Validate**: All services can access required secrets

### Configuration Standards
- **Environment Variables**: Standardized naming convention
- **Feature Flags**: Consistent structure across all components
- **Logging**: Unified logging configuration
- **Monitoring**: Consistent health check and metrics endpoints

## Cleanup Strategy

### Phase 1: Inventory and Analysis
1. **Catalog all configuration files**
   - List all Dockerfiles, main files, deployment scripts
   - Identify which are actively used vs experimental
   - Map dependencies between files

2. **Analyze current deployment**
   - Document exactly what's running in production
   - Identify all AWS resources in use
   - Map secret usage across all components

### Phase 2: Consolidation
1. **Create canonical configuration**
   - Rename working files to standard names
   - Consolidate requirements files
   - Update all references to use standard names

2. **Update secret references**
   - Remove all `learning/*` secret references
   - Ensure all code uses `full-ml/*` secrets
   - Test connectivity after changes

### Phase 3: Cleanup
1. **Archive experimental files**
   - Move learning/experimental files to archive/
   - Remove unused files completely
   - Update documentation

2. **Remove backward-compatible hacks**
   - Delete `multimodal-librarian/learning/*` secrets
   - Remove temporary workarounds
   - Validate everything still works

### Phase 4: Documentation
1. **Create deployment guide**
   - Document canonical deployment process
   - Create troubleshooting guide
   - Document rollback procedures

2. **Establish conventions**
   - File naming conventions
   - Secret naming conventions
   - Development workflow

## Success Criteria

### Immediate Goals
- [ ] Single main application file in use
- [ ] Single Dockerfile for production
- [ ] Single deployment script that works
- [ ] All secrets use consistent naming
- [ ] No backward-compatible hacks

### Long-term Goals
- [ ] Clear separation between production and experimental code
- [ ] Documented deployment process
- [ ] Established conventions for future development
- [ ] Reduced cognitive load for developers

## Risks and Mitigations

### Risk: Breaking Production
- **Mitigation**: Test each change thoroughly, maintain rollback capability
- **Validation**: Comprehensive testing after each phase

### Risk: Losing Experimental Work
- **Mitigation**: Archive rather than delete experimental configurations
- **Documentation**: Document what each experimental configuration was for

### Risk: Secret Access Issues
- **Mitigation**: Update and test secret access before removing old secrets
- **Validation**: Verify all services can access required secrets

## Out of Scope
- Major architectural changes (keep current working architecture)
- New feature development (focus only on cleanup)
- Performance optimization (maintain current performance)
- Infrastructure changes (keep current AWS resources)

## Dependencies
- Current `multimodal-librarian-full-ml` deployment must remain stable
- All existing functionality must be preserved
- No downtime during cleanup process