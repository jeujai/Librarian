#!/usr/bin/env python3
"""
Sample Analytics and Metrics Data Generator

This script generates sample analytics and metrics data for local development.
It creates realistic usage patterns, performance metrics, and audit logs.

Usage:
    python scripts/seed-sample-analytics.py [--days N] [--reset] [--events-per-day M]
    
    --days N: Number of days of historical data (default: 30)
    --reset: Drop existing analytics data before creating new data
    --events-per-day M: Average events per day (default: 100)
"""

import asyncio
import argparse
import logging
import uuid
import json
import random
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SampleAnalyticsGenerator:
    """Generator for sample analytics and metrics data."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Event type templates with realistic distributions
        self.event_types = [
            {"type": "document_upload", "weight": 0.15, "level": "info"},
            {"type": "document_processing", "weight": 0.12, "level": "info"},
            {"type": "chat_message", "weight": 0.25, "level": "info"},
            {"type": "search_query", "weight": 0.20, "level": "info"},
            {"type": "document_download", "weight": 0.08, "level": "info"},
            {"type": "user_login", "weight": 0.10, "level": "info"},
            {"type": "user_logout", "weight": 0.05, "level": "info"},
            {"type": "api_request", "weight": 0.03, "level": "info"},
            {"type": "system_error", "weight": 0.015, "level": "error"},
            {"type": "security_event", "weight": 0.005, "level": "warning"}
        ]
        
        # Sample actions for different resource types
        self.actions = {
            "document": ["upload", "download", "view", "delete", "process", "share"],
            "user": ["login", "logout", "register", "update_profile", "change_password"],
            "chat": ["send_message", "start_conversation", "end_conversation"],
            "search": ["query", "filter", "sort", "export_results"],
            "system": ["backup", "maintenance", "update", "restart"],
            "api": ["authenticate", "rate_limit", "request", "response"]
        }
        
        # Sample IP addresses for realistic distribution
        self.sample_ips = [
            "192.168.1.100", "192.168.1.101", "192.168.1.102",
            "10.0.0.50", "10.0.0.51", "10.0.0.52",
            "172.16.0.10", "172.16.0.11", "172.16.0.12",
            "127.0.0.1"  # localhost
        ]
        
        # Sample user agents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            "PostmanRuntime/7.28.0",  # API client
            "curl/7.68.0",  # Command line
            "Python/3.9 requests/2.25.1"  # Python client
        ]
    
    async def generate_analytics_data(self, days: int = 30, reset: bool = False, events_per_day: int = 100) -> Dict[str, Any]:
        """
        Generate sample analytics and metrics data.
        
        Args:
            days: Number of days of historical data to generate
            reset: Whether to reset existing analytics data first
            events_per_day: Average number of events per day
            
        Returns:
            Dictionary with statistics about generated data
        """
        logger.info(f"Generating {days} days of analytics data (reset={reset}, events_per_day={events_per_day})")
        
        try:
            # Get database client
            db_client = await self.factory.get_relational_client()
            
            # Get sample users and documents for realistic references
            users = await self._get_sample_users(db_client)
            documents = await self._get_sample_documents(db_client)
            
            # Reset analytics data if requested
            if reset:
                await self._reset_analytics_data(db_client)
            
            # Generate data for each day
            stats = {
                "total_audit_logs": 0,
                "total_interaction_feedback": 0,
                "total_security_incidents": 0,
                "days_generated": days,
                "events_by_type": {},
                "events_by_level": {}
            }
            
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            for day_offset in range(days):
                current_date = start_date + timedelta(days=day_offset)
                
                # Generate events for this day
                daily_events = int(random.gauss(events_per_day, events_per_day * 0.2))
                daily_events = max(10, daily_events)  # At least 10 events per day
                
                # Generate audit logs
                audit_logs = await self._generate_daily_audit_logs(
                    db_client, current_date, daily_events, users, documents
                )
                stats["total_audit_logs"] += len(audit_logs)
                
                # Generate interaction feedback (fewer events)
                if users and documents:
                    feedback_events = max(1, daily_events // 10)  # 10% of audit events
                    feedback_logs = await self._generate_daily_interaction_feedback(
                        db_client, current_date, feedback_events, users, documents
                    )
                    stats["total_interaction_feedback"] += len(feedback_logs)
                
                # Generate security incidents (rare events)
                if random.random() < 0.1:  # 10% chance per day
                    incident = await self._generate_security_incident(db_client, current_date)
                    if incident:
                        stats["total_security_incidents"] += 1
                
                # Update statistics
                for log in audit_logs:
                    event_type = log["event_type"]
                    level = log["level"]
                    
                    stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
                    stats["events_by_level"][level] = stats["events_by_level"].get(level, 0) + 1
                
                if day_offset % 7 == 0:  # Log progress weekly
                    logger.info(f"Generated data for {day_offset + 1}/{days} days")
            
            logger.info(f"Successfully generated analytics data: {stats['total_audit_logs']} audit logs, "
                       f"{stats['total_interaction_feedback']} feedback events, "
                       f"{stats['total_security_incidents']} security incidents")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to generate analytics data: {e}")
            raise
    
    async def _get_sample_users(self, db_client) -> List[Dict[str, Any]]:
        """Get existing sample users for analytics references."""
        try:
            async with db_client.get_async_session() as session:
                result = await session.execute(
                    "SELECT id, user_id, username, email FROM users WHERE is_active = true"
                )
                users = [
                    {"id": row[0], "user_id": row[1], "username": row[2], "email": row[3]}
                    for row in result.fetchall()
                ]
                return users
        except Exception as e:
            logger.warning(f"Could not fetch users: {e}")
            return []
    
    async def _get_sample_documents(self, db_client) -> List[Dict[str, Any]]:
        """Get existing sample documents for analytics references."""
        try:
            async with db_client.get_async_session() as session:
                result = await session.execute(
                    "SELECT id, title, filename, status FROM documents LIMIT 50"
                )
                documents = [
                    {"id": row[0], "title": row[1], "filename": row[2], "status": row[3]}
                    for row in result.fetchall()
                ]
                return documents
        except Exception as e:
            logger.warning(f"Could not fetch documents: {e}")
            return []
    
    async def _reset_analytics_data(self, db_client) -> None:
        """Reset existing analytics and audit data."""
        logger.info("Resetting existing analytics and audit data")
        
        try:
            async with db_client.get_async_session() as session:
                # Delete analytics data
                await session.execute("DELETE FROM interaction_feedback")
                await session.execute("DELETE FROM security_incidents")
                await session.execute("DELETE FROM audit_logs")
                
                # Reset sequences if they exist
                try:
                    await session.execute("ALTER SEQUENCE audit_logs_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE interaction_feedback_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE security_incidents_id_seq RESTART WITH 1")
                except Exception:
                    # Sequences might not exist, ignore
                    pass
                
                await session.commit()
                
            logger.info("Successfully reset analytics data")
            
        except Exception as e:
            logger.error(f"Failed to reset analytics data: {e}")
            raise
    
    async def _generate_daily_audit_logs(self, db_client, date: datetime, event_count: int, 
                                       users: List[Dict], documents: List[Dict]) -> List[Dict[str, Any]]:
        """Generate audit logs for a single day."""
        
        audit_logs = []
        
        for _ in range(event_count):
            # Select event type based on weights
            event_template = random.choices(
                self.event_types,
                weights=[et["weight"] for et in self.event_types]
            )[0]
            
            # Generate timestamp within the day
            event_time = date + timedelta(
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59)
            )
            
            # Select user (if available)
            user = random.choice(users) if users else None
            
            # Generate event details based on type
            event_details = self._generate_event_details(event_template["type"], users, documents)
            
            # Create audit log record
            audit_log = {
                "id": str(uuid.uuid4()),
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "event_type": event_template["type"],
                "level": event_template["level"],
                "timestamp": event_time,
                "user_id": user["id"] if user else None,
                "session_id": f"sess_{uuid.uuid4().hex[:16]}" if user else None,
                "ip_address": random.choice(self.sample_ips),
                "user_agent": random.choice(self.user_agents),
                "resource_type": event_details["resource_type"],
                "resource_id": event_details["resource_id"],
                "action": event_details["action"],
                "result": event_details["result"],
                "details": json.dumps(event_details["details"]),
                "sensitive_data_hash": self._generate_data_hash(event_details) if event_details.get("sensitive") else None
            }
            
            # Insert audit log
            async with db_client.get_async_session() as session:
                audit_sql = """
                    INSERT INTO audit_logs (
                        id, event_id, event_type, level, timestamp, user_id,
                        session_id, ip_address, user_agent, resource_type,
                        resource_id, action, result, details, sensitive_data_hash
                    ) VALUES (
                        :id, :event_id, :event_type, :level, :timestamp, :user_id,
                        :session_id, :ip_address, :user_agent, :resource_type,
                        :resource_id, :action, :result, :details, :sensitive_data_hash
                    )
                """
                await session.execute(audit_sql, audit_log)
                await session.commit()
            
            audit_logs.append({
                "event_type": audit_log["event_type"],
                "level": audit_log["level"],
                "timestamp": audit_log["timestamp"],
                "action": audit_log["action"],
                "result": audit_log["result"]
            })
        
        return audit_logs
    
    def _generate_event_details(self, event_type: str, users: List[Dict], documents: List[Dict]) -> Dict[str, Any]:
        """Generate realistic event details based on event type."""
        
        if event_type == "document_upload":
            doc = random.choice(documents) if documents else {"id": str(uuid.uuid4()), "title": "Sample Document"}
            return {
                "resource_type": "document",
                "resource_id": doc["id"],
                "action": "upload",
                "result": random.choices(["success", "failure"], weights=[0.95, 0.05])[0],
                "details": {
                    "filename": doc.get("title", "document.pdf"),
                    "file_size": random.randint(1048576, 10485760),
                    "processing_time": random.uniform(1.0, 30.0)
                }
            }
        
        elif event_type == "chat_message":
            return {
                "resource_type": "chat",
                "resource_id": f"thread_{uuid.uuid4().hex[:12]}",
                "action": "send_message",
                "result": "success",
                "details": {
                    "message_length": random.randint(10, 500),
                    "response_time": random.uniform(0.5, 5.0),
                    "knowledge_sources": random.randint(0, 3)
                }
            }
        
        elif event_type == "search_query":
            return {
                "resource_type": "search",
                "resource_id": f"query_{uuid.uuid4().hex[:8]}",
                "action": "query",
                "result": "success",
                "details": {
                    "query_length": random.randint(5, 100),
                    "results_count": random.randint(0, 50),
                    "search_time": random.uniform(0.1, 2.0)
                }
            }
        
        elif event_type == "user_login":
            user = random.choice(users) if users else {"user_id": "unknown"}
            return {
                "resource_type": "user",
                "resource_id": user.get("user_id", "unknown"),
                "action": "login",
                "result": random.choices(["success", "failure"], weights=[0.9, 0.1])[0],
                "details": {
                    "login_method": random.choice(["password", "api_key"]),
                    "two_factor": random.choice([True, False])
                },
                "sensitive": True
            }
        
        elif event_type == "system_error":
            return {
                "resource_type": "system",
                "resource_id": "application",
                "action": "error",
                "result": "error",
                "details": {
                    "error_type": random.choice([
                        "database_connection", "memory_limit", "timeout",
                        "validation_error", "processing_error"
                    ]),
                    "severity": random.choice(["low", "medium", "high"]),
                    "component": random.choice([
                        "pdf_processor", "vector_store", "graph_db", "api_server"
                    ])
                }
            }
        
        elif event_type == "security_event":
            return {
                "resource_type": "security",
                "resource_id": f"sec_{uuid.uuid4().hex[:8]}",
                "action": "security_check",
                "result": "security_event",
                "details": {
                    "event_type": random.choice([
                        "failed_login_attempt", "rate_limit_exceeded",
                        "suspicious_activity", "unauthorized_access"
                    ]),
                    "severity": random.choice(["medium", "high"]),
                    "blocked": random.choice([True, False])
                }
            }
        
        else:
            # Generic event
            return {
                "resource_type": "system",
                "resource_id": str(uuid.uuid4()),
                "action": "generic_action",
                "result": "success",
                "details": {
                    "event_type": event_type,
                    "processing_time": random.uniform(0.1, 1.0)
                }
            }
    
    async def _generate_daily_interaction_feedback(self, db_client, date: datetime, event_count: int,
                                                 users: List[Dict], documents: List[Dict]) -> List[Dict[str, Any]]:
        """Generate interaction feedback events for a single day."""
        
        feedback_logs = []
        
        for _ in range(event_count):
            # Generate timestamp within the day
            event_time = date + timedelta(
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59)
            )
            
            # Select user and document
            user = random.choice(users) if users else None
            document = random.choice(documents) if documents else None
            
            if not user or not document:
                continue
            
            # Generate feedback data
            interaction_types = ["view", "cite", "export", "rate"]
            interaction_type = random.choice(interaction_types)
            
            # Generate feedback score (-1.0 to 1.0)
            if interaction_type == "rate":
                # Explicit ratings tend to be more extreme
                feedback_score = random.choices(
                    [-1.0, -0.5, 0.0, 0.5, 1.0],
                    weights=[0.1, 0.15, 0.2, 0.3, 0.25]
                )[0]
            else:
                # Implicit feedback based on interaction type
                if interaction_type in ["cite", "export"]:
                    feedback_score = random.uniform(0.3, 1.0)  # Positive actions
                else:
                    feedback_score = random.uniform(-0.2, 0.8)  # Mostly positive
            
            feedback_record = {
                "id": str(uuid.uuid4()),
                "feedback_id": f"fb_{uuid.uuid4().hex[:12]}",
                "chunk_id": f"chunk_{uuid.uuid4().hex[:8]}",  # Simulated chunk reference
                "user_id": user["user_id"],
                "interaction_type": interaction_type,
                "feedback_score": feedback_score,
                "context_query": self._generate_context_query(),
                "timestamp": event_time
            }
            
            # Insert feedback record
            async with db_client.get_async_session() as session:
                feedback_sql = """
                    INSERT INTO interaction_feedback (
                        id, feedback_id, chunk_id, user_id, interaction_type,
                        feedback_score, context_query, timestamp
                    ) VALUES (
                        :id, :feedback_id, :chunk_id, :user_id, :interaction_type,
                        :feedback_score, :context_query, :timestamp
                    )
                """
                await session.execute(feedback_sql, feedback_record)
                await session.commit()
            
            feedback_logs.append({
                "interaction_type": interaction_type,
                "feedback_score": feedback_score,
                "timestamp": event_time
            })
        
        return feedback_logs
    
    async def _generate_security_incident(self, db_client, date: datetime) -> Optional[Dict[str, Any]]:
        """Generate a security incident for the given date."""
        
        incident_types = [
            "unauthorized_access", "brute_force", "dos", "malware", "data_breach"
        ]
        
        severities = ["low", "medium", "high", "critical"]
        
        incident_type = random.choice(incident_types)
        severity = random.choices(severities, weights=[0.4, 0.3, 0.2, 0.1])[0]
        
        # Generate incident timestamp
        incident_time = date + timedelta(
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )
        
        # Generate incident details
        indicators = {
            "source_ip": random.choice(self.sample_ips),
            "user_agent": random.choice(self.user_agents),
            "request_count": random.randint(1, 1000),
            "time_window": random.randint(1, 3600)
        }
        
        response_actions = [
            "blocked_ip", "rate_limited", "logged_event", "notified_admin"
        ]
        
        incident_record = {
            "id": str(uuid.uuid4()),
            "incident_id": f"inc_{uuid.uuid4().hex[:12]}",
            "incident_type": incident_type,
            "severity": severity,
            "status": random.choice(["open", "investigating", "resolved"]),
            "detected_at": incident_time,
            "resolved_at": incident_time + timedelta(hours=random.randint(1, 24)) if random.random() < 0.7 else None,
            "source_ip": indicators["source_ip"],
            "user_id": None,  # Usually unknown for security incidents
            "description": f"Security incident of type {incident_type} detected from {indicators['source_ip']}",
            "indicators": json.dumps(indicators),
            "response_actions": json.dumps(random.sample(response_actions, random.randint(1, 3))),
            "false_positive": random.random() < 0.1  # 10% false positive rate
        }
        
        # Insert security incident
        async with db_client.get_async_session() as session:
            incident_sql = """
                INSERT INTO security_incidents (
                    id, incident_id, incident_type, severity, status,
                    detected_at, resolved_at, source_ip, user_id, description,
                    indicators, response_actions, false_positive
                ) VALUES (
                    :id, :incident_id, :incident_type, :severity, :status,
                    :detected_at, :resolved_at, :source_ip, :user_id, :description,
                    :indicators, :response_actions, :false_positive
                )
            """
            await session.execute(incident_sql, incident_record)
            await session.commit()
        
        return {
            "incident_type": incident_type,
            "severity": severity,
            "detected_at": incident_time
        }
    
    def _generate_context_query(self) -> str:
        """Generate a realistic context query for feedback."""
        queries = [
            "What is machine learning?",
            "How do neural networks work?",
            "Explain deep learning concepts",
            "Best practices for data preprocessing",
            "Computer vision applications",
            "Natural language processing techniques",
            "Model evaluation methods",
            "Feature engineering strategies",
            "Hyperparameter optimization",
            "Transfer learning examples"
        ]
        return random.choice(queries)
    
    def _generate_data_hash(self, event_details: Dict[str, Any]) -> str:
        """Generate a hash for sensitive data."""
        sensitive_data = json.dumps(event_details, sort_keys=True)
        return hashlib.sha256(sensitive_data.encode()).hexdigest()
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the sample analytics generator."""
    parser = argparse.ArgumentParser(description="Generate sample analytics data for local development")
    parser.add_argument("--days", type=int, default=30, help="Number of days of historical data")
    parser.add_argument("--reset", action="store_true", help="Reset existing analytics data first")
    parser.add_argument("--events-per-day", type=int, default=100, help="Average events per day")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    try:
        config = LocalDatabaseConfig()
        logger.info(f"Loaded configuration for {config.database_type} environment")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
    
    # Generate sample analytics data
    generator = SampleAnalyticsGenerator(config)
    
    try:
        stats = await generator.generate_analytics_data(
            days=args.days,
            reset=args.reset,
            events_per_day=args.events_per_day
        )
        
        print(f"\n✅ Successfully generated {args.days} days of analytics data!")
        
        print(f"\n📊 Analytics Statistics:")
        print("=" * 50)
        print(f"Total Audit Logs:       {stats['total_audit_logs']:6d}")
        print(f"Interaction Feedback:   {stats['total_interaction_feedback']:6d}")
        print(f"Security Incidents:     {stats['total_security_incidents']:6d}")
        print(f"Days Generated:         {stats['days_generated']:6d}")
        
        print(f"\nEvents by Type:")
        print("=" * 40)
        for event_type, count in sorted(stats['events_by_type'].items(), key=lambda x: x[1], reverse=True):
            print(f"{event_type:20} | {count:6d}")
        
        print(f"\nEvents by Level:")
        print("=" * 30)
        for level, count in sorted(stats['events_by_level'].items(), key=lambda x: x[1], reverse=True):
            emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(level, "📝")
            print(f"{emoji} {level:10} | {count:6d}")
        
        avg_events_per_day = stats['total_audit_logs'] / args.days
        print(f"\n📈 Average Events/Day:   {avg_events_per_day:6.1f}")
        
        print(f"\n💡 Analytics data includes realistic timestamps, user interactions, and system events")
        print(f"   Use this data to test dashboards, reports, and monitoring systems")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate sample analytics data: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)