#!/usr/bin/env python3
"""
Master Vector Test Data Generator

This script orchestrates the generation of comprehensive vector database test data
for local development environments. It combines document embeddings, similarity
search scenarios, and performance testing vectors into a complete test suite.

The script generates:
- Realistic document embeddings with metadata
- Comprehensive similarity search test scenarios
- Large-scale performance testing datasets
- Validation and benchmarking data

Usage:
    python scripts/seed-all-vector-test-data.py [--profile PROFILE] [--reset] [--verbose]
    
    --profile PROFILE: Test data profile (development/testing/performance) (default: development)
    --reset: Clear all existing vector test data before generating new data
    --verbose: Enable detailed logging and progress monitoring
"""

import asyncio
import argparse
import logging
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MasterVectorDataGenerator:
    """Master orchestrator for all vector test data generation."""
    
    def __init__(self, verbose: bool = False):
        """Initialize the master generator."""
        self.verbose = verbose
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        self.scripts_dir = Path(__file__).parent
        
        # Test data profiles
        self.profiles = {
            "development": {
                "description": "Minimal test data for daily development",
                "document_embeddings": {"count": 25},
                "similarity_scenarios": {"scenarios": 10},
                "performance_data": {"scale": "small"}
            },
            "testing": {
                "description": "Comprehensive test data for integration testing",
                "document_embeddings": {"count": 100},
                "similarity_scenarios": {"scenarios": 25},
                "performance_data": {"scale": "medium"}
            },
            "performance": {
                "description": "Large-scale data for performance benchmarking",
                "document_embeddings": {"count": 500},
                "similarity_scenarios": {"scenarios": 50},
                "performance_data": {"scale": "large"}
            }
        }
        
        # Generation steps
        self.generation_steps = [
            {
                "name": "Document Embeddings",
                "script": "seed-vector-document-embeddings.py",
                "description": "Generate realistic document embeddings with diverse metadata",
                "required": True
            },
            {
                "name": "Similarity Search Scenarios",
                "script": "seed-vector-similarity-scenarios.py",
                "description": "Generate comprehensive similarity search test scenarios",
                "required": True
            },
            {
                "name": "Performance Testing Vectors",
                "script": "seed-vector-performance-data.py",
                "description": "Generate large-scale performance testing datasets",
                "required": True
            }
        ]
    
    def get_script_args(self, step: Dict[str, Any], profile_config: Dict[str, Any]) -> List[str]:
        """Get command line arguments for a generation script."""
        script_name = step["script"]
        args = []
        
        if self.verbose:
            args.append("--verbose")
        
        if script_name == "seed-vector-document-embeddings.py":
            config = profile_config["document_embeddings"]
            args.extend(["--count", str(config["count"])])
            
        elif script_name == "seed-vector-similarity-scenarios.py":
            config = profile_config["similarity_scenarios"]
            args.extend(["--scenarios", str(config["scenarios"])])
            
        elif script_name == "seed-vector-performance-data.py":
            config = profile_config["performance_data"]
            args.extend(["--scale", config["scale"]])
        
        return args
    
    async def run_generation_script(
        self, 
        script_name: str, 
        args: List[str]
    ) -> Dict[str, Any]:
        """
        Run a vector data generation script.
        
        Args:
            script_name: Name of the script to run
            args: Command line arguments
            
        Returns:
            Execution result with success status and output
        """
        script_path = self.scripts_dir / script_name
        
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        
        # Build command
        cmd = [sys.executable, str(script_path)] + args
        
        logger.debug(f"Running: {' '.join(cmd)}")
        
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
                "output": output,
                "command": ' '.join(cmd)
            }
            
        except Exception as e:
            return {
                "success": False,
                "return_code": -1,
                "output": f"Failed to execute script: {str(e)}",
                "command": ' '.join(cmd)
            }
    
    async def generate_all_vector_data(self, profile: str, reset: bool = False) -> Dict[str, Any]:
        """
        Generate all vector test data for the specified profile.
        
        Args:
            profile: Test data profile name
            reset: Whether to reset existing data
            
        Returns:
            Generation results with success status and metrics
        """
        if profile not in self.profiles:
            raise ValueError(f"Unknown profile '{profile}'. Available: {list(self.profiles.keys())}")
        
        profile_config = self.profiles[profile]
        
        logger.info(f"Starting vector test data generation for '{profile}' profile")
        logger.info(f"Description: {profile_config['description']}")
        
        results = {
            "profile": profile,
            "success": True,
            "steps_completed": 0,
            "total_steps": len(self.generation_steps),
            "step_results": {},
            "errors": [],
            "start_time": datetime.now().isoformat(),
            "generation_summary": {}
        }
        
        print("🚀 Vector Test Data Generation")
        print("=" * 70)
        print(f"Profile: {profile} - {profile_config['description']}")
        if reset:
            print("⚠️  RESET MODE: All existing vector test data will be cleared!")
        print()
        
        total_start_time = time.time()
        
        for i, step in enumerate(self.generation_steps, 1):
            step_name = step["name"]
            script_name = step["script"]
            
            print(f"📝 Step {i}/{len(self.generation_steps)}: {step_name}")
            print(f"   {step['description']}")
            
            try:
                # Get script arguments
                script_args = self.get_script_args(step, profile_config)
                if reset:
                    script_args.append("--reset")
                
                # Run the generation script
                step_start_time = time.time()
                result = await self.run_generation_script(script_name, script_args)
                step_time = time.time() - step_start_time
                
                results["step_results"][step_name] = {
                    "success": result["success"],
                    "return_code": result["return_code"],
                    "execution_time": step_time,
                    "command": result["command"],
                    "output_lines": len(result["output"].split('\n')) if result["output"] else 0
                }
                
                if result["success"]:
                    print(f"   ✅ Completed successfully in {step_time:.2f}s")
                    results["steps_completed"] += 1
                    
                    # Extract key metrics from output if available
                    output = result["output"]
                    if "vectors" in output.lower() and "generated" in output.lower():
                        # Try to extract vector count from output
                        import re
                        vector_match = re.search(r'(\d+(?:,\d+)*)\s+(?:vectors?|embeddings?)', output, re.IGNORECASE)
                        if vector_match:
                            vector_count = vector_match.group(1).replace(',', '')
                            results["step_results"][step_name]["vectors_generated"] = int(vector_count)
                else:
                    print(f"   ❌ Failed with return code {result['return_code']}")
                    results["success"] = False
                    error_msg = f"{step_name}: Script failed"
                    results["errors"].append(error_msg)
                    
                    if self.verbose:
                        print(f"   Error output: {result['output'][:200]}...")
                    
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
        
        total_time = time.time() - total_start_time
        results["total_time"] = total_time
        results["end_time"] = datetime.now().isoformat()
        
        # Generate summary
        self.generate_summary(results, profile_config)
        
        return results
    
    def generate_summary(self, results: Dict[str, Any], profile_config: Dict[str, Any]):
        """Generate and print a comprehensive summary of the generation results."""
        print("📊 Vector Test Data Generation Summary")
        print("=" * 60)
        
        if results["success"]:
            print(f"✅ All {results['steps_completed']}/{results['total_steps']} steps completed successfully!")
        else:
            print(f"❌ {results['steps_completed']}/{results['total_steps']} steps completed")
            if results['errors']:
                print(f"   Errors encountered:")
                for error in results['errors']:
                    print(f"   • {error}")
        
        print(f"\n⏱️  Total generation time: {results['total_time']:.2f} seconds")
        
        # Step-by-step results
        print(f"\n📋 Step Results:")
        total_vectors = 0
        
        for step_name, step_result in results["step_results"].items():
            status = "✅" if step_result["success"] else "❌"
            time_str = f"{step_result['execution_time']:.2f}s"
            
            print(f"{status} {step_name} ({time_str})")
            
            if "vectors_generated" in step_result:
                vectors = step_result["vectors_generated"]
                total_vectors += vectors
                print(f"      Vectors generated: {vectors:,}")
        
        if total_vectors > 0:
            print(f"\n📊 Total vectors generated: {total_vectors:,}")
        
        # Profile-specific summary
        print(f"\n🎯 Profile Configuration ({results['profile']}):")
        for component, config in profile_config.items():
            if component != "description":
                print(f"   • {component.replace('_', ' ').title()}: {config}")
        
        if results["success"]:
            print(f"\n🎉 Vector test data generation completed successfully!")
            print(f"\nNext steps:")
            print(f"1. Start your local development environment:")
            print(f"   make dev-local")
            print(f"2. Run vector database tests:")
            print(f"   pytest tests/components/test_vector_store.py -v")
            print(f"3. Perform similarity search testing:")
            print(f"   python scripts/test-vector-similarity-search.py")
            print(f"4. Run performance benchmarks:")
            print(f"   python scripts/benchmark-vector-performance.py")
        else:
            print(f"\n❌ Vector test data generation failed!")
            print(f"Check the error messages above and try again.")
            print(f"\nTroubleshooting:")
            print(f"• Ensure all dependencies are installed")
            print(f"• Check that Milvus service is running")
            print(f"• Try running individual scripts with --verbose for details")
        
        # Save results to file
        results_file = Path(__file__).parent.parent / "test_data" / "generation_results.json"
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Generation results saved to: {results_file}")


async def main():
    """Main function to orchestrate vector test data generation."""
    parser = argparse.ArgumentParser(description="Generate comprehensive vector test data")
    parser.add_argument("--profile", choices=["development", "testing", "performance"], 
                       default="development", help="Test data profile")
    parser.add_argument("--reset", action="store_true", help="Clear all existing vector test data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Create and run the master generator
        generator = MasterVectorDataGenerator(verbose=args.verbose)
        
        results = await generator.generate_all_vector_data(
            profile=args.profile,
            reset=args.reset
        )
        
        return 0 if results["success"] else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)