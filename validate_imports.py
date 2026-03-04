#!/usr/bin/env python3
"""
Validate that all critical imports can be resolved.
This script tests the most commonly failing imports.
"""

import sys
import importlib

# Critical imports that commonly cause deployment failures
CRITICAL_IMPORTS = [
    # Data science and ML
    'numpy',
    'pandas', 
    'matplotlib',
    'seaborn',
    'plotly',
    'sklearn',
    'torch',
    'transformers',
    'sentence_transformers',
    
    # Web framework
    'fastapi',
    'uvicorn',
    'starlette',
    'websockets',
    'aiohttp',
    
    # Database and storage
    'psycopg2',
    'sqlalchemy',
    'redis',
    'pymilvus',
    'neo4j',
    'opensearchpy',
    
    # AWS and cloud
    'boto3',
    'botocore',
    'gremlin_python',
    'requests_aws4auth',
    
    # Background processing
    'celery',
    
    # Configuration and utilities
    'yaml',
    'pydantic',
    'pydantic_settings',
    'structlog',
    'rich',
    
    # Security
    'cryptography',
    'jwt',
    'passlib',
    
    # Document processing
    'fitz',  # PyMuPDF
    'pdfplumber',
    'PIL',   # Pillow
    'docx',  # python-docx
    
    # Testing
    'pytest',
    'hypothesis',
    'moto',
]

def test_import(module_name):
    """Test if a module can be imported."""
    try:
        importlib.import_module(module_name)
        return True, None
    except ImportError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def main():
    """Test all critical imports."""
    print("🧪 Testing critical imports...")
    print("=" * 50)
    
    failed_imports = []
    successful_imports = []
    
    for module in CRITICAL_IMPORTS:
        success, error = test_import(module)
        
        if success:
            print(f"✅ {module}")
            successful_imports.append(module)
        else:
            print(f"❌ {module}: {error}")
            failed_imports.append((module, error))
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"  ✅ Successful imports: {len(successful_imports)}")
    print(f"  ❌ Failed imports: {len(failed_imports)}")
    
    if failed_imports:
        print("\n❌ FAILED IMPORTS:")
        print("-" * 30)
        for module, error in failed_imports:
            print(f"  {module}: {error}")
        
        print("\n📝 RECOMMENDED ACTIONS:")
        print("1. Check if these packages are in requirements.txt")
        print("2. Install missing packages: pip install <package_name>")
        print("3. Check for package name variations (e.g., PIL vs Pillow)")
        
        return 1
    else:
        print("\n🎉 All critical imports successful!")
        return 0

if __name__ == "__main__":
    sys.exit(main())