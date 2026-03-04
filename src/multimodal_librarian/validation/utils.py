"""
Common utilities for the validation framework.

This module provides utility functions for ARN parsing, configuration validation,
and other common operations used across validators.
"""

import json
import re
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class ARNParser:
    """Utility class for parsing and validating AWS ARNs."""
    
    ARN_PATTERN = re.compile(
        r'^arn:aws:([^:]+):([^:]*):([^:]*):(.+)$'
    )
    
    @classmethod
    def parse(cls, arn: str) -> Dict[str, str]:
        """
        Parse AWS ARN into components.
        
        Args:
            arn: AWS ARN string
            
        Returns:
            Dictionary with ARN components
            
        Raises:
            ValidationError: If ARN format is invalid
        """
        if not isinstance(arn, str) or not arn.strip():
            raise ValidationError("ARN cannot be empty")
        
        match = cls.ARN_PATTERN.match(arn.strip())
        if not match:
            raise ValidationError(f"Invalid ARN format: {arn}")
        
        service, region, account_id, resource = match.groups()
        
        # Parse resource part
        resource_type = ""
        resource_id = ""
        
        if '/' in resource:
            resource_type, resource_id = resource.split('/', 1)
        elif ':' in resource:
            resource_type, resource_id = resource.split(':', 1)
        else:
            resource_type = resource
        
        return {
            'service': service,
            'region': region,
            'account_id': account_id,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'full_resource': resource
        }
    
    @classmethod
    def validate_service(cls, arn: str, expected_service: str) -> bool:
        """
        Validate that ARN is for expected service.
        
        Args:
            arn: ARN to validate
            expected_service: Expected AWS service
            
        Returns:
            True if ARN is for expected service
        """
        try:
            components = cls.parse(arn)
            return components['service'] == expected_service
        except ValidationError:
            return False
    
    @classmethod
    def extract_resource_name(cls, arn: str) -> str:
        """
        Extract resource name from ARN.
        
        Args:
            arn: ARN to parse
            
        Returns:
            Resource name/ID
        """
        components = cls.parse(arn)
        return components['resource_id'] or components['resource_type']


class ConfigurationValidator:
    """Utility class for validating configuration structures."""
    
    @staticmethod
    def validate_task_definition(task_def: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate and parse ECS task definition.
        
        Args:
            task_def: Task definition as JSON string or dict
            
        Returns:
            Parsed task definition dictionary
            
        Raises:
            ValidationError: If task definition is invalid
        """
        if isinstance(task_def, str):
            try:
                task_def = json.loads(task_def)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON in task definition: {e}")
        
        if not isinstance(task_def, dict):
            raise ValidationError("Task definition must be a dictionary")
        
        # Validate required fields
        required_fields = ['family', 'containerDefinitions']
        missing_fields = [field for field in required_fields if field not in task_def]
        
        if missing_fields:
            raise ValidationError(f"Task definition missing required fields: {missing_fields}")
        
        return task_def
    
    @staticmethod
    def extract_ephemeral_storage(task_def: Dict[str, Any]) -> Optional[int]:
        """
        Extract ephemeral storage configuration from task definition.
        
        Args:
            task_def: Task definition dictionary
            
        Returns:
            Ephemeral storage size in GB, or None if not configured
        """
        ephemeral_storage = task_def.get('ephemeralStorage', {})
        size_in_gib = ephemeral_storage.get('sizeInGiB')
        
        if size_in_gib is not None:
            try:
                return int(size_in_gib)
            except (ValueError, TypeError):
                raise ValidationError(f"Invalid ephemeral storage size: {size_in_gib}")
        
        return None
    
    @staticmethod
    def validate_url(url: str, require_https: bool = False) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL to validate
            require_https: Whether to require HTTPS scheme
            
        Returns:
            True if URL is valid
        """
        try:
            parsed = urlparse(url)
            
            if not parsed.scheme or not parsed.netloc:
                return False
            
            if require_https and parsed.scheme != 'https':
                return False
            
            return True
            
        except Exception:
            return False


class StorageCalculator:
    """Utility class for storage calculations and formatting."""
    
    STORAGE_UNITS = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4
    }
    
    @classmethod
    def format_bytes(cls, bytes_value: int) -> str:
        """
        Format bytes value in human-readable format.
        
        Args:
            bytes_value: Size in bytes
            
        Returns:
            Formatted string (e.g., "1.5 GB")
        """
        if bytes_value == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                if unit == 'B':
                    return f"{int(bytes_value)} {unit}"
                else:
                    return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        
        return f"{bytes_value:.1f} PB"
    
    @classmethod
    def gb_to_bytes(cls, gb_value: Union[int, float]) -> int:
        """
        Convert GB to bytes.
        
        Args:
            gb_value: Size in GB
            
        Returns:
            Size in bytes
        """
        return int(gb_value * cls.STORAGE_UNITS['GB'])
    
    @classmethod
    def bytes_to_gb(cls, bytes_value: int) -> float:
        """
        Convert bytes to GB.
        
        Args:
            bytes_value: Size in bytes
            
        Returns:
            Size in GB
        """
        return bytes_value / cls.STORAGE_UNITS['GB']


class ValidationReportFormatter:
    """Utility class for formatting validation reports."""
    
    @staticmethod
    def format_console_report(validation_report) -> str:
        """
        Format validation report for console output.
        
        Args:
            validation_report: ValidationReport instance
            
        Returns:
            Formatted string for console display
        """
        lines = []
        lines.append("=" * 60)
        lines.append("PRODUCTION DEPLOYMENT VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Environment: {validation_report.deployment_config.target_environment}")
        lines.append(f"Timestamp: {validation_report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Overall Status: {'✅ PASSED' if validation_report.overall_status else '❌ FAILED'}")
        lines.append(f"Checks: {validation_report.passed_checks}/{validation_report.total_checks} passed")
        lines.append("")
        
        # Individual check results
        lines.append("VALIDATION RESULTS:")
        lines.append("-" * 40)
        
        for result in validation_report.checks_performed:
            status_icon = "✅" if result.passed else "❌"
            lines.append(f"{status_icon} {result.check_name}")
            lines.append(f"   {result.message}")
            
            if result.remediation_steps:
                lines.append("   Remediation steps:")
                for step in result.remediation_steps:
                    lines.append(f"   - {step}")
            
            if result.fix_scripts:
                lines.append("   Fix scripts:")
                for script in result.fix_scripts:
                    lines.append(f"   - {script}")
            
            lines.append("")
        
        if validation_report.remediation_summary:
            lines.append("REMEDIATION SUMMARY:")
            lines.append("-" * 40)
            lines.append(validation_report.remediation_summary)
        
        lines.append("=" * 60)
        return "\n".join(lines)
    
    @staticmethod
    def format_json_report(validation_report) -> str:
        """
        Format validation report as JSON.
        
        Args:
            validation_report: ValidationReport instance
            
        Returns:
            JSON string
        """
        return json.dumps(validation_report.to_dict(), indent=2)


class ScriptPathResolver:
    """Utility class for resolving fix script paths."""
    
    SCRIPT_MAPPINGS = {
        'iam_permissions': [
            'scripts/fix-iam-secrets-permissions.py',
            'scripts/fix-iam-secrets-permissions-correct.py'
        ],
        'storage_configuration': [
            'task-definition-update.json'
        ],
        'ssl_configuration': [
            'scripts/add-https-ssl-support.py'
        ]
    }
    
    @classmethod
    def get_fix_scripts(cls, validation_type: str) -> List[str]:
        """
        Get fix scripts for a validation type.
        
        Args:
            validation_type: Type of validation that failed
            
        Returns:
            List of script paths
        """
        return cls.SCRIPT_MAPPINGS.get(validation_type, [])
    
    @classmethod
    def get_all_scripts(cls) -> Dict[str, List[str]]:
        """
        Get all available fix scripts.
        
        Returns:
            Dictionary mapping validation types to script lists
        """
        return cls.SCRIPT_MAPPINGS.copy()