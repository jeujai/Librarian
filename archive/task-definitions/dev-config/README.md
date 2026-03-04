# Development Configuration Archive

**Date**: 2026-01-16 18:23:47

## Purpose

This archive contains task definition revisions that used **development/localhost configuration** instead of AWS-native services. These have been deregistered from ECS to prevent accidental deployment.

## Archived Revisions


### Revision 41

- **ARN**: `arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:41`
- **CPU**: 4096
- **Memory**: 24576
- **Image**: `591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest`
- **Archived**: 2026-01-16T18:23:47.030089
- **Archive File**: `archive/task-definitions/dev-config/task-definition-rev41.json`

**Issues Detected**:
- No AWS_NATIVE flag
- Missing Neptune endpoint
- Missing OpenSearch endpoint
- Missing RDS host


## Why These Were Archived

These task definitions were configured to connect to services on `localhost`:
- PostgreSQL on `localhost:5432`
- Milvus on `localhost:19530`
- Redis on `localhost:6379`
- Neo4j on `localhost:7687`

In the Fargate environment, these services don't exist, causing the application to fail on startup.

## Current Production Configuration

**Use Revision 42 or later** - These revisions use AWS-native services:
- **Neptune**: Graph database (replaces Neo4j)
- **OpenSearch**: Vector search (replaces Milvus)
- **RDS PostgreSQL**: Relational database
- **ElastiCache Redis**: Caching layer

See `AWS_NATIVE_CONFIG_RESTORATION.md` for details.

## Restoring from Archive

If you need to reference these configurations:

1. Find the archived JSON file in `archive/task-definitions/dev-config/`
2. Review the configuration
3. **DO NOT** re-register without updating to AWS-native endpoints

## Prevention

To prevent this in the future:

1. Always base new task definitions on revision 42 or later
2. Validate environment variables before deployment
3. Use `scripts/switch-to-aws-native-config.py` to ensure correct configuration
4. Check for `USE_AWS_NATIVE=true` environment variable

## Related Documentation

- `AWS_NATIVE_CONFIG_RESTORATION.md` - How to restore AWS-native configuration
- `.kiro/specs/aws-native-database-implementation/` - AWS-native database spec
- `scripts/switch-to-aws-native-config.py` - Configuration restoration script
