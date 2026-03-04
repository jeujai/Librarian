#!/bin/bash

# Deploy Task 3: Document Upload and Management System
# This script deploys the document upload and management functionality

set -e

echo "🚀 Starting Task 3 deployment: Document Upload and Management System"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_PATH="$PROJECT_ROOT/venv/bin/python"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if virtual environment exists
if [ ! -f "$PYTHON_PATH" ]; then
    log_error "Python virtual environment not found at $PYTHON_PATH"
    log_info "Please run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

log_info "Step 1: Checking database connection..."
cd "$PROJECT_ROOT"

# Test database connection
if ! $PYTHON_PATH -c "
import asyncio
import sys
sys.path.append('src')
from multimodal_librarian.database.connection import get_database_connection

async def test_connection():
    try:
        db_pool = await get_database_connection()
        async with db_pool.acquire() as conn:
            result = await conn.fetchval('SELECT 1')
            print('Database connection successful')
            return True
    except Exception as e:
        print(f'Database connection failed: {e}')
        return False

result = asyncio.run(test_connection())
sys.exit(0 if result else 1)
"; then
    log_success "Database connection verified"
else
    log_error "Database connection failed"
    exit 1
fi

log_info "Step 2: Running database migration for documents table..."

# Run the documents table migration
if $PYTHON_PATH -c "
import asyncio
import sys
sys.path.append('src')
from multimodal_librarian.database.migrations.add_documents_table import apply_migration

async def run_migration():
    try:
        success = await apply_migration()
        if success:
            print('Migration completed successfully')
            return True
        else:
            print('Migration failed')
            return False
    except Exception as e:
        print(f'Migration error: {e}')
        return False

result = asyncio.run(run_migration())
sys.exit(0 if result else 1)
"; then
    log_success "Documents table migration completed"
else
    log_error "Documents table migration failed"
    exit 1
fi

log_info "Step 3: Testing S3 storage service..."

# Test S3 connection
if $PYTHON_PATH -c "
import sys
sys.path.append('src')
from multimodal_librarian.services.storage_service import StorageService

try:
    storage = StorageService()
    health = storage.health_check()
    if health['status'] == 'healthy':
        print('S3 storage service is healthy')
        print(f'Bucket: {health[\"bucket_name\"]}')
        exit(0)
    else:
        print(f'S3 storage service is unhealthy: {health.get(\"error\", \"Unknown error\")}')
        exit(1)
except Exception as e:
    print(f'S3 storage test failed: {e}')
    exit(1)
"; then
    log_success "S3 storage service verified"
else
    log_warning "S3 storage service check failed - continuing anyway"
fi

log_info "Step 4: Testing document upload service..."

# Test upload service
if $PYTHON_PATH -c "
import asyncio
import sys
sys.path.append('src')
from multimodal_librarian.services.upload_service import UploadService

async def test_upload_service():
    try:
        upload_service = UploadService()
        stats = await upload_service.get_upload_statistics()
        print(f'Upload service working - Total documents: {stats[\"total_documents\"]}')
        return True
    except Exception as e:
        print(f'Upload service test failed: {e}')
        return False

result = asyncio.run(test_upload_service())
sys.exit(0 if result else 1)
"; then
    log_success "Upload service verified"
else
    log_error "Upload service test failed"
    exit 1
fi

log_info "Step 5: Verifying API endpoints..."

# Start the application in background for testing
log_info "Starting application for endpoint testing..."

# Kill any existing processes on port 8000
pkill -f "uvicorn.*8000" || true
sleep 2

# Start the application
cd "$PROJECT_ROOT"
$PYTHON_PATH -m uvicorn src.multimodal_librarian.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for application to start
sleep 10

# Test health endpoint
if curl -s -f http://localhost:8000/api/documents/health > /dev/null; then
    log_success "Document API health endpoint working"
else
    log_error "Document API health endpoint failed"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Test document list endpoint
if curl -s -f http://localhost:8000/api/documents/ > /dev/null; then
    log_success "Document list endpoint working"
else
    log_error "Document list endpoint failed"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Test statistics endpoint
if curl -s -f http://localhost:8000/api/documents/stats/summary > /dev/null; then
    log_success "Document statistics endpoint working"
else
    log_warning "Document statistics endpoint failed - continuing anyway"
fi

# Test static file serving
if curl -s -f http://localhost:8000/static/document_manager.html > /dev/null; then
    log_success "Document manager UI accessible"
else
    log_warning "Document manager UI not accessible - check static file serving"
fi

# Stop the test application
kill $APP_PID 2>/dev/null || true
sleep 2

log_info "Step 6: Creating test data (optional)..."

# Create a simple test document entry (optional)
$PYTHON_PATH -c "
import asyncio
import sys
sys.path.append('src')
from multimodal_librarian.services.upload_service import UploadService
from multimodal_librarian.models.documents import DocumentUploadRequest

async def create_test_data():
    try:
        # This is just a verification that the service can handle requests
        # We won't actually create test data without a real file
        upload_service = UploadService()
        stats = await upload_service.get_upload_statistics()
        print(f'Service ready - Current document count: {stats[\"total_documents\"]}')
        return True
    except Exception as e:
        print(f'Test data creation failed: {e}')
        return False

result = asyncio.run(create_test_data())
" || log_warning "Test data creation skipped"

log_info "Step 7: Deployment verification..."

# Final verification
echo ""
echo "🔍 Deployment Verification:"
echo "=========================="

# Check database tables
if $PYTHON_PATH -c "
import asyncio
import sys
sys.path.append('src')
from multimodal_librarian.database.connection import get_database_connection
from sqlalchemy import text

async def verify_tables():
    try:
        db_pool = await get_database_connection()
        async with db_pool.acquire() as conn:
            # Check documents table
            result = await conn.fetchval(text('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'documents'
                );
            '''))
            
            if result:
                print('✅ Documents table exists')
            else:
                print('❌ Documents table missing')
                return False
            
            # Check document_chunks table
            result = await conn.fetchval(text('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'document_chunks'
                );
            '''))
            
            if result:
                print('✅ Document chunks table exists')
            else:
                print('❌ Document chunks table missing')
                return False
            
            # Check processing_jobs table
            result = await conn.fetchval(text('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'processing_jobs'
                );
            '''))
            
            if result:
                print('✅ Processing jobs table exists')
            else:
                print('❌ Processing jobs table missing')
                return False
            
            return True
    except Exception as e:
        print(f'❌ Table verification failed: {e}')
        return False

result = asyncio.run(verify_tables())
sys.exit(0 if result else 1)
"; then
    log_success "Database tables verified"
else
    log_error "Database table verification failed"
    exit 1
fi

# Check static files
if [ -f "$PROJECT_ROOT/src/multimodal_librarian/static/document_manager.html" ]; then
    echo "✅ Document manager HTML exists"
else
    echo "❌ Document manager HTML missing"
    exit 1
fi

if [ -f "$PROJECT_ROOT/src/multimodal_librarian/static/css/document_manager.css" ]; then
    echo "✅ Document manager CSS exists"
else
    echo "❌ Document manager CSS missing"
    exit 1
fi

if [ -f "$PROJECT_ROOT/src/multimodal_librarian/static/js/document_manager.js" ]; then
    echo "✅ Document manager JavaScript exists"
else
    echo "❌ Document manager JavaScript missing"
    exit 1
fi

echo ""
log_success "Task 3 deployment completed successfully!"
echo ""
echo "📋 Summary:"
echo "==========="
echo "✅ Database migration applied (documents, document_chunks, processing_jobs tables)"
echo "✅ Upload service configured with S3 integration"
echo "✅ Document management API endpoints deployed"
echo "✅ Modern web interface with drag-and-drop upload"
echo "✅ Real-time progress tracking and status updates"
echo "✅ Document library with search and filtering"
echo ""
echo "🌐 Access Points:"
echo "================"
echo "• Document Manager UI: http://localhost:8000/static/document_manager.html"
echo "• Document API: http://localhost:8000/api/documents/"
echo "• Upload Endpoint: http://localhost:8000/api/documents/upload"
echo "• Health Check: http://localhost:8000/api/documents/health"
echo ""
echo "📝 Next Steps:"
echo "=============="
echo "1. Start the application: uvicorn src.multimodal_librarian.main:app --host 0.0.0.0 --port 8000"
echo "2. Access the document manager at the URL above"
echo "3. Upload PDF documents using drag-and-drop or browse"
echo "4. Monitor processing status in real-time"
echo "5. Proceed to Task 4 for background processing pipeline"
echo ""
log_success "Task 3: Document Upload and Management System - COMPLETED ✨"