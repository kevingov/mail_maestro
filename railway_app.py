"""
🚂 Railway Email Tracking App with PostgreSQL
Complete email tracking system with send and open tracking
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

# Global database connection status
DB_AVAILABLE = False

def get_db_connection():
    """Get PostgreSQL connection from Railway environment variables."""
    global DB_AVAILABLE
    try:
        # Railway provides DATABASE_URL environment variable
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
        DB_AVAILABLE = True
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        DB_AVAILABLE = False

# Initialize database on startup
init_database()

@app.route('/')
def home():
    """Home page with service info."""
    db_status = "PostgreSQL (connected)" if DB_AVAILABLE else "Memory mode (no persistence)"
    return jsonify({
        'service': 'Email Tracking System',
        'status': 'running',
        'version': '1.0.0',
        'database': db_status,
        'endpoints': {
            'track_email_send': 'POST /api/track-send',
            'tracking_pixel': 'GET /track/<tracking_id>',
            'health_check': 'GET /api/health',
            'tracking_stats': 'GET /api/stats'
        }
    })

@app.route('/api/track-send', methods=['POST'])
def track_email_send():
    """API endpoint to track email sends."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'error': 'Database not available',
                'message': 'PostgreSQL database is not connected'
            }), 503
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Extract required fields
        recipient_email = data.get('recipient_email')
        sender_email = data.get('sender_email')
        subject = data.get('subject')
        campaign_name = data.get('campaign_name')
        
        if not recipient_email:
            return jsonify({'error': 'recipient_email is required'}), 400
        
        # Generate tracking ID
        tracking_id = str(uuid.uuid4())
        
        # Store in database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
            VALUES (%s, %s, %s, %s, %s)
        ''', (tracking_id, recipient_email, sender_email, subject, campaign_name))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📧 Email send tracked: {tracking_id} -> {recipient_email}")
        
        return jsonify({
            'status': 'success',
            'tracking_id': tracking_id,
            'tracking_url': f"https://web-production-6dfbd.up.railway.app/track/{tracking_id}",
            'message': f'Email send tracked for {recipient_email}'
        })
        
    except Exception as e:
        logger.error(f"❌ Error tracking email send: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """Serve tracking pixel and log the request to PostgreSQL with simplified filtering."""
    try:
        # Log the tracking request
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Simple filtering - only filter very rapid opens (within 2 seconds)
        is_false_open = False
        false_open_reasons = []
        
        # Try to track in database if available
        if DB_AVAILABLE:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    
                    # Check if tracking_id exists in email_tracking table
                    cursor.execute('SELECT tracking_id, sent_at FROM email_tracking WHERE tracking_id = %s', (tracking_id,))
                    email_record = cursor.fetchone()
                    
                    if not email_record:
                        logger.warning(f"Tracking ID {tracking_id} not found in email_tracking table")
                        # Create a placeholder record
                        cursor.execute('''
                            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (tracking_id) DO NOTHING
                        ''', (tracking_id, 'unknown@example.com', 'unknown@example.com', 'Unknown', 'Unknown'))
                        conn.commit()
                        
                        # Get the sent_at time for the new record
                        cursor.execute('SELECT sent_at FROM email_tracking WHERE tracking_id = %s', (tracking_id,))
                        email_record = cursor.fetchone()
                    
                    if email_record:
                        sent_at = email_record[1]  # sent_at timestamp
                        
                        # Check for very rapid opens (within 2 seconds of sending) - much more lenient
                        from datetime import datetime, timedelta
                        current_time = datetime.now()
                        
                        # Handle timezone-aware datetime comparison
                        if sent_at.tzinfo is None:
                            # If sent_at is naive, assume UTC
                            sent_at = sent_at.replace(tzinfo=None)
                            current_time = current_time.replace(tzinfo=None)
                        
                        time_diff = (current_time - sent_at).total_seconds()
                        
                        # Only filter out very rapid opens (2 seconds or less)
                        if time_diff < 2:
                            is_false_open = True
                            false_open_reasons.append(f"Very rapid open: {time_diff:.1f}s after send")
                        
                        # Check for rapid successive opens (within 2 seconds of last open)
                        cursor.execute('''
                            SELECT opened_at FROM email_opens 
                            WHERE tracking_id = %s 
                            ORDER BY opened_at DESC 
                            LIMIT 1
                        ''', (tracking_id,))
                        
                        last_open = cursor.fetchone()
                        if last_open:
                            last_open_time = last_open[0]
                            
                            # Handle timezone-aware datetime comparison
                            if last_open_time.tzinfo is None:
                                last_open_time = last_open_time.replace(tzinfo=None)
                            
                            if (current_time - last_open_time).total_seconds() < 2:
                                is_false_open = True
                                false_open_reasons.append("Rapid successive open")
                    
                    # Only insert if it's not a false open
                    if not is_false_open:
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
                        logger.info(f"✅ Real email opened! Tracking ID: {tracking_id}")
                    else:
                        # Log false open for debugging (but don't count it)
                        cursor.execute('''
                            INSERT INTO email_opens (tracking_id, user_agent, ip_address, referer)
                            VALUES (%s, %s, %s, %s)
                        ''', (tracking_id, user_agent, ip_address, referer))
                        
                        conn.commit()
                        logger.info(f"🤖 False open filtered: {tracking_id} - {'; '.join(false_open_reasons)}")
                    
                    conn.close()
                except Exception as db_error:
                    logger.error(f"Database error: {db_error}")
                    if conn:
                        conn.close()
                    logger.info(f"📧 Email opened! Tracking ID: {tracking_id} (DB error, logged to console)")
        else:
            if not is_false_open:
                logger.info(f"📧 Email opened! Tracking ID: {tracking_id} (no DB)")
            else:
                logger.info(f"🤖 False open filtered: {tracking_id} - {'; '.join(false_open_reasons)} (no DB)")
        
        # Log details
        if not is_false_open:
            logger.info(f"🌐 IP: {ip_address}")
            logger.info(f" User Agent: {user_agent}")
        else:
            logger.info(f" Filtered - IP: {ip_address}")
            logger.info(f"🤖 Filtered - User Agent: {user_agent}")
        
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
        
        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    if DB_AVAILABLE:
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.close()
                return jsonify({
                    'status': 'healthy',
                    'service': 'Email Tracking System',
                    'version': '1.0.0',
                    'database': 'PostgreSQL connected'
                })
        except Exception as e:
            return jsonify({
                'status': 'healthy',
                'service': 'Email Tracking System',
                'version': '1.0.0',
                'database': f'PostgreSQL error: {str(e)}'
            })
    
    return jsonify({
        'status': 'healthy',
        'service': 'Email Tracking System',
        'version': '1.0.0',
        'database': 'Memory mode (no persistence)'
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get email tracking statistics with instant open filtering only."""
    try:
        if not DB_AVAILABLE:
            return jsonify({'error': 'Database not available'}), 503
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cursor = conn.cursor()
        
        # Get total emails sent
        cursor.execute('SELECT COUNT(*) FROM email_tracking')
        total_emails_sent = cursor.fetchone()[0]
        
        # Get all opens (no user agent filtering - only instant open filtering is applied at insert time)
        cursor.execute('SELECT COUNT(*) FROM email_opens')
        total_opens = cursor.fetchone()[0]
        
        # Calculate open rate
        open_rate = (total_opens / total_emails_sent * 100) if total_emails_sent > 0 else 0
        
        # Get recent opens
        cursor.execute('''
            SELECT tracking_id, opened_at, user_agent, ip_address 
            FROM email_opens 
            ORDER BY opened_at DESC 
            LIMIT 10
        ''')
        recent_opens = []
        for row in cursor.fetchall():
            recent_opens.append({
                'tracking_id': row[0],
                'opened_at': row[1].isoformat(),
                'user_agent': row[2],
                'ip_address': row[3]
            })
        
        # Get recent sends
        cursor.execute('''
            SELECT tracking_id, recipient_email, subject, sent_at 
            FROM email_tracking 
            ORDER BY sent_at DESC 
            LIMIT 10
        ''')
        recent_sends = []
        for row in cursor.fetchall():
            recent_sends.append({
                'tracking_id': row[0],
                'recipient_email': row[1],
                'subject': row[2],
                'sent_at': row[3].isoformat()
            })
        
        conn.close()
        
        return jsonify({
            'total_emails_sent': total_emails_sent,
            'total_opens': total_opens,
            'open_rate': round(open_rate, 2),
            'recent_opens': recent_opens,
            'recent_sends': recent_sends
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
