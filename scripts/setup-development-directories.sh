#!/bin/bash
"""
Setup Development Directories

This script creates all necessary directories for local development with hot reload.
It ensures proper permissions and creates any missing directories that are needed
for the application to run correctly in development mode.

Features:
- Creates all required application directories
- Sets up proper permissions for development
- Creates cache directories for better performance
- Sets up log directories for debugging
- Creates backup directories for data safety
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to create directory with proper permissions
create_directory() {
    local dir=$1
    local description=$2
    
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        print_success "Created $description: $dir"
    else
        print_status "$description already exists: $dir"
    fi
    
    # Ensure proper permissions for development
    chmod 755 "$dir" 2>/dev/null || true
}

# Function to create file with content if it doesn't exist
create_file_if_missing() {
    local file=$1
    local content=$2
    local description=$3
    
    if [[ ! -f "$file" ]]; then
        echo "$content" > "$file"
        print_success "Created $description: $file"
    else
        print_status "$description already exists: $file"
    fi
}

main() {
    print_status "🗂️  Setting up development directories..."
    echo
    
    # Application data directories
    print_status "Creating application data directories..."
    create_directory "uploads" "uploads directory"
    create_directory "media" "media directory"
    create_directory "exports" "exports directory"
    create_directory "logs" "logs directory"
    create_directory "audit_logs" "audit logs directory"
    
    # Test data directories
    print_status "Creating test data directories..."
    create_directory "test_uploads" "test uploads directory"
    create_directory "test_media" "test media directory"
    create_directory "test_exports" "test exports directory"
    create_directory "test_data" "test data directory"
    
    # Cache directories for better performance
    print_status "Creating cache directories..."
    create_directory "cache" "cache root directory"
    create_directory "cache/models" "ML models cache directory"
    create_directory "cache/pip" "Python packages cache directory"
    create_directory "cache/pytest" "pytest cache directory"
    
    # Database data directories (for Docker volumes)
    print_status "Creating database data directories..."
    create_directory "data" "data root directory"
    create_directory "data/postgres" "PostgreSQL data directory"
    create_directory "data/postgres-config" "PostgreSQL config directory"
    create_directory "data/neo4j" "Neo4j data directory"
    create_directory "data/neo4j-logs" "Neo4j logs directory"
    create_directory "data/neo4j-import" "Neo4j import directory"
    create_directory "data/neo4j-plugins" "Neo4j plugins directory"
    create_directory "data/milvus" "Milvus data directory"
    create_directory "data/etcd" "etcd data directory"
    create_directory "data/minio" "MinIO data directory"
    create_directory "data/redis" "Redis data directory"
    create_directory "data/pgadmin" "pgAdmin data directory"
    
    # Backup directories
    print_status "Creating backup directories..."
    create_directory "backups" "backups root directory"
    create_directory "backups/postgresql" "PostgreSQL backups directory"
    create_directory "backups/neo4j" "Neo4j backups directory"
    create_directory "backups/local" "local development backups directory"
    
    # Development workspace directories
    print_status "Creating development workspace directories..."
    create_directory "notebooks" "Jupyter notebooks directory"
    
    # Create .gitkeep files for empty directories that should be tracked
    print_status "Creating .gitkeep files for version control..."
    create_file_if_missing "uploads/.gitkeep" "" "uploads .gitkeep"
    create_file_if_missing "media/.gitkeep" "" "media .gitkeep"
    create_file_if_missing "exports/.gitkeep" "" "exports .gitkeep"
    create_file_if_missing "logs/.gitkeep" "" "logs .gitkeep"
    create_file_if_missing "notebooks/.gitkeep" "" "notebooks .gitkeep"
    
    # Create development-specific .gitignore entries
    print_status "Creating development .gitignore entries..."
    local gitignore_content="# Development directories
/data/
/cache/
/backups/
*.log
*.tmp
.DS_Store
Thumbs.db

# Test files
/test_uploads/*
!/test_uploads/.gitkeep
/test_media/*
!/test_media/.gitkeep
/test_exports/*
!/test_exports/.gitkeep
/test_data/*
!/test_data/.gitkeep

# Runtime files
/uploads/*
!/uploads/.gitkeep
/media/*
!/media/.gitkeep
/exports/*
!/exports/.gitkeep
/logs/*
!/logs/.gitkeep
/audit_logs/*
!/audit_logs/.gitkeep"
    
    if [[ ! -f ".gitignore.dev" ]]; then
        echo "$gitignore_content" > .gitignore.dev
        print_success "Created development .gitignore: .gitignore.dev"
        print_warning "Consider merging .gitignore.dev into your main .gitignore file"
    fi
    
    # Create a README for the development setup
    local readme_content="# Development Directories

This directory structure is created automatically for local development with hot reload.

## Directory Structure

### Application Data
- \`uploads/\` - File uploads during development
- \`media/\` - Generated media files
- \`exports/\` - Exported documents and reports
- \`logs/\` - Application logs
- \`audit_logs/\` - Security and audit logs

### Test Data
- \`test_uploads/\` - Test files for upload testing
- \`test_media/\` - Test media files
- \`test_exports/\` - Test export files
- \`test_data/\` - General test data

### Cache Directories
- \`cache/models/\` - ML model cache (persistent across restarts)
- \`cache/pip/\` - Python package cache
- \`cache/pytest/\` - pytest cache for faster test runs

### Database Data (Docker Volumes)
- \`data/postgres/\` - PostgreSQL data files
- \`data/neo4j/\` - Neo4j graph database files
- \`data/milvus/\` - Milvus vector database files
- \`data/redis/\` - Redis cache files
- \`data/etcd/\` - etcd configuration store
- \`data/minio/\` - MinIO object storage files

### Backups
- \`backups/postgresql/\` - PostgreSQL database backups
- \`backups/neo4j/\` - Neo4j database backups
- \`backups/local/\` - Local development backups

### Development Workspace
- \`notebooks/\` - Jupyter notebooks for experimentation

## Hot Reload Features

The development environment includes enhanced hot reload functionality:

- **Automatic restart** on Python file changes
- **Configuration monitoring** for .env.local and pyproject.toml changes
- **Intelligent exclusions** for cache and temporary files
- **Real-time feedback** on file changes
- **Graceful restart** with minimal downtime

## Usage

Start the development environment with hot reload:

\`\`\`bash
make dev-hot-reload
\`\`\`

This will:
1. Create all necessary directories
2. Start all database services
3. Start the application with hot reload enabled
4. Monitor file changes and restart automatically

## Useful Commands

- \`make logs-hot-reload\` - View application logs
- \`make restart-app\` - Restart just the application
- \`make shell-hot-reload\` - Open shell in app container
- \`make watch-files\` - Watch file changes (debugging)
- \`make down\` - Stop all services
"
    
    create_file_if_missing "DEV_SETUP_README.md" "$readme_content" "development setup README"
    
    echo
    print_success "🎉 Development directories setup complete!"
    print_status "All directories and files are ready for hot reload development"
    print_status "Run 'make dev-hot-reload' to start the development environment"
}

# Run main function
main "$@"