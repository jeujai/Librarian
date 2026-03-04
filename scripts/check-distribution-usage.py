#!/usr/bin/env python3
"""
Check CloudFront Distribution Usage

This script checks if a specific CloudFront distribution is in use by:
1. Testing connectivity to the distribution
2. Checking for references in infrastructure code
3. Analyzing traffic patterns (if available)
"""

import boto3
import json
import sys
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
import os
import glob

class DistributionUsageChecker:
    """Checks if a CloudFront distribution is actively in use."""
    
    def __init__(self, distribution_domain: str):
        self.distribution_domain = distribution_domain
        self.cloudfront_client = boto3.client('cloudfront', region_name='us-east-1')
        self.cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'check_distribution_usage',
            'distribution_domain': distribution_domain,
            'distribution_id': None,
            'tests': {},
            'infrastructure_references': [],
            'usage_analysis': {}
        }
    
    def check_usage(self) -> Dict[str, Any]:
        """Check if the distribution is in use."""
        
        print(f"🔍 Checking Usage for CloudFront Distribution")
        print(f"Domain: {self.distribution_domain}")
        print("=" * 50)
        print()
        
        try:
            # Step 1: Find the distribution ID
            distribution_id = self._find_distribution_id()
            if not distribution_id:
                print("❌ Distribution not found")
                return self.results
            
            self.results['distribution_id'] = distribution_id
            print(f"📋 Distribution ID: {distribution_id}")
            print()
            
            # Step 2: Test connectivity
            self._test_connectivity()
            
            # Step 3: Check infrastructure references
            self._check_infrastructure_references()
            
            # Step 4: Check CloudWatch metrics (if available)
            self._check_cloudwatch_metrics(distribution_id)
            
            # Step 5: Analyze usage
            self._analyze_usage()
            
        except Exception as e:
            print(f"❌ Error checking distribution usage: {e}")
            self.results['error'] = str(e)
        
        return self.results
    
    def _find_distribution_id(self) -> str:
        """Find the distribution ID for the given domain."""
        
        try:
            response = self.cloudfront_client.list_distributions()
            
            if 'DistributionList' not in response or 'Items' not in response['DistributionList']:
                return None
            
            for dist in response['DistributionList']['Items']:
                if dist.get('DomainName') == self.distribution_domain:
                    return dist.get('Id')
            
            return None
            
        except Exception as e:
            print(f"Error finding distribution: {e}")
            return None
    
    def _test_connectivity(self):
        """Test connectivity to the distribution."""
        
        print("🌐 Testing Connectivity")
        
        endpoints_to_test = [
            ('/', 'Root endpoint'),
            ('/health', 'Health check'),
            ('/health/simple', 'Simple health check'),
            ('/docs', 'API documentation'),
            ('/api/health', 'API health'),
        ]
        
        connectivity_results = {}
        working_endpoints = 0
        
        for path, description in endpoints_to_test:
            url = f"https://{self.distribution_domain}{path}"
            print(f"   Testing {description}: {path}")
            
            try:
                response = requests.get(url, timeout=10, verify=False)
                success = response.status_code in [200, 301, 302, 404]  # 404 is OK, means it's responding
                
                if success:
                    print(f"     ✅ {response.status_code}")
                    working_endpoints += 1
                else:
                    print(f"     ⚠️  {response.status_code}")
                
                connectivity_results[path] = {
                    'success': success,
                    'status_code': response.status_code,
                    'response_size': len(response.content)
                }
                
            except requests.exceptions.RequestException as e:
                print(f"     ❌ Connection failed: {str(e)[:50]}...")
                connectivity_results[path] = {
                    'success': False,
                    'error': str(e)
                }
        
        self.results['tests']['connectivity'] = {
            'working_endpoints': working_endpoints,
            'total_endpoints': len(endpoints_to_test),
            'results': connectivity_results
        }
        
        print(f"   📊 Working endpoints: {working_endpoints}/{len(endpoints_to_test)}")
        print()
    
    def _check_infrastructure_references(self):
        """Check for references to this distribution in infrastructure code."""
        
        print("🔍 Checking Infrastructure References")
        
        # Patterns to search for
        search_patterns = [
            self.distribution_domain,
            self.results.get('distribution_id', ''),
            # Remove protocol and check base domain
            self.distribution_domain.replace('https://', '').replace('http://', '')
        ]
        
        # File patterns to search in
        file_patterns = [
            '**/*.tf',
            '**/*.py',
            '**/*.yml',
            '**/*.yaml',
            '**/*.json',
            '**/*.md',
            '**/*.sh'
        ]
        
        references = []
        
        for pattern in search_patterns:
            if not pattern:
                continue
                
            print(f"   Searching for: {pattern}")
            
            for file_pattern in file_patterns:
                try:
                    files = glob.glob(file_pattern, recursive=True)
                    for file_path in files:
                        # Skip certain directories
                        if any(skip in file_path for skip in ['.git', '__pycache__', 'node_modules', '.pytest_cache']):
                            continue
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                if pattern in content:
                                    # Count occurrences
                                    count = content.count(pattern)
                                    references.append({
                                        'file': file_path,
                                        'pattern': pattern,
                                        'occurrences': count
                                    })
                                    print(f"     ✅ Found in {file_path} ({count} times)")
                        except Exception:
                            continue  # Skip files we can't read
                            
                except Exception:
                    continue  # Skip patterns that cause issues
        
        self.results['infrastructure_references'] = references
        
        if references:
            print(f"   📋 Found {len(references)} file(s) with references")
        else:
            print("   📭 No infrastructure references found")
        print()
    
    def _check_cloudwatch_metrics(self, distribution_id: str):
        """Check CloudWatch metrics for the distribution."""
        
        print("📊 Checking CloudWatch Metrics")
        
        try:
            # Get metrics for the last 7 days
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            metrics_to_check = [
                ('Requests', 'Sum'),
                ('BytesDownloaded', 'Sum'),
                ('4xxErrorRate', 'Average'),
                ('5xxErrorRate', 'Average')
            ]
            
            metrics_results = {}
            
            for metric_name, statistic in metrics_to_check:
                try:
                    response = self.cloudwatch_client.get_metric_statistics(
                        Namespace='AWS/CloudFront',
                        MetricName=metric_name,
                        Dimensions=[
                            {
                                'Name': 'DistributionId',
                                'Value': distribution_id
                            }
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=86400,  # 1 day
                        Statistics=[statistic]
                    )
                    
                    datapoints = response.get('Datapoints', [])
                    if datapoints:
                        total_value = sum(dp[statistic] for dp in datapoints)
                        metrics_results[metric_name] = {
                            'total': total_value,
                            'datapoints': len(datapoints),
                            'has_activity': total_value > 0
                        }
                        
                        if total_value > 0:
                            print(f"   ✅ {metric_name}: {total_value:.2f} (last 7 days)")
                        else:
                            print(f"   📊 {metric_name}: No activity")
                    else:
                        metrics_results[metric_name] = {
                            'total': 0,
                            'datapoints': 0,
                            'has_activity': False
                        }
                        print(f"   📊 {metric_name}: No data available")
                        
                except Exception as e:
                    print(f"   ⚠️  Error getting {metric_name}: {e}")
                    metrics_results[metric_name] = {'error': str(e)}
            
            self.results['tests']['cloudwatch_metrics'] = metrics_results
            
        except Exception as e:
            print(f"   ❌ Error checking CloudWatch metrics: {e}")
            self.results['tests']['cloudwatch_metrics'] = {'error': str(e)}
        
        print()
    
    def _analyze_usage(self):
        """Analyze overall usage based on all checks."""
        
        print("🎯 Usage Analysis")
        
        # Connectivity analysis
        connectivity = self.results['tests'].get('connectivity', {})
        working_endpoints = connectivity.get('working_endpoints', 0)
        total_endpoints = connectivity.get('total_endpoints', 0)
        
        # Infrastructure references
        references = len(self.results.get('infrastructure_references', []))
        
        # CloudWatch metrics
        metrics = self.results['tests'].get('cloudwatch_metrics', {})
        has_traffic = any(
            metric.get('has_activity', False) 
            for metric in metrics.values() 
            if isinstance(metric, dict) and 'has_activity' in metric
        )
        
        # Determine usage status
        usage_indicators = []
        
        if working_endpoints > 0:
            usage_indicators.append(f"Responds to {working_endpoints}/{total_endpoints} endpoints")
        
        if references > 0:
            usage_indicators.append(f"Referenced in {references} infrastructure files")
        
        if has_traffic:
            usage_indicators.append("Has recent traffic (last 7 days)")
        
        # Overall assessment
        if working_endpoints > 0 or references > 0 or has_traffic:
            status = "IN USE"
            recommendation = "This distribution appears to be actively used"
        elif working_endpoints == 0 and references == 0:
            status = "POTENTIALLY UNUSED"
            recommendation = "This distribution may be safe to remove, but verify with your team"
        else:
            status = "UNCLEAR"
            recommendation = "Usage status is unclear, manual verification recommended"
        
        analysis = {
            'status': status,
            'recommendation': recommendation,
            'indicators': usage_indicators,
            'connectivity_score': f"{working_endpoints}/{total_endpoints}",
            'infrastructure_references': references,
            'has_recent_traffic': has_traffic
        }
        
        self.results['usage_analysis'] = analysis
        
        print(f"   Status: {status}")
        print(f"   Recommendation: {recommendation}")
        
        if usage_indicators:
            print("   Evidence:")
            for indicator in usage_indicators:
                print(f"     • {indicator}")
        else:
            print("   Evidence: No clear usage indicators found")
        
        print()
    
    def save_results(self) -> str:
        """Save results to file."""
        
        filename = f"distribution-usage-check-{int(datetime.now().timestamp())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    if len(sys.argv) != 2:
        print("Usage: python check-distribution-usage.py <distribution-domain>")
        print("Example: python check-distribution-usage.py d347w7yibz52wg.cloudfront.net")
        sys.exit(1)
    
    distribution_domain = sys.argv[1]
    
    print("🔍 CloudFront Distribution Usage Check")
    print(f"Checking: {distribution_domain}")
    print()
    
    checker = DistributionUsageChecker(distribution_domain)
    results = checker.check_usage()
    
    # Save results
    results_file = checker.save_results()
    print(f"📄 Results saved to: {results_file}")
    
    # Final summary
    analysis = results.get('usage_analysis', {})
    if analysis:
        print("\n" + "="*50)
        print("🎯 FINAL ASSESSMENT")
        print("="*50)
        print(f"Status: {analysis.get('status', 'Unknown')}")
        print(f"Recommendation: {analysis.get('recommendation', 'No recommendation')}")
        
        if analysis.get('status') == 'IN USE':
            return 0
        elif analysis.get('status') == 'POTENTIALLY UNUSED':
            return 2
        else:
            return 1
    else:
        print("\n❌ Could not complete usage analysis")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)