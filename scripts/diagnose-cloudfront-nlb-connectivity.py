#!/usr/bin/env python3
"""
Diagnose CloudFront to NLB connectivity issues.

This script checks:
1. CloudFront distribution configuration
2. NLB health and accessibility
3. Origin configuration details
4. Security and network path
"""

import boto3
import json
import time
import requests
from datetime import datetime

def diagnose_cloudfront_nlb():
    """Comprehensive diagnosis of CloudFront to NLB connectivity."""
    
    cloudfront = boto3.client('cloudfront')
    elbv2 = boto3.client('elbv2')
    
    distribution_id = 'E3NVIH7ET1R4G9'
    nlb_dns = 'multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com'
    
    print("=" * 80)
    print("CloudFront to NLB Connectivity Diagnosis")
    print("=" * 80)
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'distribution_id': distribution_id,
        'tests': {}
    }
    
    # 1. Check CloudFront Distribution Status
    print("\n1️⃣  CLOUDFRONT DISTRIBUTION STATUS")
    print("-" * 80)
    
    try:
        dist_response = cloudfront.get_distribution(Id=distribution_id)
        dist = dist_response['Distribution']
        
        status = dist['Status']
        domain = dist['DomainName']
        enabled = dist['DistributionConfig']['Enabled']
        
        print(f"   Status: {status}")
        print(f"   Domain: {domain}")
        print(f"   Enabled: {enabled}")
        print(f"   Last Modified: {dist['LastModifiedTime']}")
        
        results['tests']['cloudfront_status'] = {
            'status': status,
            'domain': domain,
            'enabled': enabled,
            'passed': status == 'Deployed' and enabled
        }
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['cloudfront_status'] = {'passed': False, 'error': str(e)}
    
    # 2. Check Origin Configuration
    print("\n2️⃣  ORIGIN CONFIGURATION")
    print("-" * 80)
    
    try:
        config_response = cloudfront.get_distribution_config(Id=distribution_id)
        config = config_response['DistributionConfig']
        origin = config['Origins']['Items'][0]
        
        print(f"   Origin Domain: {origin['DomainName']}")
        print(f"   Origin ID: {origin['Id']}")
        print(f"   Origin Protocol: {origin.get('CustomOriginConfig', {}).get('OriginProtocolPolicy', 'N/A')}")
        print(f"   HTTP Port: {origin.get('CustomOriginConfig', {}).get('HTTPPort', 'N/A')}")
        print(f"   HTTPS Port: {origin.get('CustomOriginConfig', {}).get('HTTPSPort', 'N/A')}")
        
        # Check if origin matches NLB
        origin_matches = origin['DomainName'] == nlb_dns
        print(f"   Origin Matches NLB: {'✅' if origin_matches else '❌'}")
        
        results['tests']['origin_config'] = {
            'origin_domain': origin['DomainName'],
            'matches_nlb': origin_matches,
            'protocol': origin.get('CustomOriginConfig', {}).get('OriginProtocolPolicy'),
            'passed': origin_matches
        }
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['origin_config'] = {'passed': False, 'error': str(e)}
    
    # 3. Test NLB Direct Access
    print("\n3️⃣  NLB DIRECT ACCESS TEST")
    print("-" * 80)
    
    try:
        nlb_url = f"http://{nlb_dns}:8000/health"
        print(f"   Testing: {nlb_url}")
        
        response = requests.get(nlb_url, timeout=10)
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Time: {response.elapsed.total_seconds():.2f}s")
        
        if response.status_code == 200:
            print(f"   ✅ NLB is accessible and healthy")
        else:
            print(f"   ⚠️  NLB returned non-200 status")
        
        results['tests']['nlb_direct'] = {
            'status_code': response.status_code,
            'response_time': response.elapsed.total_seconds(),
            'passed': response.status_code == 200
        }
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['nlb_direct'] = {'passed': False, 'error': str(e)}
    
    # 4. Test CloudFront Access
    print("\n4️⃣  CLOUDFRONT ACCESS TEST")
    print("-" * 80)
    
    try:
        cf_url = f"https://{domain}/health"
        print(f"   Testing: {cf_url}")
        
        response = requests.get(cf_url, timeout=30)
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Time: {response.elapsed.total_seconds():.2f}s")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print(f"   ✅ CloudFront is accessible")
        else:
            print(f"   ❌ CloudFront returned {response.status_code}")
            print(f"   Response: {response.text[:500]}")
        
        results['tests']['cloudfront_access'] = {
            'status_code': response.status_code,
            'response_time': response.elapsed.total_seconds(),
            'passed': response.status_code == 200
        }
        
    except requests.exceptions.Timeout:
        print(f"   ❌ Request timed out after 30 seconds")
        results['tests']['cloudfront_access'] = {'passed': False, 'error': 'Timeout'}
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Connection error: {str(e)}")
        results['tests']['cloudfront_access'] = {'passed': False, 'error': f'Connection error: {str(e)}'}
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['cloudfront_access'] = {'passed': False, 'error': str(e)}
    
    # 5. Check NLB Target Health
    print("\n5️⃣  NLB TARGET HEALTH")
    print("-" * 80)
    
    try:
        # Get NLB ARN
        lbs = elbv2.describe_load_balancers(Names=['multimodal-lib-prod-nlb'])
        nlb_arn = lbs['LoadBalancers'][0]['LoadBalancerArn']
        
        # Get target groups
        tgs = elbv2.describe_target_groups(LoadBalancerArn=nlb_arn)
        
        for tg in tgs['TargetGroups']:
            tg_arn = tg['TargetGroupArn']
            print(f"   Target Group: {tg['TargetGroupName']}")
            print(f"   Port: {tg['Port']}")
            print(f"   Protocol: {tg['Protocol']}")
            
            # Get target health
            health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
            
            for target in health['TargetHealthDescriptions']:
                target_id = target['Target']['Id']
                target_port = target['Target']['Port']
                health_state = target['TargetHealth']['State']
                
                print(f"   Target: {target_id}:{target_port}")
                print(f"   Health: {health_state}")
                
                if health_state == 'healthy':
                    print(f"   ✅ Target is healthy")
                else:
                    print(f"   ❌ Target is {health_state}")
                    if 'Reason' in target['TargetHealth']:
                        print(f"   Reason: {target['TargetHealth']['Reason']}")
        
        results['tests']['nlb_targets'] = {'passed': True}
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['nlb_targets'] = {'passed': False, 'error': str(e)}
    
    # 6. Check Cache Behavior
    print("\n6️⃣  CLOUDFRONT CACHE BEHAVIOR")
    print("-" * 80)
    
    try:
        default_behavior = config['DefaultCacheBehavior']
        print(f"   Target Origin ID: {default_behavior['TargetOriginId']}")
        print(f"   Viewer Protocol Policy: {default_behavior['ViewerProtocolPolicy']}")
        print(f"   Allowed Methods: {default_behavior['AllowedMethods']['Items']}")
        print(f"   Cached Methods: {default_behavior.get('CachedMethods', {}).get('Items', [])}")
        print(f"   Compress: {default_behavior.get('Compress', False)}")
        
        # Check if target origin matches
        target_matches = default_behavior['TargetOriginId'] == origin['Id']
        print(f"   Target Matches Origin: {'✅' if target_matches else '❌'}")
        
        results['tests']['cache_behavior'] = {
            'target_origin_id': default_behavior['TargetOriginId'],
            'matches_origin': target_matches,
            'passed': target_matches
        }
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        results['tests']['cache_behavior'] = {'passed': False, 'error': str(e)}
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    
    all_passed = all(test.get('passed', False) for test in results['tests'].values())
    
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed:")
        for test_name, test_result in results['tests'].items():
            if not test_result.get('passed', False):
                print(f"   - {test_name}: {test_result.get('error', 'Failed')}")
    
    # Save results
    timestamp = int(time.time())
    filename = f'cloudfront-nlb-diagnosis-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    return results

if __name__ == '__main__':
    diagnose_cloudfront_nlb()
