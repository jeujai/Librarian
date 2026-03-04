#!/usr/bin/env python3
"""
Demo script to show CLI interactive features.
"""

import subprocess
import sys
import tempfile
import json

def demo_cli_features():
    """Demonstrate CLI features."""
    print("🚀 Production Deployment Validation CLI Demo")
    print("=" * 60)
    
    # Create example config
    config = {
        "task_definition_arn": "arn:aws:ecs:us-east-1:123456789012:task-definition/multimodal-librarian:1",
        "iam_role_arn": "arn:aws:iam::123456789012:role/multimodal-librarian-task-role",
        "load_balancer_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/multimodal-librarian-lb/1234567890123456",
        "target_environment": "production",
        "region": "us-east-1",
        "ssl_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        config_file = f.name
    
    print(f"1. Configuration file created: {config_file}")
    print("\n2. Running validation with progress indicators...")
    
    # Run CLI with progress indicators
    result = subprocess.run([
        sys.executable, '-m', 'multimodal_librarian.validation.cli',
        '--config', config_file,
        '--show-progress',
        '--output-format', 'console'
    ], cwd='src')
    
    print(f"\n3. Validation completed with exit code: {result.returncode}")
    
    print("\n4. Running validation with JSON output...")
    
    # Run CLI with JSON output
    result = subprocess.run([
        sys.executable, '-m', 'multimodal_librarian.validation.cli',
        '--config', config_file,
        '--output-format', 'json'
    ], capture_output=True, text=True, cwd='src')
    
    if result.stdout:
        try:
            report = json.loads(result.stdout)
            print(f"   - Overall status: {report.get('overall_status', 'Unknown')}")
            print(f"   - Total checks: {report.get('total_checks', 0)}")
            print(f"   - Passed checks: {report.get('passed_checks', 0)}")
            print(f"   - Failed checks: {report.get('failed_checks', 0)}")
        except json.JSONDecodeError:
            print("   - Could not parse JSON output")
    
    print("\n5. CLI Features Summary:")
    print("   ✅ Command line argument parsing")
    print("   ✅ Configuration file support (JSON/YAML)")
    print("   ✅ Interactive mode (--interactive)")
    print("   ✅ Progress indicators (--show-progress)")
    print("   ✅ Multiple output formats (console/json)")
    print("   ✅ Verbose and debug logging")
    print("   ✅ File output support")
    print("   ✅ Error handling and exit codes")
    
    print("\n6. Usage Examples:")
    print("   # Interactive mode:")
    print("   python -m multimodal_librarian.validation.cli --interactive")
    print()
    print("   # Config file with progress:")
    print("   python -m multimodal_librarian.validation.cli --config config.json --show-progress")
    print()
    print("   # Command line args with JSON output:")
    print("   python -m multimodal_librarian.validation.cli \\")
    print("     --task-definition-arn arn:aws:ecs:... \\")
    print("     --iam-role-arn arn:aws:iam:... \\")
    print("     --load-balancer-arn arn:aws:elasticloadbalancing:... \\")
    print("     --output-format json")
    
    import os
    os.unlink(config_file)

if __name__ == '__main__':
    demo_cli_features()