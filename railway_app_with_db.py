"""
🚂 Railway Email Tracking App with Database
Includes tracking pixel functionality with SQLite database storage
"""

import os
import sqlite3
from flask import Flask, Response, request, jsonify
from email_tracker import EmailTracker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize email tracker with database
tracker = EmailTracker()

@app.route('/')
def home():
    """Home page with service info."""
    return jsonify({
        'service': 'Email Tracking Pixel',
        'status': 'running',
        'version': '1.0.0',
        'endpoints': {
            'tracking_pixel': '/track/<tracking_id>',
            'health_check': '/api/health',
            'tracking_stats': '/api/stats'
        }
    })

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """Serve tracking pixel and log the request to database."""
    try:
        # Log the tracking request to database
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Track the email open in database
        tracker.track_email_open(tracking_id, user_agent, ip_address, referer)
        
        logger.info(f"📧 Email opened! Tracking ID: {tracking_id}")
        logger.info(f"🌐 IP: {ip_address}")
        logger.info(f"🔍 User Agent: {user_agent}")
        logger.info(f"📄 Referer: {referer}")
        
        # Create and return the pixel
        pixel_data = tracker.create_tracking_pixel()
        
        return Response(
            pixel_data,
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
        from io import BytesIO
        from PIL import Image
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        return Response(img_io.getvalue(), mimetype='image/png')

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        conn = tracker.get_connection()
        conn.close()
        return jsonify({
            'status': 'healthy',
            'service': 'Email Tracking Pixel',
            'version': '1.0.0',
            'database': 'connected'
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
    """Get tracking statistics."""
    try:
        conn = tracker.get_connection()
        cursor = conn.cursor()
        
        # Get total emails sent
        cursor.execute("SELECT COUNT(*) FROM email_sends")
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
                    'opened_at': row[1],
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
