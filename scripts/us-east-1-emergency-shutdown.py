#!/usr/bin/env python3
"""
Emergency shutdown for us-east-1 region specifically
Based on billing analysis showing $469.92 in costs from this region
"""

import boto3
import json
from datetime import datetime
import sys

class USEast1Shutdown:
    def __init__(self):
        self.session = boto3.Session()
        self.region = 'us-east-1'  # Focus on the high-cost region
        self.shutdown_log = []
        
    def log_action(self, action: str, resource: str, status: str, details: str = ""):
        """Log shutdown actions"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'resource': resource,
            'status': status,
            'details': details,
            'region': self.region
        }
        self.shutdown_log.append(entry)
        print(f"{'✅' if status == 'SUCCESS' else '❌'} {action}: {resource} - {details}")
    
    def shutdown_neptune_instances(self):
        """Shutdown Neptune instances (db.r5.large costing $115.79)"""
        print(f"\n🛑 SHUTTING DOWN NEPTUNE IN {self.region}...")
        
        try:
            neptune = self.session.client('neptune', region_name=self.region)
            
            # Get all Neptune instances
            instances_response = neptune.describe_db_instances()
            
            for instance in instances_response['DBInstances']:
                instance_id = instance['DBInstanceIdentifier']
                instance_class = instance.get('DBInstanceClass', '')
                status = instance['DBInstanceStatus']
                
                print(f"  Found Neptune instance: {instance_id} ({instance_class}) - {status}")
                
                if status == 'available':
                    try:
                        neptune.delete_db_instance(
                            DBInstanceIdentifier=instance_id,
                            SkipFinalSnapshot=True
                        )
                        self.log_action("DELETE_NEPTUNE_INSTANCE", instance_id, "SUCCESS", f"Deleted {instance_class}")
                        
                    except Exception as e:
                        self.log_action("DELETE_NEPTUNE_INSTANCE", instance_id, "ERROR", str(e))
                else:
                    self.log_action("SKIP_NEPTUNE_INSTANCE", instance_id, "INFO", f"Already {status}")
            
            # Get all Neptune clusters
            clusters_response = neptune.describe_db_clusters()
            
            for cluster in clusters_response['DBClusters']:
                cluster_id = cluster['DBClusterIdentifier']
                status = cluster['Status']
                
                print(f"  Found Neptune cluster: {cluster_id} - {status}")
                
                if status == 'available':
                    try:
                        neptune.delete_db_cluster(
                            DBClusterIdentifier=cluster_id,
                            SkipFinalSnapshot=True
                        )
                        self.log_action("DELETE_NEPTUNE_CLUSTER", cluster_id, "SUCCESS", "Deleted cluster")
                        
                    except Exception as e:
                        self.log_action("DELETE_NEPTUNE_CLUSTER", cluster_id, "ERROR", str(e))
                        
        except Exception as e:
            self.log_action("NEPTUNE_SCAN", self.region, "ERROR", str(e))
    
    def shutdown_ecs_fargate(self):
        """Shutdown ECS Fargate tasks (costing $75.07 in vCPU hours)"""
        print(f"\n🛑 SHUTTING DOWN ECS FARGATE IN {self.region}...")
        
        try:
            ecs = self.session.client('ecs', region_name=self.region)
            
            # List all clusters
            clusters_response = ecs.list_clusters()
            
            for cluster_arn in clusters_response['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                print(f"  Found ECS cluster: {cluster_name}")
                
                # List services in cluster
                services_response = ecs.list_services(cluster=cluster_arn)
                
                for service_arn in services_response['serviceArns']:
                    service_name = service_arn.split('/')[-1]
                    
                    try:
                        # Get service details
                        service_details = ecs.describe_services(cluster=cluster_arn, services=[service_arn])
                        if service_details['services']:
                            service = service_details['services'][0]
                            desired_count = service.get('desiredCount', 0)
                            running_count = service.get('runningCount', 0)
                            
                            print(f"    Service: {service_name} (desired: {desired_count}, running: {running_count})")
                            
                            if desired_count > 0:
                                # Scale to 0
                                ecs.update_service(
                                    cluster=cluster_arn,
                                    service=service_arn,
                                    desiredCount=0
                                )
                                self.log_action("SCALE_DOWN_SERVICE", service_name, "SUCCESS", f"Scaled from {desired_count} to 0")
                            
                            # Delete the service
                            ecs.delete_service(
                                cluster=cluster_arn,
                                service=service_arn,
                                force=True
                            )
                            self.log_action("DELETE_SERVICE", service_name, "SUCCESS", "Deleted service")
                            
                    except Exception as e:
                        self.log_action("DELETE_SERVICE", service_name, "ERROR", str(e))
                
                # Stop all running tasks
                tasks_response = ecs.list_tasks(cluster=cluster_arn)
                
                for task_arn in tasks_response['taskArns']:
                    task_id = task_arn.split('/')[-1]
                    
                    try:
                        ecs.stop_task(cluster=cluster_arn, task=task_arn, reason="Emergency cost shutdown")
                        self.log_action("STOP_TASK", task_id, "SUCCESS", "Stopped Fargate task")
                        
                    except Exception as e:
                        self.log_action("STOP_TASK", task_id, "ERROR", str(e))
                
                # Delete the cluster
                try:
                    ecs.delete_cluster(cluster=cluster_arn)
                    self.log_action("DELETE_CLUSTER", cluster_name, "SUCCESS", "Deleted cluster")
                except Exception as e:
                    self.log_action("DELETE_CLUSTER", cluster_name, "ERROR", str(e))
                    
        except Exception as e:
            self.log_action("ECS_SCAN", self.region, "ERROR", str(e))
    
    def delete_vpc_endpoints(self):
        """Delete VPC endpoints (costing $47.04)"""
        print(f"\n🛑 DELETING VPC ENDPOINTS IN {self.region}...")
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            # List VPC endpoints
            endpoints_response = ec2.describe_vpc_endpoints()
            
            for endpoint in endpoints_response['VpcEndpoints']:
                endpoint_id = endpoint['VpcEndpointId']
                service_name = endpoint.get('ServiceName', '')
                state = endpoint['State']
                
                print(f"  Found VPC endpoint: {endpoint_id} ({service_name}) - {state}")
                
                if state in ['available', 'pending']:
                    try:
                        ec2.delete_vpc_endpoints(VpcEndpointIds=[endpoint_id])
                        self.log_action("DELETE_VPC_ENDPOINT", endpoint_id, "SUCCESS", f"Deleted {service_name}")
                        
                    except Exception as e:
                        self.log_action("DELETE_VPC_ENDPOINT", endpoint_id, "ERROR", str(e))
                        
        except Exception as e:
            self.log_action("VPC_ENDPOINTS_SCAN", self.region, "ERROR", str(e))
    
    def delete_nat_gateways(self):
        """Delete NAT gateways (costing $45.59 + $41.29)"""
        print(f"\n🛑 DELETING NAT GATEWAYS IN {self.region}...")
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            # List NAT gateways
            nat_response = ec2.describe_nat_gateways()
            
            for nat in nat_response['NatGateways']:
                nat_id = nat['NatGatewayId']
                state = nat['State']
                vpc_id = nat.get('VpcId', '')
                
                print(f"  Found NAT gateway: {nat_id} ({state}) in VPC {vpc_id}")
                
                if state not in ['deleted', 'deleting']:
                    try:
                        ec2.delete_nat_gateway(NatGatewayId=nat_id)
                        self.log_action("DELETE_NAT_GATEWAY", nat_id, "SUCCESS", f"Deleted from VPC {vpc_id}")
                        
                    except Exception as e:
                        self.log_action("DELETE_NAT_GATEWAY", nat_id, "ERROR", str(e))
                        
        except Exception as e:
            self.log_action("NAT_GATEWAYS_SCAN", self.region, "ERROR", str(e))
    
    def delete_load_balancers(self):
        """Delete load balancers (costing $29.63)"""
        print(f"\n🛑 DELETING LOAD BALANCERS IN {self.region}...")
        
        try:
            elbv2 = self.session.client('elbv2', region_name=self.region)
            
            # List load balancers
            lb_response = elbv2.describe_load_balancers()
            
            for lb in lb_response['LoadBalancers']:
                lb_arn = lb['LoadBalancerArn']
                lb_name = lb['LoadBalancerName']
                lb_type = lb['Type']
                state = lb['State']['Code']
                
                print(f"  Found load balancer: {lb_name} ({lb_type}) - {state}")
                
                if state == 'active':
                    try:
                        elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
                        self.log_action("DELETE_LOAD_BALANCER", lb_name, "SUCCESS", f"Deleted {lb_type}")
                        
                    except Exception as e:
                        self.log_action("DELETE_LOAD_BALANCER", lb_name, "ERROR", str(e))
                        
        except Exception as e:
            self.log_action("LOAD_BALANCERS_SCAN", self.region, "ERROR", str(e))
    
    def shutdown_opensearch(self):
        """Delete OpenSearch domains (costing $11.99)"""
        print(f"\n🛑 DELETING OPENSEARCH DOMAINS IN {self.region}...")
        
        try:
            opensearch = self.session.client('opensearch', region_name=self.region)
            
            # List domains
            domains_response = opensearch.list_domain_names()
            
            for domain in domains_response['DomainNames']:
                domain_name = domain['DomainName']
                
                print(f"  Found OpenSearch domain: {domain_name}")
                
                try:
                    opensearch.delete_domain(DomainName=domain_name)
                    self.log_action("DELETE_OPENSEARCH_DOMAIN", domain_name, "SUCCESS", "Deleted domain")
                    
                except Exception as e:
                    self.log_action("DELETE_OPENSEARCH_DOMAIN", domain_name, "ERROR", str(e))
                    
        except Exception as e:
            self.log_action("OPENSEARCH_SCAN", self.region, "ERROR", str(e))
    
    def shutdown_elasticache(self):
        """Delete ElastiCache clusters (costing $27.29)"""
        print(f"\n🛑 DELETING ELASTICACHE CLUSTERS IN {self.region}...")
        
        try:
            elasticache = self.session.client('elasticache', region_name=self.region)
            
            # Redis clusters
            redis_response = elasticache.describe_replication_groups()
            for cluster in redis_response['ReplicationGroups']:
                cluster_id = cluster['ReplicationGroupId']
                status = cluster['Status']
                
                print(f"  Found Redis cluster: {cluster_id} - {status}")
                
                if status == 'available':
                    try:
                        elasticache.delete_replication_group(
                            ReplicationGroupId=cluster_id,
                            RetainPrimaryCluster=False
                        )
                        self.log_action("DELETE_REDIS_CLUSTER", cluster_id, "SUCCESS", "Deleted Redis cluster")
                        
                    except Exception as e:
                        self.log_action("DELETE_REDIS_CLUSTER", cluster_id, "ERROR", str(e))
            
            # Memcached clusters
            memcached_response = elasticache.describe_cache_clusters()
            for cluster in memcached_response['CacheClusters']:
                cluster_id = cluster['CacheClusterId']
                status = cluster['CacheClusterStatus']
                
                print(f"  Found Memcached cluster: {cluster_id} - {status}")
                
                if status == 'available':
                    try:
                        elasticache.delete_cache_cluster(CacheClusterId=cluster_id)
                        self.log_action("DELETE_MEMCACHED_CLUSTER", cluster_id, "SUCCESS", "Deleted Memcached cluster")
                        
                    except Exception as e:
                        self.log_action("DELETE_MEMCACHED_CLUSTER", cluster_id, "ERROR", str(e))
                        
        except Exception as e:
            self.log_action("ELASTICACHE_SCAN", self.region, "ERROR", str(e))
    
    def execute_us_east_1_shutdown(self):
        """Execute complete shutdown of us-east-1 resources"""
        print("🚨 US-EAST-1 EMERGENCY SHUTDOWN")
        print("=" * 60)
        print(f"⚠️  Targeting $469.92 in costs from {self.region}")
        print("⚠️  This will delete resources causing the high costs!")
        print("=" * 60)
        
        # Execute shutdowns in order of cost impact
        self.shutdown_neptune_instances()    # $115.79
        self.shutdown_ecs_fargate()          # $75.07
        self.delete_vpc_endpoints()          # $47.04
        self.delete_nat_gateways()           # $45.59 + $41.29
        self.delete_load_balancers()         # $29.63
        self.shutdown_elasticache()          # $27.29
        self.shutdown_opensearch()           # $11.99
        
        # Save shutdown log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"us-east-1-shutdown-{timestamp}.json"
        
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
            print(f"💰 Expected cost reduction: Up to $469.92/month from us-east-1")
        
        if error_count > 0:
            print(f"\n⚠️  {error_count} actions failed. Check the log file for details.")
        
        print(f"\n💰 Monitor your AWS billing over the next few hours to confirm cost reduction.")
        
        return success_count > 0

def main():
    shutdown = USEast1Shutdown()
    
    try:
        success = shutdown.execute_us_east_1_shutdown()
        return 0 if success else 1
        
    except Exception as e:
        print(f"❌ Critical error during us-east-1 shutdown: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())