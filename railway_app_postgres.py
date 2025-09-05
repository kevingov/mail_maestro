"""
�� Railway Email Tracking App with PostgreSQL
Uses Railway's managed PostgreSQL database for persistent storage
"""

import os
import psycopg2
from flask import Flask, Response, request, jsonify
import logging
from io import BytesIO
from PIL import Image
import uuid
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

def get_db_connection():
    """Get PostgreSQL connection from Railway environment variables."""
    try:
        # Railway provides DATABASE_URL environment variable
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise Exception("DATABASE_URL not found in environment variables")
        
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_database():
    """Initialize PostgreSQL database tables."""
    try:
        conn = get_db_connection()
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
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
        
        conn.commit()
        conn.close()
        logger.info("✅ PostgreSQL database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")

# Initialize database on startup
init_database()

@app.route('/')
def home():
    """Home page with service info."""
    return jsonify({
        'service': 'Email Tracking Pixel',
        'status': 'running',
        'version': '1.0.0',
        'database': 'PostgreSQL',
        'endpoints': {
            'tracking_pixel': '/track/<tracking_id>',
            'health_check': '/api/health',
            'tracking_stats': '/api/stats'
        }
    })

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """Serve tracking pixel and log the request to PostgreSQL."""
    try:
        # Log the tracking request to database
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Track the email open in PostgreSQL
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert open record
        cursor.execute('''
            INSERT INTO email_opens (tracking_id, user_agent, ip_address, referer)
            VALUES (%s, %s, %s, %s)
        ''', (tracking_id, user_agent, ip_address, referer))
        
        # Update open count
        cursor.execute('''
            UPDATE email_tracking 
            SET open_count = open_count + 1, last_opened_at = CURRENT_TIMESTAMP
            WHERE tracking_id = %s
        ''', (tracking_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📧 Email opened! Tracking ID: {tracking_id}")
        logger.info(f"🌐 IP: {ip_address}")
        
        # Create and return the pixel
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        
        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    except Exception as e:
        logger.error(f"❌ Error tracking email open: {e}")
        # Return a simple pixel even if tracking fails
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        return Response(img_io.getvalue(), mimetype='image/png')

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return jsonify({
            'status': 'healthy',
            'service': 'Email Tracking Pixel',
            'version': '1.0.0',
            'database': 'PostgreSQL connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'service': 'Email Tracking Pixel',
            'version': '1.0.0',
            'database': 'error',
            'error': str(e)
        }), 500

@app.route('/api/stats')
def tracking_stats():
    """Get tracking statistics from PostgreSQL."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total emails sent
        cursor.execute("SELECT COUNT(*) FROM email_tracking")
        total_sent = cursor.fetchone()[0]
        
        # Get total opens
        cursor.execute("SELECT COUNT(*) FROM email_opens")
        total_opens = cursor.fetchone()[0]
        
        # Get recent opens
        cursor.execute("""
            SELECT tracking_id, opened_at, ip_address, user_agent 
            FROM email_opens 
            ORDER BY opened_at DESC 
            LIMIT 10
        """)
        recent_opens = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'total_emails_sent': total_sent,
            'total_opens': total_opens,
            'open_rate': (total_opens / total_sent * 100) if total_sent > 0 else 0,
            'recent_opens': [
                {
                    'tracking_id': row[0],
                    'opened_at': row[1].isoformat() if row[1] else None,
                    'ip_address': row[2],
                    'user_agent': row[3]
                } for row in recent_opens
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
