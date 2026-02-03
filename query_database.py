#!/usr/bin/env python3
"""
Simple script to query the PostgreSQL database.
Usage: python query_database.py "SELECT * FROM email_tracking LIMIT 10;"
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Get database connection from DATABASE_URL environment variable."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not found")
        print("   Please set DATABASE_URL in your environment or Railway config")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        sys.exit(1)

def run_query(query):
    """Execute a SQL query and return results."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(query)
        
        # Check if query returns results (SELECT) or just affects rows (INSERT/UPDATE/DELETE)
        if cursor.description:
            # SELECT query - fetch results
            results = cursor.fetchall()
            return results
        else:
            # INSERT/UPDATE/DELETE - return rowcount
            conn.commit()
            return f"Query executed successfully. Rows affected: {cursor.rowcount}"
            
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error executing query: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def print_results(results):
    """Pretty print query results."""
    if isinstance(results, str):
        print(results)
        return
    
    if not results:
        print("No results found.")
        return
    
    # Print headers
    headers = list(results[0].keys())
    print("\n" + " | ".join(headers))
    print("-" * (sum(len(str(h)) for h in headers) + len(headers) * 3))
    
    # Print rows
    for row in results:
        values = [str(row[h]) if row[h] is not None else 'NULL' for h in headers]
        print(" | ".join(values))
    
    print(f"\nTotal rows: {len(results)}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python query_database.py \"SELECT * FROM email_tracking LIMIT 10;\"")
        print("\nExample queries:")
        print("  python query_database.py \"SELECT COUNT(*) FROM email_tracking;\"")
        print("  python query_database.py \"SELECT * FROM email_tracking WHERE status = 'Email Open' LIMIT 10;\"")
        print("  python query_database.py \"SELECT tracking_id, recipient_email, status FROM email_tracking ORDER BY sent_at DESC LIMIT 20;\"")
        sys.exit(1)
    
    query = sys.argv[1]
    print(f"🔍 Executing query: {query}\n")
    
    results = run_query(query)
    print_results(results)

