#!/usr/bin/env python3
"""
Basic AWS Integration Tests for Learning CI/CD
Tests essential AWS services and application functionality in the cloud environment.
"""

import os
import sys
import time
import json
import boto3
import requests
import pytest
from typing import Dict, Any, Optional
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.aws.s3_simple import S3SimpleClient
from multimodal_librarian.aws.secrets_manager_basic import SecretsManagerBasic


class AWSBasicTests:
    """Basic AWS integration tests for learning deployment."""
    
    def __init__(self):
        self.project_name = "multimodal-librarian"
        self.environment = os.getenv("ENVIRONMENT", "learning")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.stack_name = "MultimodalLibrarianStack"
        
        # Initialize AWS clients
        self.cloudformation = boto3.client('cloudformation', region_name=self.region)
        self.ecs = boto3.client('ecs', region_name=self.region)
        self.rds = boto3.client('rds', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        self.secretsmanager = boto3.client('secretsmanager', region_name=self.region)
        
        # Get stack outputs
        self.stack_outputs = self._get_stack_outputs()
        
        print(f"🧪 Initializing AWS tests for {self.project_name}-{self.environment}")
        print(f"📍 Region: {self.region}")
        print(f"📋 Stack: {self.stack_name}")
    
    def _get_stack_outputs(self) -> Dict[str, str]:
        """Get CloudFormation stack outputs."""
        try:
            response = self.cloudformation.describe_stacks(StackName=self.stack_name)
            outputs = {}
            
            if response['Stacks']:
                stack_outputs = response['Stacks'][0].get('Outputs', [])
                for output in stack_outputs:
                    outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
        except Exception as e:
            print(f"⚠️  Could not get stack outputs: {e}")
            return {}
    
    def test_cloudformation_stack(self) -> bool:
        """Test CloudFormation stack status."""
        print("\n🏗️  Testing CloudFormation Stack...")
        
        try:
            response = self.cloudformation.describe_stacks(StackName=self.stack_name)
            
            if not response['Stacks']:
                print("❌ Stack not found")
                return False
            
            stack = response['Stacks'][0]
            status = stack['StackStatus']
            
            print(f"   Stack Status: {status}")
            print(f"   Creation Time: {stack.get('CreationTime', 'N/A')}")
            print(f"   Last Updated: {stack.get('LastUpdatedTime', 'N/A')}")
            
            # Check if stack is in a good state
            good_states = ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
            if status in good_states:
                print("✅ CloudFormation stack is healthy")
                return True
            else:
                print(f"❌ Stack is in unexpected state: {status}")
                return False
                
        except Exception as e:
            print(f"❌ CloudFormation test failed: {e}")
            return False
    
    def test_ecs_cluster(self) -> bool:
        """Test ECS cluster and services."""
        print("\n🐳 Testing ECS Cluster...")
        
        cluster_name = f"{self.project_name}-{self.environment}"
        
        try:
            # Check cluster
            response = self.ecs.describe_clusters(clusters=[cluster_name])
            
            if not response['clusters']:
                print(f"❌ ECS cluster {cluster_name} not found")
                return False
            
            cluster = response['clusters'][0]
            print(f"   Cluster: {cluster['clusterName']}")
            print(f"   Status: {cluster['status']}")
            print(f"   Active Services: {cluster['activeServicesCount']}")
            print(f"   Running Tasks: {cluster['runningTasksCount']}")
            
            # Check services
            services_response = self.ecs.list_services(cluster=cluster_name)
            
            if not services_response['serviceArns']:
                print("⚠️  No services found in cluster")
                return True  # Cluster exists but no services yet
            
            # Check service health
            services_detail = self.ecs.describe_services(
                cluster=cluster_name,
                services=services_response['serviceArns']
            )
            
            all_healthy = True
            for service in services_detail['services']:
                service_name = service['serviceName']
                status = service['status']
                desired = service['desiredCount']
                running = service['runningCount']
                
                print(f"   Service {service_name}: {status} ({running}/{desired})")
                
                if status != 'ACTIVE' or running != desired:
                    all_healthy = False
            
            if all_healthy:
                print("✅ ECS cluster and services are healthy")
                return True
            else:
                print("⚠️  Some ECS services are not fully healthy")
                return False
                
        except Exception as e:
            print(f"❌ ECS test failed: {e}")
            return False
    
    def test_rds_database(self) -> bool:
        """Test RDS database connectivity."""
        print("\n🗄️  Testing RDS Database...")
        
        db_identifier = f"{self.project_name}-{self.environment}-db"
        
        try:
            response = self.rds.describe_db_instances(DBInstanceIdentifier=db_identifier)
            
            if not response['DBInstances']:
                print(f"❌ RDS instance {db_identifier} not found")
                return False
            
            db = response['DBInstances'][0]
            print(f"   Database: {db['DBInstanceIdentifier']}")
            print(f"   Status: {db['DBInstanceStatus']}")
            print(f"   Engine: {db['Engine']} {db['EngineVersion']}")
            print(f"   Instance Class: {db['DBInstanceClass']}")
            print(f"   Multi-AZ: {db['MultiAZ']}")
            
            if db['DBInstanceStatus'] == 'available':
                print("✅ RDS database is available")
                return True
            else:
                print(f"⚠️  Database status: {db['DBInstanceStatus']}")
                return False
                
        except Exception as e:
            print(f"❌ RDS test failed: {e}")
            return False
    
    def test_s3_storage(self) -> bool:
        """Test S3 storage functionality."""
        print("\n📦 Testing S3 Storage...")
        
        bucket_name = f"{self.project_name}-{self.environment}-storage"
        
        try:
            # Check if bucket exists
            self.s3.head_bucket(Bucket=bucket_name)
            print(f"   Bucket: {bucket_name}")
            
            # Test basic operations using our S3 client
            s3_client = S3SimpleClient()
            
            # Test upload
            test_content = f"Test file created at {datetime.now()}"
            test_key = "test/integration-test.txt"
            
            success = s3_client.upload_text(test_content, test_key)
            if not success:
                print("❌ Failed to upload test file")
                return False
            
            print(f"   ✓ Uploaded test file: {test_key}")
            
            # Test download
            downloaded_content = s3_client.download_text(test_key)
            if downloaded_content != test_content:
                print("❌ Downloaded content doesn't match uploaded content")
                return False
            
            print(f"   ✓ Downloaded and verified test file")
            
            # Test presigned URL generation
            presigned_url = s3_client.generate_presigned_url(test_key, expiration=3600)
            if not presigned_url:
                print("❌ Failed to generate presigned URL")
                return False
            
            print(f"   ✓ Generated presigned URL")
            
            # Clean up test file
            s3_client.delete_file(test_key)
            print(f"   ✓ Cleaned up test file")
            
            print("✅ S3 storage tests passed")
            return True
            
        except Exception as e:
            print(f"❌ S3 test failed: {e}")
            return False
    
    def test_secrets_manager(self) -> bool:
        """Test AWS Secrets Manager functionality."""
        print("\n🔐 Testing Secrets Manager...")
        
        try:
            # Test our secrets manager client
            secrets_client = SecretsManagerBasic()
            
            # Test API keys secret
            api_keys = secrets_client.get_api_keys()
            if api_keys:
                print(f"   ✓ Retrieved API keys secret")
                print(f"   ✓ Found {len(api_keys)} API keys")
            else:
                print("⚠️  No API keys found (this may be expected)")
            
            # Test database secret
            db_config = secrets_client.get_database_config()
            if db_config:
                print(f"   ✓ Retrieved database configuration")
                # Don't print actual values for security
                print(f"   ✓ Database config has {len(db_config)} parameters")
            else:
                print("⚠️  No database config found")
            
            print("✅ Secrets Manager tests passed")
            return True
            
        except Exception as e:
            print(f"❌ Secrets Manager test failed: {e}")
            return False
    
    def test_load_balancer(self) -> bool:
        """Test Application Load Balancer."""
        print("\n🌐 Testing Load Balancer...")
        
        alb_dns = self.stack_outputs.get('LoadBalancerDNS')
        if not alb_dns:
            print("⚠️  Load balancer DNS not found in stack outputs")
            return False
        
        print(f"   Load Balancer: {alb_dns}")
        
        try:
            # Test health endpoint
            health_url = f"http://{alb_dns}/health"
            print(f"   Testing: {health_url}")
            
            response = requests.get(health_url, timeout=30)
            
            if response.status_code == 200:
                print("   ✓ Health endpoint responded successfully")
                
                # Try to parse response
                try:
                    health_data = response.json()
                    print(f"   ✓ Health check data: {health_data}")
                except:
                    print(f"   ✓ Health check response: {response.text[:100]}")
                
                print("✅ Load balancer health check passed")
                return True
            else:
                print(f"❌ Health endpoint returned status {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Health endpoint request timed out")
            return False
        except Exception as e:
            print(f"❌ Load balancer test failed: {e}")
            return False
    
    def test_application_endpoints(self) -> bool:
        """Test basic application endpoints."""
        print("\n🚀 Testing Application Endpoints...")
        
        alb_dns = self.stack_outputs.get('LoadBalancerDNS')
        if not alb_dns:
            print("⚠️  Load balancer DNS not found, skipping endpoint tests")
            return False
        
        base_url = f"http://{alb_dns}"
        
        endpoints_to_test = [
            ("/", "Root endpoint"),
            ("/health", "Health check"),
            ("/api/health", "API health check"),
        ]
        
        passed_tests = 0
        total_tests = len(endpoints_to_test)
        
        for endpoint, description in endpoints_to_test:
            try:
                url = f"{base_url}{endpoint}"
                print(f"   Testing {description}: {url}")
                
                response = requests.get(url, timeout=15)
                
                if response.status_code == 200:
                    print(f"   ✓ {description} - OK")
                    passed_tests += 1
                elif response.status_code == 404:
                    print(f"   ⚠️  {description} - Not Found (may not be implemented)")
                else:
                    print(f"   ❌ {description} - Status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"   ❌ {description} - Timeout")
            except Exception as e:
                print(f"   ❌ {description} - Error: {e}")
        
        if passed_tests > 0:
            print(f"✅ Application endpoints test passed ({passed_tests}/{total_tests})")
            return True
        else:
            print("❌ No application endpoints responded successfully")
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all AWS integration tests."""
        print("🧪 Starting AWS Basic Integration Tests")
        print("=" * 50)
        
        tests = [
            ("CloudFormation Stack", self.test_cloudformation_stack),
            ("ECS Cluster", self.test_ecs_cluster),
            ("RDS Database", self.test_rds_database),
            ("S3 Storage", self.test_s3_storage),
            ("Secrets Manager", self.test_secrets_manager),
            ("Load Balancer", self.test_load_balancer),
            ("Application Endpoints", self.test_application_endpoints),
        ]
        
        results = {}
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results[test_name] = result
                if result:
                    passed += 1
            except Exception as e:
                print(f"❌ {test_name} test crashed: {e}")
                results[test_name] = False
        
        print("\n" + "=" * 50)
        print("🏁 Test Results Summary")
        print("=" * 50)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All AWS integration tests passed!")
        elif passed > total // 2:
            print("⚠️  Most tests passed, but some issues found")
        else:
            print("❌ Multiple test failures - check AWS deployment")
        
        return results


def main():
    """Main function to run tests."""
    # Check if we're in AWS environment
    if not os.getenv("AWS_REGION"):
        print("⚠️  AWS_REGION not set, using default: us-east-1")
        os.environ["AWS_REGION"] = "us-east-1"
    
    # Run tests
    tester = AWSBasicTests()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    failed_tests = [name for name, result in results.items() if not result]
    
    if failed_tests:
        print(f"\n❌ Failed tests: {', '.join(failed_tests)}")
        sys.exit(1)
    else:
        print("\n✅ All tests passed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()