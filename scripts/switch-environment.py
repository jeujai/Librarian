#!/usr/bin/env python3
"""
Environment switching utility for Multimodal Librarian.

This script provides command-line utilities for switching between local development
and AWS production environments.
"""

import sys
import os
import argparse
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from multimodal_librarian.config.environment_switcher import (
        get_environment_switcher, 
        EnvironmentType,
        switch_to_local,
        switch_to_aws,
        get_current_environment_info,
        validate_current_environment,
        create_local_env_file,
        create_aws_env_file
    )
    from multimodal_librarian.config import (
        get_settings, 
        reload_settings, 
        validate_environment_configuration
    )
except ImportError as e:
    print(f"Error importing environment switcher: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def print_status(message: str, status: str = "INFO"):
    """Print a status message with formatting."""
    colors = {
        "INFO": "\033[94m",      # Blue
        "SUCCESS": "\033[92m",   # Green
        "WARNING": "\033[93m",   # Yellow
        "ERROR": "\033[91m",     # Red
        "RESET": "\033[0m"       # Reset
    }
    
    color = colors.get(status, colors["INFO"])
    reset = colors["RESET"]
    print(f"{color}[{status}]{reset} {message}")


def print_validation_results(validation: dict):
    """Print validation results in a formatted way."""
    if validation["valid"]:
        print_status("✓ Environment validation passed", "SUCCESS")
    else:
        print_status("✗ Environment validation failed", "ERROR")
    
    if validation.get("errors"):
        print_status("Errors:", "ERROR")
        for error in validation["errors"]:
            print(f"  - {error}")
    
    if validation.get("warnings"):
        print_status("Warnings:", "WARNING")
        for warning in validation["warnings"]:
            print(f"  - {warning}")
    
    if validation.get("missing_required"):
        print_status("Missing required variables:", "ERROR")
        for var in validation["missing_required"]:
            print(f"  - {var}")
    
    if validation.get("missing_optional"):
        print_status("Missing optional variables:", "WARNING")
        for var in validation["missing_optional"]:
            print(f"  - {var}")


def cmd_status(args):
    """Show current environment status."""
    print_status("Getting current environment status...", "INFO")
    
    try:
        switcher = get_environment_switcher()
        current_env = switcher.get_current_environment()
        env_info = switcher.get_environment_info()
        
        print(f"\nCurrent Environment: {env_info['name']} ({current_env.value})")
        print(f"Description: {env_info['description']}")
        print(f"Database Backend: {env_info['current_settings']['database_backend']}")
        print(f"Debug Mode: {env_info['current_settings']['debug']}")
        print(f"Log Level: {env_info['current_settings']['log_level']}")
        
        print(f"\nEnabled Features:")
        for feature in env_info['current_settings']['features_enabled']:
            print(f"  ✓ {feature}")
        
        # Validate current environment
        validation = switcher.validate_environment(current_env)
        print(f"\nEnvironment Validation:")
        print_validation_results(validation)
        
    except Exception as e:
        print_status(f"Error getting environment status: {e}", "ERROR")
        return 1
    
    return 0


def cmd_list(args):
    """List all available environments."""
    print_status("Available environments:", "INFO")
    
    try:
        switcher = get_environment_switcher()
        environments = switcher.list_environments()
        
        for env_name, env_info in environments["available_environments"].items():
            current_marker = " (current)" if env_info["is_current"] else ""
            print(f"\n{env_name.upper()}{current_marker}")
            print(f"  Name: {env_info['name']}")
            print(f"  Description: {env_info['description']}")
            print(f"  Database Type: {env_info['database_type']}")
            print(f"  Debug Mode: {env_info['debug']}")
            print(f"  Required Variables: {env_info['required_vars_count']}")
            print(f"  Optional Variables: {env_info['optional_vars_count']}")
        
    except Exception as e:
        print_status(f"Error listing environments: {e}", "ERROR")
        return 1
    
    return 0


def cmd_switch(args):
    """Switch to a different environment."""
    env_type = args.environment.lower()
    
    print_status(f"Switching to {env_type} environment...", "INFO")
    
    try:
        # Validate environment type
        try:
            target_env = EnvironmentType(env_type)
        except ValueError:
            valid_types = [e.value for e in EnvironmentType]
            print_status(f"Invalid environment type: {env_type}", "ERROR")
            print_status(f"Valid types: {', '.join(valid_types)}", "INFO")
            return 1
        
        switcher = get_environment_switcher()
        
        # Validate environment before switching (unless forced)
        if not args.force:
            validation = switcher.validate_environment(target_env)
            print(f"\nPre-switch validation:")
            print_validation_results(validation)
            
            if not validation["valid"]:
                print_status("Environment validation failed. Use --force to switch anyway.", "ERROR")
                return 1
        
        # Perform the switch
        result = switcher.switch_environment(target_env, force=args.force)
        
        if result["success"]:
            print_status(result["message"], "SUCCESS")
            
            if result.get("warnings"):
                print_status("Warnings:", "WARNING")
                for warning in result["warnings"]:
                    print(f"  - {warning}")
            
            # Show post-switch validation
            if result.get("validation"):
                print(f"\nPost-switch validation:")
                print_validation_results(result["validation"])
        else:
            print_status(result["message"], "ERROR")
            if result.get("errors"):
                for error in result["errors"]:
                    print_status(f"  - {error}", "ERROR")
            return 1
        
    except Exception as e:
        print_status(f"Error switching environment: {e}", "ERROR")
        return 1
    
    return 0


def cmd_validate(args):
    """Validate an environment."""
    env_type = args.environment.lower()
    
    print_status(f"Validating {env_type} environment...", "INFO")
    
    try:
        # Validate environment type
        try:
            target_env = EnvironmentType(env_type)
        except ValueError:
            valid_types = [e.value for e in EnvironmentType]
            print_status(f"Invalid environment type: {env_type}", "ERROR")
            print_status(f"Valid types: {', '.join(valid_types)}", "INFO")
            return 1
        
        switcher = get_environment_switcher()
        validation = switcher.validate_environment(target_env)
        
        print_validation_results(validation)
        
        return 0 if validation["valid"] else 1
        
    except Exception as e:
        print_status(f"Error validating environment: {e}", "ERROR")
        return 1


def cmd_create_env(args):
    """Create an environment file template."""
    env_type = args.environment.lower()
    output_path = args.output or f".env.{env_type}"
    
    print_status(f"Creating {env_type} environment file: {output_path}", "INFO")
    
    try:
        # Validate environment type
        try:
            target_env = EnvironmentType(env_type)
        except ValueError:
            valid_types = [e.value for e in EnvironmentType]
            print_status(f"Invalid environment type: {env_type}", "ERROR")
            print_status(f"Valid types: {', '.join(valid_types)}", "INFO")
            return 1
        
        switcher = get_environment_switcher()
        result = switcher.create_environment_file(target_env, output_path)
        
        if result["success"]:
            print_status(result["message"], "SUCCESS")
            print_status(f"Edit {output_path} and copy to .env.local to use", "INFO")
        else:
            print_status(result["message"], "ERROR")
            return 1
        
    except Exception as e:
        print_status(f"Error creating environment file: {e}", "ERROR")
        return 1
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Environment switching utility for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                    # Show current environment status
  %(prog)s list                     # List all available environments
  %(prog)s switch local             # Switch to local development
  %(prog)s switch aws --force       # Force switch to AWS production
  %(prog)s validate local           # Validate local environment
  %(prog)s create-env local         # Create local environment file template
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show current environment status")
    status_parser.set_defaults(func=cmd_status)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all available environments")
    list_parser.set_defaults(func=cmd_list)
    
    # Switch command
    switch_parser = subparsers.add_parser("switch", help="Switch to a different environment")
    switch_parser.add_argument("environment", choices=["local", "aws"], help="Target environment")
    switch_parser.add_argument("--force", action="store_true", help="Force switch even if validation fails")
    switch_parser.set_defaults(func=cmd_switch)
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate an environment")
    validate_parser.add_argument("environment", choices=["local", "aws"], help="Environment to validate")
    validate_parser.set_defaults(func=cmd_validate)
    
    # Create environment file command
    create_env_parser = subparsers.add_parser("create-env", help="Create environment file template")
    create_env_parser.add_argument("environment", choices=["local", "aws"], help="Environment type")
    create_env_parser.add_argument("--output", "-o", help="Output file path (default: .env.{environment})")
    create_env_parser.set_defaults(func=cmd_create_env)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())