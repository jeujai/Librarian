#!/usr/bin/env python3
"""
Check ECR repository and image status.
"""

import boto3
import json
import sys
from datetime import datetime

def check_ecr_repository_status():
    """Check ECR repository and image status."""
    
    try:
        # Initialize clients
        ecr_client = boto3.client('ecr', region_name='us-east-1')
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'repository_status': {},
            'image_status': {},
            'recommendations': []
        }
        
        print("🔍 CHECKING ECR REPOSITORY STATUS")
        print("=" * 40)
        
        # 1. Get current task definition to see what image is being used
        print("\n1. CURRENT TASK DEFINITION IMAGE:")
        print("-" * 35)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_details['services'][0]
        task_def_arn = service['taskDefinition']
        
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        container_def = task_def['containerDefinitions'][0]
        image_uri = container_def['image']
        
        print(f"📋 Current image: {image_uri}")
        
        # Parse image URI
        if '.dkr.ecr.' in image_uri:
            # ECR image
            parts = image_uri.split('/')
            if len(parts) >= 2:
                registry_part = parts[0]  # account.dkr.ecr.region.amazonaws.com
                repo_and_tag = '/'.join(parts[1:])  # repo:tag
                
                if ':' in repo_and_tag:
                    repository_name = repo_and_tag.split(':')[0]
                    tag = repo_and_tag.split(':')[1]
                else:
                    repository_name = repo_and_tag
                    tag = 'latest'
                
                print(f"   Repository: {repository_name}")
                print(f"   Tag: {tag}")
                
                result['image_status'] = {
                    'image_uri': image_uri,
                    'repository_name': repository_name,
                    'tag': tag,
                    'is_ecr': True
                }
            else:
                print("❌ Cannot parse ECR image URI")
                result['recommendations'].append("Cannot parse ECR image URI")
                return result
        else:
            print("⚠️  Not an ECR image")
            result['image_status'] = {
                'image_uri': image_uri,
                'is_ecr': False
            }
            result['recommendations'].append("Image is not from ECR")
            return result
        
        # 2. Check if ECR repository exists
        print("\n2. ECR REPOSITORY CHECK:")
        print("-" * 26)
        
        try:
            repo_response = ecr_client.describe_repositories(
                repositoryNames=[repository_name]
            )
            
            if repo_response['repositories']:
                repo = repo_response['repositories'][0]
                print(f"✅ Repository exists: {repository_name}")
                print(f"   URI: {repo['repositoryUri']}")
                print(f"   Created: {repo['createdAt']}")
                
                result['repository_status'] = {
                    'exists': True,
                    'name': repository_name,
                    'uri': repo['repositoryUri'],
                    'created_at': repo['createdAt'].isoformat()
                }
            else:
                print(f"❌ Repository not found: {repository_name}")
                result['recommendations'].append(f"ECR repository {repository_name} does not exist")
                return result
        
        except ecr_client.exceptions.RepositoryNotFoundException:
            print(f"❌ Repository not found: {repository_name}")
            result['recommendations'].append(f"ECR repository {repository_name} does not exist")
            return result
        except Exception as e:
            print(f"❌ Error checking repository: {e}")
            result['recommendations'].append(f"Error checking repository: {e}")
            return result
        
        # 3. Check if image/tag exists
        print("\n3. IMAGE TAG CHECK:")
        print("-" * 20)
        
        try:
            images_response = ecr_client.describe_images(
                repositoryName=repository_name,
                imageIds=[{'imageTag': tag}]
            )
            
            if images_response['imageDetails']:
                image = images_response['imageDetails'][0]
                print(f"✅ Image tag exists: {tag}")
                print(f"   Pushed: {image['imagePushedAt']}")
                print(f"   Size: {image['imageSizeInBytes'] / 1024 / 1024:.1f} MB")
                
                # Check if image has manifest
                if 'imageManifest' in image:
                    print(f"   ✅ Has manifest")
                
                result['image_status'].update({
                    'tag_exists': True,
                    'pushed_at': image['imagePushedAt'].isoformat(),
                    'size_mb': image['imageSizeInBytes'] / 1024 / 1024
                })
            else:
                print(f"❌ Image tag not found: {tag}")
                result['recommendations'].append(f"Image tag {tag} does not exist in repository")
                
                # List available tags
                print(f"\n   📋 Available tags:")
                all_images = ecr_client.describe_images(repositoryName=repository_name)
                
                available_tags = []
                for img in all_images['imageDetails']:
                    if 'imageTags' in img:
                        for img_tag in img['imageTags']:
                            available_tags.append(img_tag)
                            print(f"      - {img_tag}")
                
                if available_tags:
                    result['recommendations'].append(f"Available tags: {', '.join(available_tags[:5])}")
                else:
                    result['recommendations'].append("No tags found in repository")
                
                return result
        
        except Exception as e:
            print(f"❌ Error checking image: {e}")
            result['recommendations'].append(f"Error checking image: {e}")
            return result
        
        # 4. Test ECR authentication
        print("\n4. ECR AUTHENTICATION TEST:")
        print("-" * 30)
        
        try:
            auth_response = ecr_client.get_authorization_token()
            
            if auth_response['authorizationData']:
                auth_data = auth_response['authorizationData'][0]
                proxy_endpoint = auth_data['proxyEndpoint']
                expires_at = auth_data['expiresAt']
                
                print(f"✅ ECR authentication successful")
                print(f"   Endpoint: {proxy_endpoint}")
                print(f"   Expires: {expires_at}")
                
                result['repository_status']['auth_success'] = True
            else:
                print(f"❌ ECR authentication failed")
                result['recommendations'].append("ECR authentication failed")
        
        except Exception as e:
            print(f"❌ ECR authentication error: {e}")
            result['recommendations'].append(f"ECR authentication error: {e}")
        
        # 5. Summary
        print("\n5. SUMMARY:")
        print("-" * 12)
        
        if result['repository_status'].get('exists') and result['image_status'].get('tag_exists'):
            print("✅ ECR repository and image are accessible")
            print("⚠️  ECR connectivity issue is likely network-related")
            result['recommendations'].append("ECR repository and image exist - issue is network connectivity")
        else:
            print("❌ ECR repository or image issues found")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during ECR check: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = check_ecr_repository_status()
    
    # Save result to file
    result_file = f"ecr-repository-status-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 ECR status check saved to: {result_file}")
    
    if result.get('recommendations'):
        print(f"\n🔧 RECOMMENDATIONS:")
        for i, rec in enumerate(result['recommendations'], 1):
            print(f"   {i}. {rec}")
        sys.exit(1)
    else:
        print("\n✅ ECR repository and image are healthy")
        sys.exit(0)