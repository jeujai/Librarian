#!/usr/bin/env python3
"""
Cleanup script to remove unused ALB and NLB resources.

This script removes:
- multimodal-lib-prod-alb (Application Load Balancer)
- multimodal-lib-prod-nlb (Network Load Balancer)  
- multimodal-lib-prod-alb-tg (ALB Target Group)
- multimodal-lib-prod-nlb-tg (NLB Target Group)

These resources are no longer in use by the current ECS service.
"""

import boto3
import json
import time
from datetime import datetime

def log_action(message):
    """Log actions with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def main():
    # Initialize AWS clients
    elbv2_client = boto3.client('elbv2')
    
    # Resources to remove
    resources_to_remove = {
        'load_balancers': [
            'multimodal-lib-prod-alb',
            'multimodal-lib-prod-nlb'
        ],
        'target_groups': [
            'multimodal-lib-prod-alb-tg', 
            'multimodal-lib-prod-nlb-tg'
        ]
    }
    
    results = {
        'removed_load_balancers': [],
        'removed_target_groups': [],
        'errors': []
    }
    
    log_action("Starting cleanup of unused load balancer resources...")
    
    # Step 1: Get ARNs for load balancers
    lb_arns = {}
    try:
        response = elbv2_client.describe_load_balancers()
        for lb in response['LoadBalancers']:
            if lb['LoadBalancerName'] in resources_to_remove['load_balancers']:
                lb_arns[lb['LoadBalancerName']] = lb['LoadBalancerArn']
                log_action(f"Found load balancer: {lb['LoadBalancerName']} ({lb['State']['Code']})")
    except Exception as e:
        error_msg = f"Error describing load balancers: {str(e)}"
        log_action(error_msg)
        results['errors'].append(error_msg)
    
    # Step 2: Get ARNs for target groups
    tg_arns = {}
    try:
        response = elbv2_client.describe_target_groups()
        for tg in response['TargetGroups']:
            if tg['TargetGroupName'] in resources_to_remove['target_groups']:
                tg_arns[tg['TargetGroupName']] = tg['TargetGroupArn']
                log_action(f"Found target group: {tg['TargetGroupName']}")
    except Exception as e:
        error_msg = f"Error describing target groups: {str(e)}"
        log_action(error_msg)
        results['errors'].append(error_msg)
    
    # Step 3: Remove load balancers first (this will automatically detach target groups)
    for lb_name in resources_to_remove['load_balancers']:
        if lb_name in lb_arns:
            try:
                log_action(f"Deleting load balancer: {lb_name}")
                elbv2_client.delete_load_balancer(LoadBalancerArn=lb_arns[lb_name])
                results['removed_load_balancers'].append(lb_name)
                log_action(f"Successfully initiated deletion of load balancer: {lb_name}")
            except Exception as e:
                error_msg = f"Error deleting load balancer {lb_name}: {str(e)}"
                log_action(error_msg)
                results['errors'].append(error_msg)
        else:
            log_action(f"Load balancer {lb_name} not found - may already be deleted")
    
    # Step 4: Wait for load balancers to be deleted before removing target groups
    if results['removed_load_balancers']:
        log_action("Waiting for load balancers to be deleted before removing target groups...")
        time.sleep(30)  # Give load balancers time to start deletion process
        
        # Check deletion status
        for lb_name in results['removed_load_balancers']:
            max_attempts = 20
            attempt = 0
            while attempt < max_attempts:
                try:
                    response = elbv2_client.describe_load_balancers(
                        LoadBalancerArns=[lb_arns[lb_name]]
                    )
                    if response['LoadBalancers']:
                        state = response['LoadBalancers'][0]['State']['Code']
                        log_action(f"Load balancer {lb_name} state: {state}")
                        if state == 'active':
                            time.sleep(10)
                            attempt += 1
                        else:
                            break
                    else:
                        log_action(f"Load balancer {lb_name} successfully deleted")
                        break
                except elbv2_client.exceptions.LoadBalancerNotFoundException:
                    log_action(f"Load balancer {lb_name} successfully deleted")
                    break
                except Exception as e:
                    log_action(f"Error checking load balancer {lb_name} status: {str(e)}")
                    break
    
    # Step 5: Remove target groups
    for tg_name in resources_to_remove['target_groups']:
        if tg_name in tg_arns:
            try:
                log_action(f"Deleting target group: {tg_name}")
                elbv2_client.delete_target_group(TargetGroupArn=tg_arns[tg_name])
                results['removed_target_groups'].append(tg_name)
                log_action(f"Successfully deleted target group: {tg_name}")
            except Exception as e:
                error_msg = f"Error deleting target group {tg_name}: {str(e)}"
                log_action(error_msg)
                results['errors'].append(error_msg)
        else:
            log_action(f"Target group {tg_name} not found - may already be deleted")
    
    # Step 6: Generate summary report
    log_action("Cleanup completed. Generating summary report...")
    
    timestamp = int(time.time())
    report_file = f"load-balancer-cleanup-{timestamp}.json"
    
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    log_action(f"Summary report saved to: {report_file}")
    
    # Print summary
    print("\n" + "="*60)
    print("CLEANUP SUMMARY")
    print("="*60)
    print(f"Removed Load Balancers: {len(results['removed_load_balancers'])}")
    for lb in results['removed_load_balancers']:
        print(f"  - {lb}")
    
    print(f"\nRemoved Target Groups: {len(results['removed_target_groups'])}")
    for tg in results['removed_target_groups']:
        print(f"  - {tg}")
    
    if results['errors']:
        print(f"\nErrors: {len(results['errors'])}")
        for error in results['errors']:
            print(f"  - {error}")
    
    print("\nCleanup completed successfully!")
    return len(results['errors']) == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)