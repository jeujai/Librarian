#!/usr/bin/env python3
"""
Interactive Log Viewer for Local Development

This script provides an interactive terminal-based log viewer for all services
in the local development environment with real-time filtering and search capabilities.
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import subprocess
import signal
import os
from dataclasses import dataclass
from enum import Enum
import curses
import threading
import queue
import time

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class LogEntry:
    timestamp: datetime
    level: LogLevel
    service: str
    message: str
    raw_line: str
    context: Dict = None

class LogViewer:
    """Interactive log viewer with filtering and search capabilities"""
    
    def __init__(self, compose_file: str = "docker-compose.local.yml"):
        self.compose_file = compose_file
        self.services = [
            "multimodal-librarian",
            "postgres", 
            "neo4j",
            "milvus",
            "redis",
            "etcd",
            "minio"
        ]
        self.log_queue = queue.Queue()
        self.running = True
        self.filters = {
            'services': set(self.services),
            'levels': set([level.value for level in LogLevel]),
            'search_term': '',
            'since': None
        }
        
    def start_interactive_viewer(self):
        """Start the interactive curses-based log viewer"""
        try:
            curses.wrapper(self._run_interactive)
        except KeyboardInterrupt:
            self.stop()
    
    def _run_interactive(self, stdscr):
        """Run the interactive log viewer with curses"""
        # Initialize curses
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(1)   # Non-blocking input
        stdscr.timeout(100) # 100ms timeout for getch()
        
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)     # ERROR
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # WARNING
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)   # INFO
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)    # DEBUG
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # CRITICAL
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)    # Header
        
        # Start log collection thread
        log_thread = threading.Thread(target=self._collect_logs, daemon=True)
        log_thread.start()
        
        # Display state
        log_lines = []
        scroll_pos = 0
        filter_mode = False
        search_mode = False
        search_buffer = ""
        
        while self.running:
            height, width = stdscr.getmaxyx()
            
            # Clear screen
            stdscr.clear()
            
            # Draw header
            self._draw_header(stdscr, width)
            
            # Draw filter status
            filter_line = 2
            self._draw_filters(stdscr, filter_line, width)
            
            # Calculate log display area
            log_start_line = 4
            log_height = height - log_start_line - 2
            
            # Collect new log entries
            while not self.log_queue.empty():
                try:
                    entry = self.log_queue.get_nowait()
                    if self._matches_filters(entry):
                        formatted_line = self._format_log_entry(entry, width - 2)
                        log_lines.append((entry, formatted_line))
                        
                        # Keep only last 1000 lines
                        if len(log_lines) > 1000:
                            log_lines = log_lines[-1000:]
                            
                except queue.Empty:
                    break
            
            # Auto-scroll to bottom unless user has scrolled up
            if scroll_pos == 0:
                scroll_pos = max(0, len(log_lines) - log_height)
            
            # Draw log lines
            for i in range(log_height):
                line_idx = scroll_pos + i
                if line_idx < len(log_lines):
                    entry, formatted_line = log_lines[line_idx]
                    color = self._get_log_color(entry.level)
                    
                    try:
                        stdscr.addstr(log_start_line + i, 1, formatted_line[:width-2], color)
                    except curses.error:
                        pass  # Ignore if line is too long
            
            # Draw status line
            status_line = height - 1
            if search_mode:
                status_text = f"Search: {search_buffer}_"
            elif filter_mode:
                status_text = "Filter mode - Press 's' for services, 'l' for levels, 'q' to exit"
            else:
                status_text = f"Lines: {len(log_lines)} | Scroll: {scroll_pos} | Press 'h' for help"
            
            try:
                stdscr.addstr(status_line, 1, status_text[:width-2])
            except curses.error:
                pass
            
            # Refresh screen
            stdscr.refresh()
            
            # Handle input
            key = stdscr.getch()
            
            if key == ord('q') and not search_mode:
                break
            elif key == ord('h') and not search_mode:
                self._show_help(stdscr)
            elif key == ord('f') and not search_mode:
                filter_mode = not filter_mode
            elif key == ord('/') and not search_mode:
                search_mode = True
                search_buffer = ""
            elif key == ord('c') and not search_mode:
                log_lines.clear()
                scroll_pos = 0
            elif key == curses.KEY_UP and not search_mode:
                scroll_pos = max(0, scroll_pos - 1)
            elif key == curses.KEY_DOWN and not search_mode:
                scroll_pos = min(len(log_lines) - log_height, scroll_pos + 1)
            elif key == curses.KEY_PPAGE and not search_mode:  # Page Up
                scroll_pos = max(0, scroll_pos - log_height)
            elif key == curses.KEY_NPAGE and not search_mode:  # Page Down
                scroll_pos = min(len(log_lines) - log_height, scroll_pos + log_height)
            elif search_mode:
                if key == 27:  # ESC
                    search_mode = False
                    search_buffer = ""
                    self.filters['search_term'] = ""
                elif key == ord('\n') or key == ord('\r'):
                    search_mode = False
                    self.filters['search_term'] = search_buffer
                elif key == curses.KEY_BACKSPACE or key == 127:
                    search_buffer = search_buffer[:-1]
                elif 32 <= key <= 126:  # Printable characters
                    search_buffer += chr(key)
            elif filter_mode:
                if key == ord('s'):
                    self._toggle_service_filter(stdscr)
                elif key == ord('l'):
                    self._toggle_level_filter(stdscr)
                elif key == ord('q'):
                    filter_mode = False
        
        self.stop()
    
    def _draw_header(self, stdscr, width):
        """Draw the header line"""
        header = "Multimodal Librarian - Log Viewer"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            stdscr.addstr(0, 1, header, curses.color_pair(6))
            stdscr.addstr(0, width - len(timestamp) - 2, timestamp, curses.color_pair(6))
        except curses.error:
            pass
    
    def _draw_filters(self, stdscr, line, width):
        """Draw current filter status"""
        services_text = f"Services: {', '.join(sorted(self.filters['services']))}"
        levels_text = f"Levels: {', '.join(sorted(self.filters['levels']))}"
        search_text = f"Search: '{self.filters['search_term']}'" if self.filters['search_term'] else "Search: none"
        
        try:
            stdscr.addstr(line, 1, services_text[:width-2])
            stdscr.addstr(line + 1, 1, f"{levels_text} | {search_text}"[:width-2])
        except curses.error:
            pass
    
    def _get_log_color(self, level: LogLevel):
        """Get curses color pair for log level"""
        color_map = {
            LogLevel.DEBUG: curses.color_pair(4),
            LogLevel.INFO: curses.color_pair(3),
            LogLevel.WARNING: curses.color_pair(2),
            LogLevel.ERROR: curses.color_pair(1),
            LogLevel.CRITICAL: curses.color_pair(5)
        }
        return color_map.get(level, curses.color_pair(3))
    
    def _format_log_entry(self, entry: LogEntry, max_width: int) -> str:
        """Format a log entry for display"""
        timestamp_str = entry.timestamp.strftime("%H:%M:%S")
        service_str = entry.service[:12].ljust(12)
        level_str = entry.level.value[:4].ljust(4)
        
        prefix = f"{timestamp_str} {service_str} {level_str} "
        message_width = max_width - len(prefix)
        
        if len(entry.message) > message_width:
            message = entry.message[:message_width-3] + "..."
        else:
            message = entry.message
        
        return f"{prefix}{message}"
    
    def _matches_filters(self, entry: LogEntry) -> bool:
        """Check if log entry matches current filters"""
        # Service filter
        if entry.service not in self.filters['services']:
            return False
        
        # Level filter
        if entry.level.value not in self.filters['levels']:
            return False
        
        # Search filter
        if self.filters['search_term']:
            search_term = self.filters['search_term'].lower()
            if search_term not in entry.message.lower() and search_term not in entry.service.lower():
                return False
        
        # Time filter
        if self.filters['since']:
            if entry.timestamp < self.filters['since']:
                return False
        
        return True
    
    def _collect_logs(self):
        """Collect logs from docker-compose in background thread"""
        try:
            cmd = [
                "docker-compose", "-f", self.compose_file,
                "logs", "-f", "--tail=100"
            ] + self.services
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            for line in iter(process.stdout.readline, ''):
                if not self.running:
                    break
                
                entry = self._parse_log_line(line.strip())
                if entry:
                    self.log_queue.put(entry)
            
        except Exception as e:
            # Put error in queue to display
            error_entry = LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.ERROR,
                service="log-viewer",
                message=f"Failed to collect logs: {str(e)}",
                raw_line=""
            )
            self.log_queue.put(error_entry)
    
    def _parse_log_line(self, line: str) -> Optional[LogEntry]:
        """Parse a log line from docker-compose logs"""
        if not line:
            return None
        
        try:
            # Try to extract service name from docker-compose format
            # Format: service_name_1  | log message
            parts = line.split('|', 1)
            if len(parts) != 2:
                return None
            
            service_part = parts[0].strip()
            message_part = parts[1].strip()
            
            # Extract service name (remove container suffix like _1)
            service_match = re.match(r'^([^_]+)(?:_\d+)?', service_part)
            if not service_match:
                return None
            
            service = service_match.group(1)
            
            # Try to parse structured JSON log
            try:
                log_data = json.loads(message_part)
                timestamp = datetime.fromisoformat(log_data.get('timestamp', '').replace('Z', '+00:00'))
                level = LogLevel(log_data.get('level', 'INFO'))
                message = log_data.get('message', message_part)
                context = log_data.get('context', {})
            except (json.JSONDecodeError, ValueError):
                # Fall back to plain text parsing
                timestamp = datetime.now()
                
                # Try to extract log level from message
                level = LogLevel.INFO
                for log_level in LogLevel:
                    if log_level.value in message_part.upper():
                        level = log_level
                        break
                
                message = message_part
                context = {}
            
            return LogEntry(
                timestamp=timestamp,
                level=level,
                service=service,
                message=message,
                raw_line=line,
                context=context
            )
            
        except Exception:
            # Return a basic entry for unparseable lines
            return LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO,
                service="unknown",
                message=line,
                raw_line=line
            )
    
    def _show_help(self, stdscr):
        """Show help screen"""
        help_text = [
            "Log Viewer Help",
            "===============",
            "",
            "Navigation:",
            "  ↑/↓        - Scroll up/down one line",
            "  PgUp/PgDn   - Scroll up/down one page",
            "",
            "Commands:",
            "  q          - Quit",
            "  h          - Show this help",
            "  f          - Toggle filter mode",
            "  /          - Search logs",
            "  c          - Clear log buffer",
            "",
            "Filter Mode:",
            "  s          - Toggle service filters",
            "  l          - Toggle log level filters",
            "  q          - Exit filter mode",
            "",
            "Search Mode:",
            "  Type to search, Enter to apply, Esc to cancel",
            "",
            "Press any key to continue..."
        ]
        
        stdscr.clear()
        for i, line in enumerate(help_text):
            try:
                stdscr.addstr(i + 1, 2, line)
            except curses.error:
                pass
        
        stdscr.refresh()
        stdscr.getch()
    
    def _toggle_service_filter(self, stdscr):
        """Interactive service filter toggle"""
        stdscr.clear()
        stdscr.addstr(1, 2, "Toggle Services (space to toggle, enter to finish):")
        
        selected = list(self.filters['services'])
        current = 0
        
        while True:
            for i, service in enumerate(self.services):
                marker = "[x]" if service in selected else "[ ]"
                highlight = curses.A_REVERSE if i == current else 0
                try:
                    stdscr.addstr(3 + i, 4, f"{marker} {service}", highlight)
                except curses.error:
                    pass
            
            stdscr.refresh()
            key = stdscr.getch()
            
            if key == curses.KEY_UP:
                current = max(0, current - 1)
            elif key == curses.KEY_DOWN:
                current = min(len(self.services) - 1, current + 1)
            elif key == ord(' '):
                service = self.services[current]
                if service in selected:
                    selected.remove(service)
                else:
                    selected.append(service)
            elif key == ord('\n') or key == ord('\r'):
                break
        
        self.filters['services'] = set(selected)
    
    def _toggle_level_filter(self, stdscr):
        """Interactive log level filter toggle"""
        stdscr.clear()
        stdscr.addstr(1, 2, "Toggle Log Levels (space to toggle, enter to finish):")
        
        levels = [level.value for level in LogLevel]
        selected = list(self.filters['levels'])
        current = 0
        
        while True:
            for i, level in enumerate(levels):
                marker = "[x]" if level in selected else "[ ]"
                highlight = curses.A_REVERSE if i == current else 0
                try:
                    stdscr.addstr(3 + i, 4, f"{marker} {level}", highlight)
                except curses.error:
                    pass
            
            stdscr.refresh()
            key = stdscr.getch()
            
            if key == curses.KEY_UP:
                current = max(0, current - 1)
            elif key == curses.KEY_DOWN:
                current = min(len(levels) - 1, current + 1)
            elif key == ord(' '):
                level = levels[current]
                if level in selected:
                    selected.remove(level)
                else:
                    selected.append(level)
            elif key == ord('\n') or key == ord('\r'):
                break
        
        self.filters['levels'] = set(selected)
    
    def stop(self):
        """Stop the log viewer"""
        self.running = False

def main():
    parser = argparse.ArgumentParser(description="Interactive log viewer for local development")
    parser.add_argument(
        "--compose-file", "-f",
        default="docker-compose.local.yml",
        help="Docker compose file to use"
    )
    parser.add_argument(
        "--services", "-s",
        nargs="+",
        help="Specific services to monitor"
    )
    parser.add_argument(
        "--since",
        help="Show logs since timestamp (e.g., '2024-01-15T10:00:00')"
    )
    
    args = parser.parse_args()
    
    viewer = LogViewer(args.compose_file)
    
    if args.services:
        viewer.services = args.services
        viewer.filters['services'] = set(args.services)
    
    if args.since:
        try:
            viewer.filters['since'] = datetime.fromisoformat(args.since)
        except ValueError:
            print(f"Invalid timestamp format: {args.since}")
            sys.exit(1)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        viewer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("Starting interactive log viewer...")
    print("Press 'h' for help, 'q' to quit")
    time.sleep(1)
    
    try:
        viewer.start_interactive_viewer()
    except Exception as e:
        print(f"Error starting log viewer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()