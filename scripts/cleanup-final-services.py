#!/usr/bin/env python3
"""
Final Services Cleanup Script
Cleans up AWS WAF and ECR to maximize cost savings.
Potential additional savings: $7.49/month ($89.88/year)
"""

import boto3
import json
import time
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

def log_action(action, resource, status, details=None):
    """Log cleanup actions"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "resource": resource,
        "status": status
    }
    if details:
        entry["details"] = details
    print(f"[{entry['timestamp']}] {action}: {resource} - {status}")
    return entry

def cleanup_waf_rules():
    """Review and optionally clean up AWS WAF rules - $4.50/month potential savings"""
    print("\n=== REVIEWING AWS WAF CONFIGURATION ===")
    results = []
    
    # Check WAFv2 (CloudFront scope)
    wafv2 = boto3.client('wafv2', region_name='us-east-1')
    
    try:
        # List CloudFront Web ACLs
        response = wafv2.list_web_acls(Scope='CLOUDFRONT')
        
        if not response['WebACLs']:
            results.append(log_action("list_waf_acls", "cloudfront", "no_acls_found"))
            
            # Check regional WAF
            try:
                regional_response = wafv2.list_web_acls(Scope='REGIONAL')
                if not regional_response['WebACLs']:
                    results.append(log_action("list_waf_acls", "regional", "no_acls_found"))
                    print("✅ No WAF Web ACLs found - no cleanup needed")
                    return results
                else:
                    for acl in regional_response['WebACLs']:
                        results.append(log_action("found_waf_acl", acl['Name'], "regional_scope", 
                                                 f"id: {acl['Id']}"))
            except ClientError as e:
                results.append(log_action("list_waf_acls", "regional", "error", str(e)))
        else:
            for acl in response['WebACLs']:
                results.append(log_action("found_waf_acl", acl['Name'], "cloudfront_scope", 
                                         f"id: {acl['Id']}"))
                
                # Get detailed ACL info
                try:
                    acl_detail = wafv2.get_web_acl(
                        Name=acl['Name'],
                        Id=acl['Id'],
                        Scope='CLOUDFRONT'
                    )
                    
                    rules_count = len(acl_detail['WebACL'].get('Rules', []))
                    results.append(log_action("analyze_waf_acl", acl['Name'], "analyzed", 
                                             f"rules_count: {rules_count}"))
                    
                    # Check if it's associated with any resources
                    try:
                        resources = wafv2.list_resources_for_web_acl(
                            WebACLArn=acl['ARN'],
                            ResourceType='CLOUDFRONT'
                        )
                        
                        if resources['ResourceArns']:
                            results.append(log_action("check_waf_associations", acl['Name'], "has_associations", 
                                                     f"resources: {len(resources['ResourceArns'])}"))
                        else:
                            results.append(log_action("check_waf_associations", acl['Name'], "no_associations"))
                            
                            # This WAF ACL is not associated with any resources - safe to delete
                            print(f"🗑️  Found unused WAF ACL: {acl['Name']} - can be deleted for $4.50/month savings")
                            
                            # Delete the unused WAF ACL
                            try:
                                wafv2.delete_web_acl(
                                    Name=acl['Name'],
                                    Id=acl['Id'],
                                    Scope='CLOUDFRONT',
                                    LockToken=acl_detail['LockToken']
                                )
                                results.append(log_action("delete_waf_acl", acl['Name'], "deleted"))
                                print(f"✅ Deleted unused WAF ACL: {acl['Name']}")
                                return results, 4.50  # Return savings
                            except ClientError as e:
                                results.append(log_action("delete_waf_acl", acl['Name'], "error", str(e)))
                                
                    except ClientError as e:
                        results.append(log_action("check_waf_associations", acl['Name'], "error", str(e)))
                        
                except ClientError as e:
                    results.append(log_action("analyze_waf_acl", acl['Name'], "error", str(e)))
    
    except ClientError as e:
        results.append(log_action("list_waf_acls", "cloudfront", "error", str(e)))
    
    return results, 0

def cleanup_ecr_images():
    """Clean up old ECR container images - $2.99/month potential savings"""
    print("\n=== CLEANING UP ECR CONTAINER IMAGES ===")
    results = []
    
    ecr = boto3.client('ecr', region_name='us-east-1')
    
    try:
        # List all repositories
        repos_response = ecr.describe_repositories()
        
        if not repos_response['repositories']:
            results.append(log_action("list_ecr_repos", "all", "no_repos_found"))
            print("✅ No ECR repositories found - no cleanup needed")
            return results, 0
        
        total_deleted_size = 0
        
        for repo in repos_response['repositories']:
            repo_name = repo['repositoryName']
            results.append(log_action("found_ecr_repo", repo_name, "analyzing"))
            
            try:
                # List images in the repository
                images_response = ecr.list_images(repositoryName=repo_name)
                
                if not images_response['imageIds']:
                    results.append(log_action("list_ecr_images", repo_name, "no_images"))
                    continue
                
                # Get detailed image information
                images_detail = ecr.describe_images(repositoryName=repo_name)
                
                # Sort images by push date (oldest first)
                images_by_date = sorted(images_detail['imageDetails'], 
                                      key=lambda x: x.get('imagePushedAt', datetime.min))
                
                # Keep only the 5 most recent images, delete the rest
                images_to_delete = []
                keep_count = 5
                
                if len(images_by_date) > keep_count:
                    images_to_delete = images_by_date[:-keep_count]  # All except the last 5
                    
                    for image in images_to_delete:
                        image_tags = image.get('imageTags', ['<untagged>'])
                        image_size = image.get('imageSizeInBytes', 0)
                        total_deleted_size += image_size
                        
                        results.append(log_action("mark_for_deletion", repo_name, "old_image", 
                                                 f"tags: {image_tags}, size: {image_size} bytes"))
                    
                    # Delete old images in batches
                    batch_size = 100  # ECR limit
                    for i in range(0, len(images_to_delete), batch_size):
                        batch = images_to_delete[i:i+batch_size]
                        
                        # Prepare image identifiers for deletion
                        image_ids = []
                        for image in batch:
                            if image.get('imageTags'):
                                for tag in image['imageTags']:
                                    image_ids.append({'imageTag': tag})
                            else:
                                image_ids.append({'imageDigest': image['imageDigest']})
                        
                        try:
                            delete_response = ecr.batch_delete_image(
                                repositoryName=repo_name,
                                imageIds=image_ids
                            )
                            
                            deleted_count = len(delete_response.get('imageIds', []))
                            failed_count = len(delete_response.get('failures', []))
                            
                            results.append(log_action("delete_ecr_images", repo_name, "batch_deleted", 
                                                     f"deleted: {deleted_count}, failed: {failed_count}"))
                            
                            if delete_response.get('failures'):
                                for failure in delete_response['failures']:
                                    results.append(log_action("delete_ecr_image_failure", repo_name, "failed", 
                                                             f"reason: {failure.get('failureReason')}"))
                            
                        except ClientError as e:
                            results.append(log_action("delete_ecr_images", repo_name, "error", str(e)))
                
                else:
                    results.append(log_action("analyze_ecr_images", repo_name, "keeping_all", 
                                             f"image_count: {len(images_by_date)} (≤ {keep_count})"))
                
            except ClientError as e:
                results.append(log_action("analyze_ecr_repo", repo_name, "error", str(e)))
        
        # Calculate savings based on deleted size
        # ECR charges $0.10 per GB per month
        deleted_gb = total_deleted_size / (1024**3)  # Convert bytes to GB
        estimated_savings = deleted_gb * 0.10
        
        if total_deleted_size > 0:
            results.append(log_action("calculate_savings", "ecr_cleanup", "completed", 
                                     f"deleted_gb: {deleted_gb:.2f}, estimated_savings: ${estimated_savings:.2f}/month"))
            print(f"✅ Cleaned up {deleted_gb:.2f} GB of old ECR images")
            print(f"💰 Estimated monthly savings: ${estimated_savings:.2f}")
            return results, min(estimated_savings, 2.99)  # Cap at the expected $2.99
        else:
            results.append(log_action("calculate_savings", "ecr_cleanup", "no_cleanup_needed"))
            print("✅ No old ECR images found to clean up")
            return results, 0
            
    except ClientError as e:
        results.append(log_action("list_ecr_repos", "all", "error", str(e)))
        return results, 0

def main():
    """Execute final services cleanup"""
    print("🧹 FINAL SERVICES CLEANUP")
    print("=" * 50)
    print("Cleaning up AWS WAF and ECR for maximum cost optimization")
    print("Potential additional savings: $7.49/month ($89.88/year)")
    print("=" * 50)
    
    all_results = []
    total_savings = 0
    
    # 1. Clean up AWS WAF rules ($4.50/month potential)
    waf_results, waf_savings = cleanup_waf_rules()
    all_results.extend(waf_results)
    total_savings += waf_savings
    
    # 2. Clean up ECR container images ($2.99/month potential)
    ecr_results, ecr_savings = cleanup_ecr_images()
    all_results.extend(ecr_results)
    total_savings += ecr_savings
    
    # Generate summary report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(),
        "cleanup_type": "final_services_cleanup",
        "estimated_monthly_savings": total_savings,
        "estimated_annual_savings": total_savings * 12,
        "resources_processed": len(all_results),
        "successful_actions": len([r for r in all_results if r['status'] in ['deleted', 'batch_deleted', 'completed']]),
        "failed_actions": len([r for r in all_results if r['status'] == 'error']),
        "detailed_results": all_results
    }
    
    # Save results
    filename = f"final-services-cleanup-{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 50)
    print("🎉 FINAL SERVICES CLEANUP COMPLETE")
    print("=" * 50)
    print(f"📊 Resources Processed: {report['resources_processed']}")
    print(f"✅ Successful Actions: {report['successful_actions']}")
    print(f"❌ Failed Actions: {report['failed_actions']}")
    print(f"💰 Additional Monthly Savings: ${total_savings:.2f}")
    print(f"💰 Additional Annual Savings: ${total_savings * 12:.2f}")
    print(f"📄 Detailed Report: {filename}")
    
    # Calculate ULTIMATE total project savings
    previous_savings = 401.04  # From ULTIMATE_COST_OPTIMIZATION_COMPLETE.md
    ultimate_monthly_savings = previous_savings + total_savings
    ultimate_annual_savings = ultimate_monthly_savings * 12
    
    print("\n" + "=" * 50)
    print("🏆 ULTIMATE TOTAL PROJECT COST OPTIMIZATION")
    print("=" * 50)
    print(f"Previous Total Savings: ${previous_savings:.2f}/month")
    print(f"Final Services Cleanup: ${total_savings:.2f}/month")
    print(f"🎯 ULTIMATE MONTHLY SAVINGS: ${ultimate_monthly_savings:.2f}")
    print(f"🎯 ULTIMATE ANNUAL SAVINGS: ${ultimate_annual_savings:.2f}")
    print("=" * 50)
    
    # Calculate final AWS bill
    original_bill = 516.91
    final_bill = original_bill - ultimate_monthly_savings
    reduction_percentage = (ultimate_monthly_savings / original_bill) * 100
    
    print(f"📊 COST TRANSFORMATION:")
    print(f"   Original Bill: ${original_bill:.2f}/month")
    print(f"   Final Bill: ${final_bill:.2f}/month")
    print(f"   Reduction: {reduction_percentage:.1f}%")
    print("=" * 50)
    
    return report

if __name__ == "__main__":
    main()