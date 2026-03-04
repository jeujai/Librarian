#!/usr/bin/env python3
"""
SQL Syntax Validation Script

This script validates the SQL syntax of initialization scripts
without requiring a database connection.
"""

import os
import re
import sys
from pathlib import Path

def validate_sql_file(file_path: Path) -> tuple[bool, list[str]]:
    """Validate SQL file for basic syntax issues."""
    errors = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Basic syntax checks
        
        # Check for unmatched parentheses
        paren_count = content.count('(') - content.count(')')
        if paren_count != 0:
            errors.append(f"Unmatched parentheses: {paren_count} extra opening" if paren_count > 0 else f"{abs(paren_count)} extra closing")
        
        # Check for unmatched quotes (basic check)
        single_quotes = content.count("'")
        if single_quotes % 2 != 0:
            errors.append("Unmatched single quotes")
        
        # Check for common SQL syntax patterns
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Skip comments and empty lines
            if not line_stripped or line_stripped.startswith('--'):
                continue
            
            # Check for CREATE statements without IF NOT EXISTS where appropriate
            if re.match(r'^\s*CREATE\s+(TABLE|SCHEMA|INDEX)\s+(?!IF\s+NOT\s+EXISTS)', line_stripped, re.IGNORECASE):
                # This is just a warning, not an error
                pass
            
            # Check for missing semicolons on statement-ending lines
            if re.match(r'^\s*(CREATE|INSERT|UPDATE|DELETE|ALTER|DROP)', line_stripped, re.IGNORECASE):
                # Look ahead to find the end of this statement
                statement_lines = []
                j = i - 1
                while j < len(lines):
                    statement_lines.append(lines[j].strip())
                    if lines[j].strip().endswith(';'):
                        break
                    if j > i + 20:  # Avoid infinite loops
                        break
                    j += 1
                
                if j < len(lines) and not lines[j].strip().endswith(';'):
                    # Check if this might be a DO block or function
                    statement_text = ' '.join(statement_lines).upper()
                    if 'DO $$' not in statement_text and 'FUNCTION' not in statement_text:
                        errors.append(f"Line {i}: Possible missing semicolon")
        
        # Check for DO blocks syntax
        do_blocks = re.findall(r'DO\s*\$\$.*?\$\$', content, re.DOTALL | re.IGNORECASE)
        for block in do_blocks:
            if block.count('$$') != 2:
                errors.append("DO block with unmatched $$ delimiters")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        return False, [f"Error reading file: {str(e)}"]

def main():
    """Main validation function."""
    init_dir = Path("database/postgresql/init")
    
    if not init_dir.exists():
        print(f"Error: Directory {init_dir} does not exist")
        sys.exit(1)
    
    sql_files = sorted(init_dir.glob("*.sql"))
    
    if not sql_files:
        print(f"No SQL files found in {init_dir}")
        sys.exit(1)
    
    print("PostgreSQL Initialization Scripts - SQL Syntax Validation")
    print("=" * 60)
    
    total_files = len(sql_files)
    valid_files = 0
    
    for sql_file in sql_files:
        print(f"\nValidating: {sql_file.name}")
        is_valid, errors = validate_sql_file(sql_file)
        
        if is_valid:
            print("  ✓ PASS - No syntax issues detected")
            valid_files += 1
        else:
            print("  ✗ FAIL - Issues detected:")
            for error in errors:
                print(f"    - {error}")
    
    print("\n" + "=" * 60)
    print(f"Summary: {valid_files}/{total_files} files passed validation")
    
    if valid_files == total_files:
        print("✓ All SQL files passed basic syntax validation")
        return 0
    else:
        print("✗ Some SQL files have potential issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())