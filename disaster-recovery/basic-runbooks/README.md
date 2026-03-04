# Basic Disaster Recovery Runbooks

This directory contains disaster recovery procedures for the Multimodal Librarian learning deployment on AWS.

## Overview

The disaster recovery strategy focuses on:
- **RTO (Recovery Time Objective)**: 4-8 hours for full system recovery
- **RPO (Recovery Point Objective)**: 24 hours maximum data loss
- **Scope**: Learning environment with cost-optimized recovery procedures

## Runbooks

### Core Infrastructure Recovery
- [Infrastructure Recreation](./infrastructure-recreation.md) - Recreate AWS infrastructure from CDK code
- [Database Recovery](./database-recovery.md) - Restore PostgreSQL, Neo4j, and Milvus databases
- [Application Recovery](./application-recovery.md) - Redeploy application services

### Data Recovery
- [S3 Data Recovery](./s3-data-recovery.md) - Restore files and media from backups
- [Configuration Recovery](./configuration-recovery.md) - Restore secrets and configuration

### Testing and Validation
- [Recovery Testing](./recovery-testing.md) - Procedures for testing disaster recovery
- [Validation Checklist](./validation-checklist.md) - Post-recovery validation steps

## Emergency Contacts

- **Primary**: Learning Project Owner
- **Secondary**: AWS Support (if applicable)
- **Escalation**: Technical Lead

## Quick Recovery Commands

```bash
# 1. Recreate infrastructure
cd infrastructure/learning
npm run deploy

# 2. Restore database from latest snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier multimodal-librarian-learning-restored \
  --db-snapshot-identifier <latest-snapshot-id>

# 3. Trigger application deployment
aws lambda invoke \
  --function-name multimodal-librarian-learning-backup \
  --payload '{"backup_type": "restore"}' \
  response.json
```

## Recovery Priority

1. **Critical (0-2 hours)**
   - Infrastructure recreation
   - Database restoration
   - Core application deployment

2. **High (2-4 hours)**
   - Vector database restoration
   - Knowledge graph restoration
   - File storage restoration

3. **Medium (4-8 hours)**
   - Monitoring restoration
   - Performance optimization
   - Documentation updates

## Cost Considerations

- Use smallest instance sizes during recovery testing
- Clean up test resources immediately after validation
- Consider using spot instances for non-critical recovery testing
- Monitor costs during recovery operations

## Lessons Learned

Document lessons learned from each recovery exercise:
- What worked well
- What could be improved
- Time taken for each step
- Cost implications
- Process improvements