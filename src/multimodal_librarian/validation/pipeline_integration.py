"""
Deployment Pipeline Integration for Production Deployment Validation

This module provides integration hooks for deployment pipelines including:
- Webhook notifications
- Script execution
- AWS Lambda integration
- SNS notifications
"""

import json
import logging
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import asyncio
import aiohttp

try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

from .models import ValidationReport, ValidationResult
from .config_manager import PipelineHook, ConfigurationManager


class PipelineIntegrationError(Exception):
    """Raised when pipeline integration fails."""
    pass


class HookExecutionResult:
    """Result of executing a pipeline hook."""
    
    def __init__(self, hook_name: str, success: bool, message: str, 
                 execution_time: float, details: Optional[Dict[str, Any]] = None):
        self.hook_name = hook_name
        self.success = success
        self.message = message
        self.execution_time = execution_time
        self.details = details or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'hook_name': self.hook_name,
            'success': self.success,
            'message': self.message,
            'execution_time': self.execution_time,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


class PipelineIntegrationManager:
    """
    Manages deployment pipeline integration hooks.
    
    Provides execution of various hook types including webhooks, scripts,
    AWS Lambda functions, and SNS notifications.
    """
    
    def __init__(self, config_manager: ConfigurationManager):
        """
        Initialize pipeline integration manager.
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize AWS clients if available
        self._aws_lambda_client = None
        self._aws_sns_client = None
        
        if AWS_AVAILABLE:
            try:
                self._aws_lambda_client = boto3.client('lambda')
                self._aws_sns_client = boto3.client('sns')
            except Exception as e:
                self.logger.warning(f"Failed to initialize AWS clients: {e}")
    
    async def execute_hooks_for_event(self, trigger_event: str, 
                                    validation_report: ValidationReport) -> List[HookExecutionResult]:
        """
        Execute all hooks for a specific trigger event.
        
        Args:
            trigger_event: Event that triggered the hooks
            validation_report: Validation report to pass to hooks
            
        Returns:
            List of HookExecutionResult objects
        """
        hooks = self.config_manager.get_pipeline_hooks_for_event(trigger_event)
        
        if not hooks:
            self.logger.debug(f"No hooks configured for event: {trigger_event}")
            return []
        
        self.logger.info(f"Executing {len(hooks)} hooks for event: {trigger_event}")
        
        results = []
        
        # Execute hooks concurrently where possible
        tasks = []
        for hook in hooks:
            task = self._execute_single_hook(hook, validation_report)
            tasks.append(task)
        
        # Wait for all hooks to complete
        hook_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(hook_results):
            if isinstance(result, Exception):
                # Handle exceptions from hook execution
                error_result = HookExecutionResult(
                    hook_name=hooks[i].name,
                    success=False,
                    message=f"Hook execution failed: {str(result)}",
                    execution_time=0.0,
                    details={'error_type': type(result).__name__}
                )
                results.append(error_result)
            else:
                results.append(result)
        
        # Log summary
        successful_hooks = sum(1 for r in results if r.success)
        self.logger.info(f"Hook execution complete: {successful_hooks}/{len(results)} successful")
        
        return results
    
    async def _execute_single_hook(self, hook: PipelineHook, 
                                 validation_report: ValidationReport) -> HookExecutionResult:
        """
        Execute a single pipeline hook.
        
        Args:
            hook: Pipeline hook to execute
            validation_report: Validation report to pass to hook
            
        Returns:
            HookExecutionResult
        """
        start_time = time.time()
        
        try:
            self.logger.debug(f"Executing hook: {hook.name} ({hook.hook_type})")
            
            # Prepare context data for the hook
            context = self._prepare_hook_context(validation_report, hook)
            
            # Execute based on hook type
            if hook.hook_type == 'webhook':
                result = await self._execute_webhook_hook(hook, context)
            elif hook.hook_type == 'script':
                result = await self._execute_script_hook(hook, context)
            elif hook.hook_type == 'aws_lambda':
                result = await self._execute_lambda_hook(hook, context)
            elif hook.hook_type == 'sns':
                result = await self._execute_sns_hook(hook, context)
            else:
                raise PipelineIntegrationError(f"Unsupported hook type: {hook.hook_type}")
            
            execution_time = time.time() - start_time
            
            return HookExecutionResult(
                hook_name=hook.name,
                success=True,
                message=result.get('message', 'Hook executed successfully'),
                execution_time=execution_time,
                details=result
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            self.logger.error(f"Hook {hook.name} failed: {str(e)}")
            
            # Retry if configured
            if hook.retry_on_failure and hook.max_retries > 0:
                return await self._retry_hook_execution(hook, validation_report, e, execution_time)
            
            return HookExecutionResult(
                hook_name=hook.name,
                success=False,
                message=f"Hook execution failed: {str(e)}",
                execution_time=execution_time,
                details={'error_type': type(e).__name__, 'error_message': str(e)}
            )
    
    async def _retry_hook_execution(self, hook: PipelineHook, validation_report: ValidationReport,
                                  original_error: Exception, original_execution_time: float) -> HookExecutionResult:
        """
        Retry hook execution with exponential backoff.
        
        Args:
            hook: Pipeline hook to retry
            validation_report: Validation report
            original_error: Original error that caused retry
            original_execution_time: Time of original execution
            
        Returns:
            HookExecutionResult from retry attempt
        """
        self.logger.info(f"Retrying hook {hook.name} (max retries: {hook.max_retries})")
        
        for attempt in range(hook.max_retries):
            try:
                # Exponential backoff
                delay = (2 ** attempt) * 1.0  # 1s, 2s, 4s, etc.
                await asyncio.sleep(delay)
                
                self.logger.debug(f"Retry attempt {attempt + 1} for hook: {hook.name}")
                
                # Execute the hook again
                result = await self._execute_single_hook(hook, validation_report)
                
                if result.success:
                    self.logger.info(f"Hook {hook.name} succeeded on retry attempt {attempt + 1}")
                    result.details['retry_attempt'] = attempt + 1
                    result.details['original_error'] = str(original_error)
                    return result
                
            except Exception as e:
                self.logger.warning(f"Retry attempt {attempt + 1} failed for hook {hook.name}: {str(e)}")
                if attempt == hook.max_retries - 1:
                    # Last attempt failed
                    return HookExecutionResult(
                        hook_name=hook.name,
                        success=False,
                        message=f"Hook failed after {hook.max_retries} retries. Last error: {str(e)}",
                        execution_time=original_execution_time,
                        details={
                            'retry_attempts': hook.max_retries,
                            'original_error': str(original_error),
                            'final_error': str(e)
                        }
                    )
        
        # Should not reach here, but handle gracefully
        return HookExecutionResult(
            hook_name=hook.name,
            success=False,
            message=f"Hook failed after retries",
            execution_time=original_execution_time,
            details={'original_error': str(original_error)}
        )
    
    def _prepare_hook_context(self, validation_report: ValidationReport, 
                            hook: PipelineHook) -> Dict[str, Any]:
        """
        Prepare context data for hook execution.
        
        Args:
            validation_report: Validation report
            hook: Pipeline hook configuration
            
        Returns:
            Context dictionary with template variables
        """
        # Extract key information from validation report
        failed_checks = [
            result.check_name for result in validation_report.checks_performed 
            if not result.passed
        ]
        
        passed_checks = [
            result.check_name for result in validation_report.checks_performed 
            if result.passed
        ]
        
        context = {
            # Validation summary
            'overall_status': 'PASSED' if validation_report.overall_status else 'FAILED',
            'environment': validation_report.deployment_config.target_environment,
            'region': validation_report.deployment_config.region,
            'timestamp': validation_report.timestamp.isoformat(),
            
            # Check details
            'total_checks': validation_report.total_checks,
            'passed_checks': validation_report.passed_checks,
            'failed_checks': validation_report.failed_checks,
            'failed_check_names': failed_checks,
            'passed_check_names': passed_checks,
            'failed_checks_list': ', '.join(failed_checks) if failed_checks else 'None',
            
            # Deployment configuration
            'task_definition_arn': validation_report.deployment_config.task_definition_arn,
            'iam_role_arn': validation_report.deployment_config.iam_role_arn,
            'load_balancer_arn': validation_report.deployment_config.load_balancer_arn,
            
            # Remediation
            'remediation_summary': validation_report.remediation_summary or 'No remediation needed',
            
            # Hook metadata
            'hook_name': hook.name,
            'hook_type': hook.hook_type,
            'trigger_event': hook.trigger_event
        }
        
        return context
    
    async def _execute_webhook_hook(self, hook: PipelineHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a webhook hook.
        
        Args:
            hook: Webhook hook configuration
            context: Context data for the hook
            
        Returns:
            Result dictionary
        """
        if not hook.endpoint_url:
            raise PipelineIntegrationError("Webhook hook missing endpoint_url")
        
        # Prepare payload
        payload = self._render_template(hook.payload_template or '{}', context)
        
        try:
            payload_data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise PipelineIntegrationError(f"Invalid JSON payload template: {e}")
        
        # Prepare headers
        headers = dict(hook.headers)
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        
        # Execute webhook
        timeout = aiohttp.ClientTimeout(total=hook.timeout_seconds)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                hook.endpoint_url,
                json=payload_data,
                headers=headers
            ) as response:
                response_text = await response.text()
                
                if response.status >= 400:
                    raise PipelineIntegrationError(
                        f"Webhook returned status {response.status}: {response_text}"
                    )
                
                return {
                    'message': f'Webhook executed successfully (status: {response.status})',
                    'status_code': response.status,
                    'response_body': response_text[:500],  # Limit response size
                    'endpoint_url': hook.endpoint_url
                }
    
    async def _execute_script_hook(self, hook: PipelineHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a script hook.
        
        Args:
            hook: Script hook configuration
            context: Context data for the hook
            
        Returns:
            Result dictionary
        """
        if not hook.script_path:
            raise PipelineIntegrationError("Script hook missing script_path")
        
        script_path = Path(hook.script_path)
        
        if not script_path.exists():
            raise PipelineIntegrationError(f"Script not found: {hook.script_path}")
        
        if not script_path.is_file():
            raise PipelineIntegrationError(f"Script path is not a file: {hook.script_path}")
        
        # Prepare environment variables
        env = dict(hook.environment_variables)
        
        # Add context variables to environment
        for key, value in context.items():
            env_key = f"VALIDATION_{key.upper()}"
            env[env_key] = str(value)
        
        # Execute script
        try:
            result = subprocess.run(
                [str(script_path)],
                capture_output=True,
                text=True,
                timeout=hook.timeout_seconds,
                env=env,
                cwd=script_path.parent
            )
            
            if result.returncode != 0:
                raise PipelineIntegrationError(
                    f"Script exited with code {result.returncode}: {result.stderr}"
                )
            
            return {
                'message': 'Script executed successfully',
                'return_code': result.returncode,
                'stdout': result.stdout[:1000],  # Limit output size
                'stderr': result.stderr[:1000] if result.stderr else None,
                'script_path': str(script_path)
            }
            
        except subprocess.TimeoutExpired:
            raise PipelineIntegrationError(f"Script execution timed out after {hook.timeout_seconds}s")
    
    async def _execute_lambda_hook(self, hook: PipelineHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an AWS Lambda hook.
        
        Args:
            hook: Lambda hook configuration
            context: Context data for the hook
            
        Returns:
            Result dictionary
        """
        if not AWS_AVAILABLE:
            raise PipelineIntegrationError("boto3 is required for AWS Lambda hooks")
        
        if not self._aws_lambda_client:
            raise PipelineIntegrationError("AWS Lambda client not initialized")
        
        if not hook.lambda_function_arn:
            raise PipelineIntegrationError("Lambda hook missing lambda_function_arn")
        
        # Prepare payload
        payload = {
            'validation_context': context,
            'hook_config': {
                'name': hook.name,
                'trigger_event': hook.trigger_event
            }
        }
        
        try:
            # Invoke Lambda function
            response = self._aws_lambda_client.invoke(
                FunctionName=hook.lambda_function_arn,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = response['Payload'].read()
            
            if response.get('FunctionError'):
                raise PipelineIntegrationError(
                    f"Lambda function error: {response_payload.decode()}"
                )
            
            # Try to parse JSON response
            try:
                lambda_result = json.loads(response_payload.decode())
            except json.JSONDecodeError:
                lambda_result = {'raw_response': response_payload.decode()}
            
            return {
                'message': 'Lambda function executed successfully',
                'status_code': response['StatusCode'],
                'lambda_result': lambda_result,
                'function_arn': hook.lambda_function_arn
            }
            
        except Exception as e:
            raise PipelineIntegrationError(f"Lambda execution failed: {str(e)}")
    
    async def _execute_sns_hook(self, hook: PipelineHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an SNS notification hook.
        
        Args:
            hook: SNS hook configuration
            context: Context data for the hook
            
        Returns:
            Result dictionary
        """
        if not AWS_AVAILABLE:
            raise PipelineIntegrationError("boto3 is required for SNS hooks")
        
        if not self._aws_sns_client:
            raise PipelineIntegrationError("AWS SNS client not initialized")
        
        if not hook.sns_topic_arn:
            raise PipelineIntegrationError("SNS hook missing sns_topic_arn")
        
        # Prepare message
        message_template = hook.payload_template or (
            "Deployment validation {{overall_status}} for {{environment}}\n"
            "Checks: {{passed_checks}}/{{total_checks}} passed\n"
            "Failed checks: {{failed_checks_list}}"
        )
        
        message = self._render_template(message_template, context)
        
        # Prepare subject
        subject = f"Deployment Validation {context['overall_status']} - {context['environment']}"
        
        try:
            # Publish to SNS
            response = self._aws_sns_client.publish(
                TopicArn=hook.sns_topic_arn,
                Message=message,
                Subject=subject
            )
            
            return {
                'message': 'SNS notification sent successfully',
                'message_id': response['MessageId'],
                'topic_arn': hook.sns_topic_arn,
                'subject': subject
            }
            
        except Exception as e:
            raise PipelineIntegrationError(f"SNS publish failed: {str(e)}")
    
    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render a template string with context variables.
        
        Args:
            template: Template string with {{variable}} placeholders
            context: Context variables
            
        Returns:
            Rendered string
        """
        result = template
        
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        
        return result
    
    def execute_hooks_sync(self, trigger_event: str, 
                          validation_report: ValidationReport) -> List[HookExecutionResult]:
        """
        Synchronous wrapper for executing hooks.
        
        Args:
            trigger_event: Event that triggered the hooks
            validation_report: Validation report to pass to hooks
            
        Returns:
            List of HookExecutionResult objects
        """
        try:
            # Create new event loop if none exists
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                self.execute_hooks_for_event(trigger_event, validation_report)
            )
        finally:
            # Don't close the loop if it was already running
            if loop.is_running():
                pass
            else:
                loop.close()
    
    def test_hook(self, hook_name: str) -> HookExecutionResult:
        """
        Test a specific hook with dummy data.
        
        Args:
            hook_name: Name of the hook to test
            
        Returns:
            HookExecutionResult from test execution
        """
        try:
            hook = self.config_manager.get_pipeline_hook(hook_name)
        except Exception as e:
            return HookExecutionResult(
                hook_name=hook_name,
                success=False,
                message=f"Hook not found: {str(e)}",
                execution_time=0.0
            )
        
        # Create dummy validation report for testing
        from .models import DeploymentConfig, ValidationReport, ValidationResult, ValidationStatus
        
        dummy_config = DeploymentConfig(
            task_definition_arn="arn:aws:ecs:us-east-1:123456789012:task-definition/test:1",
            iam_role_arn="arn:aws:iam::123456789012:role/test-role",
            load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test-lb/1234567890123456",
            target_environment="test"
        )
        
        dummy_result = ValidationResult(
            check_name="Test Validation",
            status=ValidationStatus.PASSED,
            message="Test validation for hook testing"
        )
        
        dummy_report = ValidationReport(
            overall_status=True,
            timestamp=datetime.utcnow(),
            checks_performed=[dummy_result],
            deployment_config=dummy_config
        )
        
        # Execute hook with dummy data
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                self._execute_single_hook(hook, dummy_report)
            )
        finally:
            if not loop.is_running():
                loop.close()