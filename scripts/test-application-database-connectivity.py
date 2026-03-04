#!/usr/bin/env python3
"""
Test if the application container can actually reach the database.
This will exec into the running container and test database connectivity.
"""

import boto3
import json
import time

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
DB_HOST = 'ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com'
DB_PORT = '5432'

ecs = boto3.client('ecs', region_name=REGION)

def get_running_task():
    """Get a running task ARN"""
    tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return None
    
    return tasks['taskArns'][0]

def test_network_connectivity(task_arn):
    """Test basic network connectivity to database"""
    print("\n" + "=" * 70)
    print("TEST 1: NETWORK CONNECTIVITY (ping/telnet)")
    print("=" * 70)
    
    # Extract task ID
    task_id = task_arn.split('/')[-1]
    
    # Test 1: Can we resolve the hostname?
    print(f"\n🔍 Testing DNS resolution for {DB_HOST}...")
    response = ecs.execute_command(
        cluster=CLUSTER_NAME,
        task=task_id,
        container='multimodal-lib-prod-app',
        interactive=False,
        command=f'nslookup {DB_HOST}'
    )
    
    # Test 2: Can we reach the port?
    print(f"\n🔍 Testing TCP connectivity to {DB_HOST}:{DB_PORT}...")
    print("   (Using timeout to avoid hanging)")
    
    # Try to connect using nc (netcat) or telnet
    response = ecs.execute_command(
        cluster=CLUSTER_NAME,
        task=task_id,
        container='multimodal-lib-prod-app',
        interactive=False,
        command=f'timeout 5 bash -c "echo > /dev/tcp/{DB_HOST}/{DB_PORT}" && echo "SUCCESS" || echo "FAILED"'
    )
    
    print(f"   Session ARN: {response.get('session', {}).get('sessionId', 'N/A')}")

def test_database_connection_with_psql(task_arn):
    """Test actual PostgreSQL connection"""
    print("\n" + "=" * 70)
    print("TEST 2: POSTGRESQL CONNECTION (using psql)")
    print("=" * 70)
    
    task_id = task_arn.split('/')[-1]
    
    print(f"\n🔍 Testing PostgreSQL connection...")
    print(f"   Host: {DB_HOST}")
    print(f"   Port: {DB_PORT}")
    print(f"   Database: multimodal_librarian")
    print(f"   User: postgres")
    print(f"   Password: (from environment)")
    
    # Try to connect using psql
    command = f'PGPASSWORD=$DB_PASSWORD psql -h {DB_HOST} -p {DB_PORT} -U postgres -d multimodal_librarian -c "SELECT version();" 2>&1'
    
    print(f"\n   Command: {command}")
    print("   Note: This requires psql to be installed in the container")
    
    response = ecs.execute_command(
        cluster=CLUSTER_NAME,
        task=task_id,
        container='multimodal-lib-prod-app',
        interactive=False,
        command=command
    )
    
    print(f"   Session ARN: {response.get('session', {}).get('sessionId', 'N/A')}")

def test_python_database_connection(task_arn):
    """Test database connection using Python (like the app does)"""
    print("\n" + "=" * 70)
    print("TEST 3: PYTHON DATABASE CONNECTION (like the application)")
    print("=" * 70)
    
    task_id = task_arn.split('/')[-1]
    
    print(f"\n🔍 Testing Python database connection...")
    
    # Create a Python script to test connection
    python_test = f'''
import os
import psycopg2

try:
    conn = psycopg2.connect(
        host="{DB_HOST}",
        port={DB_PORT},
        database="multimodal_librarian",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", ""),
        connect_timeout=5
    )
    print("✅ SUCCESS: Connected to database!")
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"   PostgreSQL version: {{version[0][:50]}}...")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ FAILED: {{str(e)}}")
    import traceback
    traceback.print_exc()
'''
    
    command = f'python3 -c "{python_test}"'
    
    print("   Testing with psycopg2 (same library the app uses)")
    
    response = ecs.execute_command(
        cluster=CLUSTER_NAME,
        task=task_id,
        container='multimodal-lib-prod-app',
        interactive=False,
        command=command
    )
    
    print(f"   Session ARN: {response.get('session', {}).get('sessionId', 'N/A')}")

def test_environment_variables(task_arn):
    """Check if environment variables are set correctly"""
    print("\n" + "=" * 70)
    print("TEST 4: ENVIRONMENT VARIABLES")
    print("=" * 70)
    
    task_id = task_arn.split('/')[-1]
    
    print(f"\n🔍 Checking database environment variables...")
    
    command = 'echo "DB_HOST=$DB_HOST" && echo "DB_PORT=$DB_PORT" && echo "DB_NAME=$DB_NAME" && echo "DB_USER=$DB_USER" && echo "DB_PASSWORD=${DB_PASSWORD:0:5}..." '
    
    response = ecs.execute_command(
        cluster=CLUSTER_NAME,
        task=task_id,
        container='multimodal-lib-prod-app',
        interactive=False,
        command=command
    )
    
    print(f"   Session ARN: {response.get('session', {}).get('sessionId', 'N/A')}")

def main():
    print("=" * 70)
    print("APPLICATION → DATABASE CONNECTIVITY TEST")
    print("=" * 70)
    print("\nThis script will exec into the running container and test:")
    print("1. Network connectivity (DNS, TCP)")
    print("2. PostgreSQL connection (psql)")
    print("3. Python database connection (psycopg2)")
    print("4. Environment variables")
    
    print("\n⚠️  NOTE: ECS Exec must be enabled on the service!")
    print("   If not enabled, these tests will fail.")
    
    # Get running task
    task_arn = get_running_task()
    if not task_arn:
        return 1
    
    print(f"\n📋 Using task: {task_arn.split('/')[-1]}")
    
    try:
        test_environment_variables(task_arn)
        test_network_connectivity(task_arn)
        test_database_connection_with_psql(task_arn)
        test_python_database_connection(task_arn)
        
        print("\n" + "=" * 70)
        print("TESTS INITIATED")
        print("=" * 70)
        print("\n⚠️  Note: ECS Execute Command is asynchronous.")
        print("   Check CloudWatch Logs or use AWS Console to see results.")
        print("   Log Group: /ecs/multimodal-lib-prod-app")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
