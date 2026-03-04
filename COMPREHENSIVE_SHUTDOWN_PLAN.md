# Comprehensive AWS Shutdown Plan

## Current Status
✅ **Completed**: High-cost databases (Neptune + ElastiCache) - **$143.08/month saved**
✅ **Completed**: ALB cleanup - **$32.40/month saved**

## Additional Shutdown Opportunities

### Phase 1: Major Infrastructure ($197.76/month)
**Script**: `scripts/shutdown-remaining-infrastructure.py`

1. **ECS Fargate Services** - $100.56/month
   - All ECS services and clusters
   - Task definitions and container instances

2. **OpenSearch Domain** - $13.09/month  
   - `multimodal-lib-prod-search` domain
   - Vector database for semantic search

3. **PostgreSQL RDS Instances** - $9.47/month
   - `ml-librarian-postgres-prod`
   - `multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro`

4. **Load Balancers** - $29.64/month
   - All Application Load Balancers
   - Network Load Balancers

5. **NAT Gateway** - $45/month (estimated from VPC costs)
   - `nat-057025a3296d82cb2` in us-east-1

### Phase 2: Cross-Region Resources ($7.96/month)
**Manual cleanup required**

1. **Collaborative Editor (us-west-2)** - ~$7.96/month
   - EC2 instance: `i-098359c54b3c1cd3a` (t3.micro)
   - Elastic Beanstalk environment
   - Associated EBS volume

### Phase 3: Legacy Resources ($0-5/month)
**Low priority cleanup**

1. **Old Lambda Functions** - Minimal cost
   - Legacy Java 8 functions from 2018
   - `GetBizRule`, `SavePerson`, etc.

2. **Unused S3 Buckets** - $0.15/month
   - Empty buckets with minimal storage

3. **Stopped EC2 Instance** - $0/month (already stopped)
   - `i-0255d25fd1950ed2d` (Neo4j instance)

## Execution Plan

### Step 1: Run Infrastructure Shutdown
```bash
python scripts/shutdown-remaining-infrastructure.py
```

### Step 2: Shutdown Collaborative Editor
```bash
# Switch to us-west-2 region
aws configure set region us-west-2

# Terminate EC2 instance
aws ec2 terminate-instances --instance-ids i-098359c54b3c1cd3a

# Delete Elastic Beanstalk environment
aws elasticbeanstalk terminate-environment --environment-name collaborative-editor-env
```

### Step 3: Clean Up Legacy Resources (Optional)
```bash
# Delete old Lambda functions
aws lambda delete-function --function-name GetBizRule
aws lambda delete-function --function-name GetBiiizRule
aws lambda delete-function --function-name SavePerson
aws lambda delete-function --function-name GetBusinessRule
aws lambda delete-function --function-name SaveBusinessRule

# Delete empty S3 buckets (after confirming they're empty)
aws s3 rb s3://elasticbeanstalk-us-west-2-591222106065 --force
```

## Cost Savings Summary

| Phase | Resources | Monthly Savings | Annual Savings |
|-------|-----------|-----------------|----------------|
| ✅ **Completed** | Neptune + ElastiCache | $143.08 | $1,716.96 |
| ✅ **Completed** | ALB Cleanup | $32.40 | $388.80 |
| **Phase 1** | Main Infrastructure | $197.76 | $2,373.12 |
| **Phase 2** | Cross-Region | $7.96 | $95.52 |
| **Phase 3** | Legacy Resources | $5.00 | $60.00 |
| **TOTAL** | **All Resources** | **$386.20** | **$4,634.40** |

## Risk Assessment

### Low Risk ✅
- **Database shutdown**: Already completed, data preserved in snapshots
- **Load balancers**: No services to balance
- **NAT Gateway**: No private resources needing internet access

### Medium Risk ⚠️
- **ECS Services**: Application will be completely unavailable
- **OpenSearch**: Vector search data will be lost (no snapshots)

### High Risk 🚨
- **RDS Deletion**: PostgreSQL data will be lost after snapshot retention period
- **Cross-region cleanup**: May affect other projects

## Recovery Plan

If you need to restore services later:

1. **Database Recovery**: Restore from final snapshots
2. **Infrastructure**: Re-run Terraform deployment
3. **Application**: Redeploy from existing Docker images
4. **Estimated restoration time**: 2-4 hours
5. **Estimated restoration cost**: $50-100 one-time + monthly costs resume

## Recommendations

### Immediate Action (Maximum Savings)
Run Phase 1 shutdown for **$197.76/month additional savings**

### Conservative Approach  
Keep RDS instances running ($9.47/month) for easier recovery

### Aggressive Approach
Shut down everything for **$386.20/month total savings**

## Next Steps

1. **Confirm shutdown scope**: Which phases do you want to execute?
2. **Execute shutdown script**: Run the infrastructure shutdown
3. **Monitor costs**: Verify savings in next month's bill
4. **Document recovery**: Keep snapshots and deployment scripts for restoration

The infrastructure shutdown script is ready to execute and will save an additional **$197.76/month** on top of the **$175.48/month** already saved.