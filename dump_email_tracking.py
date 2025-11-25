#!/usr/bin/env python3
"""
📧 Email Tracking Data Dump Script
Dumps all email_tracking data to CSV/JSON files daily.
Can be run via cron job or scheduled task.
"""

import os
import sys
import psycopg2
import csv
import json
import datetime
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_dump.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Output directory for dumps
OUTPUT_DIR = Path('email_dumps')
OUTPUT_DIR.mkdir(exist_ok=True)

def get_db_connection():
    """Get PostgreSQL connection from Railway environment variables."""
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL environment variable not found")
            logger.error("Please set DATABASE_URL in your environment or .env file")
            return None
        
        conn = psycopg2.connect(database_url)
        logger.info("✅ Connected to PostgreSQL database")
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return None

def dump_to_csv(records, filename):
    """Dump records to CSV file."""
    if not records:
        logger.warning("No records to dump")
        return False
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Get field names from first record
            fieldnames = records[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for record in records:
                # Convert None to empty string for CSV
                cleaned_record = {k: (v if v is not None else '') for k, v in record.items()}
                writer.writerow(cleaned_record)
        
        logger.info(f"✅ Exported {len(records)} records to {filename}")
        return True
    except Exception as e:
        logger.error(f"❌ Error writing CSV file: {e}")
        return False

def dump_to_json(records, filename):
    """Dump records to JSON file."""
    if not records:
        logger.warning("No records to dump")
        return False
    
    try:
        # Convert datetime objects to ISO format strings
        def datetime_serializer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(records, jsonfile, default=datetime_serializer, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Exported {len(records)} records to {filename}")
        return True
    except Exception as e:
        logger.error(f"❌ Error writing JSON file: {e}")
        return False

def dump_email_tracking(export_format='both', limit=None, date_filter=None):
    """
    Dump all email_tracking records to file(s).
    
    Args:
        export_format: 'csv', 'json', or 'both' (default: 'both')
        limit: Maximum number of records to export (None = all)
        date_filter: Only export records from this date onwards (YYYY-MM-DD format)
    """
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        return False
    
    try:
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                id,
                tracking_id,
                recipient_email,
                sender_email,
                subject,
                campaign_name,
                sent_at,
                open_count,
                last_opened_at,
                created_at
            FROM email_tracking
        """
        
        params = []
        conditions = []
        
        # Add date filter if provided
        if date_filter:
            conditions.append("sent_at >= %s")
            params.append(date_filter)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY sent_at DESC"
        
        # Add limit if specified
        if limit:
            query += f" LIMIT {limit}"
        
        logger.info(f"📊 Executing query: {query}")
        if params:
            logger.info(f"📊 Query parameters: {params}")
        
        cursor.execute(query, params)
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        # Fetch all records
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        records = []
        for row in rows:
            record = dict(zip(columns, row))
            records.append(record)
        
        logger.info(f"📊 Retrieved {len(records)} records from database")
        
        if not records:
            logger.warning("No records found to export")
            conn.close()
            return False
        
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        
        success = True
        
        # Export to CSV
        if export_format in ['csv', 'both']:
            csv_filename = OUTPUT_DIR / f'email_tracking_{date_str}.csv'
            if not dump_to_csv(records, csv_filename):
                success = False
        
        # Export to JSON
        if export_format in ['json', 'both']:
            json_filename = OUTPUT_DIR / f'email_tracking_{date_str}.json'
            if not dump_to_json(records, json_filename):
                success = False
        
        conn.close()
        
        if success:
            logger.info(f"✅ Successfully dumped {len(records)} records")
            logger.info(f"📁 Output directory: {OUTPUT_DIR.absolute()}")
            return True
        else:
            logger.error("❌ Some exports failed")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error dumping email tracking data: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()
        return False

def main():
    """Main function to run the dump script."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Dump email tracking data to CSV/JSON')
    parser.add_argument(
        '--format',
        choices=['csv', 'json', 'both'],
        default='both',
        help='Export format: csv, json, or both (default: both)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of records to export (default: all)'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='Only export records from this date onwards (YYYY-MM-DD format)'
    )
    parser.add_argument(
        '--since-days',
        type=int,
        default=None,
        help='Only export records from the last N days'
    )
    
    args = parser.parse_args()
    
    # Calculate date filter if --since-days is provided
    date_filter = args.date
    if args.since_days:
        date_filter = (datetime.datetime.now() - datetime.timedelta(days=args.since_days)).date().isoformat()
        logger.info(f"📅 Filtering records from last {args.since_days} days (since {date_filter})")
    
    logger.info("🚀 Starting email tracking data dump...")
    logger.info(f"📋 Format: {args.format}")
    if args.limit:
        logger.info(f"📋 Limit: {args.limit} records")
    if date_filter:
        logger.info(f"📋 Date filter: {date_filter} onwards")
    
    success = dump_email_tracking(
        export_format=args.format,
        limit=args.limit,
        date_filter=date_filter
    )
    
    if success:
        logger.info("✅ Dump completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Dump failed")
        sys.exit(1)

if __name__ == '__main__':
    main()

