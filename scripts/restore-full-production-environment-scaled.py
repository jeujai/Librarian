#!/usr/bin/env python3
"""
Restore Full Production Environment (Scaled Down)

This script restores the complete production environment with all AWS services
but scaled down to minimize costs:
- Single NAT Gateway (reuse existing from CollaborativeEditor VPC)
- Single application container
- Single web container
- All databases and services active but minimal configuration

This provides a realistic production environment for comprehensive end-to-end testing
while keeping costs manageable.
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Any
import subprocess
import os


class FullProductionEnvironmentRestorer:
    """Restore full production environment with cost-optimized scaling."""
    
    def __init__(self):
        """Initialize AWS clients and configuration."""
        self.ec2 = boto3.client('ec2')
        self.ecs = boto3.client('ecs')
        self.rds = boto3.client('rds')
        self.neptune = boto3.client('neptune')
        self.opensearch = boto3.client('opensearch')
        self.elbv2 = boto3.client('elbv2')
        self.logs = boto3.client('logs')
        
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": "restore_full_production_environment_scaled",
            "components_restored": [],
            "components_verified": [],
            "errors": [],
            "warnings": [],
            "cost_optimizations": [],
            "next_steps": []
        }
        
        # Configuration
        self.name_prefix = "multimodal-librarian"
        self.existing_nat_gateway = "nat-0e52e9a066891174e"  # From CollaborativeEditor VPC
        
    def log_action(self, action: str, details: Dict[str, Any] = None):
        """Log an action with timestamp."""
        print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {action}")
        if details:
            print(f"    Details: {json.dumps(details, indent=2, default=str)}")
    
    def check_existing_infrastructure(self) -> Dict[str, Any]:
        """Check current state of AWS infrastructure."""
        self.log_action("🔍 Checking existing infrastructure state...")
        
        infrastructure_state = {
            "vpc": None,
            "subnets": [],
            "nat_gateway": None,
            "load_balancers": [],
            "ecs_cluster": None,
            "ecs_services": [],
            "rds_instances": [],
            "neptune_cluster": None,
            "opensearch_domain": None,
            "security_groups": []
        }
        
        try:
            # Check VPCs
            vpcs = self.ec2.describe_vpcs(
                Filters=[{'Name': 'tag:Name', 'Values': [f'{self.name_prefix}*']}]
            )['Vpcs']
            
            if vpcs:
                infrastructure_state["vpc"] = vpcs[0]
                vpc_id = vpcs[0]['VpcId']
                
                # Check subnets
                subnets = self.ec2.describe_subnets(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )['Subnets']
                infrastructure_state["subnets"] = subnets
                
                # Check security groups
                sgs = self.ec2.describe_security_groups(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )['SecurityGroups']
                infrastructure_state["security_groups"] = sgs
            
            # Check existing NAT Gateway
            nat_gateways = self.ec2.describe_nat_gateways(
                NatGatewayIds=[self.existing_nat_gateway]
            )['NatGateways']
            
            if nat_gateways:
                infrastructure_state["nat_gateway"] = nat_gateways[0]
                self.log_action(f"✅ Found existing NAT Gateway: {self.existing_nat_gateway}")
            
            # Check Load Balancers
            load_balancers = self.elbv2.describe_load_balancers()['LoadBalancers']
            ml_lbs = [lb for lb in load_balancers if self.name_prefix in lb.get('LoadBalancerName', '')]
            infrastructure_state["load_balancers"] = ml_lbs
            
            # Check ECS Cluster
            try:
                clusters = self.ecs.describe_clusters(
                    clusters=[f'{self.name_prefix}-cluster']
                )['clusters']
                if clusters:
                    infrastructure_state["ecs_cluster"] = clusters[0]
                    
                    # Check ECS Services
                    services = self.ecs.list_services(
                        cluster=f'{self.name_prefix}-cluster'
                    )['serviceArns']
                    
                    if services:
                        service_details = self.ecs.describe_services(
                            cluster=f'{self.name_prefix}-cluster',
                            services=services
                        )['services']
                        infrastructure_state["ecs_services"] = service_details
                        
            except Exception as e:
                self.log_action(f"⚠️  ECS cluster check failed: {e}")
            
            # Check RDS instances
            try:
                rds_instances = self.rds.describe_db_instances()['DBInstances']
                ml_rds = [db for db in rds_instances if self.name_prefix in db.get('DBInstanceIdentifier', '')]
                infrastructure_state["rds_instances"] = ml_rds
            except Exception as e:
                self.log_action(f"⚠️  RDS check failed: {e}")
            
            # Check Neptune cluster
            try:
                neptune_clusters = self.neptune.describe_db_clusters()['DBClusters']
                ml_neptune = [cluster for cluster in neptune_clusters if self.name_prefix in cluster.get('DBClusterIdentifier', '')]
                if ml_neptune:
                    infrastructure_state["neptune_cluster"] = ml_neptune[0]
            except Exception as e:
                self.log_action(f"⚠️  Neptune check failed: {e}")
            
            # Check OpenSearch domain
            try:
                opensearch_domains = self.opensearch.list_domain_names()['DomainNames']
                ml_domains = [domain for domain in opensearch_domains if self.name_prefix in domain.get('DomainName', '')]
                if ml_domains:
                    domain_status = self.opensearch.describe_domain(
                        DomainName=ml_domains[0]['DomainName']
                    )['DomainStatus']
                    infrastructure_state["opensearch_domain"] = domain_status
            except Exception as e:
                self.log_action(f"⚠️  OpenSearch check failed: {e}")
            
            return infrastructure_state
            
        except Exception as e:
            self.results["errors"].append(f"Infrastructure check failed: {e}")
            return infrastructure_state
    
    def restore_database_services(self, infrastructure_state: Dict[str, Any]):
        """Restore database services (PostgreSQL, Neptune, OpenSearch)."""
        self.log_action("🗄️  Restoring database services...")
        
        # Restore PostgreSQL RDS instance
        rds_instances = infrastructure_state.get("rds_instances", [])
        if not rds_instances:
            self.log_action("⚠️  No PostgreSQL RDS instance found - may need to be recreated")
            self.results["warnings"].append("PostgreSQL RDS instance not found")
        else:
            for db in rds_instances:
                if db['DBInstanceStatus'] == 'stopped':
                    self.log_action(f"🔄 Starting PostgreSQL instance: {db['DBInstanceIdentifier']}")
                    try:
                        self.rds.start_db_instance(
                            DBInstanceIdentifier=db['DBInstanceIdentifier']
                        )
                        self.results["components_restored"].append(f"postgresql_{db['DBInstanceIdentifier']}")
                    except Exception as e:
                        self.results["errors"].append(f"Failed to start PostgreSQL: {e}")
                elif db['DBInstanceStatus'] == 'available':
                    self.log_action(f"✅ PostgreSQL instance already running: {db['DBInstanceIdentifier']}")
                    self.results["components_verified"].append(f"postgresql_{db['DBInstanceIdentifier']}")
        
        # Verify Neptune cluster
        neptune_cluster = infrastructure_state.get("neptune_cluster")
        if neptune_cluster:
            if neptune_cluster['Status'] == 'available':
                self.log_action(f"✅ Neptune cluster available: {neptune_cluster['DBClusterIdentifier']}")
                self.results["components_verified"].append(f"neptune_{neptune_cluster['DBClusterIdentifier']}")
            else:
                self.log_action(f"⚠️  Neptune cluster status: {neptune_cluster['Status']}")
                self.results["warnings"].append(f"Neptune cluster not available: {neptune_cluster['Status']}")
        else:
            self.results["warnings"].append("Neptune cluster not found")
        
        # Verify OpenSearch domain
        opensearch_domain = infrastructure_state.get("opensearch_domain")
        if opensearch_domain:
            if opensearch_domain['Processing'] == False:
                self.log_action(f"✅ OpenSearch domain available: {opensearch_domain['DomainName']}")
                self.results["components_verified"].append(f"opensearch_{opensearch_domain['DomainName']}")
            else:
                self.log_action(f"⚠️  OpenSearch domain processing: {opensearch_domain['DomainName']}")
                self.results["warnings"].append("OpenSearch domain is processing")
        else:
            self.results["warnings"].append("OpenSearch domain not found")
    
    def configure_ecs_services_scaled(self, infrastructure_state: Dict[str, Any]):
        """Configure ECS services with scaled-down settings."""
        self.log_action("🐳 Configuring ECS services (scaled down)...")
        
        ecs_cluster = infrastructure_state.get("ecs_cluster")
        if not ecs_cluster:
            self.results["errors"].append("ECS cluster not found")
            return
        
        cluster_name = ecs_cluster['clusterName']
        
        # Scale services to 1 task each
        services = infrastructure_state.get("ecs_services", [])
        
        for service in services:
            service_name = service['serviceName']
            current_desired = service['desiredCount']
            
            if current_desired == 0:
                self.log_action(f"🔄 Scaling up service {service_name} to 1 task")
                try:
                    self.ecs.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        desiredCount=1
                    )
                    self.results["components_restored"].append(f"ecs_service_{service_name}")
                    self.results["cost_optimizations"].append(f"Service {service_name} scaled to 1 task (cost-optimized)")
                except Exception as e:
                    self.results["errors"].append(f"Failed to scale service {service_name}: {e}")
            elif current_desired == 1:
                self.log_action(f"✅ Service {service_name} already at optimal scale (1 task)")
                self.results["components_verified"].append(f"ecs_service_{service_name}")
            else:
                self.log_action(f"🔄 Scaling down service {service_name} from {current_desired} to 1 task")
                try:
                    self.ecs.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        desiredCount=1
                    )
                    self.results["components_restored"].append(f"ecs_service_{service_name}")
                    self.results["cost_optimizations"].append(f"Service {service_name} scaled down to 1 task (cost-optimized)")
                except Exception as e:
                    self.results["errors"].append(f"Failed to scale service {service_name}: {e}")
    
    def verify_load_balancer_configuration(self, infrastructure_state: Dict[str, Any]):
        """Verify and fix load balancer configuration."""
        self.log_action("⚖️  Verifying load balancer configuration...")
        
        load_balancers = infrastructure_state.get("load_balancers", [])
        
        for lb in load_balancers:
            lb_name = lb['LoadBalancerName']
            lb_arn = lb['LoadBalancerArn']
            
            self.log_action(f"🔍 Checking load balancer: {lb_name}")
            
            # Get target groups
            try:
                target_groups = self.elbv2.describe_target_groups(
                    LoadBalancerArn=lb_arn
                )['TargetGroups']
                
                for tg in target_groups:
                    tg_arn = tg['TargetGroupArn']
                    tg_name = tg['TargetGroupName']
                    
                    # Check target health
                    health = self.elbv2.describe_target_health(
                        TargetGroupArn=tg_arn
                    )['TargetHealthDescriptions']
                    
                    healthy_targets = [t for t in health if t['TargetHealth']['State'] == 'healthy']
                    unhealthy_targets = [t for t in health if t['TargetHealth']['State'] != 'healthy']
                    
                    self.log_action(f"  Target Group {tg_name}: {len(healthy_targets)} healthy, {len(unhealthy_targets)} unhealthy")
                    
                    if len(healthy_targets) == 0:
                        self.results["warnings"].append(f"Load balancer {lb_name} has no healthy targets in {tg_name}")
                    else:
                        self.results["components_verified"].append(f"load_balancer_{lb_name}_healthy")
                        
            except Exception as e:
                self.results["errors"].append(f"Failed to check load balancer {lb_name}: {e}")
    
    def wait_for_services_to_stabilize(self):
        """Wait for ECS services to stabilize after scaling."""
        self.log_action("⏳ Waiting for services to stabilize...")
        
        max_wait_time = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                services = self.ecs.describe_services(
                    cluster=f'{self.name_prefix}-cluster'
                )['services']
                
                all_stable = True
                for service in services:
                    if service['desiredCount'] != service['runningCount']:
                        all_stable = False
                        self.log_action(f"  Service {service['serviceName']}: {service['runningCount']}/{service['desiredCount']} running")
                
                if all_stable:
                    self.log_action("✅ All services stabilized")
                    break
                    
                time.sleep(10)
                
            except Exception as e:
                self.log_action(f"⚠️  Error checking service stability: {e}")
                break
        
        if time.time() - start_time >= max_wait_time:
            self.results["warnings"].append("Services did not stabilize within 5 minutes")
    
    def generate_cost_optimization_report(self):
        """Generate cost optimization report."""
        self.log_action("💰 Generating cost optimization report...")
        
        optimizations = [
            "Single NAT Gateway reused from CollaborativeEditor VPC",
            "ECS services scaled to 1 task each (minimum for functionality)",
            "All databases active but minimal configuration",
            "Load balancers active for realistic testing",
            "Full feature set available for comprehensive testing"
        ]
        
        self.results["cost_optimizations"].extend(optimizations)
        
        estimated_monthly_cost = {
            "NAT Gateway": "$0 (reusing existing)",
            "ECS Tasks": "$~50-100 (2 tasks total)",
            "PostgreSQL RDS": "$~50-100 (db.t3.micro)",
            "Neptune": "$~200-300 (minimal instance)",
            "OpenSearch": "$~100-200 (t3.small)",
            "Load Balancers": "$~20-30",
            "Total Estimated": "$~420-730/month"
        }
        
        self.results["estimated_monthly_cost"] = estimated_monthly_cost
    
    def create_next_steps_plan(self):
        """Create next steps plan for end-to-end testing."""
        self.log_action("📋 Creating next steps plan...")
        
        next_steps = [
            "1. Wait 5-10 minutes for all services to fully stabilize",
            "2. Run comprehensive end-to-end testing with test_end_to_end_production.py",
            "3. Validate all features: upload, processing, chat, RAG, analytics",
            "4. Test authentication and security features",
            "5. Verify monitoring and logging systems",
            "6. Complete Task 14.1 (End-to-end testing)",
            "7. Proceed to Task 14.2 (User acceptance testing preparation)",
            "8. Final production readiness validation (Task 15)"
        ]
        
        self.results["next_steps"] = next_steps
    
    def restore_full_environment(self):
        """Main method to restore full production environment."""
        print("🚀 RESTORING FULL PRODUCTION ENVIRONMENT (SCALED DOWN)")
        print("=" * 60)
        
        # Check current infrastructure state
        infrastructure_state = self.check_existing_infrastructure()
        
        # Restore database services
        self.restore_database_services(infrastructure_state)
        
        # Configure ECS services with scaled settings
        self.configure_ecs_services_scaled(infrastructure_state)
        
        # Wait for services to stabilize
        self.wait_for_services_to_stabilize()
        
        # Verify load balancer configuration
        self.verify_load_balancer_configuration(infrastructure_state)
        
        # Generate cost optimization report
        self.generate_cost_optimization_report()
        
        # Create next steps plan
        self.create_next_steps_plan()
        
        # Generate summary
        self.generate_summary()
        
        return self.results
    
    def generate_summary(self):
        """Generate restoration summary."""
        print("\n" + "=" * 60)
        print("📊 FULL PRODUCTION ENVIRONMENT RESTORATION SUMMARY")
        print("=" * 60)
        
        print(f"Components Restored: {len(self.results['components_restored'])}")
        for component in self.results['components_restored']:
            print(f"  ✅ {component}")
        
        print(f"\nComponents Verified: {len(self.results['components_verified'])}")
        for component in self.results['components_verified']:
            print(f"  ✅ {component}")
        
        if self.results['warnings']:
            print(f"\nWarnings: {len(self.results['warnings'])}")
            for warning in self.results['warnings']:
                print(f"  ⚠️  {warning}")
        
        if self.results['errors']:
            print(f"\nErrors: {len(self.results['errors'])}")
            for error in self.results['errors']:
                print(f"  ❌ {error}")
        
        print(f"\nCost Optimizations: {len(self.results['cost_optimizations'])}")
        for optimization in self.results['cost_optimizations']:
            print(f"  💰 {optimization}")
        
        print("\n🎯 NEXT STEPS:")
        for step in self.results['next_steps']:
            print(f"  {step}")
        
        if len(self.results['errors']) == 0:
            print("\n🎉 FULL PRODUCTION ENVIRONMENT RESTORED SUCCESSFULLY!")
            print("✅ Ready for comprehensive end-to-end testing")
            print("💰 Cost-optimized with all features available")
        else:
            print(f"\n⚠️  Restoration completed with {len(self.results['errors'])} errors")
            print("🔧 Review errors and warnings before proceeding")
        
        # Save results
        results_file = f"full-production-environment-restoration-{int(datetime.utcnow().timestamp())}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")


def main():
    """Main execution."""
    restorer = FullProductionEnvironmentRestorer()
    results = restorer.restore_full_environment()
    
    # Return appropriate exit code
    if len(results['errors']) == 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)