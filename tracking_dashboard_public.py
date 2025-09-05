"""
🌐 Public Email Tracking Dashboard
Enhanced for external device access (phones, tablets, etc.)
"""

from flask import Flask, render_template, jsonify, request, Response
import json
from email_tracker import EmailTracker
import os
import logging
from tracking_config import TRACKING_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)

# Initialize email tracker
tracker = EmailTracker()

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """
    Serve the tracking pixel and record email open.
    Enhanced for public access with better error handling.
    """
    try:
        # Get request information
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Log the tracking attempt
        logger.info(f"📧 Tracking pixel accessed: {tracking_id}")
        logger.info(f"📱 User Agent: {user_agent}")
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
                'Access-Control-Allow-Origin': '*',  # Allow cross-origin requests
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

@app.route('/dashboard')
def dashboard():
    """Main tracking dashboard page."""
    return render_template('tracking_dashboard.html')

@app.route('/api/dashboard-data')
def dashboard_data():
    """API endpoint for dashboard data."""
    try:
        stats = tracker.get_tracking_stats()
        campaigns = tracker.get_campaign_performance()
        
        return jsonify({
            'stats': stats,
            'campaigns': campaigns
        })
    except Exception as e:
        logger.error(f"❌ Error getting dashboard data: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint for monitoring."""
    return jsonify({
        'status': 'healthy',
        'service': 'email-tracking',
        'version': '1.0.0',
        'base_url': TRACKING_CONFIG['BASE_URL']
    })

@app.route('/test-tracking')
def test_tracking():
    """Test endpoint to verify tracking is working."""
    try:
        # Create a test tracking ID
        test_tracking_id = tracker.track_email_sent(
            recipient_email="test@example.com",
            sender_email="sender@example.com",
            subject="Test Email",
            campaign_name="Test Campaign"
        )
        
        return jsonify({
            'message': 'Test tracking ID created',
            'tracking_id': test_tracking_id,
            'test_url': f'{TRACKING_CONFIG["BASE_URL"]}/track/{test_tracking_id}',
            'instructions': 'Open this URL on your phone to test tracking'
        })
    except Exception as e:
        logger.error(f"❌ Error creating test tracking: {str(e)}")
        return jsonify({'error': 'Failed to create test tracking'}), 500

if __name__ == '__main__':
    logger.info(f"🚀 Starting public tracking server...")
    logger.info(f"🌐 Base URL: {TRACKING_CONFIG['BASE_URL']}")
    logger.info(f"📊 Dashboard: {TRACKING_CONFIG['BASE_URL']}/dashboard")
    logger.info(f"🔍 Health check: {TRACKING_CONFIG['BASE_URL']}/api/health")
    logger.info(f"🧪 Test tracking: {TRACKING_CONFIG['BASE_URL']}/test-tracking")
    
    app.run(
        host=TRACKING_CONFIG['HOST'], 
        port=TRACKING_CONFIG['PORT'], 
        debug=TRACKING_CONFIG['DEBUG']
    )
