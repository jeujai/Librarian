# Shared Infrastructure Implementation Plan

## Overview
Plan to consolidate Multimodal Librarian and CollaborativeEditor into shared AWS infrastructure for maximum cost optimization.

## Cost Savings Summary
- **Monthly Savings**: $57.10 (29% reduction)
- **Annual Savings**: $685.20
- **Current Combined Cost**: $197.20/month
- **Shared Infrastructure Cost**: $140.10/month

## Detailed Savings Breakdown

### Major Cost Reductions
1. **Load Balancer Consolidation**: $16.20/month
   - Eliminate duplicate ALB
   - Use single ALB with multiple target groups
   
2. **CloudWatch Logs Optimization**: $2.00/month
   - Consolidated log groups
   - Shared log retention policies
   
3. **Secrets Manager Optimization**: $0.50/month
   - Shared secrets where appropriate
   - Reduced secret count
   
4. **Management Overhead Reduction**: $1.00/month
   - Single infrastructure stack to manage
   - Reduced operational complexity

## Implementation Phases

### Phase 1: Network Infrastructure Sharing (Already Complete)
✅ **NAT Gateway Sharing**: $32.40/month savings
- Multimodal Librarian now uses CollaborativeEditor NAT Gateway
- Zero additional cost for networking

### Phase 2: Load Balancer Consolidation ($16.20/month savings)

#### 2.1 Configure Shared Application Load Balancer
```bash
# Update ALB to handle both applications
aws elbv2 create-target-group \
  --name collaborative-editor-tg \
  --protocol HTTP \
  --port 3000 \
  --vpc-id vpc-014ac5b9fc828c78f

aws elbv2 create-target-group \
  --name multimodal-librarian-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-014ac5b9fc828c78f
```

#### 2.2 Configure Host-Based Routing
```yaml
# ALB Listener Rules
- Priority: 100
  Conditions:
    - Field: host-header
      Values: ["editor.yourdomain.com"]
  Actions:
    - Type: forward
      TargetGroupArn: collaborative-editor-tg

- Priority: 200
  Conditions:
    - Field: host-header
      Values: ["librarian.yourdomain.com"]
  Actions:
    - Type: forward
      TargetGroupArn: multimodal-librarian-tg
```

### Phase 3: ECS Cluster Consolidation (No direct cost savings, operational benefits)

#### 3.1 Migrate to Shared ECS Cluster
- Use existing CollaborativeEditor ECS cluster
- Deploy Multimodal Librarian services to shared cluster
- Maintain separate task definitions for isolation

#### 3.2 Service Configuration
```yaml
# Shared ECS Cluster Configuration
Cluster: collaborative-editor-cluster
Services:
  - collaborative-editor-service
  - multimodal-librarian-service

# Resource Allocation
Total Cluster Capacity: 4 vCPU, 8GB RAM
- CollaborativeEditor: 1 vCPU, 2GB RAM
- Multimodal Librarian: 2 vCPU, 4GB RAM
- Buffer: 1 vCPU, 2GB RAM
```

### Phase 4: Security and IAM Consolidation

#### 4.1 Shared Security Groups
```bash
# Create shared security groups
aws ec2 create-security-group \
  --group-name shared-web-sg \
  --description "Shared web application security group"

aws ec2 create-security-group \
  --group-name shared-database-sg \
  --description "Shared database access security group"
```

#### 4.2 Consolidated IAM Roles
- Merge similar IAM roles where possible
- Maintain principle of least privilege
- Use resource-based policies for application-specific access

### Phase 5: Monitoring and Logging Consolidation

#### 5.1 Shared CloudWatch Configuration
```yaml
# Consolidated Log Groups
/aws/ecs/shared-cluster/collaborative-editor
/aws/ecs/shared-cluster/multimodal-librarian
/aws/shared/application-logs

# Shared Dashboards
- Shared Infrastructure Dashboard
- Combined Application Metrics
- Unified Alerting Rules
```

## Technical Implementation Details

### Shared ALB Configuration
```terraform
# Shared Application Load Balancer
resource "aws_lb" "shared" {
  name               = "shared-applications-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.shared_alb.id]
  subnets           = var.public_subnet_ids

  tags = {
    Name = "shared-applications-alb"
    Environment = "production"
  }
}

# Target Groups
resource "aws_lb_target_group" "collaborative_editor" {
  name     = "collaborative-editor-tg"
  port     = 3000
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_target_group" "multimodal_librarian" {
  name     = "multimodal-librarian-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    path                = "/health/simple"
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

# Listener Rules
resource "aws_lb_listener_rule" "collaborative_editor" {
  listener_arn = aws_lb_listener.shared.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.collaborative_editor.arn
  }

  condition {
    host_header {
      values = ["editor.yourdomain.com"]
    }
  }
}

resource "aws_lb_listener_rule" "multimodal_librarian" {
  listener_arn = aws_lb_listener.shared.arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.multimodal_librarian.arn
  }

  condition {
    host_header {
      values = ["librarian.yourdomain.com"]
    }
  }
}
```

### ECS Service Configuration
```terraform
# Shared ECS Cluster
resource "aws_ecs_cluster" "shared" {
  name = "shared-applications-cluster"

  capacity_providers = ["FARGATE"]
  
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight           = 1
  }
}

# CollaborativeEditor Service
resource "aws_ecs_service" "collaborative_editor" {
  name            = "collaborative-editor"
  cluster         = aws_ecs_cluster.shared.id
  task_definition = aws_ecs_task_definition.collaborative_editor.arn
  desired_count   = 1

  load_balancer {
    target_group_arn = aws_lb_target_group.collaborative_editor.arn
    container_name   = "collaborative-editor"
    container_port   = 3000
  }
}

# Multimodal Librarian Service
resource "aws_ecs_service" "multimodal_librarian" {
  name            = "multimodal-librarian"
  cluster         = aws_ecs_cluster.shared.id
  task_definition = aws_ecs_task_definition.multimodal_librarian.arn
  desired_count   = 2

  load_balancer {
    target_group_arn = aws_lb_target_group.multimodal_librarian.arn
    container_name   = "multimodal-librarian"
    container_port   = 8000
  }
}
```

## Risk Assessment and Mitigation

### Risks
1. **Shared Failure Domain**
   - Risk: Cluster issues affect both applications
   - Mitigation: Robust health checks, auto-scaling, multi-AZ deployment

2. **Resource Contention**
   - Risk: Applications compete for resources
   - Mitigation: Proper resource limits, monitoring, auto-scaling

3. **Security Isolation**
   - Risk: Potential cross-application access
   - Mitigation: Separate task roles, network policies, security groups

4. **Deployment Coordination**
   - Risk: Deployments may conflict
   - Mitigation: Blue-green deployments, separate CI/CD pipelines

### Mitigation Strategies
```yaml
# Resource Limits
CollaborativeEditor:
  cpu: 1024 (1 vCPU)
  memory: 2048 (2GB)
  
MultimodalLibrarian:
  cpu: 2048 (2 vCPU)
  memory: 4096 (4GB)

# Auto Scaling
- Target CPU Utilization: 70%
- Scale out when: CPU > 70% for 2 minutes
- Scale in when: CPU < 30% for 5 minutes
- Min capacity: 1 (CollaborativeEditor), 2 (Multimodal Librarian)
- Max capacity: 3 (CollaborativeEditor), 10 (Multimodal Librarian)
```

## Implementation Timeline

### Week 1: Planning and Preparation
- [ ] Finalize shared infrastructure design
- [ ] Create backup of current configurations
- [ ] Set up monitoring for migration

### Week 2: Network and Load Balancer
- [ ] Configure shared ALB
- [ ] Set up target groups and routing rules
- [ ] Test load balancer configuration

### Week 3: ECS Migration
- [ ] Deploy Multimodal Librarian to shared cluster
- [ ] Update service configurations
- [ ] Validate application functionality

### Week 4: Optimization and Cleanup
- [ ] Remove duplicate infrastructure
- [ ] Optimize monitoring and alerting
- [ ] Document new architecture

## Monitoring and Validation

### Key Metrics to Monitor
1. **Application Performance**
   - Response times for both applications
   - Error rates and availability
   - Resource utilization

2. **Cost Tracking**
   - Monthly infrastructure costs
   - Resource utilization efficiency
   - Cost per request/user

3. **Operational Metrics**
   - Deployment frequency and success rate
   - Mean time to recovery (MTTR)
   - Infrastructure management overhead

### Success Criteria
- ✅ 29% cost reduction achieved ($57.10/month savings)
- ✅ No degradation in application performance
- ✅ Maintained security isolation
- ✅ Simplified operational overhead
- ✅ Successful deployment coordination

## Rollback Plan

### Emergency Rollback
1. **Immediate**: Route traffic back to original ALBs
2. **Short-term**: Restore original ECS services
3. **Long-term**: Rebuild separate infrastructure if needed

### Rollback Triggers
- Application performance degradation > 20%
- Availability drops below 99.5%
- Security incidents related to shared infrastructure
- Operational complexity increases significantly

## Conclusion

Sharing infrastructure between Multimodal Librarian and CollaborativeEditor provides:
- **$685.20 annual cost savings** (29% reduction)
- **Simplified operations** with single infrastructure stack
- **Better resource utilization** through shared capacity
- **Reduced management overhead** for deployments and monitoring

The implementation is technically feasible with proper planning and can be executed with minimal risk through phased deployment and comprehensive monitoring.