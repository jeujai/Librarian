#!/usr/bin/env python3
"""
Test Neo4j connectivity from ECS task perspective
"""

import json
import socket
import time
import boto3
from neo4j import GraphDatabase

def test_port_connectivity(host, port, timeout=5):
    """Test if a port is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Port test error: {e}")
        return False

def get_neo4j_credentials():
    """Get Neo4j credentials from AWS Secrets Manager."""
    try:
        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        response = secrets_client.get_secret_value(SecretId='multimodal-librarian/full-ml/neo4j')
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Failed to get credentials: {e}")
        return None

def test_neo4j_connection():
    """Test Neo4j connection."""
    print("🔍 Testing Neo4j connectivity...")
    
    # Get credentials
    credentials = get_neo4j_credentials()
    if not credentials:
        return False
    
    host = credentials['host']
    port = credentials['port']
    username = credentials['username']
    password = credentials['password']
    
    print(f"📍 Testing connection to {host}:{port}")
    print(f"🔧 Using credentials: {username}@{host}")
    print(f"🆔 Instance: i-0255d25fd1950ed2d (10.0.1.47)")
    
    # Test port connectivity
    print("🔌 Testing port connectivity...")
    bolt_accessible = test_port_connectivity(host, 7687)
    http_accessible = test_port_connectivity(host, 7474)
    
    print(f"  Bolt port (7687): {'✅ Accessible' if bolt_accessible else '❌ Not accessible'}")
    print(f"  HTTP port (7474): {'✅ Accessible' if http_accessible else '❌ Not accessible'}")
    
    if not bolt_accessible:
        print("❌ Cannot connect to Neo4j - Bolt port not accessible")
        return False
    
    # Test Neo4j driver connection
    print("🚀 Testing Neo4j driver connection...")
    try:
        uri = f"bolt://{host}:{port}"
        driver = GraphDatabase.driver(uri, auth=(username, password))
        
        # Test connection
        driver.verify_connectivity()
        print("✅ Neo4j driver connection successful")
        
        # Test simple query
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record and record["test"] == 1:
                print("✅ Neo4j query test successful")
                
                # Get database info
                db_info = session.run("CALL dbms.components() YIELD name, versions, edition")
                components = [dict(record) for record in db_info]
                print(f"📊 Database components: {components}")
                
                return True
            else:
                print("❌ Neo4j query test failed")
                return False
                
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            driver.close()

if __name__ == "__main__":
    print("🧪 Neo4j Connectivity Test")
    print("=" * 50)
    
    success = test_neo4j_connection()
    
    print("=" * 50)
    if success:
        print("🎉 Neo4j connectivity test PASSED")
    else:
        print("💥 Neo4j connectivity test FAILED")
    
    exit(0 if success else 1)