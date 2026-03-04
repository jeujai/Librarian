"""
Command-line interface for the production deployment validation framework.

This module provides a CLI tool for running deployment validations and
generating reports in various formats. Supports configuration management
and environment profiles.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .models import DeploymentConfig, ValidationReport, ValidationResult
from .checklist_validator import ChecklistValidator
from .config_manager import ConfigurationManager, ConfigurationError
from .utils import ValidationReportFormatter


class ProgressIndicator:
    """
    Simple progress indicator for CLI operations.
    """
    
    def __init__(self, total_steps: int, interactive: bool = False):
        """
        Initialize progress indicator.
        
        Args:
            total_steps: Total number of steps
            interactive: Whether to show interactive progress
        """
        self.total_steps = total_steps
        self.current_step = 0
        self.interactive = interactive
        self.start_time = time.time()
    
    def update(self, step_name: str):
        """
        Update progress with current step.
        
        Args:
            step_name: Name of current step
        """
        self.current_step += 1
        
        if self.interactive:
            # Show progress bar and step name
            progress = self.current_step / self.total_steps
            bar_length = 40
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            elapsed = time.time() - self.start_time
            
            print(f'\r[{bar}] {self.current_step}/{self.total_steps} - {step_name} ({elapsed:.1f}s)', end='', flush=True)
            
            if self.current_step == self.total_steps:
                print()  # New line when complete
        else:
            # Simple step logging
            print(f"[{self.current_step}/{self.total_steps}] {step_name}")
    
    def finish(self):
        """Mark progress as complete."""
        if self.interactive and self.current_step < self.total_steps:
            print()  # Ensure we end on a new line


def interactive_config_builder() -> Dict[str, Any]:
    """
    Interactive configuration builder for deployment validation.
    
    Returns:
        Configuration dictionary
    """
    print("🚀 Production Deployment Validation Setup")
    print("=" * 50)
    print("Please provide the following deployment configuration:")
    print()
    
    config = {}
    
    # Required fields
    config['task_definition_arn'] = input("ECS Task Definition ARN: ").strip()
    config['iam_role_arn'] = input("IAM Role ARN: ").strip()
    config['load_balancer_arn'] = input("Load Balancer ARN: ").strip()
    
    # Optional fields
    config['target_environment'] = input("Target Environment [production]: ").strip() or "production"
    config['region'] = input("AWS Region [us-east-1]: ").strip() or "us-east-1"
    
    ssl_cert = input("SSL Certificate ARN (optional): ").strip()
    if ssl_cert:
        config['ssl_certificate_arn'] = ssl_cert
    
    print()
    print("Configuration Summary:")
    print("-" * 30)
    for key, value in config.items():
        if value:
            print(f"{key}: {value}")
    
    print()
    confirm = input("Proceed with validation? [Y/n]: ").strip().lower()
    if confirm in ['n', 'no']:
        print("Validation cancelled.")
        sys.exit(0)
    
    return config


def run_validation_with_progress(validator: ChecklistValidator, 
                                deployment_config: DeploymentConfig,
                                interactive: bool = False,
                                profile_name: Optional[str] = None) -> ValidationResult:
    """
    Run validation with progress indicators.
    
    Args:
        validator: ChecklistValidator instance
        deployment_config: Deployment configuration
        interactive: Whether to show interactive progress
        profile_name: Environment profile to use (optional)
        
    Returns:
        ValidationResult from the validation
    """
    # Define validation steps
    validation_steps = [
        "Initializing validation framework",
        "Validating IAM permissions",
        "Checking ephemeral storage configuration", 
        "Verifying SSL/HTTPS configuration",
        "Generating remediation guidance",
        "Compiling validation report"
    ]
    
    progress = ProgressIndicator(len(validation_steps), interactive)
    
    try:
        # Step 1: Initialize
        progress.update(validation_steps[0])
        time.sleep(0.5)  # Brief pause for user experience
        
        # Step 2: IAM validation
        progress.update(validation_steps[1])
        # Note: In a real implementation, we would call individual validators here
        # For now, we'll call the main validation method
        
        # Step 3: Storage validation
        progress.update(validation_steps[2])
        
        # Step 4: SSL validation
        progress.update(validation_steps[3])
        
        # Step 5: Remediation
        progress.update(validation_steps[4])
        
        # Run the actual validation
        if profile_name:
            validation_result = validator.validate_with_profile(
                profile_name,
                task_definition_arn=deployment_config.task_definition_arn,
                iam_role_arn=deployment_config.iam_role_arn,
                load_balancer_arn=deployment_config.load_balancer_arn,
                ssl_certificate_arn=deployment_config.ssl_certificate_arn,
                region=deployment_config.region
            )
        else:
            validation_result = validator.validate_deployment_readiness(deployment_config)
        
        # Step 6: Report generation
        progress.update(validation_steps[5])
        
        progress.finish()
        return validation_result
        
    except Exception as e:
        progress.finish()
        raise e


def setup_logging(verbose: bool = False, debug: bool = False):
    """
    Set up logging configuration.
    
    Args:
        verbose: Enable verbose logging
        debug: Enable debug logging
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def load_config_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_file, 'r') as f:
            if config_file.suffix.lower() == '.json':
                return json.load(f)
            else:
                # Assume YAML if not JSON
                try:
                    import yaml
                    return yaml.safe_load(f)
                except ImportError:
                    raise ImportError("PyYAML is required for YAML configuration files")
    
    except Exception as e:
        raise ValueError(f"Failed to load configuration file: {e}")


def create_deployment_config(args, config_manager: Optional[ConfigurationManager] = None) -> DeploymentConfig:
    """
    Create DeploymentConfig from command line arguments.
    
    Args:
        args: Parsed command line arguments
        config_manager: Configuration manager for profile-based configs
        
    Returns:
        DeploymentConfig instance
    """
    if args.profile and config_manager:
        # Create from profile with overrides
        overrides = {}
        
        # Add command line overrides
        if args.task_definition_arn:
            overrides['task_definition_arn'] = args.task_definition_arn
        if args.iam_role_arn:
            overrides['iam_role_arn'] = args.iam_role_arn
        if args.load_balancer_arn:
            overrides['load_balancer_arn'] = args.load_balancer_arn
        if args.ssl_certificate_arn:
            overrides['ssl_certificate_arn'] = args.ssl_certificate_arn
        if args.region:
            overrides['region'] = args.region
        
        return config_manager.create_deployment_config_from_profile(args.profile, **overrides)
    
    elif args.config:
        # Load from configuration file
        config_data = load_config_file(args.config)
        
        return DeploymentConfig(
            task_definition_arn=config_data['task_definition_arn'],
            iam_role_arn=config_data['iam_role_arn'],
            load_balancer_arn=config_data['load_balancer_arn'],
            target_environment=config_data.get('target_environment', 'production'),
            ssl_certificate_arn=config_data.get('ssl_certificate_arn'),
            region=config_data.get('region', args.region),
            additional_config=config_data.get('additional_config')
        )
    
    else:
        # Create from command line arguments
        return DeploymentConfig(
            task_definition_arn=args.task_definition_arn,
            iam_role_arn=args.iam_role_arn,
            load_balancer_arn=args.load_balancer_arn,
            target_environment=args.environment,
            ssl_certificate_arn=args.ssl_certificate_arn,
            region=args.region
        )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Production Deployment Validation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python -m multimodal_librarian.validation.cli --interactive
  
  # Validate using environment profile
  python -m multimodal_librarian.validation.cli --profile production \\
    --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \\
    --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \\
    --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456
  
  # Validate using command line arguments
  python -m multimodal_librarian.validation.cli \\
    --task-definition-arn arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:1 \\
    --iam-role-arn arn:aws:iam::123456789012:role/my-app-role \\
    --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/1234567890123456 \\
    --environment production
  
  # Validate using configuration file
  python -m multimodal_librarian.validation.cli --config deployment-config.json
  
  # Generate JSON report with progress indicators
  python -m multimodal_librarian.validation.cli --config deployment-config.json --output-format json --show-progress
  
  # List available profiles
  python -m multimodal_librarian.validation.cli --list-profiles --validation-config validation-config.yaml
  
  # Export example configuration
  python -m multimodal_librarian.validation.cli --export-example-config example-config.yaml
        """
    )
    
    # Mode selection
    mode_group = parser.add_argument_group('Mode Selection')
    mode_group.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode with guided configuration'
    )
    mode_group.add_argument(
        '--list-profiles',
        action='store_true',
        help='List available environment profiles'
    )
    mode_group.add_argument(
        '--export-example-config',
        help='Export example configuration file to specified path'
    )
    mode_group.add_argument(
        '--test-hook',
        help='Test a specific pipeline hook by name'
    )
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '--config', '-c',
        help='Path to deployment configuration file (JSON or YAML)'
    )
    config_group.add_argument(
        '--validation-config',
        help='Path to validation configuration file with profiles and hooks (JSON or YAML)'
    )
    config_group.add_argument(
        '--profile', '-p',
        help='Environment profile to use for validation'
    )
    config_group.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    
    # Deployment configuration (used if --config not provided)
    deploy_group = parser.add_argument_group('Deployment Configuration')
    deploy_group.add_argument(
        '--task-definition-arn',
        help='ECS task definition ARN'
    )
    deploy_group.add_argument(
        '--iam-role-arn',
        help='IAM role ARN for ECS task'
    )
    deploy_group.add_argument(
        '--load-balancer-arn',
        help='Application Load Balancer ARN'
    )
    deploy_group.add_argument(
        '--ssl-certificate-arn',
        help='SSL certificate ARN (optional)'
    )
    deploy_group.add_argument(
        '--environment',
        default='production',
        help='Target environment (default: production)'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--output-format',
        choices=['console', 'json'],
        default='console',
        help='Output format (default: console)'
    )
    output_group.add_argument(
        '--output-file', '-o',
        help='Output file path (default: stdout)'
    )
    output_group.add_argument(
        '--fail-on-error',
        action='store_true',
        help='Exit with non-zero code if validation fails'
    )
    output_group.add_argument(
        '--show-progress',
        action='store_true',
        help='Show progress indicators during validation'
    )
    
    # Logging options
    log_group = parser.add_argument_group('Logging Options')
    log_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    log_group.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(verbose=args.verbose, debug=args.debug)
    
    try:
        # Initialize configuration manager
        config_manager = None
        if args.validation_config:
            try:
                config_manager = ConfigurationManager(args.validation_config)
            except ConfigurationError as e:
                print(f"Error loading validation configuration: {e}")
                sys.exit(1)
        else:
            config_manager = ConfigurationManager()  # Use default configuration
        
        # Handle special modes
        if args.export_example_config:
            try:
                output_path = config_manager.export_example_configuration(
                    args.export_example_config,
                    format_type='yaml' if args.export_example_config.endswith('.yaml') or args.export_example_config.endswith('.yml') else 'json'
                )
                print(f"Example configuration exported to: {output_path}")
                sys.exit(0)
            except ConfigurationError as e:
                print(f"Error exporting example configuration: {e}")
                sys.exit(1)
        
        if args.list_profiles:
            try:
                profiles = config_manager.list_profiles()
                if not profiles:
                    print("No profiles configured.")
                else:
                    print("Available environment profiles:")
                    validator = ChecklistValidator(region=args.region, config_manager=config_manager)
                    for profile_name in profiles:
                        profile_summary = validator.get_profile_summary(profile_name)
                        print(f"  - {profile_name}: {profile_summary.get('description', 'No description')}")
                        print(f"    Environment: {profile_summary.get('environment_type', 'Unknown')}")
                        print(f"    Region: {profile_summary.get('default_region', 'Unknown')}")
                        print(f"    Enabled validations: {', '.join(profile_summary.get('enabled_validations', []))}")
                        print()
                sys.exit(0)
            except Exception as e:
                print(f"Error listing profiles: {e}")
                sys.exit(1)
        
        if args.test_hook:
            try:
                validator = ChecklistValidator(region=args.region, config_manager=config_manager)
                result = validator.test_pipeline_hook(args.test_hook)
                
                print(f"Hook test results for '{args.test_hook}':")
                print(f"  Success: {result['success']}")
                print(f"  Message: {result['message']}")
                print(f"  Execution time: {result['execution_time']:.2f}s")
                
                if not result['success']:
                    sys.exit(1)
                else:
                    sys.exit(0)
                    
            except Exception as e:
                print(f"Error testing hook: {e}")
                sys.exit(1)
        
        # Handle interactive mode
        if args.interactive:
            config_data = interactive_config_builder()
            deployment_config = DeploymentConfig(
                task_definition_arn=config_data['task_definition_arn'],
                iam_role_arn=config_data['iam_role_arn'],
                load_balancer_arn=config_data['load_balancer_arn'],
                target_environment=config_data.get('target_environment', 'production'),
                ssl_certificate_arn=config_data.get('ssl_certificate_arn'),
                region=config_data.get('region', 'us-east-1')
            )
            profile_name = None
        else:
            # Validate required arguments for non-interactive mode
            if not args.config and not args.profile:
                required_args = ['task_definition_arn', 'iam_role_arn', 'load_balancer_arn']
                missing_args = [arg for arg in required_args if not getattr(args, arg)]
                
                if missing_args:
                    parser.error(f"The following arguments are required when not using --config, --profile, or --interactive: {', '.join('--' + arg.replace('_', '-') for arg in missing_args)}")
            
            # Create deployment configuration
            deployment_config = create_deployment_config(args, config_manager)
            profile_name = args.profile
        
        # Run validation with or without progress indicators
        validator = ChecklistValidator(region=args.region, config_manager=config_manager)
        
        if args.show_progress or args.interactive:
            validation_result = run_validation_with_progress(
                validator, 
                deployment_config, 
                interactive=True,
                profile_name=profile_name
            )
        else:
            if profile_name:
                validation_result = validator.validate_with_profile(
                    profile_name,
                    task_definition_arn=deployment_config.task_definition_arn,
                    iam_role_arn=deployment_config.iam_role_arn,
                    load_balancer_arn=deployment_config.load_balancer_arn,
                    ssl_certificate_arn=deployment_config.ssl_certificate_arn,
                    region=deployment_config.region
                )
            else:
                validation_result = validator.validate_deployment_readiness(deployment_config)
        
        # Get the detailed validation report
        try:
            validation_report = validator.get_validation_report()
        except Exception:
            # If no detailed report available, create a simple one from the result
            validation_report = ValidationReport(
                overall_status=validation_result.passed,
                timestamp=validation_result.timestamp,
                checks_performed=[validation_result],
                deployment_config=deployment_config,
                remediation_summary=None
            )
        
        # Format output
        if args.output_format == 'json':
            output = ValidationReportFormatter.format_json_report(validation_report)
        else:
            output = ValidationReportFormatter.format_console_report(validation_report)
        
        # Write output
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(output)
            print(f"Validation report written to: {args.output_file}")
        else:
            print(output)
        
        # Exit with appropriate code
        if args.fail_on_error and not validation_report.overall_status:
            sys.exit(1)
        else:
            sys.exit(0)
    
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        logging.error(f"Validation failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()