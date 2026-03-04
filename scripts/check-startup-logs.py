#!/usr/bin/env python3
"""
Check Startup Logs

This script checks CloudWatch logs to see which startup step is failing or hanging.
It looks for the step-by-step logging markers added by the startup logging fix.
"""

import boto3
import sys
from datetime import datetime, timedelta

def check_startup_logs():
    """Check CloudWatch logs for startup progress."""
    
    print("=" * 80)
    print("CHECKING STARTUP LOGS")
    print("=" * 80)
    print()
    
    # Initialize CloudWatch Logs client
    logs_client = boto3.client('logs', region_name='us-east-1')
    
    log_group = '/ecs/multimodal-librarian-prod'
    
    # Get logs from the last 10 minutes
    start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
    end_time = int(datetime.now().timestamp() * 1000)
    
    print(f"Searching logs from {datetime.fromtimestamp(start_time/1000)}")
    print(f"                 to {datetime.fromtimestamp(end_time/1000)}")
    print()
    
    # Define the steps we're looking for
    steps = [
        "STARTUP EVENT BEGINNING",
        "STEP 1: Initializing startup logger",
        "STEP 2: Initializing user experience logger",
        "STEP 2a: Starting UX logger",
        "STEP 3: Initializing minimal server",
        "STEP 4: Initializing progressive loader",
        "STEP 5: Starting phase progression",
        "STEP 5a: Initializing startup metrics tracking",
        "STEP 5b: Initializing performance tracker",
        "STEP 6: Initializing cache service",
        "STEP 7: Starting alert evaluation",
        "STEP 8: Initializing health monitoring",
        "STEP 9: Initializing startup alerts",
        "STEP 10: Logging application ready state",
        "APPLICATION STARTUP COMPLETED SUCCESSFULLY"
    ]
    
    # Track which steps we've seen
    steps_found = {step: False for step in steps}
    timeout_found = None
    error_found = None
    
    try:
        # Get log streams
        response = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not response['logStreams']:
            print("No log streams found")
            return False
        
        print(f"Checking {len(response['logStreams'])} most recent log streams...")
        print()
        
        # Check each log stream
        for log_stream in response['logStreams']:
            stream_name = log_stream['logStreamName']
            
            try:
                # Get log events
                events_response = logs_client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    startTime=start_time,
                    endTime=end_time,
                    limit=1000
                )
                
                # Check each event
                for event in events_response['events']:
                    message = event['message']
                    
                    # Check for steps
                    for step in steps:
                        if step in message:
                            steps_found[step] = True
                    
                    # Check for timeouts
                    if "TIMEOUT:" in message:
                        timeout_found = message
                    
                    # Check for errors
                    if "✗" in message and "Failed" in message:
                        if not error_found:
                            error_found = message
                
            except Exception as e:
                print(f"Error reading log stream {stream_name}: {e}")
                continue
        
        # Print results
        print("Startup Progress:")
        print("-" * 80)
        
        last_completed_step = None
        for i, step in enumerate(steps):
            status = "✓" if steps_found[step] else "✗"
            print(f"{status} {step}")
            
            if steps_found[step]:
                last_completed_step = i
        
        print()
        print("Analysis:")
        print("-" * 80)
        
        if steps_found["APPLICATION STARTUP COMPLETED SUCCESSFULLY"]:
            print("✓ Startup completed successfully!")
            print()
            print("The application should be running normally.")
            return True
        
        elif timeout_found:
            print("✗ TIMEOUT DETECTED!")
            print()
            print(f"Timeout message: {timeout_found}")
            print()
            print("This tells you exactly which component is hanging.")
            print("Check the component's internal logging for more details.")
            return False
        
        elif error_found:
            print("✗ ERROR DETECTED!")
            print()
            print(f"Error message: {error_found}")
            print()
            print("Check the full logs for stack traces and more details.")
            return False
        
        elif last_completed_step is not None:
            print(f"⚠ Startup appears to be hanging after: {steps[last_completed_step]}")
            print()
            if last_completed_step < len(steps) - 1:
                next_step = steps[last_completed_step + 1]
                print(f"Next expected step: {next_step}")
                print()
                print("The application is likely hanging during this next step.")
                print("Check the component's internal logging for more details.")
            return False
        
        else:
            print("⚠ No startup logging found in recent logs")
            print()
            print("Possible reasons:")
            print("  1. The application hasn't started yet")
            print("  2. The logging fix hasn't been deployed yet")
            print("  3. The application is crashing before logging starts")
            print()
            print("Check the full logs for any error messages.")
            return False
        
    except Exception as e:
        print(f"Error checking logs: {e}")
        return False

if __name__ == "__main__":
    success = check_startup_logs()
    sys.exit(0 if success else 1)
