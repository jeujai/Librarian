"""
Configuration Management for Production Deployment Validation

This module provides comprehensive configuration management including:
- Configuration file support (YAML/JSON)
- Environment-specific validation profiles
- Deployment pipeline integration hooks
- Custom validation thresholds
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable
from enum import Enum

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .models import DeploymentConfig, ValidationStatus


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""
    pass


class EnvironmentType(Enum):
    """Supported environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class ValidationThresholds:
    """Custom validation thresholds for different checks."""
    
    # Storage thresholds
    minimum_ephemeral_storage_gb: int = 30
    recommended_ephemeral_storage_gb: int = 50
    
    # SSL/Certificate thresholds
    certificate_expiry_warning_days: int = 30
    certificate_expiry_critical_days: int = 7
    
    # IAM validation thresholds
    max_policy_size_kb: int = 10
    max_inline_policies: int = 5
    
    # Timeout thresholds (in seconds)
    iam_validation_timeout: int = 30
    storage_validation_timeout: int = 15
    ssl_validation_timeout: int = 45
    
    # Retry thresholds
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationThresholds':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EnvironmentProfile:
    """Environment-specific validation profile."""
    
    name: str
    environment_type: EnvironmentType
    description: str
    
    # Validation configuration
    enabled_validations: List[str] = field(default_factory=lambda: [
        'iam_permissions', 'storage_config', 'ssl_config', 'network_config', 'task_definition'
    ])
    
    # Custom thresholds for this environment
    thresholds: ValidationThresholds = field(default_factory=ValidationThresholds)
    
    # Environment-specific AWS configuration
    default_region: str = "us-east-1"
    allowed_regions: List[str] = field(default_factory=lambda: ["us-east-1", "us-west-2"])
    
    # Deployment pipeline integration
    pipeline_hooks: Dict[str, Any] = field(default_factory=dict)
    
    # Additional environment-specific configuration
    additional_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result['environment_type'] = self.environment_type.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnvironmentProfile':
        """Create from dictionary."""
        # Handle environment_type conversion
        if 'environment_type' in data:
            data['environment_type'] = EnvironmentType(data['environment_type'])
        
        # Handle thresholds conversion
        if 'thresholds' in data and isinstance(data['thresholds'], dict):
            data['thresholds'] = ValidationThresholds.from_dict(data['thresholds'])
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PipelineHook:
    """Configuration for deployment pipeline integration hooks."""
    
    name: str
    trigger_event: str  # 'pre_validation', 'post_validation', 'validation_failed', 'validation_passed'
    hook_type: str  # 'webhook', 'script', 'aws_lambda', 'sns'
    
    # Hook configuration
    endpoint_url: Optional[str] = None
    script_path: Optional[str] = None
    lambda_function_arn: Optional[str] = None
    sns_topic_arn: Optional[str] = None
    
    # Hook behavior
    enabled: bool = True
    timeout_seconds: int = 30
    retry_on_failure: bool = True
    max_retries: int = 3
    
    # Additional configuration
    headers: Dict[str, str] = field(default_factory=dict)
    payload_template: Optional[str] = None
    environment_variables: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineHook':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ValidationConfiguration:
    """Complete validation configuration including profiles and hooks."""
    
    # Default configuration
    default_profile: str = "production"
    default_region: str = "us-east-1"
    
    # Environment profiles
    profiles: Dict[str, EnvironmentProfile] = field(default_factory=dict)
    
    # Global pipeline hooks
    pipeline_hooks: Dict[str, PipelineHook] = field(default_factory=dict)
    
    # Global validation settings
    global_thresholds: ValidationThresholds = field(default_factory=ValidationThresholds)
    
    # Configuration metadata
    config_version: str = "1.0"
    last_updated: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'default_profile': self.default_profile,
            'default_region': self.default_region,
            'profiles': {name: profile.to_dict() for name, profile in self.profiles.items()},
            'pipeline_hooks': {name: hook.to_dict() for name, hook in self.pipeline_hooks.items()},
            'global_thresholds': self.global_thresholds.to_dict(),
            'config_version': self.config_version,
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationConfiguration':
        """Create from dictionary."""
        # Convert profiles
        profiles = {}
        if 'profiles' in data:
            for name, profile_data in data['profiles'].items():
                profiles[name] = EnvironmentProfile.from_dict(profile_data)
        
        # Convert pipeline hooks
        pipeline_hooks = {}
        if 'pipeline_hooks' in data:
            for name, hook_data in data['pipeline_hooks'].items():
                pipeline_hooks[name] = PipelineHook.from_dict(hook_data)
        
        # Convert global thresholds
        global_thresholds = ValidationThresholds()
        if 'global_thresholds' in data:
            global_thresholds = ValidationThresholds.from_dict(data['global_thresholds'])
        
        return cls(
            default_profile=data.get('default_profile', 'production'),
            default_region=data.get('default_region', 'us-east-1'),
            profiles=profiles,
            pipeline_hooks=pipeline_hooks,
            global_thresholds=global_thresholds,
            config_version=data.get('config_version', '1.0'),
            last_updated=data.get('last_updated')
        )


class ConfigurationManager:
    """
    Manages validation configuration including environment profiles,
    pipeline hooks, and custom thresholds.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self._config: Optional[ValidationConfiguration] = None
        self._config_path: Optional[Path] = None
        
        # Load configuration if path provided
        if config_path:
            self.load_configuration(config_path)
        else:
            # Initialize with default configuration
            self._config = self._create_default_configuration()
    
    def load_configuration(self, config_path: str) -> ValidationConfiguration:
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file (JSON or YAML)
            
        Returns:
            Loaded ValidationConfiguration
            
        Raises:
            ConfigurationError: If configuration cannot be loaded or is invalid
        """
        config_file = Path(config_path)
        self._config_path = config_file
        
        if not config_file.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_file, 'r') as f:
                if config_file.suffix.lower() == '.json':
                    config_data = json.load(f)
                elif config_file.suffix.lower() in ['.yml', '.yaml']:
                    if not YAML_AVAILABLE:
                        raise ConfigurationError("PyYAML is required for YAML configuration files")
                    config_data = yaml.safe_load(f)
                else:
                    raise ConfigurationError(f"Unsupported configuration file format: {config_file.suffix}")
            
            self._config = ValidationConfiguration.from_dict(config_data)
            self.logger.info(f"Configuration loaded from: {config_path}")
            
            # Validate configuration
            self._validate_configuration()
            
            return self._config
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def save_configuration(self, config_path: Optional[str] = None) -> str:
        """
        Save current configuration to file.
        
        Args:
            config_path: Path to save configuration (optional, uses loaded path if not provided)
            
        Returns:
            Path where configuration was saved
            
        Raises:
            ConfigurationError: If configuration cannot be saved
        """
        if not self._config:
            raise ConfigurationError("No configuration to save")
        
        # Determine save path
        if config_path:
            save_path = Path(config_path)
        elif self._config_path:
            save_path = self._config_path
        else:
            raise ConfigurationError("No configuration path specified")
        
        try:
            # Update last_updated timestamp
            from datetime import datetime
            self._config.last_updated = datetime.utcnow().isoformat()
            
            config_data = self._config.to_dict()
            
            with open(save_path, 'w') as f:
                if save_path.suffix.lower() == '.json':
                    json.dump(config_data, f, indent=2)
                elif save_path.suffix.lower() in ['.yml', '.yaml']:
                    if not YAML_AVAILABLE:
                        raise ConfigurationError("PyYAML is required for YAML configuration files")
                    yaml.dump(config_data, f, default_flow_style=False, indent=2)
                else:
                    # Default to JSON
                    json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Configuration saved to: {save_path}")
            return str(save_path)
            
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get_environment_profile(self, profile_name: str) -> EnvironmentProfile:
        """
        Get environment profile by name.
        
        Args:
            profile_name: Name of the profile
            
        Returns:
            EnvironmentProfile instance
            
        Raises:
            ConfigurationError: If profile not found
        """
        if not self._config:
            raise ConfigurationError("No configuration loaded")
        
        if profile_name not in self._config.profiles:
            available_profiles = list(self._config.profiles.keys())
            raise ConfigurationError(
                f"Profile '{profile_name}' not found. Available profiles: {available_profiles}"
            )
        
        return self._config.profiles[profile_name]
    
    def create_environment_profile(self, name: str, environment_type: EnvironmentType,
                                 description: str, **kwargs) -> EnvironmentProfile:
        """
        Create a new environment profile.
        
        Args:
            name: Profile name
            environment_type: Type of environment
            description: Profile description
            **kwargs: Additional profile configuration
            
        Returns:
            Created EnvironmentProfile
        """
        if not self._config:
            self._config = self._create_default_configuration()
        
        profile = EnvironmentProfile(
            name=name,
            environment_type=environment_type,
            description=description,
            **kwargs
        )
        
        self._config.profiles[name] = profile
        self.logger.info(f"Created environment profile: {name}")
        
        return profile
    
    def get_pipeline_hook(self, hook_name: str) -> PipelineHook:
        """
        Get pipeline hook by name.
        
        Args:
            hook_name: Name of the hook
            
        Returns:
            PipelineHook instance
            
        Raises:
            ConfigurationError: If hook not found
        """
        if not self._config:
            raise ConfigurationError("No configuration loaded")
        
        if hook_name not in self._config.pipeline_hooks:
            available_hooks = list(self._config.pipeline_hooks.keys())
            raise ConfigurationError(
                f"Pipeline hook '{hook_name}' not found. Available hooks: {available_hooks}"
            )
        
        return self._config.pipeline_hooks[hook_name]
    
    def create_pipeline_hook(self, name: str, trigger_event: str, hook_type: str,
                           **kwargs) -> PipelineHook:
        """
        Create a new pipeline hook.
        
        Args:
            name: Hook name
            trigger_event: Event that triggers the hook
            hook_type: Type of hook (webhook, script, etc.)
            **kwargs: Additional hook configuration
            
        Returns:
            Created PipelineHook
        """
        if not self._config:
            self._config = self._create_default_configuration()
        
        hook = PipelineHook(
            name=name,
            trigger_event=trigger_event,
            hook_type=hook_type,
            **kwargs
        )
        
        self._config.pipeline_hooks[name] = hook
        self.logger.info(f"Created pipeline hook: {name}")
        
        return hook
    
    def get_validation_thresholds(self, profile_name: Optional[str] = None) -> ValidationThresholds:
        """
        Get validation thresholds for a specific profile or global defaults.
        
        Args:
            profile_name: Name of the profile (optional, uses global if not provided)
            
        Returns:
            ValidationThresholds instance
        """
        if not self._config:
            return ValidationThresholds()
        
        if profile_name:
            try:
                profile = self.get_environment_profile(profile_name)
                return profile.thresholds
            except ConfigurationError:
                self.logger.warning(f"Profile '{profile_name}' not found, using global thresholds")
        
        return self._config.global_thresholds
    
    def create_deployment_config_from_profile(self, profile_name: str,
                                            **overrides) -> DeploymentConfig:
        """
        Create a DeploymentConfig from an environment profile.
        
        Args:
            profile_name: Name of the environment profile
            **overrides: Override values for deployment config
            
        Returns:
            DeploymentConfig instance
            
        Raises:
            ConfigurationError: If profile not found or required values missing
        """
        profile = self.get_environment_profile(profile_name)
        
        # Extract required values from overrides or profile
        required_fields = ['task_definition_arn', 'iam_role_arn', 'load_balancer_arn']
        config_values = {}
        
        for field in required_fields:
            if field in overrides:
                config_values[field] = overrides[field]
            elif field in profile.additional_config:
                config_values[field] = profile.additional_config[field]
            else:
                raise ConfigurationError(
                    f"Required field '{field}' not found in profile '{profile_name}' or overrides"
                )
        
        # Set optional values
        config_values.update({
            'target_environment': profile.name,
            'region': overrides.get('region', profile.default_region),
            'ssl_certificate_arn': overrides.get('ssl_certificate_arn', 
                                               profile.additional_config.get('ssl_certificate_arn')),
            'additional_config': profile.additional_config
        })
        
        return DeploymentConfig(**config_values)
    
    def get_enabled_validations(self, profile_name: Optional[str] = None) -> List[str]:
        """
        Get list of enabled validations for a profile.
        
        Args:
            profile_name: Name of the profile (optional)
            
        Returns:
            List of enabled validation names
        """
        if profile_name:
            try:
                profile = self.get_environment_profile(profile_name)
                return profile.enabled_validations
            except ConfigurationError:
                pass
        
        # Return default validations from EnvironmentProfile default
        default_profile = EnvironmentProfile(
            name="default",
            environment_type=EnvironmentType.PRODUCTION,
            description="Default profile"
        )
        return default_profile.enabled_validations
    
    def get_pipeline_hooks_for_event(self, trigger_event: str) -> List[PipelineHook]:
        """
        Get all pipeline hooks for a specific trigger event.
        
        Args:
            trigger_event: Event name to filter hooks
            
        Returns:
            List of PipelineHook instances for the event
        """
        if not self._config:
            return []
        
        return [
            hook for hook in self._config.pipeline_hooks.values()
            if hook.trigger_event == trigger_event and hook.enabled
        ]
    
    def list_profiles(self) -> List[str]:
        """
        Get list of available profile names.
        
        Returns:
            List of profile names
        """
        if not self._config:
            return []
        
        return list(self._config.profiles.keys())
    
    def list_pipeline_hooks(self) -> List[str]:
        """
        Get list of available pipeline hook names.
        
        Returns:
            List of hook names
        """
        if not self._config:
            return []
        
        return list(self._config.pipeline_hooks.keys())
    
    def _create_default_configuration(self) -> ValidationConfiguration:
        """
        Create default configuration with standard profiles.
        
        Returns:
            Default ValidationConfiguration
        """
        config = ValidationConfiguration()
        
        # Create default profiles
        profiles = {
            'development': EnvironmentProfile(
                name='development',
                environment_type=EnvironmentType.DEVELOPMENT,
                description='Development environment with relaxed validation',
                thresholds=ValidationThresholds(
                    minimum_ephemeral_storage_gb=20,
                    certificate_expiry_warning_days=7,
                    iam_validation_timeout=15
                )
            ),
            'staging': EnvironmentProfile(
                name='staging',
                environment_type=EnvironmentType.STAGING,
                description='Staging environment with production-like validation',
                thresholds=ValidationThresholds(
                    minimum_ephemeral_storage_gb=25,
                    certificate_expiry_warning_days=14
                )
            ),
            'production': EnvironmentProfile(
                name='production',
                environment_type=EnvironmentType.PRODUCTION,
                description='Production environment with strict validation',
                thresholds=ValidationThresholds()  # Use defaults (most strict)
            )
        }
        
        config.profiles = profiles
        
        # Create default pipeline hooks
        hooks = {
            'slack_notification': PipelineHook(
                name='slack_notification',
                trigger_event='validation_failed',
                hook_type='webhook',
                endpoint_url='https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK',
                enabled=False,  # Disabled by default
                payload_template='{"text": "Deployment validation failed for {{environment}}: {{failed_checks}}"}'
            ),
            'deployment_gate': PipelineHook(
                name='deployment_gate',
                trigger_event='validation_passed',
                hook_type='script',
                script_path='scripts/approve-deployment.sh',
                enabled=False
            )
        }
        
        config.pipeline_hooks = hooks
        
        return config
    
    def _validate_configuration(self):
        """
        Validate the loaded configuration for consistency and completeness.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not self._config:
            return
        
        # Validate profiles
        for profile_name, profile in self._config.profiles.items():
            if not profile.name:
                raise ConfigurationError(f"Profile '{profile_name}' missing name")
            
            if profile.name != profile_name:
                raise ConfigurationError(
                    f"Profile name mismatch: key='{profile_name}', name='{profile.name}'"
                )
            
            # Validate enabled validations
            valid_validations = ['iam_permissions', 'storage_config', 'ssl_config']
            for validation in profile.enabled_validations:
                if validation not in valid_validations:
                    raise ConfigurationError(
                        f"Invalid validation '{validation}' in profile '{profile_name}'. "
                        f"Valid options: {valid_validations}"
                    )
        
        # Validate pipeline hooks
        for hook_name, hook in self._config.pipeline_hooks.items():
            if not hook.name:
                raise ConfigurationError(f"Pipeline hook '{hook_name}' missing name")
            
            if hook.name != hook_name:
                raise ConfigurationError(
                    f"Hook name mismatch: key='{hook_name}', name='{hook.name}'"
                )
            
            # Validate trigger events
            valid_events = ['pre_validation', 'post_validation', 'validation_failed', 'validation_passed']
            if hook.trigger_event not in valid_events:
                raise ConfigurationError(
                    f"Invalid trigger event '{hook.trigger_event}' in hook '{hook_name}'. "
                    f"Valid options: {valid_events}"
                )
            
            # Validate hook types
            valid_types = ['webhook', 'script', 'aws_lambda', 'sns']
            if hook.hook_type not in valid_types:
                raise ConfigurationError(
                    f"Invalid hook type '{hook.hook_type}' in hook '{hook_name}'. "
                    f"Valid options: {valid_types}"
                )
        
        self.logger.info("Configuration validation passed")
    
    def export_example_configuration(self, output_path: str, format_type: str = 'yaml') -> str:
        """
        Export an example configuration file with all available options.
        
        Args:
            output_path: Path to save the example configuration
            format_type: Format to export ('yaml' or 'json')
            
        Returns:
            Path where example was saved
        """
        example_config = self._create_comprehensive_example_configuration()
        
        output_file = Path(output_path)
        
        try:
            with open(output_file, 'w') as f:
                if format_type.lower() == 'json':
                    json.dump(example_config.to_dict(), f, indent=2)
                else:
                    if not YAML_AVAILABLE:
                        raise ConfigurationError("PyYAML is required for YAML export")
                    yaml.dump(example_config.to_dict(), f, default_flow_style=False, indent=2)
            
            self.logger.info(f"Example configuration exported to: {output_path}")
            return str(output_file)
            
        except Exception as e:
            raise ConfigurationError(f"Failed to export example configuration: {e}")
    
    def _create_comprehensive_example_configuration(self) -> ValidationConfiguration:
        """
        Create a comprehensive example configuration with all options.
        
        Returns:
            ValidationConfiguration with example values
        """
        # Create example profiles with different configurations
        profiles = {
            'development': EnvironmentProfile(
                name='development',
                environment_type=EnvironmentType.DEVELOPMENT,
                description='Development environment with relaxed validation thresholds',
                enabled_validations=['iam_permissions', 'storage_config'],  # Skip SSL for dev
                thresholds=ValidationThresholds(
                    minimum_ephemeral_storage_gb=20,
                    certificate_expiry_warning_days=7,
                    iam_validation_timeout=15,
                    max_retry_attempts=2
                ),
                default_region='us-west-2',
                allowed_regions=['us-west-2', 'us-east-1'],
                additional_config={
                    'skip_ssl_validation': True,
                    'allow_self_signed_certs': True
                }
            ),
            'staging': EnvironmentProfile(
                name='staging',
                environment_type=EnvironmentType.STAGING,
                description='Staging environment with production-like validation',
                enabled_validations=['iam_permissions', 'storage_config', 'ssl_config'],
                thresholds=ValidationThresholds(
                    minimum_ephemeral_storage_gb=25,
                    certificate_expiry_warning_days=14,
                    ssl_validation_timeout=30
                ),
                default_region='us-east-1',
                allowed_regions=['us-east-1'],
                additional_config={
                    'require_valid_ssl': True,
                    'staging_specific_checks': True
                }
            ),
            'production': EnvironmentProfile(
                name='production',
                environment_type=EnvironmentType.PRODUCTION,
                description='Production environment with strict validation requirements',
                enabled_validations=['iam_permissions', 'storage_config', 'ssl_config'],
                thresholds=ValidationThresholds(
                    minimum_ephemeral_storage_gb=30,
                    recommended_ephemeral_storage_gb=50,
                    certificate_expiry_warning_days=30,
                    certificate_expiry_critical_days=7,
                    max_retry_attempts=3,
                    ssl_validation_timeout=60
                ),
                default_region='us-east-1',
                allowed_regions=['us-east-1', 'us-west-2'],
                additional_config={
                    'require_valid_ssl': True,
                    'enforce_security_headers': True,
                    'production_specific_checks': True
                }
            )
        }
        
        # Create example pipeline hooks
        hooks = {
            'slack_notification': PipelineHook(
                name='slack_notification',
                trigger_event='validation_failed',
                hook_type='webhook',
                endpoint_url='https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK',
                enabled=True,
                timeout_seconds=10,
                headers={'Content-Type': 'application/json'},
                payload_template='{"text": "🚨 Deployment validation failed for {{environment}}: {{failed_checks}}"}'
            ),
            'teams_notification': PipelineHook(
                name='teams_notification',
                trigger_event='validation_passed',
                hook_type='webhook',
                endpoint_url='https://outlook.office.com/webhook/YOUR/TEAMS/WEBHOOK',
                enabled=False,
                payload_template='{"text": "✅ Deployment validation passed for {{environment}}"}'
            ),
            'deployment_approval': PipelineHook(
                name='deployment_approval',
                trigger_event='validation_passed',
                hook_type='script',
                script_path='scripts/approve-deployment.sh',
                enabled=True,
                environment_variables={
                    'DEPLOYMENT_ENV': '{{environment}}',
                    'VALIDATION_TIMESTAMP': '{{timestamp}}'
                }
            ),
            'lambda_processor': PipelineHook(
                name='lambda_processor',
                trigger_event='post_validation',
                hook_type='aws_lambda',
                lambda_function_arn='arn:aws:lambda:us-east-1:123456789012:function:process-validation-results',
                enabled=False,
                timeout_seconds=30
            ),
            'sns_alert': PipelineHook(
                name='sns_alert',
                trigger_event='validation_failed',
                hook_type='sns',
                sns_topic_arn='arn:aws:sns:us-east-1:123456789012:deployment-alerts',
                enabled=False
            )
        }
        
        # Create comprehensive configuration
        config = ValidationConfiguration(
            default_profile='production',
            default_region='us-east-1',
            profiles=profiles,
            pipeline_hooks=hooks,
            global_thresholds=ValidationThresholds(
                minimum_ephemeral_storage_gb=30,
                certificate_expiry_warning_days=30,
                max_retry_attempts=3
            ),
            config_version='1.0'
        )
        
        return config