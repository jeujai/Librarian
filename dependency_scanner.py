#!/usr/bin/env python3
"""
Comprehensive dependency scanner for the Multimodal Librarian project.
Scans all Python files for imports and checks against requirements.txt.
"""

import os
import re
import sys
from pathlib import Path
from typing import Set, Dict, List, Tuple

def extract_imports_from_file(file_path: str) -> Set[str]:
    """Extract all import statements from a Python file."""
    imports = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find all import statements
        import_patterns = [
            r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)',
            r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+import',
        ]
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#') or not line:
                continue
                
            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module_name = match.group(1)
                    # Get the top-level module name
                    top_level = module_name.split('.')[0]
                    imports.add(top_level)
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return imports

def get_installed_packages() -> Set[str]:
    """Get packages from requirements.txt."""
    packages = set()
    
    try:
        with open('requirements.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before ==, >=, etc.)
                    package = re.split(r'[>=<!=]', line)[0].strip()
                    # Handle extras like package[extra]
                    package = package.split('[')[0]
                    packages.add(package.lower())
    except FileNotFoundError:
        print("requirements.txt not found!")
        
    return packages

def scan_python_files(directory: str = '.') -> Dict[str, Set[str]]:
    """Scan all Python files in directory for imports."""
    all_imports = {}
    
    for root, dirs, files in os.walk(directory):
        # Skip certain directories
        skip_dirs = {'.git', '__pycache__', '.pytest_cache', 'venv', '.venv', 'node_modules'}
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                imports = extract_imports_from_file(file_path)
                if imports:
                    all_imports[file_path] = imports
                    
    return all_imports

def get_standard_library_modules() -> Set[str]:
    """Get a set of standard library module names."""
    # Common standard library modules
    stdlib_modules = {
        'os', 'sys', 'json', 'time', 'datetime', 'pathlib', 'typing', 'uuid',
        'logging', 'asyncio', 'threading', 'multiprocessing', 'subprocess',
        'collections', 'itertools', 'functools', 'operator', 'math', 'random',
        'statistics', 'decimal', 'fractions', 're', 'string', 'io', 'tempfile',
        'shutil', 'glob', 'fnmatch', 'linecache', 'pickle', 'copyreg', 'copy',
        'pprint', 'reprlib', 'enum', 'numbers', 'cmath', 'struct', 'codecs',
        'unicodedata', 'stringprep', 'readline', 'rlcompleter', 'bisect',
        'array', 'weakref', 'types', 'gc', 'inspect', 'site', 'importlib',
        'pkgutil', 'modulefinder', 'runpy', 'argparse', 'optparse', 'getopt',
        'shlex', 'configparser', 'fileinput', 'calendar', 'hashlib', 'hmac',
        'secrets', 'base64', 'binascii', 'quopri', 'uu', 'html', 'xml',
        'urllib', 'http', 'ftplib', 'poplib', 'imaplib', 'nntplib', 'smtplib',
        'smtpd', 'telnetlib', 'uuid', 'socketserver', 'xmlrpc', 'ipaddress',
        'email', 'mailcap', 'mailbox', 'mimetypes', 'base64', 'binhex',
        'binascii', 'quopri', 'uu', 'wave', 'chunk', 'colorsys', 'imghdr',
        'sndhdr', 'ossaudiodev', 'audioop', 'aifc', 'sunau', 'wave',
        'gettext', 'locale', 'platform', 'errno', 'ctypes', 'threading',
        'multiprocessing', 'concurrent', 'subprocess', 'sched', 'queue',
        'dummy_threading', '_thread', '_dummy_thread', 'signal', 'mmap',
        'contextlib', 'abc', 'atexit', 'traceback', 'warnings', 'dataclasses'
    }
    
    return stdlib_modules

def normalize_package_name(name: str) -> str:
    """Normalize package names for comparison."""
    # Handle common package name mappings
    mappings = {
        'cv2': 'opencv-python',
        'sklearn': 'scikit-learn',
        'PIL': 'Pillow',
        'yaml': 'PyYAML',
        'pymilvus': 'pymilvus',
        'celery': 'celery',
        'redis': 'redis',
        'psycopg2': 'psycopg2-binary',
        'jwt': 'PyJWT',
        'jose': 'python-jose',
        'passlib': 'passlib',
        'cryptography': 'cryptography',
        'boto3': 'boto3',
        'botocore': 'botocore',
        'fastapi': 'fastapi',
        'uvicorn': 'uvicorn',
        'gunicorn': 'gunicorn',
        'websockets': 'websockets',
        'pydantic': 'pydantic',
        'sqlalchemy': 'sqlalchemy',
        'alembic': 'alembic',
        'structlog': 'structlog',
        'rich': 'rich',
        'psutil': 'psutil',
        'openai': 'openai',
        'anthropic': 'anthropic',
        'requests': 'requests',
        'matplotlib': 'matplotlib',
        'seaborn': 'seaborn',
        'plotly': 'plotly',
        'numpy': 'numpy',
        'pandas': 'pandas',
        'scipy': 'scipy',
        'torch': 'torch',
        'transformers': 'transformers',
        'sentence_transformers': 'sentence-transformers',
        'spacy': 'spacy',
        'nltk': 'nltk',
        'neo4j': 'neo4j',
        'networkx': 'networkx',
        'gremlinpython': 'gremlinpython',
        'opensearch': 'opensearch-py',
        'pytest': 'pytest',
        'hypothesis': 'hypothesis',
        'httpx': 'httpx',
        'aiofiles': 'aiofiles',
        'aiohttp': 'aiohttp',
        'docx': 'python-docx',
        'reportlab': 'reportlab',
        'pptx': 'python-pptx',
        'openpyxl': 'openpyxl',
        'fitz': 'PyMuPDF',
        'pdfplumber': 'pdfplumber',
        'pytesseract': 'pytesseract',
        'pdf2image': 'pdf2image',
        'moviepy': 'moviepy',
        'gtts': 'gTTS',
        'pyttsx3': 'pyttsx3',
        'imageio': 'imageio',
        'joblib': 'joblib',
        'tqdm': 'tqdm',
        'dateutil': 'python-dateutil',
        'pytz': 'pytz',
        'dotenv': 'python-dotenv',
        'multipart': 'python-multipart',
        'bcrypt': 'passlib',
        'asyncpg': 'asyncpg',
        'toml': 'toml',
        'black': 'black',
        'isort': 'isort',
        'flake8': 'flake8'
    }
    
    return mappings.get(name.lower(), name.lower())

def main():
    """Main function to scan dependencies."""
    print("🔍 Scanning for missing dependencies...")
    print("=" * 60)
    
    # Get all imports from Python files
    all_imports = scan_python_files()
    
    # Collect all unique imports
    unique_imports = set()
    for file_imports in all_imports.values():
        unique_imports.update(file_imports)
    
    # Get installed packages
    installed_packages = get_installed_packages()
    
    # Get standard library modules
    stdlib_modules = get_standard_library_modules()
    
    # Find missing dependencies
    missing_deps = []
    
    for import_name in sorted(unique_imports):
        # Skip standard library modules
        if import_name.lower() in stdlib_modules:
            continue
            
        # Skip local imports (starting with multimodal_librarian)
        if import_name.startswith('multimodal_librarian'):
            continue
            
        # Normalize package name
        normalized_name = normalize_package_name(import_name)
        
        # Check if package is installed
        if normalized_name not in installed_packages:
            missing_deps.append((import_name, normalized_name))
    
    # Report results
    if missing_deps:
        print("❌ MISSING DEPENDENCIES FOUND:")
        print("-" * 40)
        for import_name, package_name in missing_deps:
            print(f"  Import: {import_name}")
            print(f"  Package: {package_name}")
            print()
        
        print("📝 ADD TO requirements.txt:")
        print("-" * 30)
        for _, package_name in missing_deps:
            print(f"{package_name}")
        
    else:
        print("✅ No missing dependencies found!")
    
    print("\n📊 SUMMARY:")
    print(f"  Total Python files scanned: {len(all_imports)}")
    print(f"  Unique imports found: {len(unique_imports)}")
    print(f"  Installed packages: {len(installed_packages)}")
    print(f"  Missing dependencies: {len(missing_deps)}")
    
    # Show some example files with imports
    print("\n📁 FILES WITH MOST IMPORTS:")
    print("-" * 30)
    sorted_files = sorted(all_imports.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, imports in sorted_files[:5]:
        print(f"  {file_path}: {len(imports)} imports")

if __name__ == "__main__":
    main()