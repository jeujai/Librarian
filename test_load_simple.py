#!/usr/bin/env python3
"""
Simple test to validate the comprehensive load testing implementation.
"""

import sys
import os

# Add paths
sys.path.insert(0, 'tests/performance')
sys.path.insert(0, 'src')

def test_imports():
    """Test individual imports."""
    print("Testing imports...")
    
    try:
        import asyncio
        print("✅ asyncio")
    except ImportError as e:
        print(f"❌ asyncio: {e}")
        return False
    
    try:
        import aiohttp
        print("✅ aiohttp")
    except ImportError as e:
        print(f"❌ aiohttp: {e}")
        return False
    
    try:
        import psutil
        print("✅ psutil")
    except ImportError as e:
        print(f"❌ psutil: {e}")
        return False
    
    try:
        from multimodal_librarian.logging_config import get_logger
        print("✅ logging_config")
    except ImportError as e:
        print(f"❌ logging_config: {e}")
        return False
    
    return True

def test_module_structure():
    """Test the module structure."""
    print("\nTesting module structure...")
    
    try:
        # Read the file and check for class definition
        with open('tests/performance/comprehensive_load_test.py', 'r') as f:
            content = f.read()
        
        if 'class ComprehensiveLoadTester:' in content:
            print("✅ ComprehensiveLoadTester class found in file")
        else:
            print("❌ ComprehensiveLoadTester class not found in file")
            return False
        
        if 'def main():' in content:
            print("✅ main function found in file")
        else:
            print("❌ main function not found in file")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def test_module_import():
    """Test importing the module."""
    print("\nTesting module import...")
    
    try:
        # Try to import the module
        import comprehensive_load_test
        print("✅ Module imported")
        
        # Check if classes are available
        if hasattr(comprehensive_load_test, 'ComprehensiveLoadTester'):
            print("✅ ComprehensiveLoadTester class available")
        else:
            print("❌ ComprehensiveLoadTester class not available")
            print("Available attributes:", [attr for attr in dir(comprehensive_load_test) if not attr.startswith('_')])
            return False
        
        if hasattr(comprehensive_load_test, 'LoadTestScenario'):
            print("✅ LoadTestScenario class available")
        else:
            print("❌ LoadTestScenario class not available")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("🧪 Simple Load Testing Validation")
    print("=" * 40)
    
    # Test 1: Dependencies
    if not test_imports():
        print("\n❌ Dependency test failed")
        return False
    
    # Test 2: File structure
    if not test_module_structure():
        print("\n❌ Module structure test failed")
        return False
    
    # Test 3: Module import
    if not test_module_import():
        print("\n❌ Module import test failed")
        return False
    
    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)