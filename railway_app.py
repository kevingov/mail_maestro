"""
🚂 Railway Email Tracking App
Optimized for Railway deployment with cloud database support
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

# Initialize email tracker with Railway-optimized database path
db_path = os.environ.get('DATABASE_URL', 'email_tracking.db')
tracker = EmailTracker(db_path=db_path)

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
            'tracking_details': '/tracking/details/<tracking_id>'
        }
    })

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """
    Serve the tracking pixel and record email open.
    This is the main endpoint that email clients will call.
    """
    try:
        # Get request information
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Log the tracking attempt
        logger.info(f"📧 Tracking pixel accessed: {tracking_id}")
        logger.info(f"�� User Agent: {user_agent[:100]}...")  # Truncate for logs
        logger.info(f"🌐 IP Address: {ip_address}")
        
        # Record the email open
        success = tracker.track_email_open(tracking_id, user_agent, ip_address, referer)
        
        if success:
            logger.info(f"✅ Successfully tracked email open for: {tracking_id}")
        else:
            logger.warning(f"⚠️ Failed to track email open for: {tracking_id}")
        
        # Create and return a 1x1 transparent pixel
        pixel_data = tracker.create_tracking_pixel()
        
        return Response(
            pixel_data,
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error in track_pixel: {str(e)}")
        # Still return a pixel even if tracking fails
        pixel_data = tracker.create_tracking_pixel()
        return Response(
            pixel_data,
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Access-Control-Allow-Origin': '*'
            }
        )

@app.route('/tracking/details/<tracking_id>')
def tracking_details(tracking_id):
    """Get detailed tracking information for a specific email."""
    try:
        conn = tracker.get_connection()
        cursor = conn.cursor()
        
        # Get email tracking info
        cursor.execute('''
            SELECT * FROM email_tracking WHERE tracking_id = ?
        ''', (tracking_id,))
        
        email_data = cursor.fetchone()
        if not email_data:
            return jsonify({'error': 'Tracking ID not found'}), 404
        
        # Get all opens for this email
        cursor.execute('''
            SELECT * FROM email_opens WHERE tracking_id = ? ORDER BY opened_at DESC
        ''', (tracking_id,))
        
        opens_data = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'tracking_id': tracking_id,
            'email_data': dict(zip([col[0] for col in cursor.description], email_data)),
            'opens': [dict(zip([col[0] for col in cursor.description], row)) for row in opens_data]
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting tracking details: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        conn = tracker.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM email_tracking')
        email_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'service': 'email-tracking',
            'version': '1.0.0',
            'database': 'connected',
            'total_emails_tracked': email_count
        })
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/api/stats')
def get_stats():
    """Get basic tracking statistics."""
    try:
        stats = tracker.get_tracking_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"❌ Error getting stats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/test')
def test_tracking():
    """Test endpoint to verify tracking is working."""
    try:
        # Create a test tracking ID
        test_tracking_id = tracker.track_email_sent(
            recipient_email="test@example.com",
            sender_email="sender@example.com",
            subject="Test Email - Railway Deployment",
            campaign_name="Railway Test"
        )
        
        return jsonify({
            'message': 'Test tracking ID created successfully',
            'tracking_id': test_tracking_id,
            'test_url': f'/track/{test_tracking_id}',
            'instructions': 'Open the test_url to simulate an email open'
        })
    except Exception as e:
        logger.error(f"❌ Error creating test tracking: {str(e)}")
        return jsonify({'error': 'Failed to create test tracking'}), 500

if __name__ == '__main__':
    # Railway will set the PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Railway email tracking server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
