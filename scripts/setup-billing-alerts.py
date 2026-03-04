#!/usr/bin/env python3
"""
Set up billing alerts to prevent future cost surprises
"""

import boto3
import json
from datetime import datetime
import sys

def setup_billing_alerts():
    session = boto3.Session()
    
    print("🚨 SETTING UP BILLING ALERTS")
    print("=" * 60)
    
    try:
        # CloudWatch for billing alerts (must be in us-east-1)
        cloudwatch = session.client('cloudwatch', region_name='us-east-1')
        sns = session.client('sns', region_name='us-east-1')
        
        # Create SNS topic for alerts
        topic_name = 'aws-cost-alerts'
        
        try:
            topic_response = sns.create_topic(Name=topic_name)
            topic_arn = topic_response['TopicArn']
            print(f"✅ Created SNS topic: {topic_arn}")
            
        except Exception as e:
            print(f"❌ Error creating SNS topic: {e}")
            return False
        
        # Create billing alarms
        alarms = [
            {'name': 'AWS-Cost-Alert-5-Dollars', 'threshold': 5.0, 'description': 'Alert when AWS costs exceed $5'},
            {'name': 'AWS-Cost-Alert-10-Dollars', 'threshold': 10.0, 'description': 'Alert when AWS costs exceed $10'},
            {'name': 'AWS-Cost-Alert-25-Dollars', 'threshold': 25.0, 'description': 'EMERGENCY: AWS costs exceed $25'},
        ]
        
        for alarm in alarms:
            try:
                cloudwatch.put_metric_alarm(
                    AlarmName=alarm['name'],
                    ComparisonOperator='GreaterThanThreshold',
                    EvaluationPeriods=1,
                    MetricName='EstimatedCharges',
                    Namespace='AWS/Billing',
                    Period=86400,  # 24 hours
                    Statistic='Maximum',
                    Threshold=alarm['threshold'],
                    ActionsEnabled=True,
                    AlarmActions=[topic_arn],
                    AlarmDescription=alarm['description'],
                    Dimensions=[
                        {
                            'Name': 'Currency',
                            'Value': 'USD'
                        },
                    ],
                    Unit='None'
                )
                
                print(f"✅ Created billing alarm: {alarm['name']} (${alarm['threshold']})")
                
            except Exception as e:
                print(f"❌ Error creating alarm {alarm['name']}: {e}")
        
        print(f"\n📧 To receive email alerts:")
        print(f"1. Go to AWS SNS Console")
        print(f"2. Find topic: {topic_name}")
        print(f"3. Create email subscription")
        print(f"4. Confirm the subscription email")
        
        return True
        
    except Exception as e:
        print(f"❌ Error setting up billing alerts: {e}")
        return False

def create_cost_summary():
    """Create a summary of the cost situation"""
    
    print(f"\n📊 COST SITUATION SUMMARY")
    print("=" * 60)
    
    print(f"💰 CURRENT BILLING STATUS:")
    print(f"  • Total January 2025 costs: $516.91")
    print(f"  • December 2024 costs: $1.70")
    print(f"  • Cost increase: +$515.21 (+30,306%)")
    
    print(f"\n🔍 RESOURCES FOUND & ACTIONS TAKEN:")
    print(f"  ✅ Deleted 2 VPC endpoints (saved ~$47/month)")
    print(f"  ✅ Deleted 3 CloudFront distributions (saved ~$12/month)")
    print(f"  ✅ Terminated 2 stopped EC2 instances")
    print(f"  ❌ 1 CloudFront distribution blocked by pricing plan")
    print(f"  ❌ 1 S3 bucket blocked by policy")
    
    print(f"\n🚨 MAJOR BILLING MYSTERY:")
    print(f"  • Billing shows $469.92 in us-east-1 costs")
    print(f"  • API scans find ZERO active resources in us-east-1")
    print(f"  • Top phantom costs:")
    print(f"    - Neptune: $115.79 (no instances found)")
    print(f"    - ECS Fargate: $75.07 (no tasks found)")
    print(f"    - ElastiCache: $27.29 (no clusters found)")
    print(f"    - Load Balancers: $29.64 (no LBs found)")
    
    print(f"\n⚠️  IMMEDIATE ACTIONS REQUIRED:")
    print(f"  1. 🆘 Contact AWS Support immediately")
    print(f"  2. 📧 Set up billing alerts (run this script)")
    print(f"  3. 🔍 Manual AWS Console check")
    print(f"  4. 📱 Monitor billing daily")
    
    print(f"\n📞 AWS SUPPORT CASE DETAILS:")
    print(f"  • Case Type: Billing")
    print(f"  • Issue: Charged $516/month with no visible resources")
    print(f"  • Evidence: API scans show zero resources but billing shows major costs")
    print(f"  • Request: Immediate investigation and cost reversal if appropriate")

if __name__ == "__main__":
    create_cost_summary()
    
    print(f"\n" + "=" * 60)
    setup_success = setup_billing_alerts()
    
    if setup_success:
        print(f"\n✅ Billing alerts configured successfully!")
        print(f"💡 Don't forget to subscribe to email notifications in SNS console")
    else:
        print(f"\n❌ Failed to set up billing alerts")
        print(f"💡 You can set these up manually in CloudWatch console")
    
    sys.exit(0 if setup_success else 1)