#!/usr/bin/env python3
"""
List CloudFront Distributions

This script lists all CloudFront distributions in your AWS account with detailed information.
"""

import boto3
import json
import sys
from datetime import datetime
from typing import Dict, List, Any

class CloudFrontDistributionLister:
    """Lists and displays CloudFront distributions."""
    
    def __init__(self):
        self.cloudfront_client = boto3.client('cloudfront', region_name='us-east-1')
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'list_cloudfront_distributions',
            'distributions': [],
            'summary': {}
        }
    
    def list_distributions(self) -> Dict[str, Any]:
        """List all CloudFront distributions."""
        
        print("🌐 CloudFront Distributions Inventory")
        print("=" * 40)
        print()
        
        try:
            # Get list of distributions
            response = self.cloudfront_client.list_distributions()
            
            if 'DistributionList' not in response or 'Items' not in response['DistributionList']:
                print("📭 No CloudFront distributions found in your account.")
                self.results['summary'] = {
                    'total_distributions': 0,
                    'enabled_distributions': 0,
                    'disabled_distributions': 0
                }
                return self.results
            
            distributions = response['DistributionList']['Items']
            
            print(f"📊 Found {len(distributions)} CloudFront distribution(s)")
            print()
            
            enabled_count = 0
            disabled_count = 0
            
            for i, dist in enumerate(distributions, 1):
                dist_info = self._extract_distribution_info(dist)
                self.results['distributions'].append(dist_info)
                
                if dist_info['enabled']:
                    enabled_count += 1
                else:
                    disabled_count += 1
                
                self._print_distribution_info(i, dist_info)
                print()
            
            # Summary
            self.results['summary'] = {
                'total_distributions': len(distributions),
                'enabled_distributions': enabled_count,
                'disabled_distributions': disabled_count
            }
            
            print("📈 Summary:")
            print(f"   Total Distributions: {len(distributions)}")
            print(f"   Enabled: {enabled_count}")
            print(f"   Disabled: {disabled_count}")
            
        except Exception as e:
            print(f"❌ Error listing distributions: {e}")
            self.results['error'] = str(e)
        
        return self.results
    
    def _extract_distribution_info(self, dist: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key information from a distribution."""
        
        # Get origins
        origins = []
        if 'Origins' in dist and 'Items' in dist['Origins']:
            for origin in dist['Origins']['Items']:
                origins.append({
                    'id': origin.get('Id', 'Unknown'),
                    'domain_name': origin.get('DomainName', 'Unknown'),
                    'origin_path': origin.get('OriginPath', ''),
                })
        
        # Get aliases (custom domains)
        aliases = []
        if 'Aliases' in dist and 'Items' in dist['Aliases']:
            aliases = dist['Aliases']['Items']
        
        # Get SSL certificate info
        ssl_info = {}
        if 'ViewerCertificate' in dist:
            cert = dist['ViewerCertificate']
            if cert.get('CloudFrontDefaultCertificate'):
                ssl_info = {
                    'type': 'CloudFront Default',
                    'certificate_arn': None
                }
            elif cert.get('ACMCertificateArn'):
                ssl_info = {
                    'type': 'ACM Certificate',
                    'certificate_arn': cert.get('ACMCertificateArn'),
                    'ssl_support_method': cert.get('SSLSupportMethod', 'Unknown'),
                    'minimum_protocol_version': cert.get('MinimumProtocolVersion', 'Unknown')
                }
            elif cert.get('IAMCertificateId'):
                ssl_info = {
                    'type': 'IAM Certificate',
                    'certificate_id': cert.get('IAMCertificateId')
                }
        
        return {
            'id': dist.get('Id', 'Unknown'),
            'domain_name': dist.get('DomainName', 'Unknown'),
            'status': dist.get('Status', 'Unknown'),
            'enabled': dist.get('Enabled', False),
            'comment': dist.get('Comment', ''),
            'price_class': dist.get('PriceClass', 'Unknown'),
            'last_modified': str(dist.get('LastModifiedTime', 'Unknown')),
            'origins': origins,
            'aliases': aliases,
            'ssl_info': ssl_info,
            'default_root_object': dist.get('DefaultRootObject', ''),
            'http_version': dist.get('HttpVersion', 'Unknown'),
            'ipv6_enabled': dist.get('IsIPV6Enabled', False)
        }
    
    def _print_distribution_info(self, index: int, dist_info: Dict[str, Any]):
        """Print formatted distribution information."""
        
        status_emoji = "✅" if dist_info['enabled'] and dist_info['status'] == 'Deployed' else "🔄" if dist_info['status'] == 'InProgress' else "⚠️"
        
        print(f"{status_emoji} Distribution #{index}")
        print(f"   ID: {dist_info['id']}")
        print(f"   Domain: {dist_info['domain_name']}")
        print(f"   Status: {dist_info['status']}")
        print(f"   Enabled: {'Yes' if dist_info['enabled'] else 'No'}")
        
        if dist_info['comment']:
            print(f"   Comment: {dist_info['comment']}")
        
        print(f"   Price Class: {dist_info['price_class']}")
        print(f"   Last Modified: {dist_info['last_modified']}")
        
        # Origins
        if dist_info['origins']:
            print(f"   Origins:")
            for origin in dist_info['origins']:
                print(f"     - {origin['domain_name']} (ID: {origin['id']})")
                if origin['origin_path']:
                    print(f"       Path: {origin['origin_path']}")
        
        # Aliases (Custom Domains)
        if dist_info['aliases']:
            print(f"   Custom Domains:")
            for alias in dist_info['aliases']:
                print(f"     - {alias}")
        
        # SSL Certificate
        if dist_info['ssl_info']:
            ssl = dist_info['ssl_info']
            print(f"   SSL Certificate: {ssl['type']}")
            if ssl.get('certificate_arn'):
                print(f"     ARN: {ssl['certificate_arn']}")
            if ssl.get('ssl_support_method'):
                print(f"     Support Method: {ssl['ssl_support_method']}")
            if ssl.get('minimum_protocol_version'):
                print(f"     Min Protocol: {ssl['minimum_protocol_version']}")
        
        # Additional Info
        if dist_info['default_root_object']:
            print(f"   Default Root Object: {dist_info['default_root_object']}")
        
        print(f"   HTTP Version: {dist_info['http_version']}")
        print(f"   IPv6 Enabled: {'Yes' if dist_info['ipv6_enabled'] else 'No'}")
    
    def save_results(self) -> str:
        """Save results to file."""
        
        filename = f"cloudfront-distributions-list-{int(datetime.now().timestamp())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🌐 CloudFront Distributions Inventory")
    print("Listing all CloudFront distributions in your AWS account")
    print()
    
    lister = CloudFrontDistributionLister()
    results = lister.list_distributions()
    
    # Save results
    results_file = lister.save_results()
    print(f"\n📄 Results saved to: {results_file}")
    
    # Final summary
    if results.get('summary'):
        summary = results['summary']
        print(f"\n🎯 Final Summary:")
        print(f"   Total CloudFront Distributions: {summary['total_distributions']}")
        if summary['total_distributions'] > 0:
            print(f"   Active (Enabled): {summary['enabled_distributions']}")
            print(f"   Inactive (Disabled): {summary['disabled_distributions']}")
            
            # Cost estimate
            if summary['enabled_distributions'] > 0:
                print(f"\n💰 Estimated Monthly Cost:")
                print(f"   Base cost per distribution: ~$0.60/month")
                print(f"   Estimated total: ~${summary['enabled_distributions'] * 0.60:.2f}/month")
                print(f"   (Plus data transfer and request charges)")
        
        return 0 if summary['total_distributions'] >= 0 else 1
    else:
        print("\n❌ Failed to retrieve distribution information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)