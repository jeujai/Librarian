#!/usr/bin/env python3
"""
Example usage of the FixScriptManager for production deployment validation.

This script demonstrates how to use the FixScriptManager to get remediation
guidance for failed deployment validations.
"""

from fix_script_manager import FixScriptManager


def main():
    """Demonstrate FixScriptManager usage."""
    
    print("🔧 FixScriptManager Usage Example")
    print("=" * 50)
    
    # Initialize the manager
    manager = FixScriptManager()
    
    # Example 1: Get scripts for specific validation types
    print("\n1. Getting scripts by validation type:")
    iam_scripts = manager.get_iam_fix_scripts()
    print(f"   IAM scripts: {len(iam_scripts)}")
    for script in iam_scripts:
        print(f"   - {script.script_path}")
    
    # Example 2: Generate remediation guide for failed validations
    print("\n2. Generating remediation guide:")
    failed_checks = [
        "IAM Permissions Check",
        "Storage Configuration Check"
    ]
    
    guide = manager.generate_remediation_guide(failed_checks)
    print(f"   Generated guide for {len(failed_checks)} failed checks")
    print(f"   Available fix scripts: {len(guide.script_references)}")
    
    # Example 3: Get remediation summary
    print("\n3. Getting remediation summary:")
    summary = manager.get_remediation_summary(failed_checks)
    print(f"   Summary: {summary}")
    
    # Example 4: List all available validation types
    print("\n4. Available validation types:")
    types = manager.get_all_script_types()
    for validation_type in types:
        scripts = manager.get_scripts_by_validation_type(validation_type)
        print(f"   - {validation_type}: {len(scripts)} scripts")
    
    print("\n✅ Example completed!")


if __name__ == "__main__":
    main()