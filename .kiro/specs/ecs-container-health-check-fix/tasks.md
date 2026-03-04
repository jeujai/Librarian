# ECS Container Health Check Fix - Tasks

## Task List

- [ ] 1. Update ECS Task Definition Health Check
  - [ ] 1.1 Create deployment script to update task definition health check command from `/health/minimal` to `/health/simple`
  - [ ] 1.2 Deploy new task definition revision to ECS service
  - [ ] 1.3 Monitor deployment for successful completion

- [ ] 2. Verify Health Check Behavior
  - [ ] 2.1 Verify `/health/simple` endpoint returns 200 immediately after server start
  - [ ] 2.2 Verify container is not killed during startup (no SIGKILL events)
  - [ ] 2.3 Verify ALB target group shows healthy targets

- [ ] 3. Documentation
  - [ ] 3.1 Document the health check endpoint responsibilities
  - [ ] 3.2 Update deployment documentation with health check configuration
