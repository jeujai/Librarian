#!/usr/bin/env python3
"""
Emergency AWS Cost Shutdown Script
Immediately stops high-cost services to prevent further charges
"""

import boto3
import json
from datetime import datetime
import sys

class EmergencyShutdown:
    def __init__(self):
        self.session = boto3.Session()
        self.regions = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']  # Focus on main regions
        self.shutdown_log = []
        
    def log_action(self, action: str, resource: str, status: str, details: str = ""):
        """Log shutdown actions"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'resource': resource,
            'status': status,
            'details': details
        }
        self.shutdown_log.append(entry)
        print(f"{'✅' if status == 'SUCCESS' else '❌'} {action}: {resource} - {details}")
    
    def shutdown_ecs_services(self):
        """Stop all ECS services and tasks"""
        print("\n🛑 Shutting down ECS services...")
        
        for region in self.regions:
            try:
                ecs = self.session.client('ecs', region_name=region)
                
                # List all clusters
                clusters_response = ecs.list_clusters()
                
                for cluster_arn in clusters_response['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    
                    # List services in cluster
                    services_response = ecs.list_services(cluster=cluster_arn)
                    
                    for service_arn in services_response['serviceArns']:
                        service_name = service_arn.split('/')[-1]
                        
                        try:
                            # Scale service to 0
                            ecs.update_service(
                                cluster=cluster_arn,
                                service=service_arn,
                                desiredCount=0
                            )
                            self.log_action("SCALE_DOWN", f"ECS Service {service_name}", "SUCCESS", f"Scaled to 0 in {region}")
                            
                        except Exception as e:
                            self.log_action("SCALE_DOWN", f"ECS Service {service_name}", "ERROR", str(e))
                    
                    # Stop all running tasks
                    tasks_response = ecs.list_tasks(cluster=cluster_arn)
                    
                    for task_arn in tasks_response['taskArns']:
                        try:
                            ecs.stop_task(cluster=cluster_arn, task=task_arn, reason="Emergency cost shutdown")
                            task_id = task_arn.split('/')[-1]
                            self.log_action("STOP_TASK", f"ECS Task {task_id}", "SUCCESS", f"Stopped in {region}")
                            
                        except Exception as e:
                            self.log_action("STOP_TASK", f"ECS Task {task_arn}", "ERROR", str(e))
                            
            except Exception as e:
                self.log_action("ECS_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_rds_instances(self):
        """Stop all RDS instances"""
        print("\n🛑 Shutting down RDS instances...")
        
        for region in self.regions:
            try:
                rds = self.session.client('rds', region_name=region)
                response = rds.describe_db_instances()
                
                for db in response['DBInstances']:
                    db_id = db['DBInstanceIdentifier']
                    status = db['DBInstanceStatus']
                    
                    if status == 'available':
                        try:
                            rds.stop_db_instance(DBInstanceIdentifier=db_id)
                            self.log_action("STOP_RDS", db_id, "SUCCESS", f"Stopped in {region}")
                            
                        except Exception as e:
                            self.log_action("STOP_RDS", db_id, "ERROR", str(e))
                    else:
                        self.log_action("SKIP_RDS", db_id, "INFO", f"Already {status} in {region}")
                        
            except Exception as e:
                self.log_action("RDS_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_neptune_clusters(self):
        """Stop Neptune clusters"""
        print("\n🛑 Shutting down Neptune clusters...")
        
        for region in self.regions:
            try:
                neptune = self.session.client('neptune', region_name=region)
                
                # List Neptune clusters
                clusters_response = neptune.describe_db_clusters()
                
                for cluster in clusters_response['DBClusters']:
                    cluster_id = cluster['DBClusterIdentifier']
                    status = cluster['Status']
                    
                    if status == 'available':
                        try:
                            neptune.stop_db_cluster(DBClusterIdentifier=cluster_id)
                            self.log_action("STOP_NEPTUNE", cluster_id, "SUCCESS", f"Stopped in {region}")
                            
                        except Exception as e:
                            self.log_action("STOP_NEPTUNE", cluster_id, "ERROR", str(e))
                    else:
                        self.log_action("SKIP_NEPTUNE", cluster_id, "INFO", f"Already {status} in {region}")
                        
            except Exception as e:
                self.log_action("NEPTUNE_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_elasticache_clusters(self):
        """Stop ElastiCache clusters"""
        print("\n🛑 Shutting down ElastiCache clusters...")
        
        for region in self.regions:
            try:
                elasticache = self.session.client('elasticache', region_name=region)
                
                # Redis clusters
                redis_response = elasticache.describe_replication_groups()
                for cluster in redis_response['ReplicationGroups']:
                    cluster_id = cluster['ReplicationGroupId']
                    status = cluster['Status']
                    
                    if status == 'available':
                        try:
                            elasticache.delete_replication_group(
                                ReplicationGroupId=cluster_id,
                                RetainPrimaryCluster=False
                            )
                            self.log_action("DELETE_REDIS", cluster_id, "SUCCESS", f"Deleted in {region}")
                            
                        except Exception as e:
                            self.log_action("DELETE_REDIS", cluster_id, "ERROR", str(e))
                
                # Memcached clusters
                memcached_response = elasticache.describe_cache_clusters()
                for cluster in memcached_response['CacheClusters']:
                    cluster_id = cluster['CacheClusterId']
                    status = cluster['CacheClusterStatus']
                    
                    if status == 'available':
                        try:
                            elasticache.delete_cache_cluster(CacheClusterId=cluster_id)
                            self.log_action("DELETE_MEMCACHED", cluster_id, "SUCCESS", f"Deleted in {region}")
                            
                        except Exception as e:
                            self.log_action("DELETE_MEMCACHED", cluster_id, "ERROR", str(e))
                            
            except Exception as e:
                self.log_action("ELASTICACHE_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_opensearch_domains(self):
        """Stop OpenSearch domains"""
        print("\n🛑 Shutting down OpenSearch domains...")
        
        for region in self.regions:
            try:
                opensearch = self.session.client('opensearch', region_name=region)
                response = opensearch.list_domain_names()
                
                for domain in response['DomainNames']:
                    domain_name = domain['DomainName']
                    
                    try:
                        opensearch.delete_domain(DomainName=domain_name)
                        self.log_action("DELETE_OPENSEARCH", domain_name, "SUCCESS", f"Deleted in {region}")
                        
                    except Exception as e:
                        self.log_action("DELETE_OPENSEARCH", domain_name, "ERROR", str(e))
                        
            except Exception as e:
                self.log_action("OPENSEARCH_SCAN", f"Region {region}", "ERROR", str(e))
    
    def delete_nat_gateways(self):
        """Delete NAT Gateways"""
        print("\n🛑 Deleting NAT Gateways...")
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                response = ec2.describe_nat_gateways()
                
                for nat in response['NatGateways']:
                    if nat['State'] != 'deleted':
                        nat_id = nat['NatGatewayId']
                        
                        try:
                            ec2.delete_nat_gateway(NatGatewayId=nat_id)
                            self.log_action("DELETE_NAT", nat_id, "SUCCESS", f"Deleted in {region}")
                            
                        except Exception as e:
                            self.log_action("DELETE_NAT", nat_id, "ERROR", str(e))
                            
            except Exception as e:
                self.log_action("NAT_SCAN", f"Region {region}", "ERROR", str(e))
    
    def delete_load_balancers(self):
        """Delete Load Balancers"""
        print("\n🛑 Deleting Load Balancers...")
        
        for region in self.regions:
            try:
                elbv2 = self.session.client('elbv2', region_name=region)
                response = elbv2.describe_load_balancers()
                
                for lb in response['LoadBalancers']:
                    lb_arn = lb['LoadBalancerArn']
                    lb_name = lb['LoadBalancerName']
                    
                    try:
                        elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
                        self.log_action("DELETE_ALB", lb_name, "SUCCESS", f"Deleted in {region}")
                        
                    except Exception as e:
                        self.log_action("DELETE_ALB", lb_name, "ERROR", str(e))
                        
                # Classic Load Balancers
                try:
                    elb = self.session.client('elb', region_name=region)
                    classic_response = elb.describe_load_balancers()
                    
                    for lb in classic_response['LoadBalancerDescriptions']:
                        lb_name = lb['LoadBalancerName']
                        
                        try:
                            elb.delete_load_balancer(LoadBalancerName=lb_name)
                            self.log_action("DELETE_CLB", lb_name, "SUCCESS", f"Deleted in {region}")
                            
                        except Exception as e:
                            self.log_action("DELETE_CLB", lb_name, "ERROR", str(e))
                            
                except Exception:
                    pass  # Classic ELB might not be available
                    
            except Exception as e:
                self.log_action("LB_SCAN", f"Region {region}", "ERROR", str(e))
    
    def execute_emergency_shutdown(self):
        """Execute complete emergency shutdown"""
        print("🚨 EMERGENCY AWS COST SHUTDOWN INITIATED")
        print("=" * 60)
        print("⚠️  WARNING: This will stop/delete AWS resources to prevent costs")
        print("⚠️  Make sure you have backups of any important data!")
        print("=" * 60)
        
        # Confirm shutdown
        confirm = input("\nType 'EMERGENCY SHUTDOWN' to confirm: ")
        if confirm != 'EMERGENCY SHUTDOWN':
            print("❌ Shutdown cancelled")
            return False
        
        print("\n🛑 Starting emergency shutdown...")
        
        # Execute shutdowns in order of cost impact
        self.shutdown_ecs_services()
        self.shutdown_neptune_clusters()
        self.shutdown_rds_instances()
        self.shutdown_elasticache_clusters()
        self.shutdown_opensearch_domains()
        self.delete_nat_gateways()
        self.delete_load_balancers()
        
        # Save shutdown log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"emergency-shutdown-log-{timestamp}.json"
        
        with open(log_filename, 'w') as f:
            json.dump(self.shutdown_log, f, indent=2)
        
        print(f"\n📝 Shutdown log saved to: {log_filename}")
        
        # Summary
        success_count = len([log for log in self.shutdown_log if log['status'] == 'SUCCESS'])
        error_count = len([log for log in self.shutdown_log if log['status'] == 'ERROR'])
        
        print(f"\n📊 SHUTDOWN SUMMARY:")
        print(f"  ✅ Successful actions: {success_count}")
        print(f"  ❌ Failed actions: {error_count}")
        print(f"  📝 Total actions logged: {len(self.shutdown_log)}")
        
        if error_count > 0:
            print(f"\n⚠️  Some resources may still be running. Check the log file for details.")
            print(f"⚠️  You may need to manually stop remaining resources in the AWS console.")
        
        print(f"\n💰 Monitor your AWS billing over the next few hours to confirm cost reduction.")
        
        return True

def main():
    shutdown = EmergencyShutdown()
    
    try:
        success = shutdown.execute_emergency_shutdown()
        return 0 if success else 1
        
    except Exception as e:
        print(f"❌ Critical error during emergency shutdown: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())