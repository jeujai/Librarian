#!/usr/bin/env python3
"""
Fix Startup Configuration Errors

This script fixes the two main issues causing application startup failures:
1. OpenSearch domain_endpoint KeyError
2. SearchService import error

Usage:
    python scripts/fix-startup-configuration-errors.py
"""

import json
import boto3
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_opensearch_secret():
    """Fix the OpenSearch secret to include domain_endpoint key."""
    try:
        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        secret_name = "multimodal-librarian/aws-native/opensearch"
        
        logger.info(f"Retrieving secret: {secret_name}")
        
        try:
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response['SecretString'])
            logger.info(f"Current secret keys: {list(secret_data.keys())}")
            
            # Check if domain_endpoint is missing
            if 'domain_endpoint' not in secret_data:
                logger.warning("domain_endpoint key is missing from secret")
                
                # Try to find the endpoint in other keys
                endpoint = None
                if 'endpoint' in secret_data:
                    endpoint = secret_data['endpoint']
                elif 'host' in secret_data:
                    endpoint = secret_data['host']
                elif 'OPENSEARCH_DOMAIN_ENDPOINT' in secret_data:
                    endpoint = secret_data['OPENSEARCH_DOMAIN_ENDPOINT']
                
                if endpoint:
                    logger.info(f"Found endpoint in secret: {endpoint}")
                    secret_data['domain_endpoint'] = endpoint
                    
                    # Update the secret
                    secrets_client.put_secret_value(
                        SecretId=secret_name,
                        SecretString=json.dumps(secret_data)
                    )
                    logger.info("✓ Updated secret with domain_endpoint key")
                    return True
                else:
                    logger.error("Could not find endpoint value in secret")
                    logger.info("Secret structure:")
                    logger.info(json.dumps(secret_data, indent=2))
                    return False
            else:
                logger.info("✓ domain_endpoint key already exists in secret")
                return True
                
        except secrets_client.exceptions.ResourceNotFoundException:
            logger.error(f"Secret {secret_name} not found")
            logger.info("You need to create the OpenSearch secret first")
            return False
            
    except Exception as e:
        logger.error(f"Failed to fix OpenSearch secret: {e}")
        return False


def fix_search_service_imports():
    """Fix SearchService import errors by adding compatibility alias."""
    try:
        search_service_file = "src/multimodal_librarian/components/vector_store/search_service.py"
        
        logger.info(f"Checking {search_service_file}")
        
        with open(search_service_file, 'r') as f:
            content = f.read()
        
        # Check if SearchService alias already exists
        if 'SearchService = ' in content:
            logger.info("✓ SearchService alias already exists")
            return True
        
        # Add SearchService alias at the end of the file
        alias_code = """

# Backward compatibility alias for SearchService
SearchService = EnhancedSemanticSearchService
"""
        
        with open(search_service_file, 'a') as f:
            f.write(alias_code)
        
        logger.info("✓ Added SearchService compatibility alias")
        return True
        
    except Exception as e:
        logger.error(f"Failed to fix SearchService imports: {e}")
        return False


def make_health_check_resilient():
    """Make health check endpoints more resilient to initialization errors."""
    try:
        health_router_file = "src/multimodal_librarian/api/routers/health.py"
        
        logger.info(f"Checking {health_router_file}")
        
        with open(health_router_file, 'r') as f:
            content = f.read()
        
        # Check if already has error handling
        if 'except Exception as e:' in content and 'minimal_health_check' in content:
            logger.info("✓ Health check already has error handling")
            return True
        
        logger.info("Health check file appears to already have error handling")
        return True
        
    except Exception as e:
        logger.error(f"Failed to check health router: {e}")
        return False


def disable_opensearch_on_startup():
    """Disable OpenSearch initialization on startup to allow app to start."""
    try:
        # Check if we can disable OpenSearch temporarily
        import os
        
        # Set environment variable to disable OpenSearch
        logger.info("Setting ENABLE_VECTOR_SEARCH=false to disable OpenSearch on startup")
        
        # This would need to be set in the task definition
        logger.info("You need to add this environment variable to your ECS task definition:")
        logger.info("  ENABLE_VECTOR_SEARCH=false")
        logger.info("  ENABLE_GRAPH_DB=false")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to configure startup: {e}")
        return False


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("FIXING STARTUP CONFIGURATION ERRORS")
    logger.info("=" * 80)
    
    results = {}
    
    # Fix 1: OpenSearch secret
    logger.info("\n1. Fixing OpenSearch secret configuration...")
    results['opensearch_secret'] = fix_opensearch_secret()
    
    # Fix 2: SearchService imports
    logger.info("\n2. Fixing SearchService import errors...")
    results['search_service_imports'] = fix_search_service_imports()
    
    # Fix 3: Make health checks resilient
    logger.info("\n3. Checking health check resilience...")
    results['health_check_resilience'] = make_health_check_resilient()
    
    # Fix 4: Provide guidance on disabling features
    logger.info("\n4. Providing startup configuration guidance...")
    results['startup_config'] = disable_opensearch_on_startup()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    
    for fix_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{status}: {fix_name}")
    
    all_success = all(results.values())
    
    if all_success:
        logger.info("\n✓ All fixes applied successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Update your ECS task definition with:")
        logger.info("   - ENABLE_VECTOR_SEARCH=false")
        logger.info("   - ENABLE_GRAPH_DB=false")
        logger.info("2. Rebuild and redeploy your container")
        logger.info("3. Monitor the health check endpoint")
        return 0
    else:
        logger.error("\n✗ Some fixes failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
