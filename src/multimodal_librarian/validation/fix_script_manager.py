"""
Fix Script Reference Manager for Production Deployment Validation

This module manages references to fix scripts and provides remediation guidance
for failed deployment validations. It maintains a catalog of available fix scripts
and generates comprehensive remediation guides based on validation failures.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from .models import ScriptReference, RemediationGuide


class FixScriptManager:
    """
    Manages references to fix scripts and provides remediation guidance.
    
    This class maintains a catalog of available fix scripts organized by validation type
    and generates comprehensive remediation guides when validations fail.
    """
    
    def __init__(self, scripts_base_path: Optional[str] = None):
        """
        Initialize the FixScriptManager.
        
        Args:
            scripts_base_path: Base path to the scripts directory. If None, uses 'scripts/'
        """
        self.scripts_base_path = scripts_base_path or "scripts/"
        self._script_catalog = self._build_script_catalog()
    
    def _build_script_catalog(self) -> Dict[str, List[ScriptReference]]:
        """
        Build the catalog of available fix scripts organized by validation type.
        
        Returns:
            Dictionary mapping validation types to lists of script references
        """
        catalog = {
            "iam_permissions": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-iam-secrets-permissions.py"),
                    description="Fix IAM permissions for ECS task role to access Secrets Manager",
                    validation_type="iam_permissions",
                    usage_instructions="Run: python scripts/fix-iam-secrets-permissions.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-iam-secrets-permissions-correct.py"),
                    description="Corrected version of IAM permissions fix with enhanced error handling",
                    validation_type="iam_permissions",
                    usage_instructions="Run: python scripts/fix-iam-secrets-permissions-correct.py"
                )
            ],
            "storage_configuration": [
                ScriptReference(
                    script_path="task-definition-update.json",
                    description="Updated ECS task definition with 50GB ephemeral storage configuration",
                    validation_type="storage_configuration",
                    usage_instructions="Update your task definition using: aws ecs register-task-definition --cli-input-json file://task-definition-update.json"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-task-definition-secrets.py"),
                    description="Fix task definition secrets configuration and storage settings",
                    validation_type="storage_configuration",
                    usage_instructions="Run: python scripts/fix-task-definition-secrets.py"
                )
            ],
            "ssl_configuration": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "add-https-ssl-support.py"),
                    description="Add HTTPS/SSL support to load balancer with certificate management",
                    validation_type="ssl_configuration",
                    usage_instructions="Run: python scripts/add-https-ssl-support.py"
                )
            ],
            "networking": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "comprehensive-networking-fix.py"),
                    description="Comprehensive networking configuration fix for production deployment",
                    validation_type="networking",
                    usage_instructions="Run: python scripts/comprehensive-networking-fix.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-vpc-security-group-mismatch.py"),
                    description="Fix VPC and security group configuration mismatches",
                    validation_type="networking",
                    usage_instructions="Run: python scripts/fix-vpc-security-group-mismatch.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-subnet-mismatch.py"),
                    description="Fix subnet configuration and availability zone compatibility issues",
                    validation_type="networking",
                    usage_instructions="Run: python scripts/fix-subnet-mismatch.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-load-balancer-target-registration.py"),
                    description="Fix load balancer target group registration and listener mapping",
                    validation_type="networking",
                    usage_instructions="Run: python scripts/fix-load-balancer-target-registration.py"
                )
            ],
            "network_config": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "comprehensive-networking-fix.py"),
                    description="Comprehensive networking configuration fix for production deployment",
                    validation_type="network_config",
                    usage_instructions="Run: python scripts/comprehensive-networking-fix.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-vpc-security-group-mismatch.py"),
                    description="Fix VPC and security group configuration mismatches",
                    validation_type="network_config",
                    usage_instructions="Run: python scripts/fix-vpc-security-group-mismatch.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-subnet-mismatch.py"),
                    description="Fix subnet configuration and availability zone compatibility issues",
                    validation_type="network_config",
                    usage_instructions="Run: python scripts/fix-subnet-mismatch.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-load-balancer-target-registration.py"),
                    description="Fix load balancer target group registration and listener mapping",
                    validation_type="network_config",
                    usage_instructions="Run: python scripts/fix-load-balancer-target-registration.py"
                )
            ],
            "task_definition": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-task-definition-secrets.py"),
                    description="Fix task definition secrets configuration and storage settings",
                    validation_type="task_definition",
                    usage_instructions="Run: python scripts/fix-task-definition-secrets.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "fix-task-definition-secret-names.py"),
                    description="Fix task definition secret names and ARN format issues",
                    validation_type="task_definition",
                    usage_instructions="Run: python scripts/fix-task-definition-secret-names.py"
                ),
                ScriptReference(
                    script_path="task-definition-update.json",
                    description="Updated ECS task definition with proper storage and secrets configuration",
                    validation_type="task_definition",
                    usage_instructions="Update your task definition using: aws ecs register-task-definition --cli-input-json file://task-definition-update.json"
                )
            ],
            "production_deployment": [
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "comprehensive-production-fix.py"),
                    description="Comprehensive production deployment fix addressing multiple issues",
                    validation_type="production_deployment",
                    usage_instructions="Run: python scripts/comprehensive-production-fix.py"
                ),
                ScriptReference(
                    script_path=os.path.join(self.scripts_base_path, "restore-full-production-environment-scaled.py"),
                    description="Restore full production environment with proper scaling",
                    validation_type="production_deployment",
                    usage_instructions="Run: python scripts/restore-full-production-environment-scaled.py"
                )
            ]
        }
        
        return catalog
    
    def get_iam_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for IAM permission issues.
        
        Returns:
            List of ScriptReference objects for IAM fixes
        """
        return self._script_catalog.get("iam_permissions", [])
    
    def get_storage_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for storage configuration issues.
        
        Returns:
            List of ScriptReference objects for storage fixes
        """
        return self._script_catalog.get("storage_configuration", [])
    
    def get_ssl_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for SSL/HTTPS configuration issues.
        
        Returns:
            List of ScriptReference objects for SSL fixes
        """
        return self._script_catalog.get("ssl_configuration", [])
    
    def get_networking_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for networking configuration issues.
        
        Returns:
            List of ScriptReference objects for networking fixes
        """
        return self._script_catalog.get("networking", [])
    
    def get_production_deployment_fix_scripts(self) -> List[ScriptReference]:
        """
        Get fix scripts for general production deployment issues.
        
        Returns:
            List of ScriptReference objects for production deployment fixes
        """
        return self._script_catalog.get("production_deployment", [])
    
    def get_scripts_by_validation_type(self, validation_type: str) -> List[ScriptReference]:
        """
        Get fix scripts for a specific validation type.
        
        Args:
            validation_type: The type of validation (e.g., 'iam_permissions', 'ssl_configuration')
        
        Returns:
            List of ScriptReference objects for the specified validation type
        """
        return self._script_catalog.get(validation_type, [])
    
    def get_all_script_types(self) -> List[str]:
        """
        Get all available validation types that have fix scripts.
        
        Returns:
            List of validation type names
        """
        return list(self._script_catalog.keys())
    
    def generate_remediation_guide(self, failed_checks: List[str]) -> RemediationGuide:
        """
        Generate a comprehensive remediation guide for failed validation checks.
        
        Args:
            failed_checks: List of failed validation check names
        
        Returns:
            RemediationGuide object with step-by-step instructions and script references
        """
        # Map check names to validation types
        check_to_validation_type = {
            "IAM Permissions Check": "iam_permissions",
            "IAM Secrets Manager Access": "iam_permissions", 
            "iam_permissions": "iam_permissions",  # Direct mapping
            "Storage Configuration Check": "storage_configuration",
            "Ephemeral Storage Validation": "storage_configuration",
            "storage_configuration": "storage_configuration",  # Direct mapping
            "SSL Configuration Check": "ssl_configuration",
            "HTTPS Listener Validation": "ssl_configuration",
            "Certificate Validation": "ssl_configuration",
            "Security Headers Check": "ssl_configuration",
            "Load Balancer SSL": "ssl_configuration",
            "ssl_configuration": "ssl_configuration",  # Direct mapping
            "Network Configuration": "network_config",
            "Network Configuration Validation": "network_config",
            "VPC Compatibility": "network_config",
            "Target Group Mapping": "network_config",
            "Subnet Configuration": "network_config",
            "Security Group Rules": "network_config",
            "VPC Configuration": "networking",
            "Security Group Configuration": "networking",
            "networking": "networking",  # Direct mapping
            "network_config": "network_config",  # Direct mapping
            "Task Definition Validation": "task_definition",
            "Task Definition Registration": "task_definition",
            "Task Definition Storage": "task_definition",
            "Task Definition Consistency": "task_definition",
            "Task Definition Revision": "task_definition",
            "task_definition": "task_definition"  # Direct mapping
        }
        
        # Collect relevant script references
        relevant_scripts = []
        validation_types_needed = set()
        
        for check in failed_checks:
            validation_type = check_to_validation_type.get(check)
            if validation_type:
                validation_types_needed.add(validation_type)
        
        # Add scripts for each needed validation type
        for validation_type in validation_types_needed:
            scripts = self.get_scripts_by_validation_type(validation_type)
            relevant_scripts.extend(scripts)
        
        # Generate step-by-step instructions
        instructions = self._generate_step_by_step_instructions(failed_checks, validation_types_needed)
        
        # Additional resources
        additional_resources = [
            "AWS ECS Task Definition Documentation: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html",
            "AWS IAM Roles for Tasks: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html",
            "AWS Certificate Manager: https://docs.aws.amazon.com/acm/latest/userguide/",
            "AWS Application Load Balancer: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/"
        ]
        
        return RemediationGuide(
            failed_checks=failed_checks,
            script_references=relevant_scripts,
            step_by_step_instructions=instructions,
            additional_resources=additional_resources
        )
    
    def _generate_step_by_step_instructions(self, failed_checks: List[str], validation_types: set) -> List[str]:
        """
        Generate step-by-step remediation instructions based on failed checks.
        
        Args:
            failed_checks: List of failed validation check names
            validation_types: Set of validation types that need remediation
        
        Returns:
            List of step-by-step instruction strings
        """
        instructions = [
            "🚨 Production Deployment Validation Failed",
            "Follow these steps to remediate the issues:",
            ""
        ]
        
        step_counter = 1
        
        if "iam_permissions" in validation_types:
            instructions.extend([
                f"{step_counter}. Fix IAM Permissions:",
                "   - Run the IAM permissions fix script to grant Secrets Manager access",
                "   - Verify the ECS task role has the required permissions",
                "   - Test secret retrieval to confirm the fix",
                ""
            ])
            step_counter += 1
        
        if "storage_configuration" in validation_types:
            instructions.extend([
                f"{step_counter}. Fix Storage Configuration:",
                "   - Update the ECS task definition to allocate minimum 30GB ephemeral storage",
                "   - Register the updated task definition with AWS ECS",
                "   - Verify the new task definition is active",
                ""
            ])
            step_counter += 1
        
        if "ssl_configuration" in validation_types:
            instructions.extend([
                f"{step_counter}. Fix SSL/HTTPS Configuration:",
                "   - Request or import SSL certificate in AWS Certificate Manager",
                "   - Add HTTPS listener (port 443) to the load balancer",
                "   - Configure HTTP to HTTPS redirect for security",
                "   - Verify SSL certificate is properly attached and valid",
                ""
            ])
            step_counter += 1
        
        if "network_config" in validation_types:
            instructions.extend([
                f"{step_counter}. Fix Network Configuration:",
                "   - Verify VPC compatibility between load balancer and ECS service",
                "   - Check target group mapping to load balancer listeners",
                "   - Validate subnet configuration and availability zone compatibility",
                "   - Ensure security group rules allow required port access",
                ""
            ])
            step_counter += 1
        
        if "task_definition" in validation_types:
            instructions.extend([
                f"{step_counter}. Fix Task Definition Issues:",
                "   - Ensure task definition is properly registered and active",
                "   - Verify storage configuration meets minimum requirements",
                "   - Check consistency between local and registered task definitions",
                "   - Ensure latest revision is being used for validation",
                ""
            ])
            step_counter += 1
        
        instructions.extend([
            f"{step_counter}. Re-run Validation:",
            "   - Execute the deployment validation checklist again",
            "   - Verify all checks now pass before proceeding with deployment",
            "   - Review the validation report for any remaining issues",
            "",
            "⚠️  Important: Do not proceed with production deployment until all validations pass!"
        ])
        
        return instructions
    
    def validate_script_exists(self, script_reference: ScriptReference) -> bool:
        """
        Validate that a referenced script actually exists on the filesystem.
        
        Args:
            script_reference: ScriptReference object to validate
        
        Returns:
            True if the script exists, False otherwise
        """
        script_path = Path(script_reference.script_path)
        return script_path.exists() and script_path.is_file()
    
    def get_missing_scripts(self) -> List[ScriptReference]:
        """
        Get a list of script references that point to non-existent files.
        
        Returns:
            List of ScriptReference objects for missing scripts
        """
        missing_scripts = []
        
        for validation_type, scripts in self._script_catalog.items():
            for script in scripts:
                if not self.validate_script_exists(script):
                    missing_scripts.append(script)
        
        return missing_scripts
    
    def get_all_script_references(self) -> List[ScriptReference]:
        """
        Get all script references from all validation types.
        
        Returns:
            List of all ScriptReference objects across all validation types
        """
        all_scripts = []
        for validation_type, scripts in self._script_catalog.items():
            all_scripts.extend(scripts)
        return all_scripts
    
    def get_remediation_summary(self, failed_checks: List[str]) -> str:
        """
        Generate a brief remediation summary for failed checks.
        
        Args:
            failed_checks: List of failed validation check names
        
        Returns:
            Brief summary string describing the remediation approach
        """
        if not failed_checks:
            return "All validations passed. No remediation needed."
        
        remediation_guide = self.generate_remediation_guide(failed_checks)
        script_count = len(remediation_guide.script_references)
        
        return (
            f"Found {len(failed_checks)} failed validation(s). "
            f"Remediation available through {script_count} fix script(s). "
            f"See detailed remediation guide for step-by-step instructions."
        )