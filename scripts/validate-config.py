#!/usr/bin/env python3
"""
Configuration Validation Script for Multimodal Librarian

This script validates the local development configuration and provides
detailed feedback on any issues found.

Usage:
    python scripts/validate-config.py [--connectivity] [--docker] [--fix]

Options:
    --connectivity    Test connectivity to all services
    --docker         Validate Docker environment
    --fix            Attempt to fix common issues automatically
    --verbose        Show detailed output
    --json           Output results in JSON format
"""

import sys
import json
import argparse
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from multimodal_librarian.config.local_config import LocalDatabaseConfig
    from multimodal_librarian.config.config_factory import (
        detect_environment,
        get_configuration_factory
    )
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def print_status(message: str, status: str = "info", verbose: bool = True):
    """Print status message with appropriate emoji."""
    if not verbose:
        return
    
    icons = {
        "success": "✅",
        "warning": "⚠️ ",
        "error": "❌",
        "info": "ℹ️ ",
        "check": "🔍"
    }
    
    icon = icons.get(status, "")
    print(f"{icon} {message}")


def validate_environment_detection(verbose: bool = True) -> dict:
    """Validate environment detection."""
    print_status("Environment Detection", "check", verbose)
    
    try:
        env_info = detect_environment()
        
        result = {
            "valid": True,
            "detected_type": env_info.detected_type,
            "confidence": env_info.confidence,
            "indicators": env_info.indicators,
            "warnings": env_info.warnings,
            "errors": env_info.errors
        }
        
        if verbose:
            print(f"   Detected: {env_info.detected_type}")
            print(f"   Confidence: {env_info.confidence:.2f}")
            
            if env_info.confidence < 0.7:
                print_status("Low confidence detection - consider setting ML_DATABASE_TYPE explicitly", "warning", verbose)
            
            if env_info.warnings:
                for warning in env_info.warnings:
                    print_status(f"Detection warning: {warning}", "warning", verbose)
            
            if env_info.errors:
                for error in env_info.errors:
                    print_status(f"Detection error: {error}", "error", verbose)
        
        return result
        
    except Exception as e:
        result = {
            "valid": False,
            "error": str(e),
            "detected_type": None,
            "confidence": 0.0
        }
        print_status(f"Environment detection failed: {e}", "error", verbose)
        return result


def validate_configuration(verbose: bool = True) -> dict:
    """Validate configuration."""
    print_status("Configuration Validation", "check", verbose)
    
    try:
        config = LocalDatabaseConfig()
        validation = config.validate_configuration()
        
        if verbose:
            if validation['valid']:
                print_status("Configuration is valid", "success", verbose)
            else:
                print_status("Configuration has issues", "error", verbose)
                for issue in validation['issues']:
                    print(f"      - {issue}")
            
            if validation['warnings']:
                print_status("Configuration warnings", "warning", verbose)
                for warning in validation['warnings']:
                    print(f"      - {warning}")
        
        return validation
        
    except Exception as e:
        result = {
            "valid": False,
            "backend": "unknown",
            "issues": [str(e)],
            "warnings": []
        }
        print_status(f"Configuration validation failed: {e}", "error", verbose)
        return result


def validate_connectivity(config: LocalDatabaseConfig, verbose: bool = True) -> dict:
    """Validate connectivity to services."""
    print_status("Connectivity Testing", "check", verbose)
    
    try:
        connectivity = config.validate_connectivity(timeout=5)
        
        if verbose:
            status_map = {
                "healthy": ("All services reachable", "success"),
                "partial": ("Some services unreachable", "warning"),
                "unhealthy": ("No services reachable", "error")
            }
            
            message, status = status_map.get(connectivity['overall_status'], ("Unknown status", "warning"))
            print_status(message, status, verbose)
            
            for service, result in connectivity['services'].items():
                status_icon = "✅" if result['connected'] else "❌"
                response_time = f" ({result['response_time']}ms)" if result.get('response_time') else ""
                print(f"      {status_icon} {service}: {result['host']}:{result['port']}{response_time}")
                
                if result.get('error') and verbose:
                    print(f"         Error: {result['error']}")
        
        return connectivity
        
    except Exception as e:
        result = {
            "overall_status": "error",
            "services": {},
            "errors": [str(e)],
            "warnings": []
        }
        print_status(f"Connectivity test failed: {e}", "error", verbose)
        return result


def validate_docker_environment(config: LocalDatabaseConfig, verbose: bool = True) -> dict:
    """Validate Docker environment."""
    print_status("Docker Environment", "check", verbose)
    
    try:
        docker_status = config.validate_docker_environment()
        
        if verbose:
            docker_ok = "✅" if docker_status['docker_available'] else "❌"
            compose_ok = "✅" if docker_status['compose_available'] else "❌"
            file_ok = "✅" if docker_status['compose_file_exists'] else "❌"
            
            print(f"   {docker_ok} Docker available")
            print(f"   {compose_ok} Docker Compose available")
            print(f"   {file_ok} Compose file exists")
            
            if docker_status['errors']:
                for error in docker_status['errors']:
                    print_status(f"Docker error: {error}", "error", verbose)
            
            if docker_status['warnings']:
                for warning in docker_status['warnings']:
                    print_status(f"Docker warning: {warning}", "warning", verbose)
        
        return docker_status
        
    except Exception as e:
        result = {
            "docker_available": False,
            "compose_available": False,
            "compose_file_exists": False,
            "errors": [str(e)],
            "warnings": []
        }
        print_status(f"Docker validation failed: {e}", "error", verbose)
        return result


def attempt_fixes(config: LocalDatabaseConfig, verbose: bool = True) -> dict:
    """Attempt to fix common configuration issues."""
    print_status("Attempting Automatic Fixes", "check", verbose)
    
    try:
        fix_results = config.validate_and_fix_configuration()
        
        if verbose:
            if fix_results['fixes_applied']:
                print_status("Fixes applied", "success", verbose)
                for fix in fix_results['fixes_applied']:
                    print(f"      ✅ {fix['action']}")
            
            if fix_results['fixes_failed']:
                print_status("Some fixes failed", "warning", verbose)
                for fix in fix_results['fixes_failed']:
                    print(f"      ❌ {fix['issue']}: {fix['error']}")
            
            if fix_results['recommendations']:
                print_status("Recommendations", "info", verbose)
                for rec in fix_results['recommendations']:
                    print(f"      💡 {rec}")
        
        return fix_results
        
    except Exception as e:
        result = {
            "validation": {"valid": False, "issues": [str(e)]},
            "fixes_applied": [],
            "fixes_failed": [],
            "recommendations": []
        }
        print_status(f"Fix attempt failed: {e}", "error", verbose)
        return result


def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(
        description="Validate Multimodal Librarian configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/validate-config.py                    # Basic validation
    python scripts/validate-config.py --connectivity    # Include connectivity tests
    python scripts/validate-config.py --docker          # Include Docker validation
    python scripts/validate-config.py --fix             # Attempt automatic fixes
    python scripts/validate-config.py --json            # JSON output
        """
    )
    
    parser.add_argument(
        "--connectivity", 
        action="store_true",
        help="Test connectivity to all services"
    )
    parser.add_argument(
        "--docker", 
        action="store_true",
        help="Validate Docker environment"
    )
    parser.add_argument(
        "--fix", 
        action="store_true",
        help="Attempt to fix common issues automatically"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        default=True,
        help="Show detailed output (default)"
    )
    parser.add_argument(
        "--quiet", 
        action="store_true",
        help="Minimal output"
    )
    parser.add_argument(
        "--json", 
        action="store_true",
        help="Output results in JSON format"
    )
    
    args = parser.parse_args()
    
    # Determine verbosity
    verbose = args.verbose and not args.quiet and not args.json
    
    if verbose:
        print("🔍 Validating Multimodal Librarian Configuration...")
        print()
    
    # Collect all results
    results = {
        "overall_status": "unknown",
        "environment_detection": None,
        "configuration": None,
        "connectivity": None,
        "docker": None,
        "fixes": None,
        "summary": {
            "total_issues": 0,
            "total_warnings": 0,
            "critical_errors": 0
        }
    }
    
    exit_code = 0
    
    # 1. Environment Detection
    env_result = validate_environment_detection(verbose)
    results["environment_detection"] = env_result
    
    if not env_result["valid"]:
        results["summary"]["critical_errors"] += 1
        exit_code = 1
    
    # 2. Configuration Validation
    config_result = validate_configuration(verbose)
    results["configuration"] = config_result
    
    if not config_result["valid"]:
        results["summary"]["critical_errors"] += 1
        results["summary"]["total_issues"] += len(config_result.get("issues", []))
        exit_code = 1
    
    results["summary"]["total_warnings"] += len(config_result.get("warnings", []))
    
    # Get config instance for further tests
    try:
        config = LocalDatabaseConfig()
    except Exception as e:
        if verbose:
            print_status(f"Cannot create config instance: {e}", "error")
        results["overall_status"] = "error"
        if args.json:
            print(json.dumps(results, indent=2))
        return exit_code
    
    # 3. Connectivity Testing (optional)
    if args.connectivity:
        if verbose:
            print()
        connectivity_result = validate_connectivity(config, verbose)
        results["connectivity"] = connectivity_result
        
        if connectivity_result["overall_status"] == "unhealthy":
            results["summary"]["critical_errors"] += 1
        elif connectivity_result["overall_status"] == "partial":
            results["summary"]["total_warnings"] += 1
    
    # 4. Docker Validation (optional)
    if args.docker:
        if verbose:
            print()
        docker_result = validate_docker_environment(config, verbose)
        results["docker"] = docker_result
        
        if docker_result.get("errors"):
            results["summary"]["total_issues"] += len(docker_result["errors"])
        if docker_result.get("warnings"):
            results["summary"]["total_warnings"] += len(docker_result["warnings"])
    
    # 5. Automatic Fixes (optional)
    if args.fix:
        if verbose:
            print()
        fix_result = attempt_fixes(config, verbose)
        results["fixes"] = fix_result
    
    # Determine overall status
    if results["summary"]["critical_errors"] > 0:
        results["overall_status"] = "error"
        exit_code = 1
    elif results["summary"]["total_issues"] > 0:
        results["overall_status"] = "warning"
    elif results["summary"]["total_warnings"] > 0:
        results["overall_status"] = "warning"
    else:
        results["overall_status"] = "success"
    
    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    elif verbose:
        print()
        print("📊 Validation Summary:")
        
        status_icons = {
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌"
        }
        
        icon = status_icons.get(results["overall_status"], "❓")
        print(f"   {icon} Overall Status: {results['overall_status'].upper()}")
        
        if results["summary"]["critical_errors"] > 0:
            print(f"   ❌ Critical Errors: {results['summary']['critical_errors']}")
        if results["summary"]["total_issues"] > 0:
            print(f"   ⚠️  Issues: {results['summary']['total_issues']}")
        if results["summary"]["total_warnings"] > 0:
            print(f"   ⚠️  Warnings: {results['summary']['total_warnings']}")
        
        if results["overall_status"] == "success":
            print("   🎉 Configuration is ready for use!")
        elif results["overall_status"] == "warning":
            print("   💡 Configuration works but has warnings - consider addressing them")
        else:
            print("   🔧 Configuration has issues that need to be fixed")
        
        print()
        print("✨ Validation complete!")
    
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)