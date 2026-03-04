#!/usr/bin/env python3
"""
Analyze ALB usage and determine why we have multiple load balancers.
This script will examine each ALB's configuration, target groups, and usage.
"""

import boto3
import json
from datetime import datetime, timedelta

def analyze_alb_configuration():
    """Analyze all ALBs and their configurations."""
    elbv2 = boto3.client('elbv2')
    ec2 = boto3.client('ec2')
    
    print("🔍 Analyzing Application Load Balancer Configuration")
    print("=" * 60)
    
    # Get all load balancers
    response = elbv2.describe_load_balancers()
    load_balancers = response['LoadBalancers']
    
    alb_analysis = {}
    
    for lb in load_balancers:
        if lb['Type'] == 'application':
            lb_name = lb['LoadBalancerName']
            lb_arn = lb['LoadBalancerArn']
            
            print(f"\n📊 Analyzing ALB: {lb_name}")
            print("-" * 40)
            
            # Get basic info
            analysis = {
                'name': lb_name,
                'dns_name': lb['DNSName'],
                'state': lb['State']['Code'],
                'vpc_id': lb['VpcId'],
                'availability_zones': [az['ZoneName'] for az in lb['AvailabilityZones']],
                'subnets': [az['SubnetId'] for az in lb['AvailabilityZones']],
                'scheme': lb['Scheme'],
                'ip_address_type': lb['IpAddressType'],
                'created_time': lb['CreatedTime'].isoformat(),
                'listeners': [],
                'target_groups': [],
                'tags': {}
            }
            
            # Get VPC name
            try:
                vpc_response = ec2.describe_vpcs(VpcIds=[lb['VpcId']])
                vpc_tags = vpc_response['Vpcs'][0].get('Tags', [])
                vpc_name = next((tag['Value'] for tag in vpc_tags if tag['Key'] == 'Name'), 'Unknown')
                analysis['vpc_name'] = vpc_name
            except:
                analysis['vpc_name'] = 'Unknown'
            
            # Get tags
            try:
                tags_response = elbv2.describe_tags(ResourceArns=[lb_arn])
                for tag_desc in tags_response['TagDescriptions']:
                    for tag in tag_desc['Tags']:
                        analysis['tags'][tag['Key']] = tag['Value']
            except:
                pass
            
            # Get listeners
            try:
                listeners_response = elbv2.describe_listeners(LoadBalancerArn=lb_arn)
                for listener in listeners_response['Listeners']:
                    listener_info = {
                        'port': listener['Port'],
                        'protocol': listener['Protocol'],
                        'ssl_policy': listener.get('SslPolicy', 'N/A'),
                        'certificates': len(listener.get('Certificates', [])),
                        'default_actions': []
                    }
                    
                    for action in listener['DefaultActions']:
                        if action['Type'] == 'forward':
                            target_group_arn = action['TargetGroupArn']
                            listener_info['default_actions'].append({
                                'type': 'forward',
                                'target_group_arn': target_group_arn
                            })
                    
                    analysis['listeners'].append(listener_info)
            except Exception as e:
                print(f"  ⚠️  Error getting listeners: {e}")
            
            # Get target groups
            try:
                target_groups_response = elbv2.describe_target_groups(LoadBalancerArn=lb_arn)
                for tg in target_groups_response['TargetGroups']:
                    tg_arn = tg['TargetGroupArn']
                    
                    # Get target health
                    health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                    targets = health_response['TargetHealthDescriptions']
                    
                    healthy_targets = [t for t in targets if t['TargetHealth']['State'] == 'healthy']
                    unhealthy_targets = [t for t in targets if t['TargetHealth']['State'] != 'healthy']
                    
                    tg_info = {
                        'name': tg['TargetGroupName'],
                        'arn': tg_arn,
                        'protocol': tg['Protocol'],
                        'port': tg['Port'],
                        'vpc_id': tg['VpcId'],
                        'health_check_path': tg.get('HealthCheckPath', 'N/A'),
                        'target_type': tg['TargetType'],
                        'total_targets': len(targets),
                        'healthy_targets': len(healthy_targets),
                        'unhealthy_targets': len(unhealthy_targets),
                        'targets': []
                    }
                    
                    for target in targets:
                        tg_info['targets'].append({
                            'id': target['Target']['Id'],
                            'port': target['Target']['Port'],
                            'health': target['TargetHealth']['State'],
                            'description': target['TargetHealth'].get('Description', '')
                        })
                    
                    analysis['target_groups'].append(tg_info)
            except Exception as e:
                print(f"  ⚠️  Error getting target groups: {e}")
            
            alb_analysis[lb_name] = analysis
            
            # Print summary
            print(f"  DNS: {analysis['dns_name']}")
            print(f"  VPC: {analysis['vpc_name']} ({analysis['vpc_id']})")
            print(f"  State: {analysis['state']}")
            print(f"  Listeners: {len(analysis['listeners'])}")
            print(f"  Target Groups: {len(analysis['target_groups'])}")
            
            if analysis['target_groups']:
                total_targets = sum(tg['total_targets'] for tg in analysis['target_groups'])
                healthy_targets = sum(tg['healthy_targets'] for tg in analysis['target_groups'])
                print(f"  Targets: {healthy_targets}/{total_targets} healthy")
    
    return alb_analysis

def analyze_usage_patterns(alb_analysis):
    """Analyze usage patterns and identify redundancy."""
    print(f"\n🔍 Usage Pattern Analysis")
    print("=" * 60)
    
    # Group by VPC
    vpc_groups = {}
    for alb_name, analysis in alb_analysis.items():
        vpc_id = analysis['vpc_id']
        if vpc_id not in vpc_groups:
            vpc_groups[vpc_id] = []
        vpc_groups[vpc_id].append((alb_name, analysis))
    
    print(f"\n📊 ALBs by VPC:")
    for vpc_id, albs in vpc_groups.items():
        vpc_name = albs[0][1]['vpc_name']
        print(f"\n  VPC: {vpc_name} ({vpc_id})")
        for alb_name, analysis in albs:
            active_targets = sum(tg['healthy_targets'] for tg in analysis['target_groups'])
            total_targets = sum(tg['total_targets'] for tg in analysis['target_groups'])
            print(f"    - {alb_name}: {active_targets}/{total_targets} targets")
    
    # Identify potential issues
    print(f"\n⚠️  Potential Issues:")
    
    issues = []
    
    # Check for ALBs with no healthy targets
    for alb_name, analysis in alb_analysis.items():
        healthy_targets = sum(tg['healthy_targets'] for tg in analysis['target_groups'])
        total_targets = sum(tg['total_targets'] for tg in analysis['target_groups'])
        
        if total_targets == 0:
            issues.append(f"  - {alb_name}: No targets registered")
        elif healthy_targets == 0:
            issues.append(f"  - {alb_name}: No healthy targets ({total_targets} total)")
        elif healthy_targets < total_targets:
            issues.append(f"  - {alb_name}: Some unhealthy targets ({healthy_targets}/{total_targets})")
    
    # Check for multiple ALBs in same VPC
    for vpc_id, albs in vpc_groups.items():
        if len(albs) > 1:
            vpc_name = albs[0][1]['vpc_name']
            alb_names = [alb[0] for alb in albs]
            issues.append(f"  - Multiple ALBs in {vpc_name}: {', '.join(alb_names)}")
    
    if issues:
        for issue in issues:
            print(issue)
    else:
        print("  No obvious issues detected")

def generate_recommendations(alb_analysis):
    """Generate recommendations for optimization."""
    print(f"\n💡 Recommendations")
    print("=" * 60)
    
    recommendations = []
    
    # Check for unused ALBs
    for alb_name, analysis in alb_analysis.items():
        healthy_targets = sum(tg['healthy_targets'] for tg in analysis['target_groups'])
        total_targets = sum(tg['total_targets'] for tg in analysis['target_groups'])
        
        if total_targets == 0:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'DELETE',
                'resource': alb_name,
                'reason': 'No targets registered - appears unused',
                'cost_impact': 'Save ~$16-22/month per ALB'
            })
        elif healthy_targets == 0:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'INVESTIGATE',
                'resource': alb_name,
                'reason': 'No healthy targets - may be misconfigured',
                'cost_impact': 'Potential waste if not needed'
            })
    
    # Check for consolidation opportunities
    vpc_groups = {}
    for alb_name, analysis in alb_analysis.items():
        vpc_id = analysis['vpc_id']
        if vpc_id not in vpc_groups:
            vpc_groups[vpc_id] = []
        vpc_groups[vpc_id].append((alb_name, analysis))
    
    for vpc_id, albs in vpc_groups.items():
        if len(albs) > 1:
            vpc_name = albs[0][1]['vpc_name']
            active_albs = [(name, analysis) for name, analysis in albs 
                          if sum(tg['healthy_targets'] for tg in analysis['target_groups']) > 0]
            
            if len(active_albs) > 1:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'action': 'CONSOLIDATE',
                    'resource': f"ALBs in {vpc_name}",
                    'reason': f'Multiple active ALBs in same VPC: {", ".join([alb[0] for alb in active_albs])}',
                    'cost_impact': f'Could save ~${16 * (len(active_albs) - 1)}-{22 * (len(active_albs) - 1)}/month'
                })
    
    if recommendations:
        for rec in sorted(recommendations, key=lambda x: x['priority']):
            print(f"\n  🎯 {rec['priority']} PRIORITY: {rec['action']}")
            print(f"     Resource: {rec['resource']}")
            print(f"     Reason: {rec['reason']}")
            print(f"     Cost Impact: {rec['cost_impact']}")
    else:
        print("  No optimization opportunities identified")
    
    return recommendations

def main():
    """Main analysis function."""
    print("🔍 ALB Usage Analysis")
    print("=" * 60)
    print(f"Analysis Time: {datetime.now().isoformat()}")
    
    try:
        # Analyze ALB configuration
        alb_analysis = analyze_alb_configuration()
        
        # Analyze usage patterns
        analyze_usage_patterns(alb_analysis)
        
        # Generate recommendations
        recommendations = generate_recommendations(alb_analysis)
        
        # Summary
        print(f"\n📋 Summary")
        print("=" * 60)
        print(f"Total ALBs: {len(alb_analysis)}")
        
        active_albs = 0
        unused_albs = 0
        
        for alb_name, analysis in alb_analysis.items():
            healthy_targets = sum(tg['healthy_targets'] for tg in analysis['target_groups'])
            if healthy_targets > 0:
                active_albs += 1
            else:
                unused_albs += 1
        
        print(f"Active ALBs: {active_albs}")
        print(f"Unused ALBs: {unused_albs}")
        print(f"Optimization Opportunities: {len(recommendations)}")
        
        if unused_albs > 0:
            potential_savings = unused_albs * 19  # Average of $16-22
            print(f"Potential Monthly Savings: ~${potential_savings}")
        
        # Save detailed analysis
        with open('alb_analysis_detailed.json', 'w') as f:
            json.dump({
                'analysis_time': datetime.now().isoformat(),
                'alb_analysis': alb_analysis,
                'recommendations': recommendations
            }, f, indent=2, default=str)
        
        print(f"\n💾 Detailed analysis saved to: alb_analysis_detailed.json")
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())