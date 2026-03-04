# Legacy Database Code Archive

## Overview

This archive contains Neo4j and Milvus client code, configuration, and dependencies that were removed from the Multimodal Librarian codebase as part of the migration to AWS-native database services.

## Removal Date

January 16, 2026

## Reason for Removal

The Multimodal Librarian system has been successfully migrated to AWS-native database services:
- **Amazon Neptune** replaced Neo4j for graph database operations
- **Amazon OpenSearch** replaced Milvus for vector search operations

The legacy code was removed to:
1. Prevent accidental regressions to development/localhost configuration
2. Reduce container image size by removing unnecessary dependencies
3. Simplify the codebase by eliminating dual backend support
4. Ensure production deployments only use AWS-native services

## Migration Reference

See the AWS-Native Database Implementation spec:
- `.kiro/specs/aws-native-database-implementation/requirements.md`
- `.kiro/specs/aws-native-database-implementation/design.md`
- `.kiro/specs/aws-native-database-implementation/tasks.md`

## Archived Files

### Client Files
- **Original Path**: `src/multimodal_librarian/clients/neo4j_client.py`
- **Archive Path**: `archive/legacy-databases/clients/neo4j_client.py`
- **Description**: Neo4j graph database client implementation

### Configuration Files
- **Original Path**: `src/multimodal_librarian/config/neo4j_config.py`
- **Archive Path**: `archive/legacy-databases/config/neo4j_config.py`
- **Description**: Neo4j connection configuration

- **Original Path**: `src/multimodal_librarian/aws/milvus_config_basic.py`
- **Archive Path**: `archive/legacy-databases/aws/milvus_config_basic.py`
- **Description**: AWS-specific Milvus configuration for ECS deployment

## Dependencies Removed

From `requirements.txt`:
- `neo4j==5.15.0` - Neo4j Python driver
- `pymilvus>=2.3.0,<3.0.0` - Milvus Python SDK

## AWS-Native Replacements

The following AWS-native clients remain in the codebase:
- `src/multimodal_librarian/clients/neptune_client.py` - Amazon Neptune client
- `src/multimodal_librarian/clients/opensearch_client.py` - Amazon OpenSearch client
- `src/multimodal_librarian/config/aws_native_config.py` - AWS-native configuration
- `src/multimodal_librarian/clients/database_factory.py` - Database factory (AWS-native only)

## Restoration (Not Recommended)

If you need to restore the legacy code for reference:

1. Copy files from archive back to original locations
2. Add dependencies back to `requirements.txt`
3. Update database factory to support legacy backends
4. Rebuild container image

**Warning**: Restoring legacy code will reintroduce the risk of accidental deployment with localhost configuration.

## Incident That Prompted Cleanup

On January 16, 2026, task definition revision 41 was deployed without AWS-native environment variables, causing the application to attempt connections to localhost services (Neo4j on localhost:7687, Milvus on localhost:19530). This incident demonstrated the need to completely remove legacy code to prevent future regressions.

## Validation

After cleanup, the following validations were performed:
- ✓ No `neo4j` or `pymilvus` imports in codebase
- ✓ No localhost database URLs in configuration
- ✓ Container builds successfully without legacy dependencies
- ✓ Health checks pass with AWS-native services only
- ✓ Database factory only returns Neptune or OpenSearch clients

## Contact

For questions about this cleanup or the AWS-native migration, refer to:
- `AWS_NATIVE_CONFIG_RESTORATION.md` - How the AWS-native configuration was restored
- `DEV_CONFIG_ARCHIVE_COMPLETE.md` - How development task definitions were archived
- `.kiro/specs/legacy-database-cleanup/` - Complete cleanup specification
