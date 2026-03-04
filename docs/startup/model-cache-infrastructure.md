# Model Cache Infrastructure

## Overview

The model cache infrastructure provides persistent storage for ML models using AWS Elastic File System (EFS). This enables:

- **Persistent Model Storage**: Models are cached across container restarts
- **Shared Cache**: Multiple ECS tasks can share the same model cache
- **Reduced Startup Time**: Cached models load faster than downloading from remote sources
- **Cost Optimization**: Reduces data transfer costs by caching models locally

## Architecture

### Components

1. **EFS File System**
   - Encrypted at rest using KMS
   - Configured with lifecycle policies for cost optimization
   - Performance mode: General Purpose
   - Throughput mode: Bursting

2. **EFS Mount Targets**
   - One mount target per availability zone
   - Ensures high availability and low latency access
   - Protected by security groups

3. **EFS Access Point**
   - Provides application-specific access to EFS
   - Enforces POSIX user/group permissions
   - Root directory: `/model-cache`

4. **Security Group**
   - Allows NFS traffic (port 2049) from ECS tasks
   - Restricts access to authorized services only

5. **IAM Permissions**
   - ECS task role has permissions for EFS operations
   - Supports IAM-based access control

### Integration with ECS

The EFS file system is mounted in ECS tasks using the following configuration:

```json
{
  "volumes": [
    {
      "name": "model-cache",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-xxxxx",
        "transitEncryption": "ENABLED",
        "transitEncryptionPort": 2049,
        "authorizationConfig": {
          "accessPointId": "fsap-xxxxx",
          "iam": "ENABLED"
        }
      }
    }
  ],
  "containerDefinitions": [
    {
      "mountPoints": [
        {
          "sourceVolume": "model-cache",
          "containerPath": "/efs/model-cache",
          "readOnly": false
        }
      ]
    }
  ]
}
```

## Setup

### Prerequisites

- Terraform installed
- AWS CLI configured with appropriate credentials
- VPC and subnets already created
- Security module deployed

### Deployment

1. **Deploy Infrastructure**:
   ```bash
   ./scripts/setup-model-cache-infrastructure.sh
   ```

2. **Verify Deployment**:
   ```bash
   python scripts/validate-model-cache-infrastructure.py
   ```

3. **Update Application**:
   - Ensure `MODEL_CACHE_DIR` environment variable is set to `/efs/model-cache`
   - Deploy updated ECS task definition with EFS volume mount

### Manual Deployment

If you prefer to deploy manually:

```bash
cd infrastructure/aws-native

# Initialize Terraform
terraform init

# Plan changes
terraform plan \
  -target=module.storage \
  -target=module.security.aws_security_group.efs \
  -target=module.security.aws_iam_role_policy.ecs_task_efs

# Apply changes
terraform apply \
  -target=module.storage \
  -target=module.security.aws_security_group.efs \
  -target=module.security.aws_iam_role_policy.ecs_task_efs
```

## Configuration

### Environment Variables

Set these environment variables in your ECS task definition:

```bash
MODEL_CACHE_DIR=/efs/model-cache
MODEL_CACHE_MAX_SIZE_GB=100
MODEL_CACHE_MAX_AGE_DAYS=30
```

### Cache Configuration

The model cache can be configured through the `CacheConfig` class:

```python
from multimodal_librarian.cache.model_cache import CacheConfig, initialize_model_cache

config = CacheConfig(
    cache_dir="/efs/model-cache",
    max_cache_size_gb=100.0,
    max_model_age_days=30,
    download_timeout_seconds=3600,
    max_concurrent_downloads=3,
    validation_enabled=True,
    compression_enabled=True
)

await initialize_model_cache(config)
```

## Usage

### Basic Usage

```python
from multimodal_librarian.cache.model_cache import get_model_cache

# Get cache instance
cache = get_model_cache()

# Check if model is cached
if cache.is_cached("text-embedding-small", "latest"):
    # Load from cache
    model_path = await cache.get_cached_model_path("text-embedding-small", "latest")
else:
    # Download and cache
    model_path = await cache.download_and_cache_model(
        model_name="text-embedding-small",
        model_url="https://example.com/models/text-embedding-small.bin",
        model_version="latest"
    )
```

### Cache Warming

Pre-populate the cache with frequently used models:

```python
from multimodal_librarian.startup.cache_warmer import get_cache_warmer, WarmingStrategy

# Get cache warmer instance
warmer = get_cache_warmer()

# Warm essential models
results = await warmer.warm_essential_models()

# Or use a specific strategy
results = await warmer.warm_cache(WarmingStrategy.PRIORITY_BASED)
```

## Monitoring

### CloudWatch Metrics

The following metrics are available in CloudWatch:

- **Cache Hit Rate**: Percentage of requests served from cache
- **Cache Size**: Total size of cached models in GB
- **Download Time**: Time taken to download and cache models
- **Cache Cleanup**: Number of models cleaned up

### Cache Statistics

Get cache statistics programmatically:

```python
cache = get_model_cache()
stats = cache.get_cache_statistics()

print(f"Hit Rate: {stats['hit_rate_percent']:.1f}%")
print(f"Total Size: {stats['total_size_gb']:.2f} GB")
print(f"Cached Models: {stats['total_entries']}")
```

## Maintenance

### Cache Cleanup

The cache automatically cleans up old and unused models based on:

- **Age**: Models older than `max_model_age_days` are removed
- **Size**: Least recently used models are removed when cache exceeds `max_cache_size_gb`
- **Corruption**: Corrupted cache entries are automatically removed

Manual cleanup:

```python
cache = get_model_cache()
cleanup_stats = await cache.cleanup_cache(force=True)
```

### Backup and Recovery

EFS provides automatic backups through AWS Backup. To restore from backup:

1. Identify the backup recovery point
2. Restore to a new EFS file system
3. Update ECS task definition with new file system ID
4. Redeploy application

## Troubleshooting

### Common Issues

#### 1. EFS Mount Failures

**Symptoms**: Container fails to start with EFS mount errors

**Solutions**:
- Verify EFS mount targets exist in all AZs
- Check security group allows NFS traffic (port 2049)
- Ensure IAM permissions are correctly configured
- Verify EFS file system is in "available" state

#### 2. Slow Model Loading

**Symptoms**: Models take longer to load than expected

**Solutions**:
- Check EFS throughput mode (consider Provisioned Throughput)
- Verify network connectivity between ECS tasks and EFS
- Monitor EFS performance metrics in CloudWatch
- Consider using EFS Intelligent-Tiering

#### 3. Cache Size Exceeds Limit

**Symptoms**: Cache cleanup runs frequently, models are evicted prematurely

**Solutions**:
- Increase `max_cache_size_gb` configuration
- Reduce `max_model_age_days` to clean up old models faster
- Review model sizes and optimize where possible
- Consider using model compression

#### 4. Permission Denied Errors

**Symptoms**: Application cannot read/write to EFS

**Solutions**:
- Verify ECS task role has EFS permissions
- Check POSIX user/group permissions on access point
- Ensure container runs with correct UID/GID
- Review EFS access point configuration

### Validation

Run the validation script to check infrastructure:

```bash
python scripts/validate-model-cache-infrastructure.py \
  --region us-east-1 \
  --environment prod \
  --output validation-results.json
```

### Logs

Check CloudWatch logs for cache-related issues:

```bash
aws logs tail /ecs/multimodal-librarian-prod \
  --follow \
  --filter-pattern "model_cache"
```

## Cost Optimization

### EFS Lifecycle Policies

EFS automatically transitions files to Infrequent Access (IA) storage class after 30 days of inactivity, reducing costs by up to 92%.

### Monitoring Costs

Monitor EFS costs in AWS Cost Explorer:

```bash
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://efs-cost-filter.json
```

### Cost Reduction Strategies

1. **Enable Lifecycle Management**: Automatically move infrequently accessed files to IA storage
2. **Right-size Cache**: Set appropriate `max_cache_size_gb` based on actual usage
3. **Cleanup Old Models**: Regularly remove unused models
4. **Use Bursting Throughput**: Sufficient for most workloads, cheaper than Provisioned
5. **Monitor Access Patterns**: Identify and remove rarely used models

## Security

### Encryption

- **At Rest**: All data encrypted using AWS KMS
- **In Transit**: TLS encryption enabled for all EFS connections
- **Key Management**: Customer-managed KMS keys with automatic rotation

### Access Control

- **IAM-based**: ECS tasks authenticate using IAM roles
- **Security Groups**: Network-level access control
- **Access Points**: Application-level isolation

### Best Practices

1. **Least Privilege**: Grant only necessary EFS permissions
2. **Audit Logging**: Enable CloudTrail for EFS API calls
3. **Regular Reviews**: Periodically review access patterns and permissions
4. **Encryption Keys**: Rotate KMS keys regularly
5. **Network Isolation**: Use private subnets for EFS mount targets

## Performance

### Throughput Modes

- **Bursting**: Default mode, suitable for most workloads
  - Baseline: 50 MB/s per TB of storage
  - Burst: Up to 100 MB/s
  
- **Provisioned**: For consistent high throughput
  - Configure specific throughput independent of storage size
  - Higher cost but predictable performance

### Performance Optimization

1. **Parallel Downloads**: Use `max_concurrent_downloads` to download multiple models simultaneously
2. **Compression**: Enable compression to reduce storage and transfer time
3. **Caching Strategy**: Pre-warm cache with frequently used models
4. **Access Patterns**: Optimize file access patterns for EFS
5. **Monitoring**: Track performance metrics and adjust configuration

## References

- [AWS EFS Documentation](https://docs.aws.amazon.com/efs/)
- [EFS Performance Guide](https://docs.aws.amazon.com/efs/latest/ug/performance.html)
- [EFS Security Best Practices](https://docs.aws.amazon.com/efs/latest/ug/security-considerations.html)
- [Model Cache Implementation](../../src/multimodal_librarian/cache/model_cache.py)
- [Cache Warmer Implementation](../../src/multimodal_librarian/startup/cache_warmer.py)
