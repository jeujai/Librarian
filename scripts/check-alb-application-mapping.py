#!/usr/bin/env python3
"""
Check which applications are using which ALBs by examining target groups and their targets.
"""

import boto3
import json
from datetime import datetime

def analyze_alb_application_mapping():
    """Analyze which applications are using which ALBs."""
    elbv2 = boto3.client('elbv2')
    ecs = boto3.client('ecs')
    
    print("🔍 ALB to Application Mapping Analysis")
    print("=" * 60)
    
    # Get all ALBs
    response = elbv2.describe_load_balancers()
    load_balancers = [lb for lb in response['LoadBalancers'] if lb['Type'] == 'application']
    
    mapping = {}
    
    for lb in load_balancers:
        lb_name = lb['LoadBalancerName']
        lb_arn = lb['LoadBalancerArn']
        
        print(f"\n📊 ALB: {lb_name}")
        print(f"  DNS: {lb['DNSName']}")
        print(f"  VPC: {lb['VpcId']}")
        print("-" * 40)
        
        # Get target groups for this ALB
        try:
            tg_response = elbv2.describe_target_groups(LoadBalancerArn=lb_arn)
            target_groups = tg_response['TargetGroups']
            
            alb_info = {
                'dns_name': lb['DNSName'],
                'vpc_id': lb['VpcId'],
                'state': lb['State']['Code'],
                'target_groups': []
            }
            
            for tg in target_groups:
                tg_name = tg['TargetGroupName']
                tg_arn = tg['TargetGroupArn']
                
                # Get target health
                health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                targets = health_response['TargetHealthDescriptions']
                
                print(f"  Target Group: {tg_name}")
                print(f"    Port: {tg['Port']}")
                print(f"    Health Check: {tg.get('HealthCheckPath', 'N/A')}")
                print(f"    Targets: {len(targets)}")
                
                tg_info = {
                    'name': tg_name,
                    'port': tg['Port'],
                    'health_check_path': tg.get('HealthCheckPath', 'N/A'),
                    'targets': [],
                    'application_type': 'unknown'
                }
                
                # Analyze targets to determine application type
                for target in targets:
                    target_id = target['Target']['Id']
                    target_port = target['Target']['Port']
                    health_state = target['TargetHealth']['State']
                    
                    print(f"      Target: {target_id}:{target_port} ({health_state})")
                    
                    tg_info['targets'].append({
                        'id': target_id,
                        'port': target_port,
                        'health': health_state
                    })
                
                # Determine application type based on target group name and port
                if 'collab' in tg_name.lower() or tg['Port'] == 3001:
                    tg_info['application_type'] = 'collaborative-editor'
                elif 'multimodal' in tg_name.lower() or 'ml' in tg_name.lower() or tg['Port'] == 8000:
                    tg_info['application_type'] = 'multimodal-librarian'
                
                print(f"    Application Type: {tg_info['application_type']}")
                
                alb_info['target_groups'].append(tg_info)
            
            mapping[lb_name] = alb_info
            
        except Exception as e:
            print(f"  ❌ Error analyzing {lb_name}: {e}")
    
    return mapping

def generate_usage_summary(mapping):
    """Generate a clear summary of ALB usage."""
    print(f"\n📋 ALB Usage Summary")
    print("=" * 60)
    
    for alb_name, info in mapping.items():
        print(f"\n🔸 {alb_name}")
        print(f"  DNS: {info['dns_name']}")
        
        if not info['target_groups']:
            print(f"  Status: ❌ NO TARGET GROUPS")
            continue
        
        total_targets = sum(len(tg['targets']) for tg in info['target_groups'])
        healthy_targets = sum(len([t for t in tg['targets'] if t['health'] == 'healthy']) for tg in info['target_groups'])
        
        print(f"  Targets: {healthy_targets}/{total_targets} healthy")
        
        # Determine primary application
        app_types = [tg['application_type'] for tg in info['target_groups'] if tg['application_type'] != 'unknown']
        if app_types:
            primary_app = max(set(app_types), key=app_types.count)
            print(f"  Primary Application: {primary_app}")
        else:
            print(f"  Primary Application: unknown")
        
        # Show target group details
        for tg in info['target_groups']:
            healthy_tg_targets = len([t for t in tg['targets'] if t['health'] == 'healthy'])
            total_tg_targets = len(tg['targets'])
            print(f"    - {tg['name']}: {healthy_tg_targets}/{total_tg_targets} targets on port {tg['port']}")

def answer_specific_question(mapping):
    """Answer the specific question about ml-shared-vpc-alb and Collaborative Editor."""
    print(f"\n❓ Question: Is ml-shared-vpc-alb being used by the Collaborative Editor Application?")
    print("=" * 80)
    
    if 'ml-shared-vpc-alb' not in mapping:
        print("❌ ml-shared-vpc-alb not found!")
        return
    
    alb_info = mapping['ml-shared-vpc-alb']
    
    print(f"🔍 Analysis of ml-shared-vpc-alb:")
    print(f"  DNS: {alb_info['dns_name']}")
    print(f"  VPC: {alb_info['vpc_id']}")
    
    if not alb_info['target_groups']:
        print("❌ ANSWER: No - it has no target groups")
        return
    
    # Check each target group
    collaborative_editor_usage = False
    multimodal_librarian_usage = False
    
    for tg in alb_info['target_groups']:
        print(f"\n  Target Group: {tg['name']}")
        print(f"    Port: {tg['port']}")
        print(f"    Health Check: {tg['health_check_path']}")
        print(f"    Application Type: {tg['application_type']}")
        print(f"    Targets: {len([t for t in tg['targets'] if t['health'] == 'healthy'])}/{len(tg['targets'])} healthy")
        
        if tg['application_type'] == 'collaborative-editor':
            collaborative_editor_usage = True
        elif tg['application_type'] == 'multimodal-librarian':
            multimodal_librarian_usage = True
    
    # Final answer
    print(f"\n🎯 ANSWER:")
    if collaborative_editor_usage and multimodal_librarian_usage:
        print("❓ MIXED USAGE - ml-shared-vpc-alb is used by BOTH applications")
        print("   - Collaborative Editor targets detected")
        print("   - Multimodal Librarian targets detected")
    elif collaborative_editor_usage:
        print("✅ YES - ml-shared-vpc-alb is being used by the Collaborative Editor")
    elif multimodal_librarian_usage:
        print("❌ NO - ml-shared-vpc-alb is being used by the Multimodal Librarian (not Collaborative Editor)")
    else:
        print("❓ UNCLEAR - Could not determine application type from target analysis")
    
    # Additional context
    print(f"\n📝 Additional Context:")
    print(f"   - Port 3001 typically = Collaborative Editor")
    print(f"   - Port 8000 typically = Multimodal Librarian")
    print(f"   - Target group names and health check paths provide clues")

def main():
    """Main execution function."""
    print("🚀 ALB Application Mapping Analysis")
    print("=" * 60)
    print(f"Analysis Time: {datetime.now().isoformat()}")
    
    try:
        # Analyze ALB to application mapping
        mapping = analyze_alb_application_mapping()
        
        # Generate usage summary
        generate_usage_summary(mapping)
        
        # Answer the specific question
        answer_specific_question(mapping)
        
        # Save results
        with open(f'alb-application-mapping-{int(datetime.now().timestamp())}.json', 'w') as f:
            json.dump({
                'analysis_time': datetime.now().isoformat(),
                'alb_mapping': mapping
            }, f, indent=2, default=str)
        
        print(f"\n💾 Detailed results saved to: alb-application-mapping-{int(datetime.now().timestamp())}.json")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return 1

if __name__ == "__main__":
    exit(main())