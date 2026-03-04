#!/usr/bin/env python3
"""
Targeted High-Cost Service Shutdown
Specifically targets the services causing $516/month in costs
"""

import boto3
import json
from datetime import datetime
import sys

class TargetedShutdown:
    def __init__(self):
        self.session = boto3.Session()
        # Expand to all regions since costs are high
        self.regions = self.get_all_regions()
        self.shutdown_log = []
        
    def get_all_regions(self):
        """Get all AWS regions"""
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = ec2.describe_regions()['Regions']
        return [region['RegionName'] for region in regions]
        
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
    
    def shutdown_all_ecs_clusters(self):
        """Aggressively shutdown all ECS resources"""
        print("\n🛑 AGGRESSIVE ECS SHUTDOWN...")
        
        for region in self.regions:
            try:
                ecs = self.session.client('ecs', region_name=region)
                
                # List all clusters
                clusters_response = ecs.list_clusters()
                
                for cluster_arn in clusters_response['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    
                    try:
                        # List and stop all services
                        services_response = ecs.list_services(cluster=cluster_arn)
                        
                        for service_arn in services_response['serviceArns']:
                            service_name = service_arn.split('/')[-1]
                            
                            try:
                                # Scale to 0 first
                                ecs.update_service(
                                    cluster=cluster_arn,
                                    service=service_arn,
                                    desiredCount=0
                                )
                                self.log_action("SCALE_DOWN", f"ECS Service {service_name}", "SUCCESS", f"Scaled to 0 in {region}")
                                
                                # Then delete the service
                                ecs.delete_service(
                                    cluster=cluster_arn,
                                    service=service_arn,
                                    force=True
                                )
                                self.log_action("DELETE_SERVICE", f"ECS Service {service_name}", "SUCCESS", f"Deleted in {region}")
                                
                            except Exception as e:
                                self.log_action("DELETE_SERVICE", f"ECS Service {service_name}", "ERROR", str(e))
                        
                        # Stop all running tasks
                        tasks_response = ecs.list_tasks(cluster=cluster_arn)
                        
                        for task_arn in tasks_response['taskArns']:
                            try:
                                ecs.stop_task(cluster=cluster_arn, task=task_arn, reason="Emergency cost shutdown")
                                task_id = task_arn.split('/')[-1]
                                self.log_action("STOP_TASK", f"ECS Task {task_id}", "SUCCESS", f"Stopped in {region}")
                                
                            except Exception as e:
                                self.log_action("STOP_TASK", f"ECS Task {task_arn}", "ERROR", str(e))
                        
                        # Delete the cluster
                        try:
                            ecs.delete_cluster(cluster=cluster_arn)
                            self.log_action("DELETE_CLUSTER", f"ECS Cluster {cluster_name}", "SUCCESS", f"Deleted in {region}")
                        except Exception as e:
                            self.log_action("DELETE_CLUSTER", f"ECS Cluster {cluster_name}", "ERROR", str(e))
                            
                    except Exception as e:
                        self.log_action("CLUSTER_PROCESS", f"ECS Cluster {cluster_name}", "ERROR", str(e))
                        
            except Exception as e:
                self.log_action("ECS_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_all_neptune(self):
        """Shutdown all Neptune clusters"""
        print("\n🛑 NEPTUNE SHUTDOWN...")
        
        for region in self.regions:
            try:
                neptune = self.session.client('neptune', region_name=region)
                
                # List and delete Neptune clusters
                clusters_response = neptune.describe_db_clusters()
                
                for cluster in clusters_response['DBClusters']:
                    cluster_id = cluster['DBClusterIdentifier']
                    
                    try:
                        # Delete cluster instances first
                        instances_response = neptune.describe_db_instances(
                            Filters=[
                                {
                                    'Name': 'db-cluster-id',
                                    'Values': [cluster_id]
                                }
                            ]
                        )
                        
                        for instance in instances_response['DBInstances']:
                            instance_id = instance['DBInstanceIdentifier']
                            try:
                                neptune.delete_db_instance(
                                    DBInstanceIdentifier=instance_id,
                                    SkipFinalSnapshot=True
                                )
                                self.log_action("DELETE_NEPTUNE_INSTANCE", instance_id, "SUCCESS", f"Deleted in {region}")
                            except Exception as e:
                                self.log_action("DELETE_NEPTUNE_INSTANCE", instance_id, "ERROR", str(e))
                        
                        # Delete the cluster
                        neptune.delete_db_cluster(
                            DBClusterIdentifier=cluster_id,
                            SkipFinalSnapshot=True
                        )
                        self.log_action("DELETE_NEPTUNE_CLUSTER", cluster_id, "SUCCESS", f"Deleted in {region}")
                        
                    except Exception as e:
                        self.log_action("DELETE_NEPTUNE_CLUSTER", cluster_id, "ERROR", str(e))
                        
            except Exception as e:
                self.log_action("NEPTUNE_SCAN", f"Region {region}", "ERROR", str(e))
    
    def shutdown_all_opensearch(self):
        """Delete all OpenSearch domains"""
        print("\n🛑 OPENSEARCH SHUTDOWN...")
        
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
    
    def shutdown_all_elasticache(self):
        """Delete all ElastiCache clusters"""
        print("\n🛑 ELASTICACHE SHUTDOWN...")
        
        for region in self.regions:
            try:
                elasticache = self.session.client('elasticache', region_name=region)
                
                # Redis clusters
                redis_response = elasticache.describe_replication_groups()
                for cluster in redis_response['ReplicationGroups']:
                    cluster_id = cluster['ReplicationGroupId']
                    
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
                    
                    try:
                        elasticache.delete_cache_cluster(CacheClusterId=cluster_id)
                        self.log_action("DELETE_MEMCACHED", cluster_id, "SUCCESS", f"Deleted in {region}")
                        
                    except Exception as e:
                        self.log_action("DELETE_MEMCACHED", cluster_id, "ERROR", str(e))
                        
            except Exception as e:
                self.log_action("ELASTICACHE_SCAN", f"Region {region}", "ERROR", str(e))
    
    def delete_all_nat_gateways(self):
        """Delete all NAT Gateways"""
        print("\n🛑 NAT GATEWAY SHUTDOWN...")
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                response = ec2.describe_nat_gateways()
                
                for nat in response['NatGateways']:
                    if nat['State'] not in ['deleted', 'deleting']:
                        nat_id = nat['NatGatewayId']
                        
                        try:
                            ec2.delete_nat_gateway(NatGatewayId=nat_id)
                            self.log_action("DELETE_NAT", nat_id, "SUCCESS", f"Deleted in {region}")
                            
                        except Exception as e:
                            self.log_action("DELETE_NAT", nat_id, "ERROR", str(e))
                            
            except Exception as e:
                self.log_action("NAT_SCAN", f"Region {region}", "ERROR", str(e))
    
    def delete_all_load_balancers(self):
        """Delete all Load Balancers"""
        print("\n🛑 LOAD BALANCER SHUTDOWN...")
        
        for region in self.regions:
            try:
                # Application/Network Load Balancers
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
    
    def execute_targeted_shutdown(self):
        """Execute targeted shutdown of high-cost services"""
        print("🚨 TARGETED HIGH-COST SERVICE SHUTDOWN")
        print("=" * 60)
        print("⚠️  Targeting services causing $516/month in costs")
        print("=" * 60)
        
        # Execute shutdowns in order of cost impact
        self.shutdown_all_ecs_clusters()      # $100.56/month
        self.shutdown_all_neptune()           # $115.79/month
        self.shutdown_all_opensearch()        # $13.09/month
        self.shutdown_all_elasticache()       # $27.29/month
        self.delete_all_nat_gateways()        # $69.64/month (VPC costs)
        self.delete_all_load_balancers()      # $29.64/month
        
        # Save shutdown log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"targeted-shutdown-log-{timestamp}.json"
        
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
        
        if success_count > 0:
            print(f"\n🎉 Successfully shut down {success_count} high-cost resources!")
            print(f"💰 Expected cost reduction: Significant reduction from $516/month")
        
        if error_count > 0:
            print(f"\n⚠️  {error_count} actions failed. Check the log file for details.")
        
        print(f"\n💰 Monitor your AWS billing over the next few hours to confirm cost reduction.")
        
        return success_count > 0

def main():
    shutdown = TargetedShutdown()
    
    try:
        success = shutdown.execute_targeted_shutdown()
        return 0 if success else 1
        
    except Exception as e:
        print(f"❌ Critical error during targeted shutdown: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())