#!/usr/bin/env python3
"""
Test Neo4j connectivity from the application environment.
"""

import json
import boto3
import socket
import time
from neo4j import GraphDatabase
import sys

def get_neo4j_credentials():
    """Get Neo4j credentials from AWS Secrets Manager."""
    secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
    
    try:
        response = secrets_client.get_secret_value(
            SecretId='multimodal-librarian/full-ml/neo4j'
        )
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"❌ Failed to get Neo4j credentials: {e}")
        return None

def test_port_connectivity(host, port, timeout=5):
    """Test if a port is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"❌ Port connectivity test failed: {e}")
        return False

def test_neo4j_connection(credentials):
    """Test Neo4j database connection."""
    try:
        uri = f"bolt://{credentials['host']}:{credentials['port']}"
        driver = GraphDatabase.driver(
            uri, 
            auth=(credentials['username'], credentials['password'])
        )
        
        # Test connection with a simple query
        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            record = result.single()
            message = record["message"]
            
        driver.close()
        return True, message
    except Exception as e:
        return False, str(e)

def main():
    print("🔍 Testing Neo4j connectivity...")
    print()
    
    # Get credentials
    print("📋 Getting Neo4j credentials from Secrets Manager...")
    credentials = get_neo4j_credentials()
    if not credentials:
        sys.exit(1)
    
    host = credentials['host']
    port = credentials['port']
    print(f"✅ Retrieved credentials for {host}:{port}")
    print()
    
    # Test port connectivity
    print("🔌 Testing port connectivity...")
    
    # Test Bolt port (7687)
    if test_port_connectivity(host, 7687):
        print("✅ Neo4j Bolt port (7687) is accessible")
    else:
        print("❌ Neo4j Bolt port (7687) is not accessible")
        print("   Neo4j may still be starting up. Please wait a few more minutes.")
        return
    
    # Test HTTP port (7474)
    if test_port_connectivity(host, 7474):
        print("✅ Neo4j HTTP port (7474) is accessible")
    else:
        print("❌ Neo4j HTTP port (7474) is not accessible")
    
    print()
    
    # Test database connection
    print("🗄️  Testing Neo4j database connection...")
    success, result = test_neo4j_connection(credentials)
    
    if success:
        print(f"✅ Neo4j connection successful! Response: {result}")
        print()
        print("🎉 Neo4j is ready for use!")
    else:
        print(f"❌ Neo4j connection failed: {result}")
        print("   This might be normal if Neo4j is still initializing.")
        print("   Please wait a few more minutes and try again.")

if __name__ == "__main__":
    main()