"""
Checklist Validator for Production Deployment Validation

This module provides the main orchestrator for the production deployment checklist.
It coordinates the execution of all validation components and provides comprehensive
validation reporting with deployment blocking logic for failed validations.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base_validator import BaseValidator, ValidationError
from .config_manager import ConfigurationManager, ValidationThresholds
from .fix_script_manager import FixScriptManager
from .iam_permissions_validator import IAMPermissionsValidator
from .models import (
    DeploymentConfig,
    ValidationReport,
    ValidationResult,
    ValidationStatus,
)
from .network_config_validator import NetworkConfigValidator
from .pipeline_integration import PipelineIntegrationManager
from .ssl_config_validator import SSLConfigValidator
from .storage_config_validator import StorageConfigValidator
from .task_definition_validator import TaskDefinitionValidator


class ChecklistValidator:
    """
    Main orchestrator for production deployment validation checklist.
    
    This class coordinates the execution of all validation components,
    aggregates results, and provides deployment blocking logic for failed validations.
    Integrates with configuration management and pipeline hooks.
    """
    
    def __init__(self, region: str = "us-east-1", config_manager: Optional[ConfigurationManager] = None):
        """
        Initialize the checklist validator with all component validators.
        
        Args:
            region: AWS region for validation operations
            config_manager: Configuration manager for profiles and hooks (optional)
        """
        self.region = region
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize configuration management
        self.config_manager = config_manager or ConfigurationManager()
        
        # Initialize pipeline integration
        self.pipeline_manager = PipelineIntegrationManager(self.config_manager)
        
        # Initialize component validators
        self.iam_validator = IAMPermissionsValidator(region)
        self.storage_validator = StorageConfigValidator(region)
        self.ssl_validator = SSLConfigValidator(region)
        self.network_validator = NetworkConfigValidator(region)
        self.task_definition_validator = TaskDefinitionValidator(region)
        self.fix_script_manager = FixScriptManager()
        
        # Track validation execution
        self._last_validation_report: Optional[ValidationReport] = None
        self._current_profile: Optional[str] = None
        
        # Define the critical validation checks in order of execution
        self._validation_checks = [
            {
                'name': 'IAM Permissions Validation',
                'validator': self.iam_validator,
                'description': 'Validates ECS task IAM permissions for Secrets Manager access',
                'critical': True,
                'validation_key': 'iam_permissions'
            },
            {
                'name': 'Storage Configuration Validation', 
                'validator': self.storage_validator,
                'description': 'Validates ECS task ephemeral storage allocation (minimum 30GB)',
                'critical': True,
                'validation_key': 'storage_config'
            },
            {
                'name': 'SSL Configuration Validation',
                'validator': self.ssl_validator,
                'description': 'Validates HTTPS/SSL setup for production security',
                'critical': True,
                'validation_key': 'ssl_config'
            },
            {
                'name': 'Network Configuration Validation',
                'validator': self.network_validator,
                'description': 'Validates VPC, subnet, and load balancer configuration compatibility',
                'critical': True,
                'validation_key': 'network_config'
            },
            {
                'name': 'Task Definition Registration Validation',
                'validator': self.task_definition_validator,
                'description': 'Validates task definition registration status and timing',
                'critical': True,
                'validation_key': 'task_definition'
            }
        ]
    
    def validate_deployment_readiness(self, deployment_config: DeploymentConfig, 
                                     profile_name: Optional[str] = None) -> ValidationResult:
        """
        Validate deployment readiness by running all critical checks.
        
        Args:
            deployment_config: Configuration for the deployment to validate
            profile_name: Environment profile to use for validation (optional)
            
        Returns:
            ValidationResult indicating overall deployment readiness
        """
        check_name = "Production Deployment Readiness"
        
        try:
            # Set current profile for this validation run
            self._current_profile = profile_name or self.config_manager._config.default_profile if self.config_manager._config else None
            
            self.logger.info(f"Starting deployment validation for environment: {deployment_config.target_environment}")
            if self._current_profile:
                self.logger.info(f"Using validation profile: {self._current_profile}")
            
            # Execute pre-validation hooks
            self._execute_pipeline_hooks_sync('pre_validation', None)
            
            # Execute all validation checks
            validation_results = self._execute_all_validations(deployment_config)
            
            # Generate comprehensive validation report
            validation_report = self._generate_validation_report(deployment_config, validation_results)
            self._last_validation_report = validation_report
            
            # Determine overall deployment readiness
            overall_passed = validation_report.overall_status
            failed_checks = [result.check_name for result in validation_results if not result.passed]
            
            # Execute post-validation hooks
            self._execute_pipeline_hooks_sync('post_validation', validation_report)
            
            if overall_passed:
                # Execute validation passed hooks
                self._execute_pipeline_hooks_sync('validation_passed', validation_report)
                return self._create_deployment_ready_result(check_name, validation_report)
            else:
                # Execute validation failed hooks
                self._execute_pipeline_hooks_sync('validation_failed', validation_report)
                return self._create_deployment_blocked_result(check_name, validation_report, failed_checks)
                
        except Exception as e:
            self.logger.error(f"Error during deployment validation: {str(e)}")
            return ValidationResult(
                check_name=check_name,
                status=ValidationStatus.ERROR,
                message=f"Deployment validation failed with error: {str(e)}",
                details={'error_type': type(e).__name__, 'error_message': str(e)}
            )
    
    def _execute_all_validations(self, deployment_config: DeploymentConfig) -> List[ValidationResult]:
        """
        Execute all validation checks in sequence.
        
        Args:
            deployment_config: Configuration to validate
            
        Returns:
            List of ValidationResult objects from all checks
        """
        validation_results = []
        
        # Get enabled validations for current profile
        enabled_validations = self.config_manager.get_enabled_validations(self._current_profile)
        
        # Get validation thresholds for current profile
        thresholds = self.config_manager.get_validation_thresholds(self._current_profile)
        
        for check_config in self._validation_checks:
            check_name = check_config['name']
            validator = check_config['validator']
            is_critical = check_config['critical']
            validation_key = check_config['validation_key']
            
            # Skip validation if not enabled in profile
            if validation_key not in enabled_validations:
                self.logger.info(f"Skipping validation check: {check_name} (disabled in profile)")
                continue
            
            self.logger.info(f"Executing validation check: {check_name}")
            
            try:
                # Apply thresholds to validator if supported
                if hasattr(validator, 'set_thresholds'):
                    validator.set_thresholds(thresholds)
                
                # Execute the validation
                result = validator.validate(deployment_config)
                validation_results.append(result)
                
                # Log result
                if result.passed:
                    self.logger.info(f"✓ {check_name}: PASSED")
                else:
                    self.logger.warning(f"✗ {check_name}: FAILED - {result.message}")
                    
                    # For critical checks, log remediation steps
                    if is_critical and result.remediation_steps:
                        self.logger.info(f"Remediation steps for {check_name}:")
                        for step in result.remediation_steps[:3]:  # Log first 3 steps
                            self.logger.info(f"  - {step}")
                
            except Exception as e:
                self.logger.error(f"Error executing {check_name}: {str(e)}")
                
                # Create error result for failed validation execution
                error_result = ValidationResult(
                    check_name=check_name,
                    status=ValidationStatus.ERROR,
                    message=f"Validation execution failed: {str(e)}",
                    details={'error_type': type(e).__name__, 'validator': validator.__class__.__name__}
                )
                validation_results.append(error_result)
        
        return validation_results
    
    def _generate_validation_report(self, deployment_config: DeploymentConfig, 
                                  validation_results: List[ValidationResult]) -> ValidationReport:
        """
        Generate comprehensive validation report from individual check results.
        
        Args:
            deployment_config: Configuration that was validated
            validation_results: Results from all validation checks
            
        Returns:
            ValidationReport with aggregated results and remediation guidance
        """
        # Determine overall status
        overall_status = all(result.passed for result in validation_results)
        
        # Generate remediation summary if there are failures
        remediation_summary = None
        if not overall_status:
            failed_check_names = [result.check_name for result in validation_results if not result.passed]
            remediation_guide = self.fix_script_manager.generate_remediation_guide(failed_check_names)
            remediation_summary = self.fix_script_manager.get_remediation_summary(failed_check_names)
        
        # Create validation report
        validation_report = ValidationReport(
            overall_status=overall_status,
            timestamp=datetime.utcnow(),
            checks_performed=validation_results,
            deployment_config=deployment_config,
            remediation_summary=remediation_summary
        )
        
        # Log summary
        self.logger.info(f"Validation Summary: {validation_report.passed_checks}/{validation_report.total_checks} checks passed")
        if validation_report.failed_checks > 0:
            self.logger.warning(f"Failed checks: {validation_report.failed_checks}")
        
        return validation_report
    
    def _create_deployment_ready_result(self, check_name: str, 
                                      validation_report: ValidationReport) -> ValidationResult:
        """
        Create success result when deployment is ready.
        
        Args:
            check_name: Name of the overall check
            validation_report: Comprehensive validation report
            
        Returns:
            ValidationResult indicating deployment readiness
        """
        return ValidationResult(
            check_name=check_name,
            status=ValidationStatus.PASSED,
            message=f"✅ Deployment validation passed! All {validation_report.total_checks} critical checks successful. Deployment can proceed.",
            details={
                'validation_summary': {
                    'total_checks': validation_report.total_checks,
                    'passed_checks': validation_report.passed_checks,
                    'failed_checks': validation_report.failed_checks,
                    'deployment_environment': validation_report.deployment_config.target_environment
                },
                'checks_performed': [
                    {
                        'name': result.check_name,
                        'status': result.status.value,
                        'message': result.message
                    }
                    for result in validation_report.checks_performed
                ],
                'deployment_approved': True,
                'validation_timestamp': validation_report.timestamp.isoformat()
            }
        )
    
    def _create_deployment_blocked_result(self, check_name: str, validation_report: ValidationReport,
                                        failed_checks: List[str]) -> ValidationResult:
        """
        Create failure result when deployment should be blocked.
        
        Args:
            check_name: Name of the overall check
            validation_report: Comprehensive validation report
            failed_checks: List of failed check names
            
        Returns:
            ValidationResult indicating deployment should be blocked
        """
        # Generate comprehensive remediation steps
        remediation_guide = self.fix_script_manager.generate_remediation_guide(failed_checks)
        
        remediation_steps = [
            "🚨 DEPLOYMENT BLOCKED - Critical validation failures detected",
            f"Failed checks: {', '.join(failed_checks)}",
            "",
            "IMMEDIATE ACTIONS REQUIRED:"
        ]
        
        # Add specific remediation steps from the guide
        remediation_steps.extend(remediation_guide.step_by_step_instructions[:10])  # Limit to first 10 steps
        
        remediation_steps.extend([
            "",
            "AVAILABLE FIX SCRIPTS:",
        ])
        
        # Add fix script references
        for script_ref in remediation_guide.script_references:
            remediation_steps.append(f"  - {script_ref.script_path}: {script_ref.description}")
        
        remediation_steps.extend([
            "",
            "⚠️  DO NOT PROCEED WITH DEPLOYMENT until all validations pass!",
            "Re-run validation after applying fixes to confirm readiness."
        ])
        
        # Collect fix scripts from all failed validations
        all_fix_scripts = []
        for result in validation_report.checks_performed:
            if not result.passed and result.fix_scripts:
                all_fix_scripts.extend(result.fix_scripts)
        
        # Remove duplicates while preserving order
        unique_fix_scripts = list(dict.fromkeys(all_fix_scripts))
        
        return ValidationResult(
            check_name=check_name,
            status=ValidationStatus.FAILED,
            message=f"❌ Deployment validation failed! {validation_report.failed_checks}/{validation_report.total_checks} checks failed. Deployment is BLOCKED.",
            remediation_steps=remediation_steps,
            fix_scripts=unique_fix_scripts,
            details={
                'validation_summary': {
                    'total_checks': validation_report.total_checks,
                    'passed_checks': validation_report.passed_checks,
                    'failed_checks': validation_report.failed_checks,
                    'deployment_environment': validation_report.deployment_config.target_environment
                },
                'failed_validations': [
                    {
                        'name': result.check_name,
                        'message': result.message,
                        'remediation_steps': result.remediation_steps,
                        'fix_scripts': result.fix_scripts
                    }
                    for result in validation_report.checks_performed if not result.passed
                ],
                'deployment_blocked': True,
                'remediation_guide': remediation_guide.to_dict(),
                'validation_timestamp': validation_report.timestamp.isoformat()
            }
        )
    
    def get_validation_report(self) -> ValidationReport:
        """
        Get the comprehensive validation report from the last validation run.
        
        Returns:
            ValidationReport with detailed results from all checks
            
        Raises:
            ValidationError: If no validation has been run yet
        """
        if self._last_validation_report is None:
            raise ValidationError("No validation has been performed yet. Call validate_deployment_readiness() first.")
        
        return self._last_validation_report
    
    def validate_individual_component(self, deployment_config: DeploymentConfig, 
                                    component: str) -> ValidationResult:
        """
        Validate a specific component individually.
        
        Args:
            deployment_config: Configuration to validate
            component: Component to validate ('iam', 'storage', 'ssl')
            
        Returns:
            ValidationResult for the specific component
            
        Raises:
            ValidationError: If component name is invalid
        """
        component_validators = {
            'iam': self.iam_validator,
            'storage': self.storage_validator,
            'ssl': self.ssl_validator
        }
        
        if component not in component_validators:
            raise ValidationError(f"Invalid component '{component}'. Valid options: {list(component_validators.keys())}")
        
        validator = component_validators[component]
        
        try:
            self.logger.info(f"Validating individual component: {component}")
            result = validator.validate(deployment_config)
            
            if result.passed:
                self.logger.info(f"✓ {component} validation: PASSED")
            else:
                self.logger.warning(f"✗ {component} validation: FAILED - {result.message}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error validating {component}: {str(e)}")
            return ValidationResult(
                check_name=f"{component.upper()} Component Validation",
                status=ValidationStatus.ERROR,
                message=f"Component validation failed: {str(e)}",
                details={'error_type': type(e).__name__, 'component': component}
            )
    
    def get_available_fix_scripts(self) -> Dict[str, List[str]]:
        """
        Get all available fix scripts organized by validation type.
        
        Returns:
            Dictionary mapping validation types to lists of script paths
        """
        fix_scripts = {}
        
        for validation_type in self.fix_script_manager.get_all_script_types():
            scripts = self.fix_script_manager.get_scripts_by_validation_type(validation_type)
            fix_scripts[validation_type] = [script.script_path for script in scripts]
        
        return fix_scripts
    
    def generate_deployment_summary(self, deployment_config: DeploymentConfig) -> Dict[str, Any]:
        """
        Generate a deployment summary with configuration details and validation status.
        
        Args:
            deployment_config: Configuration to summarize
            
        Returns:
            Dictionary with deployment summary information
        """
        summary = {
            'deployment_configuration': deployment_config.to_dict(),
            'validation_checks_available': len(self._validation_checks),
            'critical_checks': [check['name'] for check in self._validation_checks if check['critical']],
            'validation_region': self.region,
            'last_validation_status': None,
            'last_validation_timestamp': None
        }
        
        if self._last_validation_report:
            summary.update({
                'last_validation_status': 'PASSED' if self._last_validation_report.overall_status else 'FAILED',
                'last_validation_timestamp': self._last_validation_report.timestamp.isoformat(),
                'last_validation_summary': {
                    'total_checks': self._last_validation_report.total_checks,
                    'passed_checks': self._last_validation_report.passed_checks,
                    'failed_checks': self._last_validation_report.failed_checks
                }
            })
        
        return summary
    
    def is_deployment_ready(self) -> bool:
        """
        Check if the last validation indicates deployment readiness.
        
        Returns:
            True if deployment is ready, False otherwise
        """
        if self._last_validation_report is None:
            return False
        
        return self._last_validation_report.overall_status
    
    def get_failed_checks(self) -> List[str]:
        """
        Get the names of checks that failed in the last validation.
        
        Returns:
            List of failed check names, empty if no validation run or all passed
        """
        if self._last_validation_report is None:
            return []
        
        return [
            result.check_name 
            for result in self._last_validation_report.checks_performed 
            if not result.passed
        ]
    
    def reset_validation_state(self):
        """Reset the validation state, clearing any cached results."""
        self._last_validation_report = None
        self._current_profile = None
        self.logger.info("Validation state reset - ready for new validation run")
    
    def _execute_pipeline_hooks_sync(self, trigger_event: str, 
                                   validation_report: Optional[ValidationReport]):
        """
        Synchronous wrapper for executing pipeline hooks.
        
        Args:
            trigger_event: Event that triggered the hooks
            validation_report: Validation report (may be None for pre-validation hooks)
        """
        try:
            import asyncio

            # Log the hook execution
            self.logger.info(f"Pipeline hook trigger: {trigger_event}")
            
            if validation_report:
                self.logger.info(f"Validation status: {validation_report.overall_status}")
            
            # Execute the async hook in a new event loop if not already in one
            try:
                loop = asyncio.get_running_loop()
                # We're already in an async context, create a task
                asyncio.create_task(
                    self._execute_pipeline_hooks(trigger_event, validation_report)
                )
            except RuntimeError:
                # No running event loop, create one and run
                asyncio.run(
                    self._execute_pipeline_hooks(trigger_event, validation_report)
                )
            
        except Exception as e:
            self.logger.error(f"Error executing pipeline hooks for {trigger_event}: {str(e)}")

    async def _execute_pipeline_hooks(self, trigger_event: str, 
                                    validation_report: Optional[ValidationReport]):
        """
        Execute pipeline hooks for a specific trigger event.
        
        Args:
            trigger_event: Event that triggered the hooks
            validation_report: Validation report (may be None for pre-validation hooks)
        """
        try:
            if validation_report:
                hook_results = await self.pipeline_manager.execute_hooks_for_event(
                    trigger_event, validation_report
                )
            else:
                # For pre-validation hooks, create a minimal report
                from .models import DeploymentConfig
                dummy_config = DeploymentConfig(
                    task_definition_arn="",
                    iam_role_arn="",
                    load_balancer_arn="",
                    target_environment="unknown"
                )
                dummy_report = ValidationReport(
                    overall_status=True,
                    timestamp=datetime.utcnow(),
                    checks_performed=[],
                    deployment_config=dummy_config
                )
                hook_results = await self.pipeline_manager.execute_hooks_for_event(
                    trigger_event, dummy_report
                )
            
            # Log hook execution results
            for result in hook_results:
                if result.success:
                    self.logger.info(f"Hook {result.hook_name} executed successfully")
                else:
                    self.logger.warning(f"Hook {result.hook_name} failed: {result.message}")
                    
        except Exception as e:
            self.logger.error(f"Error executing pipeline hooks for {trigger_event}: {str(e)}")
    
    def validate_with_profile(self, profile_name: str, **deployment_config_overrides) -> ValidationResult:
        """
        Validate deployment using a specific environment profile.
        
        Args:
            profile_name: Name of the environment profile to use
            **deployment_config_overrides: Override values for deployment configuration
            
        Returns:
            ValidationResult from validation
        """
        try:
            # Create deployment config from profile
            deployment_config = self.config_manager.create_deployment_config_from_profile(
                profile_name, **deployment_config_overrides
            )
            
            # Run validation with the profile
            return self.validate_deployment_readiness(deployment_config, profile_name)
            
        except Exception as e:
            self.logger.error(f"Error validating with profile {profile_name}: {str(e)}")
            return ValidationResult(
                check_name="Profile-based Validation",
                status=ValidationStatus.ERROR,
                message=f"Profile validation failed: {str(e)}",
                details={'profile_name': profile_name, 'error_type': type(e).__name__}
            )
    
    def get_profile_summary(self, profile_name: str) -> Dict[str, Any]:
        """
        Get summary information about an environment profile.
        
        Args:
            profile_name: Name of the profile
            
        Returns:
            Dictionary with profile summary information
        """
        try:
            profile = self.config_manager.get_environment_profile(profile_name)
            thresholds = self.config_manager.get_validation_thresholds(profile_name)
            enabled_validations = self.config_manager.get_enabled_validations(profile_name)
            
            return {
                'profile_name': profile.name,
                'environment_type': profile.environment_type.value,
                'description': profile.description,
                'default_region': profile.default_region,
                'allowed_regions': profile.allowed_regions,
                'enabled_validations': enabled_validations,
                'validation_thresholds': thresholds.to_dict(),
                'pipeline_hooks': list(profile.pipeline_hooks.keys()) if profile.pipeline_hooks else [],
                'additional_config_keys': list(profile.additional_config.keys()) if profile.additional_config else []
            }
            
        except Exception as e:
            return {
                'error': f"Failed to get profile summary: {str(e)}",
                'profile_name': profile_name
            }
    
    def list_available_profiles(self) -> List[Dict[str, Any]]:
        """
        List all available environment profiles with summary information.
        
        Returns:
            List of profile summary dictionaries
        """
        profiles = []
        
        for profile_name in self.config_manager.list_profiles():
            profile_summary = self.get_profile_summary(profile_name)
            profiles.append(profile_summary)
        
        return profiles
    
    def get_pipeline_hooks_summary(self) -> Dict[str, Any]:
        """
        Get summary of all configured pipeline hooks.
        
        Returns:
            Dictionary with pipeline hooks summary
        """
        hooks_summary = {
            'total_hooks': len(self.config_manager.list_pipeline_hooks()),
            'hooks_by_event': {},
            'hooks_by_type': {},
            'enabled_hooks': [],
            'disabled_hooks': []
        }
        
        for hook_name in self.config_manager.list_pipeline_hooks():
            try:
                hook = self.config_manager.get_pipeline_hook(hook_name)
                
                # Group by trigger event
                if hook.trigger_event not in hooks_summary['hooks_by_event']:
                    hooks_summary['hooks_by_event'][hook.trigger_event] = []
                hooks_summary['hooks_by_event'][hook.trigger_event].append(hook_name)
                
                # Group by hook type
                if hook.hook_type not in hooks_summary['hooks_by_type']:
                    hooks_summary['hooks_by_type'][hook.hook_type] = []
                hooks_summary['hooks_by_type'][hook.hook_type].append(hook_name)
                
                # Track enabled/disabled status
                if hook.enabled:
                    hooks_summary['enabled_hooks'].append(hook_name)
                else:
                    hooks_summary['disabled_hooks'].append(hook_name)
                    
            except Exception as e:
                self.logger.warning(f"Error processing hook {hook_name}: {str(e)}")
        
        return hooks_summary
    
    def test_pipeline_hook(self, hook_name: str) -> Dict[str, Any]:
        """
        Test a specific pipeline hook with dummy data.
        
        Args:
            hook_name: Name of the hook to test
            
        Returns:
            Dictionary with test results
        """
        try:
            result = self.pipeline_manager.test_hook(hook_name)
            return result.to_dict()
        except Exception as e:
            return {
                'hook_name': hook_name,
                'success': False,
                'message': f"Hook test failed: {str(e)}",
                'execution_time': 0.0,
                'error_type': type(e).__name__
            }
