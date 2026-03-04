#!/usr/bin/env python3
"""
Master Sample Data Generator

This script runs all sample data generation scripts in the correct order
to populate a local development database with realistic test data.

Usage:
    python scripts/seed-all-sample-data.py [--reset] [--quick] [--verbose]
    
    --reset: Reset all existing data before generating new data
    --quick: Generate smaller datasets for faster setup
    --verbose: Enable verbose logging
"""

import asyncio
import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MasterDataGenerator:
    """Master controller for all sample data generation."""
    
    def __init__(self, reset: bool = False, quick: bool = False, verbose: bool = False):
        """Initialize the master generator."""
        self.reset = reset
        self.quick = quick
        self.verbose = verbose
        self.scripts_dir = Path(__file__).parent
        
        # Define generation steps in dependency order
        self.generation_steps = [
            {
                "name": "Users and Authentication",
                "script": "seed-sample-users.py",
                "args": self._get_user_args(),
                "description": "Create sample user accounts with authentication data"
            },
            {
                "name": "Documents and Metadata", 
                "script": "seed-sample-documents.py",
                "args": self._get_document_args(),
                "description": "Create sample documents with processing status and chunks"
            },
            {
                "name": "Conversations and Chat History",
                "script": "seed-sample-conversations.py", 
                "args": self._get_conversation_args(),
                "description": "Create sample conversations with realistic message history"
            },
            {
                "name": "Analytics and Metrics Data",
                "script": "seed-sample-analytics.py",
                "args": self._get_analytics_args(),
                "description": "Create sample analytics data and audit logs"
            }
        ]
    
    def _get_user_args(self) -> List[str]:
        """Get arguments for user generation script."""
        args = []
        if self.reset:
            args.append("--reset")
        if self.verbose:
            args.append("--verbose")
        
        # Adjust count based on quick mode
        count = 5 if self.quick else 10
        args.extend(["--count", str(count)])
        
        return args
    
    def _get_document_args(self) -> List[str]:
        """Get arguments for document generation script."""
        args = []
        if self.reset:
            args.append("--reset")
        if self.verbose:
            args.append("--verbose")
        
        # Always generate chunks for realistic data
        args.append("--with-chunks")
        
        # Adjust count based on quick mode
        count = 10 if self.quick else 20
        args.extend(["--count", str(count)])
        
        return args
    
    def _get_conversation_args(self) -> List[str]:
        """Get arguments for conversation generation script."""
        args = []
        if self.reset:
            args.append("--reset")
        if self.verbose:
            args.append("--verbose")
        
        # Adjust parameters based on quick mode
        if self.quick:
            args.extend(["--count", "8", "--messages-per-conversation", "5"])
        else:
            args.extend(["--count", "15", "--messages-per-conversation", "8"])
        
        return args
    
    def _get_analytics_args(self) -> List[str]:
        """Get arguments for analytics generation script."""
        args = []
        if self.reset:
            args.append("--reset")
        if self.verbose:
            args.append("--verbose")
        
        # Adjust parameters based on quick mode
        if self.quick:
            args.extend(["--days", "7", "--events-per-day", "50"])
        else:
            args.extend(["--days", "30", "--events-per-day", "100"])
        
        return args
    
    async def generate_all_data(self) -> Dict[str, Any]:
        """
        Run all sample data generation scripts in order.
        
        Returns:
            Dictionary with results from each generation step
        """
        logger.info("Starting master sample data generation")
        logger.info(f"Configuration: reset={self.reset}, quick={self.quick}, verbose={self.verbose}")
        
        results = {
            "success": True,
            "steps_completed": 0,
            "total_steps": len(self.generation_steps),
            "step_results": {},
            "errors": []
        }
        
        print("🚀 Multimodal Librarian - Sample Data Generation")
        print("=" * 60)
        
        if self.reset:
            print("⚠️  RESET MODE: All existing data will be cleared!")
        
        if self.quick:
            print("⚡ QUICK MODE: Generating smaller datasets for faster setup")
        
        print()
        
        for i, step in enumerate(self.generation_steps, 1):
            step_name = step["name"]
            script_name = step["script"]
            script_args = step["args"]
            
            print(f"📝 Step {i}/{len(self.generation_steps)}: {step_name}")
            print(f"   {step['description']}")
            
            try:
                # Run the generation script
                result = await self._run_generation_script(script_name, script_args)
                
                results["step_results"][step_name] = {
                    "success": result["success"],
                    "return_code": result["return_code"],
                    "output": result["output"]
                }
                
                if result["success"]:
                    print(f"   ✅ Completed successfully")
                    results["steps_completed"] += 1
                else:
                    print(f"   ❌ Failed with return code {result['return_code']}")
                    results["success"] = False
                    results["errors"].append(f"{step_name}: {result['output']}")
                    
                    # Stop on first failure unless in verbose mode
                    if not self.verbose:
                        break
                
            except Exception as e:
                error_msg = f"Exception in {step_name}: {str(e)}"
                print(f"   ❌ {error_msg}")
                results["success"] = False
                results["errors"].append(error_msg)
                
                # Stop on first failure unless in verbose mode
                if not self.verbose:
                    break
            
            print()  # Add spacing between steps
        
        # Print final summary
        self._print_summary(results)
        
        return results
    
    async def _run_generation_script(self, script_name: str, args: List[str]) -> Dict[str, Any]:
        """
        Run a single generation script with the given arguments.
        
        Args:
            script_name: Name of the script file
            args: Command line arguments for the script
            
        Returns:
            Dictionary with execution results
        """
        script_path = self.scripts_dir / script_name
        
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        
        # Build command
        cmd = [sys.executable, str(script_path)] + args
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        try:
            # Run the script
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.scripts_dir.parent  # Run from project root
            )
            
            stdout, _ = await process.communicate()
            output = stdout.decode('utf-8') if stdout else ""
            
            return {
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "output": output
            }
            
        except Exception as e:
            return {
                "success": False,
                "return_code": -1,
                "output": f"Failed to execute script: {str(e)}"
            }
    
    def _print_summary(self, results: Dict[str, Any]) -> None:
        """Print a summary of the generation results."""
        print("📊 Generation Summary")
        print("=" * 40)
        
        if results["success"]:
            print(f"✅ All {results['steps_completed']}/{results['total_steps']} steps completed successfully!")
        else:
            print(f"❌ {results['steps_completed']}/{results['total_steps']} steps completed")
            print(f"   {len(results['errors'])} errors encountered:")
            for error in results['errors']:
                print(f"   • {error}")
        
        print()
        
        # Print step-by-step results
        for step_name, step_result in results["step_results"].items():
            status = "✅" if step_result["success"] else "❌"
            print(f"{status} {step_name}")
        
        print()
        
        if results["success"]:
            print("🎉 Sample data generation completed successfully!")
            print()
            print("Next steps:")
            print("1. Start your local development environment:")
            print("   make dev-local")
            print()
            print("2. Access the application:")
            print("   • Web UI: http://localhost:8000")
            print("   • API docs: http://localhost:8000/docs")
            print()
            print("3. Login with sample credentials:")
            print("   • Admin: admin / admin123")
            print("   • User: alice_dev / alice123")
            print()
            print("4. Explore the generated data:")
            print("   • Documents in the document manager")
            print("   • Chat history in conversations")
            print("   • Analytics in the dashboard")
        else:
            print("❌ Sample data generation failed!")
            print("Check the error messages above and try again.")
            print()
            print("Common solutions:")
            print("• Ensure database services are running")
            print("• Check database connection configuration")
            print("• Try running with --verbose for more details")


async def main():
    """Main function to run the master sample data generator."""
    parser = argparse.ArgumentParser(description="Generate all sample data for local development")
    parser.add_argument("--reset", action="store_true", help="Reset all existing data first")
    parser.add_argument("--quick", action="store_true", help="Generate smaller datasets for faster setup")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run the master generator
    generator = MasterDataGenerator(
        reset=args.reset,
        quick=args.quick,
        verbose=args.verbose
    )
    
    try:
        results = await generator.generate_all_data()
        return 0 if results["success"] else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)