#!/usr/bin/env python3
"""
Setup AI API Keys in AWS Secrets Manager

This script helps configure AI provider API keys in AWS Secrets Manager
for the multimodal-librarian application.
"""

import json
import boto3
import sys
import os
from typing import Dict, Any, Optional

def get_secrets_client():
    """Get AWS Secrets Manager client."""
    return boto3.client('secretsmanager', region_name='us-east-1')

def create_or_update_secret(secret_name: str, secret_value: Dict[str, Any]) -> bool:
    """Create or update a secret in AWS Secrets Manager."""
    client = get_secrets_client()
    
    try:
        # Try to update existing secret
        client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(secret_value)
        )
        print(f"✅ Updated secret: {secret_name}")
        return True
        
    except client.exceptions.ResourceNotFoundException:
        # Secret doesn't exist, create it
        try:
            client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(secret_value),
                Description=f"AI API keys for {secret_name}"
            )
            print(f"✅ Created secret: {secret_name}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create secret {secret_name}: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to update secret {secret_name}: {e}")
        return False

def get_secret_value(secret_name: str) -> Optional[Dict[str, Any]]:
    """Get secret value from AWS Secrets Manager."""
    client = get_secrets_client()
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except client.exceptions.ResourceNotFoundException:
        return None
    except Exception as e:
        print(f"❌ Failed to get secret {secret_name}: {e}")
        return None

def setup_ai_api_keys():
    """Setup AI API keys in AWS Secrets Manager."""
    print("🤖 Setting up AI API Keys for Multimodal Librarian")
    print("=" * 60)
    
    # Define the secret name
    secret_name = "multimodal-lib-prod/ai-api-keys"
    
    # Get existing secret if it exists
    existing_secret = get_secret_value(secret_name)
    if existing_secret:
        print(f"📋 Found existing secret: {secret_name}")
        print("Current keys:", list(existing_secret.keys()))
    else:
        print(f"🆕 Creating new secret: {secret_name}")
        existing_secret = {}
    
    # Collect API keys
    api_keys = existing_secret.copy()
    
    print("\n🔑 Enter API keys (press Enter to skip/keep existing):")
    print("Note: Keys will be stored securely in AWS Secrets Manager")
    
    # Gemini API Key
    current_gemini = api_keys.get('GEMINI_API_KEY', '')
    gemini_display = f"(current: {current_gemini[:10]}...)" if current_gemini else "(not set)"
    gemini_key = input(f"Gemini API Key {gemini_display}: ").strip()
    if gemini_key:
        api_keys['GEMINI_API_KEY'] = gemini_key
        print("✅ Gemini API key updated")
    elif not current_gemini:
        print("⚠️  Gemini API key not set")
    
    # OpenAI API Key
    current_openai = api_keys.get('OPENAI_API_KEY', '')
    openai_display = f"(current: {current_openai[:10]}...)" if current_openai else "(not set)"
    openai_key = input(f"OpenAI API Key {openai_display}: ").strip()
    if openai_key:
        api_keys['OPENAI_API_KEY'] = openai_key
        print("✅ OpenAI API key updated")
    elif not current_openai:
        print("⚠️  OpenAI API key not set")
    
    # Anthropic API Key
    current_anthropic = api_keys.get('ANTHROPIC_API_KEY', '')
    anthropic_display = f"(current: {current_anthropic[:10]}...)" if current_anthropic else "(not set)"
    anthropic_key = input(f"Anthropic API Key {anthropic_display}: ").strip()
    if anthropic_key:
        api_keys['ANTHROPIC_API_KEY'] = anthropic_key
        print("✅ Anthropic API key updated")
    elif not current_anthropic:
        print("⚠️  Anthropic API key not set")
    
    # Check if we have at least one API key
    if not any(api_keys.get(key) for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']):
        print("\n❌ No API keys provided. At least one AI provider is required.")
        return False
    
    # Confirm before saving
    print(f"\n📝 Summary of API keys to save:")
    for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
        if api_keys.get(key):
            print(f"  ✅ {key}: {api_keys[key][:10]}...")
        else:
            print(f"  ❌ {key}: Not set")
    
    confirm = input(f"\n💾 Save these keys to {secret_name}? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelled")
        return False
    
    # Save to AWS Secrets Manager
    success = create_or_update_secret(secret_name, api_keys)
    
    if success:
        print(f"\n🎉 AI API keys configured successfully!")
        print(f"Secret name: {secret_name}")
        print("\n📋 Next steps:")
        print("1. Update your ECS task definition to include these environment variables:")
        print("   - GEMINI_API_KEY")
        print("   - OPENAI_API_KEY") 
        print("   - ANTHROPIC_API_KEY")
        print("2. Restart your ECS service to pick up the new configuration")
        print("3. Test the AI chat functionality")
        
        return True
    else:
        print("\n❌ Failed to save API keys")
        return False

def test_ai_keys():
    """Test AI API keys by retrieving them from Secrets Manager."""
    print("🧪 Testing AI API Keys")
    print("=" * 30)
    
    secret_name = "multimodal-lib-prod/ai-api-keys"
    secret_value = get_secret_value(secret_name)
    
    if not secret_value:
        print(f"❌ Secret not found: {secret_name}")
        return False
    
    print(f"✅ Secret found: {secret_name}")
    
    for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
        if secret_value.get(key):
            print(f"  ✅ {key}: {secret_value[key][:10]}...")
        else:
            print(f"  ❌ {key}: Not set")
    
    return True

def generate_task_definition_env_vars():
    """Generate environment variable configuration for ECS task definition."""
    print("📋 Generating ECS Task Definition Environment Variables")
    print("=" * 60)
    
    secret_name = "multimodal-lib-prod/ai-api-keys"
    
    env_vars = [
        {
            "name": "GEMINI_API_KEY",
            "valueFrom": f"arn:aws:secretsmanager:us-east-1:591222106065:secret:{secret_name}:GEMINI_API_KEY::"
        },
        {
            "name": "OPENAI_API_KEY", 
            "valueFrom": f"arn:aws:secretsmanager:us-east-1:591222106065:secret:{secret_name}:OPENAI_API_KEY::"
        },
        {
            "name": "ANTHROPIC_API_KEY",
            "valueFrom": f"arn:aws:secretsmanager:us-east-1:591222106065:secret:{secret_name}:ANTHROPIC_API_KEY::"
        }
    ]
    
    print("Add these to your ECS task definition 'secrets' section:")
    print(json.dumps(env_vars, indent=2))
    
    return env_vars

def main():
    """Main function."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "test":
            test_ai_keys()
        elif command == "env":
            generate_task_definition_env_vars()
        elif command == "setup":
            setup_ai_api_keys()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python setup-ai-api-keys.py [setup|test|env]")
            sys.exit(1)
    else:
        setup_ai_api_keys()

if __name__ == "__main__":
    main()