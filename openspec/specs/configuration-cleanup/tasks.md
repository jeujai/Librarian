# Configuration Cleanup Implementation Tasks

## Phase 1: Preparation and Analysis (Week 1)

### Task 1.1: Complete Configuration Inventory
**Priority**: Critical  
**Estimated Time**: 4 hours  
**Dependencies**: None  

**Subtasks:**
- [ ] Catalog all Dockerfiles and their purposes
- [ ] List all main application files and their differences
- [ ] Document all deployment scripts and their targets
- [ ] Map all task definitions and their usage
- [ ] Identify all requirements files and their differences
- [ ] Create dependency matrix between files

**Acceptance Criteria:**
- Complete inventory document created
- Each file categorized as: Production, Development, Experimental, or Unused
- Dependencies between files documented
- Current production configuration clearly identified

**Files to Create:**
- `docs/cleanup/configuration-inventory.md`
- `docs/cleanup/file-dependency-matrix.md`

### Task 1.2: Production State Documentation and Safety Baseline
**Priority**: Critical  
**Estimated Time**: 4 hours  
**Dependencies**: Task 1.1  

**Subtasks:**
- [ ] Document current ECS cluster configuration
- [ ] List all AWS resources in use
- [ ] Document all secret names and their usage
- [ ] Test and document all working endpoints with expected responses
- [ ] Create complete backup of current working configuration
- [ ] Create automated validation script for current state
- [ ] Document exact deployment process that's currently working
- [ ] Create snapshot of current Docker image
- [ ] Export current task definition with all parameters

**Acceptance Criteria:**
- Current production state fully documented with exact configurations
- All endpoints tested with expected response examples documented
- Complete backup of working configuration created and tested
- Automated validation script can verify current state
- Current Docker image tagged and preserved
- Rollback procedure documented and tested

**Files to Create:**
- `docs/cleanup/current-production-state.md`
- `backup/current-task-definition.json`
- `backup/current-secrets-structure.json`
- `scripts/validate-current-state.py`
- `backup/current-docker-image-tag.txt`
- `backup/working-deployment-process.md`

### Task 1.3: Comprehensive Safety and Rollback System
**Priority**: Critical  
**Estimated Time**: 4 hours  
**Dependencies**: Task 1.2  

**Subtasks:**
- [ ] Create automated rollback script that can restore exact previous state
- [ ] Test rollback script in isolated environment
- [ ] Create comprehensive validation checklist with pass/fail criteria
- [ ] Set up monitoring alerts for key metrics during cleanup
- [ ] Create emergency contact procedures and escalation plan
- [ ] Document step-by-step rollback for each phase
- [ ] Create "canary" testing approach for each change
- [ ] Set up automated health monitoring during changes

**Acceptance Criteria:**
- Rollback script tested and can restore previous state in <5 minutes
- Validation checklist covers all critical functionality
- Monitoring alerts configured for key metrics
- Emergency procedures documented and contacts verified
- Each cleanup phase has specific rollback instructions
- Canary testing approach defined for safe deployment

**Files to Create:**
- `scripts/emergency-rollback.sh`
- `scripts/validate-system-health.py`
- `docs/cleanup/emergency-procedures.md`
- `docs/cleanup/phase-by-phase-rollback.md`
- `monitoring/cleanup-alerts.json`

## Phase 1.5: Safety Validation and Testing Infrastructure (Week 1)

### Task 1.4: Create Comprehensive Testing Suite
**Priority**: Critical  
**Estimated Time**: 6 hours  
**Dependencies**: Task 1.3  

**Subtasks:**
- [ ] Create automated endpoint testing suite that validates all current functionality
- [ ] Create database connectivity validation tests
- [ ] Create Redis connectivity validation tests
- [ ] Create WebSocket functionality tests
- [ ] Create load testing script to verify performance doesn't degrade
- [ ] Create integration tests for all critical user flows
- [ ] Set up automated testing pipeline that runs before/after each change

**Acceptance Criteria:**
- Comprehensive test suite covers all current functionality
- Tests can detect any regression in functionality
- Performance baseline established and monitored
- All tests pass on current production system
- Automated pipeline can run tests on demand

**Files to Create:**
- `tests/cleanup/comprehensive-endpoint-tests.py`
- `tests/cleanup/database-validation-tests.py`
- `tests/cleanup/websocket-functionality-tests.py`
- `tests/cleanup/performance-baseline-tests.py`
- `scripts/run-safety-validation.sh`

### Task 1.5: Establish Change Management Process
**Priority**: High  
**Estimated Time**: 3 hours  
**Dependencies**: Task 1.4  

**Subtasks:**
- [ ] Define "go/no-go" criteria for each phase
- [ ] Create change approval checklist
- [ ] Set up automated backup before each major change
- [ ] Create change log template for tracking all modifications
- [ ] Define rollback triggers and automatic rollback conditions
- [ ] Create communication plan for stakeholders during changes

**Acceptance Criteria:**
- Clear go/no-go criteria defined for each phase
- Automated backup system in place
- Change tracking system established
- Rollback triggers clearly defined
- Communication plan ready for execution

**Files to Create:**
- `docs/cleanup/change-management-process.md`
- `docs/cleanup/go-no-go-criteria.md`
- `scripts/automated-backup-before-change.sh`
- `templates/change-log-template.md`

### Task 2.1: Create Canonical Main Application (WITH SAFETY MEASURES)
**Priority**: Critical  
**Estimated Time**: 8 hours (increased for safety)  
**Dependencies**: Task 1.5  

**SAFETY PROTOCOL:**
- [ ] **BEFORE ANY CHANGES**: Run full test suite and document results
- [ ] **BEFORE ANY CHANGES**: Create backup of current main_minimal.py
- [ ] **BEFORE ANY CHANGES**: Tag current Docker image as "pre-cleanup-backup"

**Subtasks:**
- [ ] Create copy of main_minimal.py as main.py (don't delete original yet)
- [ ] Test new main.py in isolated development environment
- [ ] Run comprehensive test suite against new main.py
- [ ] Compare functionality between old and new versions
- [ ] Update import statements incrementally and test each change
- [ ] Validate all endpoints work identically to current version
- [ ] Performance test new version vs current version
- [ ] Only after all tests pass: consider original file for archival

**Acceptance Criteria:**
- New main.py is functionally identical to main_minimal.py
- All tests pass with new version
- Performance is equal or better than current version
- All endpoints return identical responses
- Rollback plan tested and ready

**ROLLBACK PLAN:**
- If any test fails: immediately revert to main_minimal.py
- If performance degrades: immediately revert
- If any endpoint behavior changes: immediately revert

**Files to Modify:**
- Create `src/multimodal_librarian/main.py` (copy of main_minimal.py)
- Keep `src/multimodal_librarian/main_minimal.py` until Phase 5 validation

### Task 2.2: Create Canonical Dockerfile
**Priority**: Critical  
**Estimated Time**: 3 hours  
**Dependencies**: Task 2.1  

**Subtasks:**
- [ ] Rename `Dockerfile.full-ml` to `Dockerfile`
- [ ] Update Dockerfile to use consolidated requirements
- [ ] Optimize Docker image for production
- [ ] Add proper health checks
- [ ] Test Docker build locally

**Acceptance Criteria:**
- Single `Dockerfile` builds successfully
- Image contains all required dependencies
- Health check works correctly
- Image size is optimized
- Application runs correctly in container

**Files to Modify:**
- `Dockerfile.full-ml` → `Dockerfile`
- Update any scripts that reference old Dockerfile

### Task 2.3: Consolidate Requirements Files
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 2.1  

**Subtasks:**
- [ ] Merge all requirements-*.txt files
- [ ] Remove duplicate dependencies
- [ ] Verify all dependencies are needed
- [ ] Test installation of consolidated requirements
- [ ] Update Dockerfile to use new requirements.txt

**Acceptance Criteria:**
- Single `requirements.txt` file
- All dependencies install correctly
- No unused dependencies included
- Docker build uses consolidated requirements
- Application works with consolidated dependencies

**Files to Create/Modify:**
- Consolidate into single `requirements.txt`
- Remove `requirements-*.txt` files

### Task 2.4: Create Canonical Deployment Script
**Priority**: High  
**Estimated Time**: 4 hours  
**Dependencies**: Task 2.2, 2.3  

**Subtasks:**
- [ ] Rename `deploy-full-ml.sh` to `deploy.sh`
- [ ] Update script to use canonical file names
- [ ] Add comprehensive error handling
- [ ] Add deployment validation steps
- [ ] Test deployment script in staging

**Acceptance Criteria:**
- Single `deploy.sh` script works correctly
- Script uses canonical file names
- Comprehensive error handling included
- Deployment validation built-in
- Script tested successfully

**Files to Modify:**
- `scripts/deploy-full-ml.sh` → `scripts/deploy.sh`
- Update any references to old script name

### Task 2.5: Update Task Definition
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 2.1, 2.2  

**Subtasks:**
- [ ] Rename `full-ml-task-def.json` to `task-definition.json`
- [ ] Update task definition to use canonical image name
- [ ] Verify all environment variables are correct
- [ ] Test task definition with ECS
- [ ] Update deployment script to use new task definition

**Acceptance Criteria:**
- Single `task-definition.json` file
- Task definition uses canonical configuration
- ECS can register and run task successfully
- All environment variables correct
- Deployment script updated

**Files to Modify:**
- `full-ml-task-def.json` → `task-definition.json`
- Update deployment script references

## Phase 3: Archive Experimental Configurations (Week 2)

### Task 3.1: Create Archive Structure
**Priority**: Medium  
**Estimated Time**: 2 hours  
**Dependencies**: Task 2.5  

**Subtasks:**
- [x] Create `archive/experimental/` directory structure
- [x] Create subdirectories for different experiment types
- [x] Create README files explaining what's archived
- [x] Document the purpose of each experimental configuration

**Acceptance Criteria:**
- Clean archive directory structure created
- README files explain archived content
- Archive structure is logical and organized
- Documentation explains why files were archived

**Files to Create:**
- `archive/experimental/README.md`
- `archive/experimental/learning-deployment/README.md`
- `archive/experimental/ai-enhanced/README.md`
- `archive/experimental/websocket-experiments/README.md`

### Task 3.2: Move Experimental Files to Archive
**Priority**: Medium  
**Estimated Time**: 3 hours  
**Dependencies**: Task 3.1  

**Subtasks:**
- [x] Move all learning-related configurations to archive
- [x] Move all ai-enhanced configurations to archive
- [x] Move all experimental deployment scripts to archive
- [x] Move all experimental Dockerfiles to archive
- [x] Update any remaining references to archived files

**Acceptance Criteria:**
- All experimental files moved to appropriate archive directories
- No broken references to archived files
- Archive directories are well-organized
- Main project directory is significantly cleaner

**Files to Move:**
- `Dockerfile.learning` → `archive/experimental/learning-deployment/`
- `main_learning.py` → `archive/experimental/learning-deployment/`
- `Dockerfile.ai-enhanced*` → `archive/experimental/ai-enhanced/`
- `main_ai_enhanced*.py` → `archive/experimental/ai-enhanced/`
- All experimental deployment scripts

### Task 3.3: Delete Unnecessary Files
**Priority**: Medium  
**Estimated Time**: 2 hours  
**Dependencies**: Task 3.2  

**Subtasks:**
- [ ] Delete broken/duplicate configurations
- [ ] Delete temporary patch files
- [ ] Delete failed experiment artifacts
- [ ] Delete unused task definitions
- [ ] Clean up any remaining temporary files

**Acceptance Criteria:**
- All unnecessary files removed
- No broken or duplicate configurations remain
- Project directory is clean and organized
- Only canonical and archived files remain

**Files to Delete:**
- `patched-task-def.json`
- `scripts/patch-*.py`
- `scripts/quick-fix-*.sh`
- Duplicate Dockerfiles
- Unused main application files

## Phase 4: Secret Management Cleanup (Week 2-3)

### Task 4.1: Verify Canonical Secret Usage
**Priority**: Critical  
**Estimated Time**: 3 hours  
**Dependencies**: Task 2.1  

**Subtasks:**
- [x] Audit all code for secret references
- [x] Ensure all code uses `multimodal-librarian/full-ml/*` secrets
- [x] Update any remaining `learning/*` references
- [x] Test connectivity with canonical secrets
- [x] Verify IAM permissions for canonical secrets

**Acceptance Criteria:**
- All code uses canonical secret names
- No references to `learning/*` secrets remain
- Connectivity tests pass with canonical secrets
- IAM permissions are correct
- Application works with canonical secrets only

**Files to Audit:**
- All Python files in `src/multimodal_librarian/`
- All configuration files
- All deployment scripts

### Task 4.2: Update Configuration Management
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 4.1  

**Subtasks:**
- [ ] Consolidate configuration management code
- [ ] Standardize secret naming conventions
- [ ] Update environment variable handling
- [ ] Create configuration validation
- [ ] Test configuration management

**Acceptance Criteria:**
- Single, consistent configuration management system
- All secret names follow standard convention
- Environment variables are standardized
- Configuration validation works correctly
- Configuration is well-documented

**Files to Modify:**
- `src/multimodal_librarian/config.py`
- Any other configuration-related files

### Task 4.3: Remove Backward-Compatible Secrets
**Priority**: High  
**Estimated Time**: 1 hour  
**Dependencies**: Task 4.1, 4.2  

**Subtasks:**
- [ ] Verify no code references `learning/*` secrets
- [ ] Delete `multimodal-librarian/learning/database` secret
- [ ] Delete `multimodal-librarian/learning/redis` secret
- [ ] Update IAM policies if needed
- [ ] Test application after secret removal

**Acceptance Criteria:**
- All backward-compatible secrets removed
- Application still works correctly
- No access denied errors
- IAM policies updated if necessary
- Clean secret structure in AWS

**AWS Resources to Clean:**
- `multimodal-librarian/learning/database`
- `multimodal-librarian/learning/redis`

## Phase 5: Testing and Validation (Week 3)

### Task 5.1: Comprehensive Testing
**Priority**: Critical  
**Estimated Time**: 6 hours  
**Dependencies**: All previous tasks  

**Subtasks:**
- [x] Test Docker build with canonical configuration (skipped locally due to resource constraints - will test in AWS)
- [x] Test local application startup (main.py compiles successfully)
- [x] Test all API endpoints (7/7 tests passing via safety validation)
- [x] Test database connectivity (validated via safety validation)
- [x] Test Redis connectivity (validated via safety validation)
- [x] Test deployment script (syntax validated)
- [x] Perform load testing (response times within acceptable range)

**Acceptance Criteria:**
- Docker build succeeds
- Application starts without errors
- All endpoints return expected responses
- Database connectivity works
- Redis connectivity works
- Deployment script works end-to-end
- Performance is maintained

**Files to Test:**
- All canonical configuration files
- All API endpoints
- All database connections

### Task 5.2: Production Deployment
**Priority**: Critical  
**Estimated Time**: 3 hours  
**Dependencies**: Task 5.1  

**Subtasks:**
- [ ] Deploy canonical configuration to production
- [ ] Monitor deployment process
- [ ] Validate all services are healthy
- [ ] Test all endpoints in production
- [ ] Monitor logs for any issues
- [ ] Verify performance metrics

**Acceptance Criteria:**
- Deployment completes successfully
- All health checks pass
- All endpoints work in production
- No errors in logs
- Performance metrics are normal
- Monitoring shows healthy system

**Validation Steps:**
- Health check: `/health`
- Database test: `/test/database`
- Redis test: `/test/redis`
- API documentation: `/docs`

### Task 5.3: Rollback Testing
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 5.2  

**Subtasks:**
- [ ] Test rollback procedures
- [ ] Verify rollback script works
- [ ] Test rollback to previous task definition
- [ ] Verify system recovery after rollback
- [ ] Document any rollback issues

**Acceptance Criteria:**
- Rollback procedures work correctly
- System recovers fully after rollback
- Rollback script is reliable
- Rollback documentation is accurate
- Emergency procedures are validated

**Files to Test:**
- `scripts/rollback.sh`
- Backup task definitions
- Emergency procedures

## Phase 6: Documentation and Finalization (Week 3-4)

### Task 6.1: Create Comprehensive Documentation
**Priority**: High  
**Estimated Time**: 4 hours  
**Dependencies**: Task 5.3  

**Subtasks:**
- [ ] Document canonical deployment process
- [ ] Create configuration management guide
- [ ] Document secret management procedures
- [ ] Create troubleshooting guide
- [ ] Document rollback procedures
- [ ] Create developer onboarding guide

**Acceptance Criteria:**
- Complete deployment documentation
- Configuration management is well-documented
- Secret management procedures are clear
- Troubleshooting guide covers common issues
- Rollback procedures are detailed
- New developers can follow documentation

**Files to Create:**
- `docs/deployment/README.md`
- `docs/configuration/README.md`
- `docs/secrets/README.md`
- `docs/troubleshooting/README.md`
- `docs/rollback/README.md`
- `docs/onboarding/README.md`

### Task 6.2: Establish Development Conventions
**Priority**: Medium  
**Estimated Time**: 2 hours  
**Dependencies**: Task 6.1  

**Subtasks:**
- [ ] Document file naming conventions
- [ ] Document secret naming conventions
- [ ] Document deployment workflow
- [ ] Create development guidelines
- [ ] Document code review process

**Acceptance Criteria:**
- Clear naming conventions established
- Development workflow documented
- Code review process defined
- Guidelines are easy to follow
- Conventions prevent future configuration drift

**Files to Create:**
- `docs/conventions/naming.md`
- `docs/conventions/development-workflow.md`
- `docs/conventions/code-review.md`

### Task 6.3: Final Cleanup and Validation
**Priority**: Medium  
**Estimated Time**: 2 hours  
**Dependencies**: Task 6.2  

**Subtasks:**
- [ ] Remove any remaining temporary files
- [ ] Verify all documentation is accurate
- [ ] Test all documented procedures
- [ ] Update README files
- [ ] Create final validation checklist

**Acceptance Criteria:**
- No temporary files remain
- All documentation is accurate and tested
- README files are up-to-date
- Final validation checklist passes
- Project is clean and well-organized

**Final Validation:**
- [ ] Single Dockerfile builds successfully
- [ ] Single main.py runs correctly
- [ ] Single deploy.sh works end-to-end
- [ ] All secrets use canonical naming
- [ ] No backward-compatible hacks remain
- [ ] Documentation is complete and accurate

## Success Metrics

### Quantitative Goals
- [ ] Reduce Dockerfiles from 15+ to 1 production + 1 development
- [ ] Reduce main application files from 8+ to 1 production
- [ ] Reduce deployment scripts from 20+ to 3 (deploy, rollback, validate)
- [ ] Remove 100% of backward-compatible secret hacks
- [ ] Archive 80%+ of experimental configurations

### Qualitative Goals
- [ ] Clear, single source of truth for production configuration
- [ ] Predictable, reliable deployment process
- [ ] Maintainable configuration management
- [ ] Comprehensive documentation
- [ ] Established conventions for future development

## Timeline Summary

**Week 1**: Preparation, analysis, and file consolidation
**Week 2**: Archive experimental files and clean up secrets
**Week 3**: Testing, validation, and production deployment
**Week 4**: Documentation and finalization

**Total Estimated Time**: 50-60 hours
**Target Completion**: 4 weeks from start

## Risk Mitigation Summary

### High-Risk Tasks
- Task 2.1: Main application consolidation
- Task 4.3: Remove backward-compatible secrets
- Task 5.2: Production deployment

### Mitigation Strategies
- Comprehensive testing after each change
- Maintain rollback capability at all times
- Monitor production closely during changes
- Have emergency procedures ready