"""
Database connection and initialization module

Handles PostgreSQL connection and table schema initialization.
"""

import os
import psycopg2
import logging

logger = logging.getLogger(__name__)

# Global database availability flag
DB_AVAILABLE = False


def get_db_connection():
    """Get PostgreSQL connection from Railway environment variables."""
    global DB_AVAILABLE
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.warning("DATABASE_URL not found - running without database")
            DB_AVAILABLE = False
            return None

        conn = psycopg2.connect(database_url)
        DB_AVAILABLE = True
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        DB_AVAILABLE = False
        return None


def init_database():
    """Initialize PostgreSQL database tables."""
    global DB_AVAILABLE
    try:
        conn = get_db_connection()
        if not conn:
            logger.warning("No database connection - running in memory mode")
            DB_AVAILABLE = False
            return

        cursor = conn.cursor()

        # Email tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_tracking (
                id SERIAL PRIMARY KEY,
                tracking_id VARCHAR(255) UNIQUE NOT NULL,
                recipient_email VARCHAR(255) NOT NULL,
                sender_email VARCHAR(255),
                subject TEXT,
                campaign_name VARCHAR(255),
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                open_count INTEGER DEFAULT 0,
                last_opened_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sfdc_task_id VARCHAR(255),
                status VARCHAR(50) DEFAULT 'AI Outbound Email'
            )
        ''')

        # Add columns if they don't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS sfdc_task_id VARCHAR(255)')
        except Exception as e:
            logger.debug(f"sfdc_task_id column check: {e}")

        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT \'AI Outbound Email\'')
            cursor.execute('UPDATE email_tracking SET status = \'AI Outbound Email\' WHERE status IS NULL')
            cursor.execute('''
                UPDATE email_tracking
                SET status = 'Email Open'
                WHERE open_count > 0 AND status = 'AI Outbound Email'
            ''')
        except Exception as e:
            logger.debug(f"status column check: {e}")

        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS version_endpoint VARCHAR(255)')
        except Exception as e:
            logger.debug(f"version_endpoint column check: {e}")

        try:
            cursor.execute('ALTER TABLE email_tracking DROP COLUMN IF EXISTS variant_endpoint')
            logger.info("✅ Removed old variant_endpoint column")
        except Exception as e:
            logger.debug(f"variant_endpoint column removal check: {e}")

        # Email opens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_opens (
                id SERIAL PRIMARY KEY,
                tracking_id VARCHAR(255) NOT NULL,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                ip_address VARCHAR(45),
                referer TEXT,
                FOREIGN KEY (tracking_id) REFERENCES email_tracking (tracking_id)
            )
        ''')

        # Prompt versions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id SERIAL PRIMARY KEY,
                version_name VARCHAR(255) NOT NULL,
                prompt_type VARCHAR(50) NOT NULL,
                prompt_content TEXT NOT NULL,
                version_letter VARCHAR(10) NOT NULL,
                endpoint_path VARCHAR(255) NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prompt_type, version_letter)
            )
        ''')

        # Test merchants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_merchants (
                id SERIAL PRIMARY KEY,
                merchant_name VARCHAR(255) NOT NULL,
                contact_email VARCHAR(255),
                contact_title VARCHAR(255),
                merchant_industry VARCHAR(255),
                merchant_website VARCHAR(255),
                account_description TEXT,
                account_revenue DECIMAL(15, 2),
                account_employees INTEGER,
                account_location VARCHAR(255),
                account_gmv DECIMAL(15, 2),
                last_activity VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("✅ PostgreSQL database initialized")
        DB_AVAILABLE = True
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        DB_AVAILABLE = False
