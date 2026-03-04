# AWS Cost Optimization Plan - Multimodal Librarian

## 💰 Immediate Cost Savings Opportunity: $615/month ($7,380/year)

Based on the infrastructure scan, we found significant cost optimization opportunities across multiple AWS services.

## 🎯 Priority 1: High-Impact Savings (~$525/month)

### NAT Gateways - $225/month savings
**5 NAT Gateways found** - Each costs ~$45/month
- `nat-0922d45658199821b` (multimodal-lib-prod)
- `nat-08dd08fa1b4ab6083` (multimodal-lib-prod) 
- `nat-0ba6c7fb864e0b7b7` (multimodal-lib-prod)
- `nat-0de7c20c01213cedb` (MultimodalLibrarianFullML)
- `nat-0e52e9a066891174e` (CollaborativeEditor - different project)

**Safe Shutdown Steps:**
1. Verify no critical services depend on outbound internet access
2. Delete NAT Gateways (can be recreated if needed)
3. Update route tables to remove NAT Gateway routes

### RDS Instance - $100/month savings
**1 PostgreSQL instance found**
- `multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro` (db.t3.micro)

**Safe Shutdown Steps:**
1. **BACKUP FIRST**: Create final snapshot
2. Stop the instance (can be restarted within 7 days)
3. After verification, delete if no longer needed

### OpenSearch Domain - $200/month savings
**1 OpenSearch domain found**
- `multimodal-lib-prod-search` (t3.small.search)

**Safe Shutdown Steps:**
1. Export any critical data/indices
2. Delete the domain (data will be lost)
3. Can be recreated from application data if needed

## 🎯 Priority 2: Medium-Impact Savings (~$90/month)

### Load Balancers - $40/month savings
**2 Application Load Balancers found**
- `multimodal-librarian-full-ml` (~$20/month)
- `multimodal-lib-prod-alb` (~$20/month)

**Safe Shutdown Steps:**
1. Verify no traffic is being served
2. Delete load balancers
3. Can be recreated quickly if needed

### EC2 Instance - $50/month savings
**1 Neo4j instance found**
- `i-0255d25fd1950ed2d` (t3.medium, neo4j-simple-multimodal-librarian)

**Safe Shutdown Steps:**
1. Backup Neo4j data if needed
2. Stop the instance (can be restarted)
3. Terminate if no longer needed

## 🚀 Recommended Execution Order

### Phase 1: Immediate Shutdown (Safe, Reversible)
```bash
# 1. Stop RDS (can restart within 7 days)
aws rds stop-db-instance --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro

# 2. Scale down ECS services to 0 (can scale back up)
aws ecs update-service --cluster multimodal-lib-prod-cluster --service multimodal-lib-prod-service --desired-count 0
aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-web --desired-count 0
aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-service --desired-count 0

# 3. Stop EC2 instance (can restart)
aws ec2 stop-instances --instance-ids i-0255d25fd1950ed2d
```

**Immediate Savings: ~$150/month**

### Phase 2: Delete Non-Critical Resources (After 24-48h verification)
```bash
# 4. Delete NAT Gateways (biggest cost savings)
aws ec2 delete-nat-gateway --nat-gateway-id nat-0922d45658199821b
aws ec2 delete-nat-gateway --nat-gateway-id nat-08dd08fa1b4ab6083
aws ec2 delete-nat-gateway --nat-gateway-id nat-0ba6c7fb864e0b7b7
aws ec2 delete-nat-gateway --nat-gateway-id nat-0de7c20c01213cedb

# 5. Delete Load Balancers
aws elbv2 delete-load-balancer --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/39e45609ae99d010
aws elbv2 delete-load-balancer --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb/0eb0ad6c3cd72ada
```

**Additional Savings: ~$265/month**

### Phase 3: Delete Data Services (After confirming data not needed)
```bash
# 6. Delete OpenSearch domain (PERMANENT DATA LOSS)
aws opensearch delete-domain --domain-name multimodal-lib-prod-search

# 7. Delete RDS instance (PERMANENT DATA LOSS - backup first!)
aws rds delete-db-instance --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro --skip-final-snapshot
```

**Additional Savings: ~$300/month**

## 🛡️ Safety Measures

### Before Any Deletions:
1. **Backup Critical Data**
   - RDS: Create final snapshot
   - OpenSearch: Export indices/data
   - Neo4j: Backup graph database

2. **Verify Dependencies**
   - Check if any applications are actively using these resources
   - Review CloudWatch metrics for recent activity
   - Confirm with team members

3. **Test Impact**
   - Start with stopping/scaling down (reversible actions)
   - Monitor for 24-48 hours
   - Only delete after confirming no issues

### Monitoring Commands:
```bash
# Check RDS status
aws rds describe-db-instances --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro

# Check ECS service status
aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service

# Check EC2 instance status
aws ec2 describe-instances --instance-ids i-0255d25fd1950ed2d
```

## 📊 Cost Tracking

### Before Cleanup:
- Estimated monthly cost: ~$615
- Annual cost: ~$7,380

### After Phase 1 (Immediate):
- Monthly savings: ~$150
- Remaining cost: ~$465

### After Phase 2 (NAT/ALB cleanup):
- Monthly savings: ~$415
- Remaining cost: ~$200

### After Phase 3 (Complete cleanup):
- Monthly savings: ~$615
- Remaining cost: ~$0

## 🎯 Next Steps

1. **Execute Phase 1 immediately** (safe, reversible actions)
2. **Monitor for 24-48 hours** to ensure no issues
3. **Execute Phase 2** (delete infrastructure resources)
4. **Execute Phase 3** (delete data services after backup)
5. **Set up billing alerts** to monitor ongoing costs
6. **Review monthly** to catch new resource creep

## 🔧 Quick Execution

The generated script `shutdown-resources.sh` contains all the commands. To execute:

```bash
# Make executable
chmod +x shutdown-resources.sh

# Execute Phase 1 (safe actions)
python scripts/shutdown-high-cost-resources.py --execute

# Or run individual commands as needed
```

This plan will significantly reduce AWS costs while maintaining the ability to restart services if needed for development or testing.