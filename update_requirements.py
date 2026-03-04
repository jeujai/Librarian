#!/usr/bin/env python3
"""
Update requirements.txt with missing dependencies.
"""

# Real missing dependencies identified from the scan
MISSING_DEPENDENCIES = [
    "aiohttp>=3.9.0,<4.0.0",  # For async HTTP requests
    "celery>=5.3.0,<6.0.0",  # For background task processing
    "PyYAML>=6.0.0,<7.0.0",  # For YAML configuration files
    "pymilvus>=2.3.0,<3.0.0",  # For Milvus vector database
    "google-generativeai>=0.3.0,<1.0.0",  # Already in requirements but checking
    "gremlinpython>=3.6.0,<4.0.0",  # Already in requirements but checking
    "pydantic-settings>=2.1.0,<3.0.0",  # For Pydantic v2 settings
    "moto>=4.2.0,<5.0.0",  # For AWS mocking in tests
    "starlette>=0.27.0,<1.0.0",  # FastAPI dependency
    "urllib3>=1.26.0,<3.0.0",  # HTTP library
]

def update_requirements():
    """Update requirements.txt with missing dependencies."""
    
    # Read current requirements
    try:
        with open('requirements.txt', 'r') as f:
            current_requirements = f.read()
    except FileNotFoundError:
        print("requirements.txt not found!")
        return
    
    # Check which dependencies are actually missing
    missing_to_add = []
    
    for dep in MISSING_DEPENDENCIES:
        package_name = dep.split('>=')[0].split('==')[0].split('<')[0]
        
        # Check if package is already in requirements
        if package_name.lower() not in current_requirements.lower():
            missing_to_add.append(dep)
            print(f"✅ Will add: {dep}")
        else:
            print(f"⏭️  Already present: {package_name}")
    
    if missing_to_add:
        print(f"\n📝 Adding {len(missing_to_add)} missing dependencies...")
        
        # Add missing dependencies to requirements.txt
        with open('requirements.txt', 'a') as f:
            f.write('\n# Additional dependencies found by dependency scanner\n')
            for dep in missing_to_add:
                f.write(f'{dep}\n')
        
        print("✅ Requirements.txt updated successfully!")
        print("\nAdded dependencies:")
        for dep in missing_to_add:
            print(f"  - {dep}")
    else:
        print("✅ All dependencies are already present in requirements.txt")

if __name__ == "__main__":
    update_requirements()