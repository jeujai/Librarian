#!/usr/bin/env python3
"""
Check Application Logs for Health Check Requests

This script checks CloudWatch logs to see if the application is receiving
health check requests from the ALB.
"""

import boto3
import time
from datetime import datetime, timedelta

def check_logs():
    """Check CloudWatch logs for health check requests."""
    print("\n" + "="*80)
    print("CHECKING APPLICATION LOGS FOR HEALTH CHECK REQUESTS")
    print("="*80)
    
    logs = boto3.client('logs', region_name='us-east-1')
    
    log_group = '/ecs/multimodal-lib-prod-app'
    
    # Get recent log streams
    print(f"\n📋 Log Group: {log_group}")
    
    try:
        streams_response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not streams_response['logStreams']:
            print("❌ No log streams found")
            return
        
        print(f"\n📝 Recent Log Streams:")
        for stream in streams_response['logStreams']:
            print(f"   - {stream['logStreamName']}")
            print(f"     Last Event: {datetime.fromtimestamp(stream['lastEventTime']/1000)}")
        
        # Check the most recent stream for health check logs
        latest_stream = streams_response['logStreams'][0]
        stream_name = latest_stream['logStreamName']
        
        print(f"\n🔍 Checking latest stream: {stream_name}")
        print(f"   Looking for health check requests in last 10 minutes...")
        
        # Get logs from last 10 minutes
        start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
        end_time = int(datetime.now().timestamp() * 1000)
        
        events_response = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            startTime=start_time,
            endTime=end_time,
            limit=1000
        )
        
        # Look for health check related logs
        health_check_logs = []
        uvicorn_logs = []
        error_logs = []
        
        for event in events_response['events']:
            message = event['message']
            timestamp = datetime.fromtimestamp(event['timestamp']/1000)
            
            if 'health' in message.lower() or '/api/health' in message:
                health_check_logs.append((timestamp, message))
            elif 'uvicorn' in message.lower() or 'started server' in message.lower():
                uvicorn_logs.append((timestamp, message))
            elif 'error' in message.lower() or 'exception' in message.lower():
                error_logs.append((timestamp, message))
        
        print(f"\n📊 Log Analysis:")
        print(f"   Total events: {len(events_response['events'])}")
        print(f"   Health check logs: {len(health_check_logs)}")
        print(f"   Uvicorn logs: {len(uvicorn_logs)}")
        print(f"   Error logs: {len(error_logs)}")
        
        if health_check_logs:
            print(f"\n✅ Found {len(health_check_logs)} health check related logs:")
            for timestamp, message in health_check_logs[-10:]:  # Show last 10
                print(f"   [{timestamp.strftime('%H:%M:%S')}] {message[:200]}")
        else:
            print(f"\n❌ NO health check logs found in last 10 minutes")
            print(f"   This means the application is NOT receiving health check requests")
        
        if uvicorn_logs:
            print(f"\n🚀 Uvicorn Server Logs:")
            for timestamp, message in uvicorn_logs[-5:]:  # Show last 5
                print(f"   [{timestamp.strftime('%H:%M:%S')}] {message[:200]}")
        
        if error_logs:
            print(f"\n⚠️  Recent Errors:")
            for timestamp, message in error_logs[-5:]:  # Show last 5
                print(f"   [{timestamp.strftime('%H:%M:%S')}] {message[:200]}")
        
        # Check if server is even starting
        print(f"\n🔍 Server Startup Check:")
        startup_logs = [msg for ts, msg in uvicorn_logs if 'started' in msg.lower() or 'application startup' in msg.lower()]
        if startup_logs:
            print(f"   ✅ Server appears to be starting")
            for msg in startup_logs[-3:]:
                print(f"      {msg[:200]}")
        else:
            print(f"   ⚠️  No clear server startup logs found")
        
        # Show some recent logs regardless
        print(f"\n📄 Most Recent Logs (last 20):")
        for event in events_response['events'][-20:]:
            timestamp = datetime.fromtimestamp(event['timestamp']/1000)
            message = event['message']
            print(f"   [{timestamp.strftime('%H:%M:%S')}] {message[:150]}")
        
    except Exception as e:
        print(f"❌ Error checking logs: {e}")

def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("APPLICATION LOG ANALYSIS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    check_logs()
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    
    print("\n💡 Next Steps:")
    print("   1. If NO health check logs: Application not receiving requests")
    print("      → Check if application is bound to 0.0.0.0:8000")
    print("      → Check if health endpoint exists at /api/health/simple")
    print("   2. If health check logs present but failing:")
    print("      → Check what error the endpoint is returning")
    print("   3. If server not starting:")
    print("      → Check for startup errors in logs")

if __name__ == "__main__":
    main()
